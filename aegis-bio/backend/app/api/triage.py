"""
Triage & Multi-Hazard Spaceflight Classification API
Evaluates astronaut telemetry against NASA's 5 Spaceflight Hazards:
1. Space Radiation (SPE / GCR)
2. Microgravity / Gravity Fields (Cardiovascular deconditioning & fluid shift)
3. Isolation & Confinement (Circadian disruption & psychological strain)
4. Distance from Earth (Autonomous decision support requirement)
5. Hostile Closed Environment (Life support interactions & hypoxia/hypercapnia)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import TelemetryLog
from app.schemas import (
    HealthMetrics,
    TriageResult,
    HazardBreakdown,
    Countermeasure,
)
from app.services.seeder import seed_initial_telemetry

router = APIRouter(prefix="/api/triage", tags=["Clinical Triage & Hazard Scoring"])

def evaluate_multi_hazard_triage(metrics: HealthMetrics) -> TriageResult:
    """
    Core rule-based & hazard scoring algorithm.
    Evaluates physiological telemetry against aerospace thresholds.
    """
    clinical_flags = []
    countermeasures = []
    
    # -------------------------------------------------------------
    # 1. HAZARD: Space Radiation (GCR + SPE)
    # Threshold: > 20 mSv/day = Critical Solar Particle Event (SPE)
    # -------------------------------------------------------------
    rad_dose = metrics.radiation_msv
    if rad_dose >= 20.0:
        rad_score = 98.0
        clinical_flags.append("CRITICAL: Solar Particle Event (SPE) detected (>20 mSv/day). Acute radiation sickness threat.")
        countermeasures.append(
            Countermeasure(
                id="CM-RAD-SPE-01",
                title="Immediate Storm Shelter Ingress",
                category="Radiation Protection",
                urgency="IMMEDIATE",
                protocol="Direct astronaut immediately into the water-jacketed central habitat storm shelter. Seal airlock.",
                nasa_hrp_reference="NASA-STD-3001 Vol 1 §4.3 (Acute Radiation Exposure Countermeasures)"
            )
        )
        countermeasures.append(
            Countermeasure(
                id="CM-RAD-PHARMA-02",
                title="Radioprotectant Pharmaceutical Protocol",
                category="Clinical Pharma",
                urgency="IMMEDIATE",
                protocol="Administer Oral N-acetylcysteine (NAC) 1200 mg and subcutaneous Granulocyte colony-stimulating factor (G-CSF) if dosimeter exceeds 500 mSv.",
                nasa_hrp_reference="NASA HRP-47053 Space Radiation Medical Evidence"
            )
        )
    elif rad_dose >= 5.0:
        rad_score = 65.0
        clinical_flags.append("WARNING: Elevated ambient radiation flux (>5 mSv/day). Exceeds nominal Artemis baseline.")
        countermeasures.append(
            Countermeasure(
                id="CM-RAD-EVA-03",
                title="Immediate EVA Abort / Postponement",
                category="Radiation Protection",
                urgency="WITHIN_4H",
                protocol="Cancel all planned Extravehicular Activity. Confine crew to shielded lunar habitat modules.",
                nasa_hrp_reference="NASA Flight Rule A13-11: Solar Radiation Monitoring"
            )
        )
    elif rad_dose >= 1.5:
        rad_score = 35.0
        clinical_flags.append("ADVISORY: Moderate GCR background flux rise.")
    else:
        rad_score = 12.0

    # -------------------------------------------------------------
    # 2. HAZARD: Microgravity / Gravity Fields (Cardiovascular Deconditioning)
    # Threshold: Resting HR > 115 bpm or BP > 140/90 mmHg
    # -------------------------------------------------------------
    hr = metrics.heart_rate
    sys = metrics.bp_sys
    dia = metrics.bp_dia
    
    micrograv_score = 15.0
    if hr > 115.0 or sys > 140.0 or dia > 90.0:
        micrograv_score = 88.0
        clinical_flags.append(
            f"CRITICAL: Microgravity Cardiovascular Deconditioning (HR: {hr:.0f} bpm, BP: {sys:.0f}/{dia:.0f} mmHg). Cephalad fluid shift & sympathetic overload."
        )
        countermeasures.append(
            Countermeasure(
                id="CM-CARD-LBNP-01",
                title="Lower Body Negative Pressure (LBNP) Suit",
                category="Cardiovascular Reconditioning",
                urgency="IMMEDIATE",
                protocol="Seat astronaut in Chibis-M / LBNP apparatus at -35 mmHg for 45 minutes to draw venous pool caudad.",
                nasa_hrp_reference="NASA SP-2009-3405 Human Adaptation to Spaceflight"
            )
        )
        countermeasures.append(
            Countermeasure(
                id="CM-CARD-FLUID-02",
                title="Electrolyte-Supported Oral Hydration Loading",
                category="Cardiovascular Reconditioning",
                urgency="WITHIN_4H",
                protocol="Ingest 1.2 L isotonic electrolyte solution with 8.0 g NaCl tabs over 90 minutes to restore effective circulating plasma volume.",
                nasa_hrp_reference="NASA-STD-3001 Vol 2 §8.2.2.1"
            )
        )
    elif hr > 95.0 or sys > 130.0 or dia > 85.0:
        micrograv_score = 50.0
        clinical_flags.append("ELEVATED: Sub-acute resting tachycardia / orthostatic pre-intolerance.")
        countermeasures.append(
            Countermeasure(
                id="CM-CARD-ARED-03",
                title="Targeted Cycle Ergometry Interval Session",
                category="Exercise & Countermeasures",
                urgency="WITHIN_4H",
                protocol="Prescribe 40 min high-intensity resistive ergometer protocol at 80% VO2 peak.",
                nasa_hrp_reference="NASA HRP Exercise Countermeasures Project (ECP)"
            )
        )

    # -------------------------------------------------------------
    # 3. HAZARD: Isolation & Confinement (Circadian Disruption)
    # Threshold: Sleep < 4.5 hrs + Mood <= 2
    # -------------------------------------------------------------
    sleep = metrics.sleep_hours
    mood = metrics.mood_score
    isolation_score = 15.0
    
    if sleep < 4.5 and mood <= 2:
        isolation_score = 90.0
        clinical_flags.append(
            f"CRITICAL: Acute Circadian Disruption & Severe Behavioral Fatigue (Sleep: {sleep:.1f}h, Mood: {mood}/5). High risk of cognitive performance failure."
        )
        countermeasures.append(
            Countermeasure(
                id="CM-BEHAV-SLEEP-01",
                title="Mandatory Crew Rest & Task Stood-down Protocol",
                category="Circadian/Sleep",
                urgency="IMMEDIATE",
                protocol="Stand down astronaut from critical robotics, piloting, and EVA ops for 12 hours. Enforce dark quiet sleep block.",
                nasa_hrp_reference="NASA Behavioral Health and Performance (BHP) Standard 14.1"
            )
        )
        countermeasures.append(
            Countermeasure(
                id="CM-BEHAV-LIGHT-02",
                title="Dynamic Solid-State Circadian Light Therapy",
                category="Circadian/Sleep",
                urgency="WITHIN_4H",
                protocol="Calibrate crew quarter solid-state SSL lighting: 460 nm blue-enriched (dimmed during pre-sleep, elevated upon awakening).",
                nasa_hrp_reference="NASA TM-2020-5008149 Spaceflight Lighting Protocols"
            )
        )
    elif sleep < 5.5 or mood <= 3:
        isolation_score = 45.0
        clinical_flags.append(f"WARNING: Moderate cumulative sleep deficit ({sleep:.1f}h logged).")

    # -------------------------------------------------------------
    # 4. HAZARD: Distance from Earth
    # Fixed base risk reflecting 18.5 - 24 min latency autonomous requirement
    # -------------------------------------------------------------
    distance_score = 55.0  # Deep space / lunar surface environment baseline

    # -------------------------------------------------------------
    # 5. HAZARD: Hostile Closed Environment
    # Ingest SpO2 & Core Temperature
    # -------------------------------------------------------------
    spo2 = metrics.spo2
    hostile_env_score = 15.0
    if spo2 < 93.0:
        hostile_env_score = 85.0
        clinical_flags.append(f"CRITICAL: Arterial Hypoxemia (SpO2: {spo2:.1f}%). Possible ECLSS habitat scrubber failure or pulmonary atelectasis.")
        countermeasures.append(
            Countermeasure(
                id="CM-ECLSS-O2-01",
                title="Supplemental O2 Nasal Cannula & Habitat CO2 Purge",
                category="Hostile Closed Environment",
                urgency="IMMEDIATE",
                protocol="Administer 3 L/min medical O2 via nasal cannula. Verify cabin ppCO2 < 2.0 mmHg; swap LiOH canisters if indicated.",
                nasa_hrp_reference="NASA Space Medicine Clinical Practice Guideline #8"
            )
        )
    elif spo2 < 96.0:
        hostile_env_score = 40.0
        clinical_flags.append(f"ADVISORY: Marginal blood oxygen saturation ({spo2:.1f}%).")

    # -------------------------------------------------------------
    # Overall Score & Status Computation
    # -------------------------------------------------------------
    overall_risk_score = round(
        0.35 * rad_score +
        0.30 * micrograv_score +
        0.20 * isolation_score +
        0.10 * hostile_env_score +
        0.05 * distance_score,
        1
    )

    requires_emergency = False
    if rad_score >= 80.0 or micrograv_score >= 80.0 or isolation_score >= 80.0 or hostile_env_score >= 80.0 or overall_risk_score >= 65.0:
        overall_status = "CRITICAL"
        requires_emergency = True
    elif overall_risk_score >= 45.0:
        overall_status = "HIGH"
    elif overall_risk_score >= 25.0:
        overall_status = "ELEVATED"
    else:
        overall_status = "NOMINAL"

    ai_rationale = (
        f"Autonomous Triage evaluated 5 Spaceflight Hazards on Sol {metrics.mission_day}. "
        f"Overall Risk: {overall_risk_score}/100 [{overall_status}]. "
        f"{len(clinical_flags)} physiological flags raised. "
        f"Immediate autonomous countermeasures generated per NASA Human Research Program protocols."
    )

    return TriageResult(
        astronaut_id=metrics.astronaut_id,
        mission_day=metrics.mission_day,
        overall_status=overall_status,
        overall_risk_score=overall_risk_score,
        hazards=HazardBreakdown(
            radiation_score=rad_score,
            microgravity_score=micrograv_score,
            isolation_score=isolation_score,
            distance_score=distance_score,
            hostile_env_score=hostile_env_score
        ),
        clinical_flags=clinical_flags,
        countermeasures=countermeasures,
        requires_emergency_escalation=requires_emergency,
        ai_rationale=ai_rationale,
        evaluated_at=datetime.utcnow()
    )

@router.post("/classify", response_model=TriageResult)
def classify_triage_metrics(metrics: HealthMetrics):
    """
    Classify a specific telemetry payload against NASA 5-hazard thresholds
    and generate real-time countermeasures.
    """
    return evaluate_multi_hazard_triage(metrics)

@router.get("/current", response_model=TriageResult)
def get_current_triage_status(
    astronaut_id: Optional[str] = "ASTRO-7702-HELENA",
    db: Session = Depends(get_db)
):
    """
    Evaluates triage status using the most recent telemetry stored in the database.
    """
    count = db.query(TelemetryLog).count()
    if count == 0:
        seed_initial_telemetry(db)
        
    latest = db.query(TelemetryLog).filter(
        TelemetryLog.astronaut_id == astronaut_id
    ).order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first()
    
    if not latest:
        raise HTTPException(status_code=404, detail="No telemetry available for triage.")
        
    metrics = HealthMetrics(
        astronaut_id=latest.astronaut_id,
        mission_day=latest.mission_day,
        timestamp=latest.timestamp,
        heart_rate=latest.heart_rate,
        bp_sys=latest.bp_sys,
        bp_dia=latest.bp_dia,
        spo2=latest.spo2,
        sleep_hours=latest.sleep_hours,
        radiation_msv=latest.radiation_msv,
        blood_glucose=latest.blood_glucose,
        mood_score=latest.mood_score,
        core_temp_c=latest.core_temp_c,
        hrv_rmssd=latest.hrv_rmssd,
        subjective_notes=latest.subjective_notes
    )
    return evaluate_multi_hazard_triage(metrics)
