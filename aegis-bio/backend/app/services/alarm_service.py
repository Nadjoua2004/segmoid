"""
Autonomous Alarm and Emergency Escalation Service for Aegis-Bio
Handles:
- Detecting dangerous / critical predictions that require action
- Generating active alarms with dead-man's switch countdown
- Proximity-based Nearest Astronaut Resolution (Indoor Positioning System across habitat compartments)
- Dynamically switching / escalating the alarm to the closest astronaut if owner does not answer in time
- Real-time synchronization to Supabase PostgreSQL database
- Acknowledgment by owner or emergency responder
"""
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import EmergencyAlertModel, UserModel
from app.schemas import EmergencyAlert
from app.config import settings

# -------------------------------------------------------------
# Habitat Modules & 3D Spatial Layout (Artemis Lunar Base Alpha)
# Coordinates in meters relative to habitat center core
# -------------------------------------------------------------
HABITAT_MODULES = {
    "COMMAND_CORE":   {"name": "Command & Operations Core",    "x": 0.0,  "y": 0.0,  "z": 0.0},
    "MED_BAY":        {"name": "Medical Bay & Bio-Lab",        "x": 4.5,  "y": 2.0,  "z": 0.0},
    "CREW_QUARTERS":  {"name": "Crew Sleeping Quarters",       "x": -6.0, "y": 1.0,  "z": 0.0},
    "ECLSS_SERVICE":  {"name": "Life Support & Engineering",   "x": 0.0,  "y": -8.0, "z": 0.0},
    "STORM_SHELTER":  {"name": "Water-Shielded SPE Bunker",    "x": -3.0, "y": -4.0, "z": -2.0},
    "EVA_AIRLOCK":    {"name": "Surface EVA Airlock",          "x": 8.0,  "y": 0.0,  "z": 0.0},
}

# Current/latest known physical compartment and beacon coordinates per astronaut device
ASTRONAUT_DEVICE_LOCATIONS = {
    "ASTRO-01": {
        "callsign": "ASTRO-01",
        "name": "Cmdr. Elena Vance",
        "role": "Mission Commander",
        "current_module": "CREW_QUARTERS",
        "x": -5.8, "y": 1.2, "z": 0.0,
    },
    "ASTRO-02": {
        "callsign": "ASTRO-02",
        "name": "Dr. Marcus Chen",
        "role": "Crew Medical Officer",
        "current_module": "MED_BAY",
        "x": 4.2, "y": 1.8, "z": 0.0,
    },
    "ASTRO-03": {
        "callsign": "ASTRO-03",
        "name": "Eng. Jan Kowalski",
        "role": "Chief ECLSS Engineer",
        "current_module": "ECLSS_SERVICE",
        "x": 0.2, "y": -7.8, "z": 0.0,
    },
    "ASTRO-04": {
        "callsign": "ASTRO-04",
        "name": "Spec. Layla Al-Mansoor",
        "role": "Navigation Specialist",
        "current_module": "COMMAND_CORE",
        "x": 0.5, "y": 0.4, "z": 0.0,
    },
    "ASTRO-7702-HELENA": {
        "callsign": "ASTRO-7702-HELENA",
        "name": "Helena Rostova",
        "role": "Payload Specialist",
        "current_module": "CREW_QUARTERS",
        "x": -6.0, "y": 1.0, "z": 0.0,
    },
}

def find_closest_astronaut(victim_callsign: str, db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Finds the closest astronaut to the unresponsive victim's device using 3D Euclidean distance.
    Evaluates habitat compartments and distance in meters.
    """
    victim_loc = ASTRONAUT_DEVICE_LOCATIONS.get(
        victim_callsign, ASTRONAUT_DEVICE_LOCATIONS["ASTRO-01"]
    )
    vx, vy, vz = victim_loc["x"], victim_loc["y"], victim_loc["z"]

    candidates = []
    for callsign, loc in ASTRONAUT_DEVICE_LOCATIONS.items():
        if callsign == victim_callsign:
            continue
        # Avoid treating same person aliases as candidates
        if victim_callsign.startswith("ASTRO-01") and callsign.startswith("ASTRO-01"):
            continue

        # 3D Euclidean Distance: sqrt((x2-x1)^2 + (y2-y1)^2 + (z2-z1)^2)
        dist = math.sqrt(
            (loc["x"] - vx) ** 2 +
            (loc["y"] - vy) ** 2 +
            (loc["z"] - vz) ** 2
        )
        candidates.append({
            "distance": dist,
            "callsign": callsign,
            "name": loc["name"],
            "role": loc["role"],
            "module": loc["current_module"],
            "module_name": HABITAT_MODULES.get(loc["current_module"], {}).get("name", loc["current_module"]),
        })

    candidates.sort(key=lambda c: c["distance"])

    if not candidates:
        return {
            "closest_callsign": "ASTRO-02",
            "closest_name": "Dr. Marcus Chen",
            "closest_role": "Crew Medical Officer",
            "closest_module": "MED_BAY",
            "distance_meters": 4.5,
            "victim_module": victim_loc["current_module"],
        }

    winner = candidates[0]
    return {
        "closest_callsign": winner["callsign"],
        "closest_name": winner["name"],
        "closest_role": winner["role"],
        "closest_module": winner["module"],
        "closest_module_name": winner["module_name"],
        "distance_meters": round(winner["distance"], 1),
        "victim_module": victim_loc["current_module"],
        "victim_module_name": HABITAT_MODULES.get(victim_loc["current_module"], {}).get("name", victim_loc["current_module"]),
    }

def get_initial_emergency_contact(db: Session, astronaut_id: str) -> Dict[str, Any]:
    """
    Look up designated initial responder or dynamically compute the closest astronaut.
    """
    closest = find_closest_astronaut(astronaut_id, db)
    user = db.query(UserModel).filter(
        (UserModel.callsign == astronaut_id) | (UserModel.username == astronaut_id)
    ).first()

    timeout_sec = user.alert_timeout_seconds if user else settings.DEFAULT_ALERT_TIMEOUT_SECONDS
    return {
        "emergency_contact_name": closest["closest_name"],
        "emergency_contact_callsign": closest["closest_callsign"],
        "emergency_contact_email": f"{closest['closest_callsign'].lower()}@artemis.nasa.gov",
        "emergency_contact_phone": f"COM-CHAN-{closest['closest_callsign']}",
        "emergency_contact_role": f"{closest['closest_role']} ({closest['distance_meters']}m away in {closest['closest_module']})",
        "alert_timeout_seconds": timeout_sec,
        "user_id": user.id if user else None,
        "closest_info": closest,
    }

def sync_to_supabase_escalation(
    astro_id: str,
    state: str,
    recipient_crew_id: str,
    countdown_seconds: int,
    reason: str
):
    """Safely synchronizes escalation state to Supabase PostgreSQL database."""
    try:
        from app.services.supabase_service import set_escalation_status
        set_escalation_status(
            astro_id=astro_id,
            state=state,
            recipient_crew_id=recipient_crew_id,
            countdown_seconds_remaining=countdown_seconds,
            reason=reason,
        )
    except Exception as e:
        print(f"[Supabase Escalation Sync] {e}")

# Aliases for backwards compatibility
get_astronaut_contact_info = get_initial_emergency_contact
sync_to_firestore_escalation = sync_to_supabase_escalation

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

    if reasons and not actions:
        actions.append("Initiate immediate clinical vitals verification and contact closest crew responder.")

    is_critical = len(reasons) > 0 or len(actions) > 0
    reason_str = " | ".join(reasons) if reasons else "Autonomous Health Predictor Alert"
    return is_critical, reason_str, actions

def create_alarm_from_prediction(
    db: Session,
    astronaut_id: str,
    prediction_data: Dict[str, Any]
) -> Optional[EmergencyAlertModel]:
    """
    Creates and dispatches an active alarm when the health predictor agent
    forecasts a dangerous or critical condition requiring action.
    Initializes tracking to the closest astronaut to the person's device.
    """
    is_critical, reason, actions = is_prediction_dangerous_or_critical(prediction_data)
    if not is_critical:
        return None

    # Check existing unacknowledged alarm
    existing_alarm = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.astronaut_id == astronaut_id,
        EmergencyAlertModel.acknowledged == False,
        EmergencyAlertModel.status.in_(["PENDING_OWNER", "SWITCHED_TO_EMERGENCY_CONTACT"])
    ).order_by(EmergencyAlertModel.timestamp.desc()).first()

    if existing_alarm:
        check_and_escalate_alarms(db)
        db.refresh(existing_alarm)
        return existing_alarm

    contact_info = get_initial_emergency_contact(db, astronaut_id)
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
        emergency_contact_role=contact_info["emergency_contact_role"],
        source="HEALTH_PREDICTOR_AGENT",
        requires_action=True,
        prediction_data=json.dumps(prediction_data)
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    # Sync to Supabase PostgreSQL database
    sync_to_supabase_escalation(
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
    Finds all alerts where status is PENDING_OWNER and timeout has elapsed.
    Dynamically resolves the closest astronaut to the victim's device in real-time,
    and automatically switches the alert to that closest astronaut!
    """
    now = datetime.utcnow()
    pending_alerts = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.status == "PENDING_OWNER",
        EmergencyAlertModel.acknowledged == False,
        EmergencyAlertModel.timeout_at <= now
    ).all()

    escalated = []
    for alert in pending_alerts:
        # Dynamically determine the closest astronaut to the person's device right now!
        closest = find_closest_astronaut(alert.astronaut_id, db)

        alert.status = "SWITCHED_TO_EMERGENCY_CONTACT"
        alert.emergency_contact_callsign = closest["closest_callsign"]
        alert.emergency_contact_name = closest["closest_name"]
        alert.emergency_contact_role = (
            f"{closest['closest_role']} (Nearest: {closest['distance_meters']}m away in {closest['closest_module_name']})"
        )
        alert.emergency_contact_notified_at = now
        escalated.append(alert)

        reason = (
            f"OWNER UNRESPONSIVE in {closest['victim_module_name']}. "
            f"Alert switched to closest astronaut: {closest['closest_name']} "
            f"({closest['closest_callsign']}, {closest['distance_meters']}m away in {closest['closest_module_name']})."
        )

        # Sync to Supabase PostgreSQL
        sync_to_supabase_escalation(
            astro_id=alert.astronaut_id,
            state="TRIGGERED",
            recipient_crew_id=closest["closest_callsign"],
            countdown_seconds=0,
            reason=reason
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
    check_and_escalate_alarms(db)

    alert = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.alert_id == alert_id
    ).first()

    if not alert:
        return False, "Alert not found", None

    if alert.status == "SWITCHED_TO_EMERGENCY_CONTACT":
        return (
            False,
            f"Alert timeout expired! The alert has already been switched to the closest astronaut ({alert.emergency_contact_callsign} - {alert.emergency_contact_name}).",
            alert
        )

    if alert.status in ("ACKNOWLEDGED_BY_OWNER", "RESOLVED") or alert.acknowledged:
        return True, "Alert was already acknowledged.", alert

    now = datetime.utcnow()
    alert.status = "ACKNOWLEDGED_BY_OWNER"
    alert.owner_answered = True
    alert.acknowledged = True
    alert.acknowledged_by = alert.astronaut_id
    alert.acknowledged_at = now
    alert.override_notes = notes or "Owner answered within countdown window. Critical alarm disengaged."
    db.commit()
    db.refresh(alert)

    # Sync resolved state to Supabase
    sync_to_supabase_escalation(
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
    Closest astronaut acknowledges the escalated alert and takes clinical action.
    """
    check_and_escalate_alarms(db)

    alert = db.query(EmergencyAlertModel).filter(
        EmergencyAlertModel.alert_id == alert_id
    ).first()

    if not alert:
        return False, "Alert not found", None

    if alert.status == "ACKNOWLEDGED_BY_CONTACT" and alert.acknowledged:
        return True, "Alert already acknowledged by closest responder.", alert

    now = datetime.utcnow()
    alert.status = "ACKNOWLEDGED_BY_CONTACT"
    alert.acknowledged = True
    alert.acknowledged_by = contact_callsign
    alert.acknowledged_at = now
    alert.override_notes = notes or f"Nearest responder {contact_callsign} intervened and acknowledged alert."
    db.commit()
    db.refresh(alert)

    # Sync acknowledgment to Supabase
    sync_to_supabase_escalation(
        astro_id=alert.astronaut_id,
        state="ACKNOWLEDGED",
        recipient_crew_id=contact_callsign,
        countdown_seconds=0,
        reason=f"Intervention completed by closest responder {contact_callsign}."
    )

    return True, f"Alert successfully acknowledged and resolved by closest astronaut {contact_callsign}.", alert

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
