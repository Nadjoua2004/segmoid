"""
Daily Check-in Service
Persistence and rule-based evaluation for the astronaut daily self-report.

Vitals are written to TelemetryLog (consumed by triage + forecasting); everything else from the
ISS-style daily sheet goes to DailyCheckIn. Both rows are created in a single transaction.

Thresholds below come from NASA ISS-era references (NASA-STD-3001 technical briefs, ISS crew
operations data) as summarised in "Astronaut Health Metrics & Daily Check-In".
"""
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ml.features import SYMPTOM_LABELS
from app.models import DailyCheckIn, TelemetryLog
from app.schemas import CheckInFlag, DailyCheckInCreate, DailyCheckInRead, HealthAssessment
from app.services import checkin_classifier

logger = logging.getLogger(__name__)

# --- Reference thresholds ----------------------------------------------------------------------
EXERCISE_TARGET_MIN = 120          # ISS countermeasure: ~2–2.5 h/day against bone & muscle loss
WATER_TARGET_L = 2.0               # hydration; also lowers kidney-stone risk from bone calcium loss
CABIN_TEMP_RANGE_C = (17.8, 26.7)  # ISS habitable range
CABIN_CO2_LIMIT_MMHG = 3.0         # NASA standard: 1-hour average ≤ 3 mmHg
CABIN_CO2_CRITICAL_MMHG = 4.5      # matches metric_classifier critical threshold
LOW_RATING = 2                     # 1–2 on a 1–5 scale is considered low


GLUCOSE_CONTEXT_LABELS = {"fasting": "fasting", "post_meal": "2 h after meal", "random": "random"}


class CheckInConflictError(Exception):
    """A check-in already exists for this astronaut and mission day."""


# --- Rules -------------------------------------------------------------------------------------
def evaluate_checkin_flags(c: DailyCheckInCreate) -> List[CheckInFlag]:
    """Lifestyle / environment findings. Vital-sign severity is handled by the triage engine."""
    flags: List[CheckInFlag] = []

    def add(code: str, severity: str, message: str) -> None:
        flags.append(CheckInFlag(code=code, severity=severity, message=message))

    env = c.environment
    if env.cabin_co2_mmhg >= CABIN_CO2_CRITICAL_MMHG:
        add("CABIN_CO2_CRITICAL", "CRITICAL",
            f"Cabin CO2 {env.cabin_co2_mmhg} mmHg. Increase ventilation and check the CO2 scrubber now.")
    elif env.cabin_co2_mmhg > CABIN_CO2_LIMIT_MMHG:
        add("CABIN_CO2_HIGH", "MEDIUM",
            f"Cabin CO2 {env.cabin_co2_mmhg} mmHg is above the {CABIN_CO2_LIMIT_MMHG} mmHg limit. "
            "Expect headaches; report to the crew.")

    if not (CABIN_TEMP_RANGE_C[0] <= env.cabin_temp_c <= CABIN_TEMP_RANGE_C[1]):
        add("CABIN_TEMP_OUT_OF_RANGE", "MEDIUM",
            f"Cabin temperature {env.cabin_temp_c} °C is outside the {CABIN_TEMP_RANGE_C[0]}–{CABIN_TEMP_RANGE_C[1]} °C range.")

    if not env.radiation_badge_worn:
        add("DOSIMETER_NOT_WORN", "MEDIUM",
            "Personal dosimeter was not worn all day, so today's radiation dose may be under-reported.")

    if "vision_change" in c.symptoms:
        add("SANS_SCREENING", "MEDIUM",
            "Vision change reported. Schedule an eye exam (fundoscopy / ocular ultrasound) to screen for SANS.")

    total_ex = c.exercise.total_minutes
    if total_ex < EXERCISE_TARGET_MIN:
        add("EXERCISE_BELOW_TARGET", "MEDIUM",
            f"{total_ex} min of exercise is below the {EXERCISE_TARGET_MIN}–150 min daily target "
            "that protects bone and muscle.")

    if c.nutrition.water_liters < WATER_TARGET_L:
        add("LOW_HYDRATION", "MEDIUM",
            f"{c.nutrition.water_liters} L of water is below the ~{WATER_TARGET_L} L target. "
            "Low intake raises kidney-stone risk in microgravity.")

    meals = sum([c.nutrition.breakfast, c.nutrition.lunch, c.nutrition.dinner])
    if meals < 2:
        add("MEALS_SKIPPED", "MEDIUM",
            f"Only {meals} of 3 meals logged. Crews tend to under-eat in space (~80 % of needs).")

    if c.wellbeing.energy_level <= LOW_RATING:
        add("LOW_ENERGY", "MEDIUM", "Low energy reported. Review sleep and workload with the crew.")
    if c.wellbeing.stress_level <= LOW_RATING:
        add("HIGH_STRESS", "MEDIUM",
            "High stress reported. Consider a private conference with the flight psychologist.")

    if c.sleep.sleep_medication:
        add("SLEEP_MEDICATION_USED", "INFO",
            "Sleep medication used. Allow for possible drowsiness before hazardous tasks.")

    tib = c.sleep.time_in_bed_hours
    if c.sleep.sleep_hours > tib + 0.25:
        add("SLEEP_HOURS_EXCEED_TIME_IN_BED", "INFO",
            f"Hours slept ({c.sleep.sleep_hours} h) exceed time in bed ({tib} h). Include naps or check times.")

    return flags


def _telemetry_notes(c: DailyCheckInCreate) -> str:
    """Compact text summary kept on TelemetryLog so the AI flight-surgeon chat sees symptoms."""
    parts = []
    if c.symptoms:
        parts.append("Symptoms: " + ", ".join(SYMPTOM_LABELS[s] for s in c.symptoms))
    parts.append(f"Glucose: {GLUCOSE_CONTEXT_LABELS[c.vitals.glucose_context]}")
    return " | ".join(parts)


# --- ML assessment -----------------------------------------------------------------------------
def run_assessment(payload: DailyCheckInCreate) -> Optional[HealthAssessment]:
    """ML assessment for a check-in, or None if the model is unavailable (the check-in is still saved)."""
    try:
        return checkin_classifier.assess(payload.model_dump(mode="json"))
    except checkin_classifier.ModelUnavailableError as exc:
        logger.warning("Check-in classifier unavailable: %s", exc)
        return None


# --- Persistence -------------------------------------------------------------------------------
def create_checkin(db: Session, payload: DailyCheckInCreate) -> DailyCheckIn:
    exists = db.scalar(
        select(DailyCheckIn.id).where(
            DailyCheckIn.astronaut_id == payload.astronaut_id,
            DailyCheckIn.mission_day == payload.mission_day,
        )
    )
    if exists is not None:
        raise CheckInConflictError(
            f"A check-in for {payload.astronaut_id} on mission day {payload.mission_day} already exists."
        )

    assessment = run_assessment(payload)

    v, s, env = payload.vitals, payload.sleep, payload.environment
    telemetry = TelemetryLog(
        astronaut_id=payload.astronaut_id,
        mission_day=payload.mission_day,
        heart_rate=v.heart_rate,
        bp_sys=v.bp_sys,
        bp_dia=v.bp_dia,
        spo2=v.spo2,
        sleep_hours=s.sleep_hours,
        radiation_msv=env.radiation_msv,
        blood_glucose=v.blood_glucose,
        mood_score=payload.wellbeing.mood_score,
        core_temp_c=v.core_temp_c,
        hrv_rmssd=v.hrv_rmssd,
        subjective_notes=_telemetry_notes(payload),
    )
    checkin = DailyCheckIn(
        telemetry=telemetry,
        astronaut_id=payload.astronaut_id,
        mission_day=payload.mission_day,
        checkin_date=payload.checkin_date,
        glucose_context=v.glucose_context,
        bedtime=s.bedtime,
        wake_time=s.wake_time,
        sleep_quality=s.sleep_quality,
        sleep_medication=s.sleep_medication,
        energy_level=payload.wellbeing.energy_level,
        stress_level=payload.wellbeing.stress_level,
        cardio_minutes=payload.exercise.cardio_minutes,
        resistance_minutes=payload.exercise.resistance_minutes,
        calories_kcal=payload.nutrition.calories_kcal,
        water_liters=payload.nutrition.water_liters,
        breakfast=payload.nutrition.breakfast,
        lunch=payload.nutrition.lunch,
        dinner=payload.nutrition.dinner,
        vitamin_d_taken=payload.nutrition.vitamin_d_taken,
        radiation_badge_worn=env.radiation_badge_worn,
        cabin_temp_c=env.cabin_temp_c,
        cabin_co2_mmhg=env.cabin_co2_mmhg,
        ear_protection_used=env.ear_protection_used,
        symptoms=list(payload.symptoms),
        # Stored with its model version so past results stay auditable after re-training.
        assessment=assessment.model_dump(mode="json") if assessment else None,
    )
    db.add_all([telemetry, checkin])
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent insert for the same day
        db.rollback()
        raise CheckInConflictError(
            f"A check-in for {payload.astronaut_id} on mission day {payload.mission_day} already exists."
        ) from exc
    db.refresh(checkin)
    return checkin


def to_read_model(row: DailyCheckIn) -> DailyCheckInRead:
    t = row.telemetry
    data = DailyCheckInCreate.model_validate({
        "astronaut_id": row.astronaut_id,
        "mission_day": row.mission_day,
        "checkin_date": row.checkin_date,
        "vitals": {
            "heart_rate": t.heart_rate, "bp_sys": t.bp_sys, "bp_dia": t.bp_dia, "spo2": t.spo2,
            "core_temp_c": t.core_temp_c, "blood_glucose": t.blood_glucose,
            "glucose_context": row.glucose_context, "hrv_rmssd": t.hrv_rmssd,
        },
        "sleep": {
            "bedtime": row.bedtime, "wake_time": row.wake_time, "sleep_hours": t.sleep_hours,
            "sleep_quality": row.sleep_quality, "sleep_medication": row.sleep_medication,
        },
        "wellbeing": {
            "mood_score": t.mood_score, "energy_level": row.energy_level, "stress_level": row.stress_level,
        },
        "exercise": {"cardio_minutes": row.cardio_minutes, "resistance_minutes": row.resistance_minutes},
        "nutrition": {
            "calories_kcal": row.calories_kcal, "water_liters": row.water_liters, "breakfast": row.breakfast,
            "lunch": row.lunch, "dinner": row.dinner, "vitamin_d_taken": row.vitamin_d_taken,
        },
        "environment": {
            "radiation_msv": t.radiation_msv, "radiation_badge_worn": row.radiation_badge_worn,
            "cabin_temp_c": row.cabin_temp_c, "cabin_co2_mmhg": row.cabin_co2_mmhg,
            "ear_protection_used": row.ear_protection_used,
        },
        "symptoms": row.symptoms or [],
    })
    return DailyCheckInRead(
        **_strip_computed(data),
        id=row.id,
        telemetry_log_id=row.telemetry_log_id,
        created_at=row.created_at,
        flags=evaluate_checkin_flags(data),
        assessment=HealthAssessment.model_validate(row.assessment) if row.assessment else None,
    )


def _strip_computed(data: DailyCheckInCreate) -> dict:
    """model_dump() includes computed fields, which the strict input sections would reject."""
    dumped = data.model_dump()
    dumped["sleep"].pop("time_in_bed_hours", None)
    dumped["exercise"].pop("total_minutes", None)
    return dumped


def list_checkins(db: Session, astronaut_id: str, limit: int, offset: int) -> List[DailyCheckIn]:
    stmt = (
        select(DailyCheckIn)
        .where(DailyCheckIn.astronaut_id == astronaut_id)
        .order_by(DailyCheckIn.mission_day.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).unique())


def get_checkin(db: Session, checkin_id: int) -> Optional[DailyCheckIn]:
    return db.get(DailyCheckIn, checkin_id)
