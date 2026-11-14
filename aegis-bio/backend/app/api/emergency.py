"""
Emergency Escalation & Alarm Routing API
Autonomous Intra-Crew Emergency Escalation Protocol for Deep Space Latency (24m).
Alerts crew members locally without requiring real-time Earth confirmation.
Features Dead-Man's Switch: If the astronaut owner does not answer within the configured
timeout window, the alarm automatically switches and escalates to the chosen Emergency Contact.
"""
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmergencyAlertModel, TelemetryLog
from app.schemas import (
    EmergencyAlert,
    EmergencyAckRequest,
    EmergencyOwnerAnswerRequest,
    EmergencyContactAckRequest,
    HealthMetrics
)
from app.api.triage import evaluate_multi_hazard_triage
from app.services.alarm_service import (
    check_and_escalate_alarms,
    answer_alarm_as_owner,
    acknowledge_as_contact,
    model_to_emergency_alert_schema,
    get_astronaut_contact_info,
    sync_to_supabase_escalation,
    find_closest_astronaut
)

router = APIRouter(prefix="/api/emergency", tags=["Intra-Crew Emergency Protocol & Alarm System"])

@router.get("/status", response_model=Optional[EmergencyAlert])
def get_emergency_status(
    astronaut_id: Optional[str] = "ASTRO-7702-HELENA",
    db: Session = Depends(get_db)
):
    """
    Returns the currently active, unacknowledged critical alert.
    Automatically evaluates dead-man's switch timeouts: if the owner has not answered
    within the configured timeout window, the status automatically switches to
    'SWITCHED_TO_EMERGENCY_CONTACT'.
    """
    # 1. Run timeout evaluation to switch overdue alerts
    check_and_escalate_alarms(db)

    # 2. Check database for active unacknowledged alert for this astronaut (or any unacknowledged)
    stored = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.acknowledged == False,
        (EmergencyAlertModel.astronaut_id == astronaut_id) | (EmergencyAlertModel.astronaut_id == "ASTRO-7702-HELENA")
    ).order_by(EmergencyAlertModel.timestamp.desc()).first()

    if not stored:
        # Check any unacknowledged alert
        stored = db.query(EmergencyAlertModel).filter(
            EmergencyAlertModel.acknowledged == False
        ).order_by(EmergencyAlertModel.timestamp.desc()).first()

    if stored:
        return model_to_emergency_alert_schema(stored)

    # 3. Check if latest telemetry triggers an emergency state
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
            contact_info = get_astronaut_contact_info(db, latest.astronaut_id)
            timeout_sec = contact_info["alert_timeout_seconds"]
            now = datetime.utcnow()
            alert_id = f"ALERT-SOL{latest.mission_day}-{int(now.timestamp())}"
            actions = [cm.protocol for cm in triage.countermeasures]

            db_alert = EmergencyAlertModel(
                alert_id=alert_id,
                astronaut_id=latest.astronaut_id,
                user_id=contact_info.get("user_id"),
                severity="CRITICAL_ESCALATION",
                hazard_origin="Spaceflight Multi-Hazard Threshold Breach",
                message="; ".join(triage.clinical_flags),
                suggested_crew_actions=json.dumps(actions),
                timestamp=now,
                acknowledged=False,
                owner_answered=False,
                status="PENDING_OWNER",
                timeout_seconds=timeout_sec,
                timeout_at=now + timedelta(seconds=timeout_sec),
                emergency_contact_name=contact_info["emergency_contact_name"],
                emergency_contact_callsign=contact_info["emergency_contact_callsign"],
                emergency_contact_email=contact_info.get("emergency_contact_email"),
                emergency_contact_phone=contact_info.get("emergency_contact_phone"),
                emergency_contact_role=contact_info.get("emergency_contact_role"),
                source="TELEMETRY_TRIAGE",
                requires_action=True
            )
            db.add(db_alert)
            db.commit()
            db.refresh(db_alert)

            sync_to_supabase_escalation(
                astro_id=latest.astronaut_id,
                state="PENDING_ACK",
                recipient_crew_id=contact_info["emergency_contact_callsign"],
                countdown_seconds=timeout_sec,
                reason="; ".join(triage.clinical_flags)
            )

            return model_to_emergency_alert_schema(db_alert)

    return None

@router.get("/alarms", response_model=List[EmergencyAlert])
def list_all_alarms(
    astronaut_id: Optional[str] = Query(None, description="Filter by astronaut callsign"),
    status_filter: Optional[str] = Query(None, description="Filter by status: PENDING_OWNER, SWITCHED_TO_EMERGENCY_CONTACT, etc."),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    List historical and active alarms with current dead-man's switch escalation state.
    """
    check_and_escalate_alarms(db)

    query = db.query(EmergencyAlertModel)
    if astronaut_id:
        query = query.filter(EmergencyAlertModel.astronaut_id == astronaut_id)
    if status_filter:
        query = query.filter(EmergencyAlertModel.status == status_filter)

    records = query.order_by(EmergencyAlertModel.timestamp.desc()).limit(limit).all()
    return [model_to_emergency_alert_schema(r) for r in records]

@router.post("/answer-owner")
def owner_answer_alarm(
    payload: EmergencyOwnerAnswerRequest,
    db: Session = Depends(get_db)
):
    """
    Owner (Astronaut) responds to the critical alarm.
    If responded within the timeout window, halts escalation and disengages siren.
    If the timeout window has expired, the alert has already switched to the designated Emergency Contact.
    """
    success, msg, alert = answer_alarm_as_owner(db, payload.alert_id, payload.notes)
    if not alert:
        raise HTTPException(status_code=404, detail=msg)

    schema = model_to_emergency_alert_schema(alert)
    return {
        "success": success,
        "message": msg,
        "alert": schema
    }

@router.post("/contact-ack", response_model=EmergencyAlert)
def contact_acknowledge_alarm(
    payload: EmergencyContactAckRequest,
    db: Session = Depends(get_db)
):
    """
    Designated Emergency Contact acknowledges the escalated alarm and logs rescue/intervention.
    """
    success, msg, alert = acknowledge_as_contact(
        db, payload.alert_id, payload.contact_callsign, payload.intervention_notes
    )
    if not alert:
        raise HTTPException(status_code=404, detail=msg)

    return model_to_emergency_alert_schema(alert)

@router.post("/check-timeout", response_model=List[EmergencyAlert])
def trigger_timeout_check(db: Session = Depends(get_db)):
    """
    Explicitly trigger the dead-man's switch timeout check.
    Any alarms that expired without owner acknowledgment are switched to their Emergency Contact.
    """
    escalated = check_and_escalate_alarms(db)
    return [model_to_emergency_alert_schema(a) for a in escalated]

@router.post("/ack", response_model=EmergencyAlert)
def acknowledge_emergency(
    payload: EmergencyAckRequest,
    db: Session = Depends(get_db)
):
    """
    Legacy acknowledgment endpoint (backwards compatible).
    Halts audio alarm sirens and logs the intervention.
    """
    check_and_escalate_alarms(db)

    alert = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.alert_id == payload.alert_id
    ).first()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert ID not found.")

    alert.acknowledged = True
    alert.acknowledged_by = payload.crew_member_callsign
    alert.acknowledged_at = datetime.utcnow()
    alert.override_notes = payload.override_notes or ""
    if alert.status == "SWITCHED_TO_EMERGENCY_CONTACT":
        alert.status = "ACKNOWLEDGED_BY_CONTACT"
    else:
        alert.status = "ACKNOWLEDGED_BY_OWNER"
        alert.owner_answered = True

    db.commit()
    db.refresh(alert)

    sync_to_supabase_escalation(
        astro_id=alert.astronaut_id,
        state="ACKNOWLEDGED",
        recipient_crew_id=payload.crew_member_callsign,
        countdown_seconds=0,
        reason=payload.override_notes or "Acknowledged"
    )

    return model_to_emergency_alert_schema(alert)

@router.post("/trigger", response_model=EmergencyAlert)
def trigger_manual_emergency(
    hazard_origin: str = "Solar Particle Event Simulation",
    message: str = "Manual Drill: Radiation threshold exceeded 25 mSv/hr.",
    timeout_seconds: Optional[int] = None,
    astronaut_id: str = "ASTRO-01",
    db: Session = Depends(get_db)
):
    """
    Simulates an intra-crew emergency escalation for habitat testing with designated Emergency Contact.
    """
    contact_info = get_astronaut_contact_info(db, astronaut_id)
    timeout_sec = timeout_seconds or contact_info["alert_timeout_seconds"]
    now = datetime.utcnow()

    alert_id = f"DRILL-{int(now.timestamp())}"
    actions = [
        "Muster all crew in Water-Shielded Module 2",
        "Engage storm shelter airlock pressure lock",
        "Prepare emergency IV hydration and dosimeters"
    ]

    alert = EmergencyAlertModel(
        alert_id=alert_id,
        astronaut_id=astronaut_id,
        user_id=contact_info.get("user_id"),
        severity="CRITICAL_ESCALATION",
        hazard_origin=hazard_origin,
        message=message,
        suggested_crew_actions=json.dumps(actions),
        timestamp=now,
        acknowledged=False,
        owner_answered=False,
        status="PENDING_OWNER",
        timeout_seconds=timeout_sec,
        timeout_at=now + timedelta(seconds=timeout_sec),
        emergency_contact_name=contact_info["emergency_contact_name"],
        emergency_contact_callsign=contact_info["emergency_contact_callsign"],
        emergency_contact_email=contact_info.get("emergency_contact_email"),
        emergency_contact_phone=contact_info.get("emergency_contact_phone"),
        emergency_contact_role=contact_info["emergency_contact_role"],
        source="MANUAL_DRILL",
        requires_action=True
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    sync_to_supabase_escalation(
        astro_id=astronaut_id,
        state="PENDING_ACK",
        recipient_crew_id=contact_info["emergency_contact_callsign"],
        countdown_seconds=timeout_sec,
        reason=message
    )

    return model_to_emergency_alert_schema(alert)
