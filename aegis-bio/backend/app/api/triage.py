"""
Triage & Multi-Hazard Spaceflight Classification API
Dual-Classifier Architecture:
- CLASSIFIER 1: Metric-Level Severity Classifier (Evaluates if each metric is NORMAL, MEDIUM, or CRITICAL)
- CLASSIFIER 2: Multi-Hazard Spaceflight Triage Classifier (Evaluates NASA's 5 Spaceflight Hazards & Prescribes Countermeasures)
"""
from typing import Optional, Dict
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
    MetricClassificationReport,
)
from app.services.metric_classifier import metric_classifier, resolve_environment
from app.services.seeder import seed_initial_telemetry

router = APIRouter(prefix="/api/triage", tags=["Clinical Triage & Classifiers"])

# -------------------------------------------------------------
# CLASSIFIER 1: Individual Metric Severity Evaluation
# -------------------------------------------------------------
@router.post("/classify-metrics", response_model=MetricClassificationReport)
def classify_individual_metrics(metrics: HealthMetrics):
    """
    CLASSIFIER 1:
    Evaluates every single physiological and environmental metric.
    Classifies each into 'NORMAL', 'MEDIUM', or 'CRITICAL' with reference ranges
    and deviation scores per NASA-STD-3001 guidelines.
    """
    raw_dict = metrics.dict()
    return metric_classifier.evaluate_all_metrics(
        metrics_dict=raw_dict,
        astronaut_id=metrics.astronaut_id,
        mission_day=metrics.mission_day,
        environment=resolve_environment(metrics.astronaut_id),
    )

# -------------------------------------------------------------
# CLASSIFIER 2: Multi-Hazard Spaceflight Triage Engine
# -------------------------------------------------------------
def evaluate_multi_hazard_triage(metrics: HealthMetrics) -> TriageResult:
    """
    CLASSIFIER 2:
    Evaluates holistic multi-hazard risk against NASA's 5 Spaceflight Hazards:
    1. Space Radiation (SPE / GCR)
    2. Microgravity / Gravity Fields (Cardiovascular Deconditioning & Fluid Shifts)
    3. Isolation & Confinement (Circadian Disruption & Behavioral Health)
    4. Distance from Earth (24-Min Communication Latency & Autonomy Transfer)
    5. Hostile Closed Environment (Life Support, Cabin ppCO2, and Hypoxemia)
    """
    # 1. Run Classifier 1 on all metrics
    metric_report = metric_classifier.evaluate_all_metrics(
        metrics_dict=metrics.dict(),
        astronaut_id=metrics.astronaut_id,
        mission_day=metrics.mission_day,
        environment=resolve_environment(metrics.astronaut_id),
    )
    metric_evals = metric_report.metrics
    clinical_flags = []
    countermeasures = []

    # -------------------------------------------------------------
    # 1. HAZARD: Space Radiation (GCR + SPE)
    # Threshold: > 20 mSv/day = Critical Solar Particle Event (SPE)
    # -------------------------------------------------------------
    rad_eval = metric_evals.get("radiation_msv")
    rad_dose = metrics.radiation_msv
    
    if rad_dose >= 20.0 or (rad_eval and rad_eval.status == "CRITICAL"):
        rad_score = 98.0
        clinical_flags.append("CRITICAL: Solar Particle Event (SPE) detected (>20 mSv/day). Acute radiation sickness threat.")
        countermeasures.append(
            Countermeasure(
                id="CM-RAD-SPE-01",
                title="Immediate Storm Shelter Ingress",
                category="Radiation Protection",
                urgency="IMMEDIATE",
                protocol="Direct astronaut immediately into water-jacketed central habitat storm shelter. Seal airlock.",
                nasa_hrp_reference="NASA-STD-3001 Vol 1 §4.3 (Acute Radiation Exposure Countermeasures)"
            )
        )
        countermeasures.append(
            Countermeasure(
                id="CM-RAD-PHARMA-02",
                title="Radioprotectant Pharmaceutical Protocol",
                category="Clinical Pharma",
                urgency="IMMEDIATE",
                protocol="Administer Oral N-acetylcysteine (NAC) 1200 mg and subcutaneous Granulocyte colony-stimulating factor (G-CSF).",
                nasa_hrp_reference="NASA HRP-47053 Space Radiation Medical Evidence"
            )
        )
    elif rad_dose >= 2.0 or (rad_eval and rad_eval.status == "MEDIUM"):
        rad_score = 65.0
        clinical_flags.append("WARNING: Elevated ambient radiation flux (>2 mSv/day). Exceeds nominal Artemis baseline.")
        countermeasures.append(
            Countermeasure(
                id="CM-RAD-EVA-03",
                title="Immediate EVA Abort / Postponement",
                category="Radiation Protection",
                urgency="WITHIN_4H",
                protocol="Cancel all planned Extravehicular Activity. Confine crew to shielded habitat modules.",
                nasa_hrp_reference="NASA Flight Rule A13-11: Solar Radiation Monitoring"
            )
        )
    else:
        rad_score = 12.0

    # -------------------------------------------------------------
    # 2. HAZARD: Microgravity (Cardiovascular Deconditioning)
    # Threshold: Resting HR > 115 bpm or BP > 140/90 mmHg
    # -------------------------------------------------------------
    hr = metrics.heart_rate
    sys = metrics.bp_sys
    dia = metrics.bp_dia
    hr_eval = metric_evals.get("heart_rate")
    bp_eval = metric_evals.get("bp_sys")

    micrograv_score = 15.0
    if hr > 115.0 or sys > 140.0 or dia > 90.0 or (hr_eval and hr_eval.status == "CRITICAL"):
        micrograv_score = 88.0
        clinical_flags.append(
            f"CRITICAL: Microgravity Cardiovascular Deconditioning (HR: {hr:.0f} bpm, BP: {sys:.0f}/{dia:.0f} mmHg). Cephalad fluid shift & autonomic overload."
        )
        countermeasures.append(
            Countermeasure(
                id="CM-CARD-LBNP-01",
                title="Lower Body Negative Pressure (LBNP) Suit",
                category="Cardiovascular Reconditioning",
                urgency="IMMEDIATE",
                protocol="Seat astronaut in LBNP apparatus at -35 mmHg for 45 minutes to draw venous pool caudad.",
                nasa_hrp_reference="NASA SP-2009-3405 Human Adaptation to Spaceflight"
            )
        )
        countermeasures.append(
            Countermeasure(
                id="CM-CARD-FLUID-02",
                title="Electrolyte-Supported Oral Hydration Loading",
                category="Cardiovascular Reconditioning",
                urgency="WITHIN_4H",
                protocol="Ingest 1.2 L isotonic electrolyte solution with 8.0 g NaCl tabs over 90 minutes.",
                nasa_hrp_reference="NASA-STD-3001 Vol 2 §8.2.2.1"
            )
        )
    elif hr > 90.0 or sys > 130.0 or dia > 85.0 or (hr_eval and hr_eval.status == "MEDIUM"):
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
    sleep_eval = metric_evals.get("sleep_hours")
    mood_eval = metric_evals.get("mood_score")
    isolation_score = 15.0

    if (sleep < 4.5 and mood <= 2) or (sleep_eval and sleep_eval.status == "CRITICAL" and mood_eval and mood_eval.status == "CRITICAL"):
        isolation_score = 90.0
        clinical_flags.append(
            f"CRITICAL: Acute Circadian Disruption & Behavioral Fatigue (Sleep: {sleep:.1f}h, Mood: {mood}/5). High risk of cognitive performance failure."
        )
        countermeasures.append(
            Countermeasure(
                id="CM-BEHAV-SLEEP-01",
                title="Mandatory Crew Rest & Task Stood-down Protocol",
                category="Circadian/Sleep",
                urgency="IMMEDIATE",
                protocol="Stand down astronaut from critical robotics, piloting, and EVA ops for 12 hours.",
                nasa_hrp_reference="NASA Behavioral Health and Performance (BHP) Standard 14.1"
            )
        )
        countermeasures.append(
            Countermeasure(
                id="CM-BEHAV-LIGHT-02",
                title="Dynamic Solid-State Circadian Light Therapy",
                category="Circadian/Sleep",
                urgency="WITHIN_4H",
                protocol="Calibrate solid-state lighting: 460 nm blue-enriched light upon waking block.",
                nasa_hrp_reference="NASA TM-2020-5008149 Spaceflight Lighting Protocols"
            )
        )
    elif sleep < 6.0 or mood <= 3 or (sleep_eval and sleep_eval.status == "MEDIUM"):
        isolation_score = 45.0
        clinical_flags.append(f"WARNING: Moderate cumulative sleep deficit ({sleep:.1f}h logged).")

    # -------------------------------------------------------------
    # 4. HAZARD: Distance from Earth (24m Comm Latency)
    # -------------------------------------------------------------
    distance_score = 55.0

    # -------------------------------------------------------------
    # 5. HAZARD: Hostile Closed Environment (ECLSS, SpO2, CO2)
    # -------------------------------------------------------------
    spo2 = metrics.spo2
    co2 = metrics.cabin_co2_mmhg or 2.8
    spo2_eval = metric_evals.get("spo2")
    co2_eval = metric_evals.get("cabin_co2_mmhg")
    hostile_env_score = 15.0

    if spo2 < 93.0 or co2 >= 4.5 or (spo2_eval and spo2_eval.status == "CRITICAL"):
        hostile_env_score = 88.0
        clinical_flags.append(f"CRITICAL: Arterial Hypoxemia / Cabin CO2 ({spo2:.1f}% SpO2, {co2:.1f} mmHg CO2).")
        countermeasures.append(
            Countermeasure(
                id="CM-ECLSS-O2-01",
                title="Supplemental O2 Nasal Cannula & Habitat CO2 Purge",
                category="Hostile Closed Environment",
                urgency="IMMEDIATE",
                protocol="Administer 3 L/min medical O2 via nasal cannula. Purge ECLSS LiOH scrubber canisters.",
                nasa_hrp_reference="NASA Space Medicine Clinical Practice Guideline #8"
            )
        )
    elif spo2 < 96.0 or co2 >= 3.0 or (spo2_eval and spo2_eval.status == "MEDIUM"):
        hostile_env_score = 45.0
        clinical_flags.append(f"ADVISORY: Marginal blood oxygen saturation ({spo2:.1f}%).")

    # Overall Multi-Hazard Score
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
        f"Dual-Classifier Triage: Evaluated {len(metric_evals)} individual metrics. "
        f"Found {metric_report.critical_count} CRITICAL, {metric_report.medium_count} MEDIUM, {metric_report.normal_count} NORMAL. "
        f"Multi-Hazard Risk: {overall_risk_score}/100 [{overall_status}]."
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
        metric_evaluations=metric_evals,
        evaluated_at=datetime.utcnow()
    )

@router.post("/classify", response_model=TriageResult)
def classify_triage_metrics(metrics: HealthMetrics):
    """Executes Dual-Classifier Triage: returns both metric severity and spaceflight hazard triage."""
    return evaluate_multi_hazard_triage(metrics)

@router.get("/current", response_model=Optional[TriageResult])
def get_current_triage_status(
    astronaut_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Evaluates triage status using latest telemetry in the database (returns null when empty)."""
    query = db.query(TelemetryLog)
    if astronaut_id:
        query = query.filter(TelemetryLog.astronaut_id == astronaut_id)

    latest = query.order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first()
    if not latest:
        return None
        
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
