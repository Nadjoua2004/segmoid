"""
Autonomous Alarm and Emergency Escalation Service for Aegis-Bio
Handles:
- Detecting dangerous / critical predictions that require action
- Generating active alarms with dead-man's switch countdown
- Dispatching alarms to astronaut / owner
- Automatically switching / escalating to designated emergency contact if owner does not answer in time
- Acknowledgment by owner or emergency contact
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import EmergencyAlertModel, UserModel
from app.schemas import EmergencyAlert
from app.config import settings

def get_astronaut_contact_info(db: Session, astronaut_id: str) -> Dict[str, Any]:
    """
    Look up designated emergency contact chosen during authentication.
    Falls back to crew mission manifest if user profile is not yet in DB.
    """
    user = db.query(UserModel).filter(
        (UserModel.callsign == astronaut_id) | (UserModel.username == astronaut_id)
    ).first()

    if user:
        return {
            "emergency_contact_name": user.emergency_contact_name,
            "emergency_contact_callsign": user.emergency_contact_callsign,
            "emergency_contact_email": user.emergency_contact_email,
            "emergency_contact_phone": user.emergency_contact_phone,
            "emergency_contact_role": user.emergency_contact_role,
            "alert_timeout_seconds": user.alert_timeout_seconds or settings.DEFAULT_ALERT_TIMEOUT_SECONDS,
            "user_id": user.id,
        }

    # Crew manifest defaults based on mission roles
    crew_contacts = {
        "ASTRO-01": {
            "name": "Dr. Marcus Chen",
            "callsign": "ASTRO-02",
            "email": "chen@artemis.nasa.gov",
            "phone": "MCC-CH-02",
            "role": "Crew Medical Officer",
            "timeout": 60,
        },
        "ASTRO-02": {
            "name": "Cmdr. Elena Vance",
            "callsign": "ASTRO-01",
            "email": "vance@artemis.nasa.gov",
            "phone": "MCC-CH-01",
            "role": "Mission Commander",
            "timeout": 60,
        },
        "ASTRO-03": {
            "name": "Dr. Marcus Chen",
            "callsign": "ASTRO-02",
            "email": "chen@artemis.nasa.gov",
            "phone": "MCC-CH-02",
            "role": "Crew Medical Officer",
            "timeout": 60,
        },
        "ASTRO-04": {
            "name": "Dr. Marcus Chen",
            "callsign": "ASTRO-02",
            "email": "chen@artemis.nasa.gov",
            "phone": "MCC-CH-02",
            "role": "Crew Medical Officer",
            "timeout": 60,
        },
        "ASTRO-7702-HELENA": {
            "name": "Dr. Marcus Chen",
            "callsign": "ASTRO-02",
            "email": "chen@artemis.nasa.gov",
            "phone": "MCC-CH-02",
            "role": "Crew Medical Officer",
            "timeout": 60,
        },
    }

    info = crew_contacts.get(astronaut_id, crew_contacts["ASTRO-01"])
    return {
        "emergency_contact_name": info["name"],
        "emergency_contact_callsign": info["callsign"],
        "emergency_contact_email": info["email"],
        "emergency_contact_phone": info["phone"],
        "emergency_contact_role": info["role"],
        "alert_timeout_seconds": info["timeout"],
        "user_id": None,
    }

def is_prediction_dangerous_or_critical(prediction: Dict[str, Any]) -> Tuple[bool, str, List[str]]:
    """
    Evaluates whether the agent predictor output contains a dangerous or critical
    forecast that requires an immediate or within-4h intra-crew action.
    """
    reasons = []
    actions = []

    # 1. Check health outlook
    outlook = str(prediction.get("health_outlook", "")).upper()
    if outlook in ("CRITICAL_DRIFT", "CRITICAL"):
        reasons.append(f"Predictor projected overall clinical state: {outlook}")

    # 2. Check risk scores
    cv_strain = float(prediction.get("cardiovascular_strain_score", 0.0))
    cog_fatigue = float(prediction.get("cognitive_fatigue_risk", 0.0))
    hypoxia = float(prediction.get("hypoxia_eclss_risk", 0.0))
    rad_index = float(prediction.get("radiation_hazard_index", 0.0))

    if cv_strain >= 65.0:
        reasons.append(f"Severe Cardiovascular Strain forecasted ({cv_strain:.1f}/100)")
    if hypoxia >= 65.0:
        reasons.append(f"Critical Hypoxia / Cabin Atmosphere risk ({hypoxia:.1f}/100)")
    if rad_index >= 60.0:
        reasons.append(f"Hazardous ionizing radiation / SPE surge forecasted ({rad_index:.1f}/100)")
    if cog_fatigue >= 75.0:
        reasons.append(f"Severe Cognitive Deconditioning / Sleep Deficit ({cog_fatigue:.1f}/100)")

    # 3. Check trajectory points for critical days
    trajectory = prediction.get("projected_trajectory", [])
    critical_days = [
        p.get("sol_label", f"Sol {p.get('sol', '?')}")
        for p in trajectory
        if str(p.get("status", "")).upper() == "CRITICAL"
    ]
    if critical_days:
        reasons.append(f"Critical threshold breach predicted on: {', '.join(critical_days[:3])}")

    # 4. Check clinical directives for urgent actions
    directives = prediction.get("clinical_directives", [])
    for d in directives:
        urgency = str(d.get("urgency", "")).upper()
        if urgency in ("IMMEDIATE", "CRITICAL", "WITHIN_4H"):
            action_desc = f"[{urgency}] {d.get('category', 'Directive')}: {d.get('action', '')}"
            if action_desc not in actions:
                actions.append(action_desc)

    # Fallback default action if none specified
    if reasons and not actions:
        actions.append("Initiate immediate clinical vitals verification and contact Crew Medical Officer.")

    is_critical = len(reasons) > 0 or len(actions) > 0
    reason_str = " | ".join(reasons) if reasons else "Autonomous Health Predictor Alert"
    return is_critical, reason_str, actions

def sync_to_firestore_escalation(
    astro_id: str,
    state: str,
    recipient_crew_id: str,
    countdown_seconds: int,
    reason: str
):
    """Safely synchronizes escalation state to Firestore if configured."""
    try:
        from app.services.firestore_service import set_escalation_status
        set_escalation_status(
            astro_id=astro_id,
            state=state,
            recipient_crew_id=recipient_crew_id,
            countdown_seconds_remaining=countdown_seconds,
            reason=reason,
        )
    except Exception:
        pass

def create_alarm_from_prediction(
    db: Session,
    astronaut_id: str,
    prediction_data: Dict[str, Any]
) -> Optional[EmergencyAlertModel]:
    """
    Creates and dispatches an active alarm when the health predictor agent
    forecasts a dangerous or critical condition requiring action.
    """
    is_critical, reason, actions = is_prediction_dangerous_or_critical(prediction_data)
    if not is_critical:
        return None

    # Check if there is already an active unacknowledged alarm for this astronaut
    existing_alarm = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.astronaut_id == astronaut_id,
        EmergencyAlertModel.acknowledged == False,
        EmergencyAlertModel.status.in_(["PENDING_OWNER", "SWITCHED_TO_EMERGENCY_CONTACT"])
    ).order_by(EmergencyAlertModel.timestamp.desc()).first()

    if existing_alarm:
        # Check if existing alarm needs escalation
        check_and_escalate_alarms(db)
        db.refresh(existing_alarm)
        return existing_alarm

    contact_info = get_astronaut_contact_info(db, astronaut_id)
    timeout_sec = int(contact_info["alert_timeout_seconds"])
    now = datetime.utcnow()
    timeout_at = now + timedelta(seconds=timeout_sec)
    alert_id = f"PRED-ALARM-{astronaut_id}-{int(now.timestamp())}"

    alert = EmergencyAlertModel(
        alert_id=alert_id,
        astronaut_id=astronaut_id,
        user_id=contact_info.get("user_id"),
        severity="CRITICAL",
        hazard_origin="Agent Predictor: Dangerous Trajectory Forecast",
        message=reason,
        suggested_crew_actions=json.dumps(actions),
        timestamp=now,
        acknowledged=False,
        owner_answered=False,
        status="PENDING_OWNER",
        timeout_seconds=timeout_sec,
        timeout_at=timeout_at,
        emergency_contact_name=contact_info["emergency_contact_name"],
        emergency_contact_callsign=contact_info["emergency_contact_callsign"],
        emergency_contact_email=contact_info.get("emergency_contact_email"),
        emergency_contact_phone=contact_info.get("emergency_contact_phone"),
        emergency_contact_role=contact_info.get("emergency_contact_role"),
        source="HEALTH_PREDICTOR_AGENT",
        requires_action=True,
        prediction_data=json.dumps(prediction_data)
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    # Sync to Firestore escalation
    sync_to_firestore_escalation(
        astro_id=astronaut_id,
        state="PENDING_ACK",
        recipient_crew_id=contact_info["emergency_contact_callsign"],
        countdown_seconds=timeout_sec,
        reason=reason
    )

    return alert

def check_and_escalate_alarms(db: Session) -> List[EmergencyAlertModel]:
    """
    Dead-Man's Switch Timeout Checker:
    Finds all alerts where status is PENDING_OWNER and timeout has elapsed,
    and automatically switches the alert to the designated emergency contact.
    """
    now = datetime.utcnow()
    pending_alerts = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.status == "PENDING_OWNER",
        EmergencyAlertModel.acknowledged == False,
        EmergencyAlertModel.timeout_at <= now
    ).all()

    escalated = []
    for alert in pending_alerts:
        alert.status = "SWITCHED_TO_EMERGENCY_CONTACT"
        alert.emergency_contact_notified_at = now
        escalated.append(alert)

        # Sync switch to Firestore
        sync_to_firestore_escalation(
            astro_id=alert.astronaut_id,
            state="TRIGGERED",
            recipient_crew_id=alert.emergency_contact_callsign or "ASTRO-02",
            countdown_seconds=0,
            reason=f"OWNER UNRESPONSIVE: Switched alert to emergency contact {alert.emergency_contact_callsign}."
        )

    if escalated:
        db.commit()
        for a in escalated:
            db.refresh(a)

    return escalated

def answer_alarm_as_owner(
    db: Session,
    alert_id: str,
    notes: Optional[str] = None
) -> Tuple[bool, str, Optional[EmergencyAlertModel]]:
    """
    Astronaut/Owner responds to the active alarm within the timeout window.
    Halts escalation if answered in time.
    """
    # Evaluate timeouts first
    check_and_escalate_alarms(db)

    alert = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.alert_id == alert_id
    ).first()

    if not alert:
        return False, "Alert not found", None

    if alert.status == "SWITCHED_TO_EMERGENCY_CONTACT":
        return (
            False,
            f"Alert timeout expired! The alert has already been switched to your emergency contact ({alert.emergency_contact_callsign} - {alert.emergency_contact_name}).",
            alert
        )

    if alert.status in ("ACKNOWLEDGED_BY_OWNER", "RESOLVED") or alert.acknowledged:
        return True, "Alert was already acknowledged.", alert

    # Answer accepted in time
    now = datetime.utcnow()
    alert.status = "ACKNOWLEDGED_BY_OWNER"
    alert.owner_answered = True
    alert.acknowledged = True
    alert.acknowledged_by = alert.astronaut_id
    alert.acknowledged_at = now
    alert.override_notes = notes or "Owner answered within countdown window. Critical alarm disengaged."
    db.commit()
    db.refresh(alert)

    sync_to_firestore_escalation(
        astro_id=alert.astronaut_id,
        state="ACKNOWLEDGED",
        recipient_crew_id=alert.emergency_contact_callsign or "ASTRO-02",
        countdown_seconds=0,
        reason="Owner answered and halted alarm escalation."
    )

    return True, "Alarm successfully answered and acknowledged by owner before timeout window expired.", alert

def acknowledge_as_contact(
    db: Session,
    alert_id: str,
    contact_callsign: str,
    notes: Optional[str] = None
) -> Tuple[bool, str, Optional[EmergencyAlertModel]]:
    """
    Emergency Contact acknowledges the escalated alert and takes clinical action.
    """
    check_and_escalate_alarms(db)

    alert = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.alert_id == alert_id
    ).first()

    if not alert:
        return False, "Alert not found", None

    if alert.status == "ACKNOWLEDGED_BY_CONTACT" and alert.acknowledged:
        return True, "Alert already acknowledged by emergency contact.", alert

    now = datetime.utcnow()
    alert.status = "ACKNOWLEDGED_BY_CONTACT"
    alert.acknowledged = True
    alert.acknowledged_by = contact_callsign
    alert.acknowledged_at = now
    alert.override_notes = notes or f"Emergency contact {contact_callsign} intervened and acknowledged alert."
    db.commit()
    db.refresh(alert)

    sync_to_firestore_escalation(
        astro_id=alert.astronaut_id,
        state="ACKNOWLEDGED",
        recipient_crew_id=contact_callsign,
        countdown_seconds=0,
        reason=f"Intervention completed by emergency contact {contact_callsign}."
    )

    return True, f"Alert successfully acknowledged and resolved by emergency contact {contact_callsign}.", alert

def model_to_emergency_alert_schema(alert: EmergencyAlertModel) -> EmergencyAlert:
    """Helper to convert ORM model to Pydantic EmergencyAlert schema with remaining seconds."""
    actions = []
    if alert.suggested_crew_actions:
        try:
            actions = json.loads(alert.suggested_crew_actions)
        except Exception:
            actions = [alert.suggested_crew_actions]

    pred_data = None
    if alert.prediction_data:
        try:
            pred_data = json.loads(alert.prediction_data)
        except Exception:
            pred_data = None

    remaining = None
    if alert.status == "PENDING_OWNER" and alert.timeout_at:
        diff = (alert.timeout_at - datetime.utcnow()).total_seconds()
        remaining = max(0, int(diff))
    elif alert.status == "SWITCHED_TO_EMERGENCY_CONTACT":
        remaining = 0

    return EmergencyAlert(
        alert_id=alert.alert_id,
        astronaut_id=alert.astronaut_id,
        severity=alert.severity,
        hazard_origin=alert.hazard_origin,
        message=alert.message,
        suggested_crew_actions=actions,
        timestamp=alert.timestamp or datetime.utcnow(),
        acknowledged=bool(alert.acknowledged),
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
        override_notes=alert.override_notes,
        status=alert.status or "PENDING_OWNER",
        timeout_seconds=alert.timeout_seconds or 60,
        timeout_at=alert.timeout_at,
        remaining_seconds=remaining,
        emergency_contact_name=alert.emergency_contact_name,
        emergency_contact_callsign=alert.emergency_contact_callsign,
        emergency_contact_email=alert.emergency_contact_email,
        emergency_contact_phone=alert.emergency_contact_phone,
        emergency_contact_role=alert.emergency_contact_role,
        emergency_contact_notified_at=alert.emergency_contact_notified_at,
        source=alert.source or "SYSTEM",
        requires_action=bool(alert.requires_action),
        owner_answered=bool(alert.owner_answered),
        prediction_data=pred_data
    )
