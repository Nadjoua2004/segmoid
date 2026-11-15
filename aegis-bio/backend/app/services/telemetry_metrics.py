"""
Build the triage input (HealthMetrics) from a stored TelemetryLog row.

Cabin CO2 is recorded on the DailyCheckIn linked to a telemetry row, not on
TelemetryLog itself. Building HealthMetrics from the row alone made the
schema fill in its defaults (CO2 2.8 mmHg, core temp 36.9 C, HRV 42 ms), so
triage and the AI reported values the astronaut never entered. Here, values
come from the row or its check-in; anything not measured stays None and is
skipped by the classifiers instead of being invented.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models import DailyCheckIn, TelemetryLog
from app.schemas import HealthMetrics


def linked_checkin(db: Session, log: TelemetryLog) -> Optional[DailyCheckIn]:
    """The check-in for this telemetry row, else the same astronaut's check-in on the same mission day."""
    checkin = db.query(DailyCheckIn).filter(DailyCheckIn.telemetry_log_id == log.id).first()
    if checkin is None:
        checkin = (db.query(DailyCheckIn)
                   .filter(DailyCheckIn.astronaut_id == log.astronaut_id,
                           DailyCheckIn.mission_day == log.mission_day)
                   .order_by(DailyCheckIn.id.desc()).first())
    return checkin


def health_metrics_from_log(db: Session, log: TelemetryLog) -> HealthMetrics:
    checkin = linked_checkin(db, log)
    return HealthMetrics(
        astronaut_id=log.astronaut_id,
        mission_day=log.mission_day,
        timestamp=log.timestamp,
        heart_rate=log.heart_rate,
        bp_sys=log.bp_sys,
        bp_dia=log.bp_dia,
        spo2=log.spo2,
        sleep_hours=log.sleep_hours,
        radiation_msv=log.radiation_msv,
        blood_glucose=log.blood_glucose,
        mood_score=log.mood_score,
        core_temp_c=log.core_temp_c,                                   # None when not measured
        hrv_rmssd=log.hrv_rmssd,                                       # None when not measured
        cabin_co2_mmhg=checkin.cabin_co2_mmhg if checkin else None,    # None when no check-in
        subjective_notes=log.subjective_notes or "",
    )
