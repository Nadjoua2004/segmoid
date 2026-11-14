"""
Emergency Escalation API
Autonomous Intra-Crew Emergency Escalation Protocol for Deep Space Latency (24m).
Alerts crew members locally without requiring real-time Earth confirmation.
"""
import json
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmergencyAlertModel, TelemetryLog
from app.schemas import EmergencyAlert, EmergencyAckRequest
from app.api.triage import evaluate_multi_hazard_triage
from app.schemas import HealthMetrics

router = APIRouter(prefix="/api/emergency", tags=["Intra-Crew Emergency Protocol"])

@router.get("/status", response_model=Optional[EmergencyAlert])
def get_emergency_status(
    astronaut_id: Optional[str] = "ASTRO-7702-HELENA",
    db: Session = Depends(get_db)
):
    """
    Returns the currently active, unacknowledged critical alert.
    If no manual or stored alert is unacknowledged, checks latest triage status.
    """
    # 1. Check database for active unacknowledged alert
    stored = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.acknowledged == False
    ).order_by(EmergencyAlertModel.timestamp.desc()).first()

    if stored:
        actions = []
        try:
            actions = json.loads(stored.suggested_crew_actions)
        except Exception:
            actions = [stored.suggested_crew_actions]

        return EmergencyAlert(
            alert_id=stored.alert_id,
            astronaut_id=stored.astronaut_id,
            severity=stored.severity,
            hazard_origin=stored.hazard_origin,
            message=stored.message,
            suggested_crew_actions=actions,
            timestamp=stored.timestamp,
            acknowledged=stored.acknowledged,
            acknowledged_by=stored.acknowledged_by,
            acknowledged_at=stored.acknowledged_at
        )

    # 2. Check if latest telemetry triggers an emergency state
    latest = db.query(TelemetryLog).filter(
        TelemetryLog.astronaut_id == astronaut_id
    ).order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first()

    if latest:
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
            mood_score=latest.mood_score
        )
        triage = evaluate_multi_hazard_triage(metrics)
        if triage.requires_emergency_escalation:
            # Create emergency record
            alert_id = f"ALERT-SOL{latest.mission_day}-{int(datetime.utcnow().timestamp())}"
            actions = [cm.protocol for cm in triage.countermeasures]
            
            db_alert = EmergencyAlertModel(
                alert_id=alert_id,
                astronaut_id=latest.astronaut_id,
                severity="CRITICAL_ESCALATION",
                hazard_origin="Spaceflight Multi-Hazard Threshold Breach",
                message="; ".join(triage.clinical_flags),
                suggested_crew_actions=json.dumps(actions),
                acknowledged=False
            )
            db.add(db_alert)
            db.commit()

            return EmergencyAlert(
                alert_id=alert_id,
                astronaut_id=latest.astronaut_id,
                severity="CRITICAL_ESCALATION",
                hazard_origin="Multi-Hazard Autonomous Trigger",
                message="; ".join(triage.clinical_flags),
                suggested_crew_actions=actions,
                timestamp=datetime.utcnow(),
                acknowledged=False
            )

    return None

@router.post("/ack", response_model=EmergencyAlert)
def acknowledge_emergency(
    payload: EmergencyAckRequest,
    db: Session = Depends(get_db)
):
    """
    Crew Medical Officer or fellow astronaut acknowledges the active emergency,
    halting audio alarm sirens and logging the intervention into the black box.
    """
    alert = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.alert_id == payload.alert_id
    ).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert ID not found.")

    alert.acknowledged = True
    alert.acknowledged_by = payload.crew_member_callsign
    alert.acknowledged_at = datetime.utcnow()
    alert.override_notes = payload.override_notes or ""
    db.commit()
    db.refresh(alert)

    actions = []
    try:
        actions = json.loads(alert.suggested_crew_actions)
    except Exception:
        actions = [alert.suggested_crew_actions]

    return EmergencyAlert(
        alert_id=alert.alert_id,
        astronaut_id=alert.astronaut_id,
        severity=alert.severity,
        hazard_origin=alert.hazard_origin,
        message=alert.message,
        suggested_crew_actions=actions,
        timestamp=alert.timestamp,
        acknowledged=alert.acknowledged,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at
    )

@router.post("/trigger", response_model=EmergencyAlert)
def trigger_manual_emergency(
    hazard_origin: str = "Solar Particle Event Simulation",
    message: str = "Manual Drill: Radiation threshold exceeded 25 mSv/hr.",
    db: Session = Depends(get_db)
):
    """Simulates an intra-crew emergency escalation for habitat testing."""
    alert_id = f"DRILL-{int(datetime.utcnow().timestamp())}"
    actions = [
        "Muster all crew in Water-Shielded Module 2",
        "Engage storm shelter airlock pressure lock",
        "Prepare emergency IV hydration and dosimeters"
    ]
    
    alert = EmergencyAlertModel(
        alert_id=alert_id,
        astronaut_id="ASTRO-7702-HELENA",
        severity="CRITICAL_ESCALATION",
        hazard_origin=hazard_origin,
        message=message,
        suggested_crew_actions=json.dumps(actions),
        acknowledged=False
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    
    return EmergencyAlert(
        alert_id=alert.alert_id,
        astronaut_id=alert.astronaut_id,
        severity=alert.severity,
        hazard_origin=alert.hazard_origin,
        message=alert.message,
        suggested_crew_actions=actions,
        timestamp=alert.timestamp,
        acknowledged=False
    )
