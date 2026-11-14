"""
Firestore Operational Database Service Layer for Aegis-Bio.

Provides strongly-typed CRUD and real-time state management helpers for FastAPI routes:
1. astronauts & astronauts/{astroId}/telemetry_logs
2. daily_checkins
3. triage_alerts
4. chat_sessions & chat_sessions/{sessionId}/messages
5. emergency_escalations
6. health_predictions

NOTE: NASA clinical RAG embeddings are managed separately in local ChromaDB.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_admin import firestore

from app.firebase_config import db


def _utc_now() -> datetime:
    """Return timezone-aware UTC datetime for Firestore timestamp fields."""
    return datetime.now(timezone.utc)


# =====================================================================
# 1. ASTRONAUTS & TELEMETRY LOGS (`astronauts/{astroId}/telemetry_logs`)
# =====================================================================

def add_telemetry_log(astro_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Append a high-frequency or hourly telemetry log to `astronauts/{astro_id}/telemetry_logs`
    and synchronize the parent astronaut's `current_status` and `mission_day`.
    """
    now_iso = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    mission_day = int(data.get("mission_day", 1))
    hour = int(data.get("hour", _utc_now().hour))
    status = str(data.get("status", "NOMINAL")).upper()

    payload: Dict[str, Any] = {
        "timestamp": str(data.get("timestamp", now_iso)),
        "mission_day": mission_day,
        "hour": hour,
        "heart_rate_bpm": int(data.get("heart_rate_bpm", 65)),
        "hrv_rmssd_ms": int(data.get("hrv_rmssd_ms", 48)),
        "spo2_percent": float(data.get("spo2_percent", 98.0)),
        "core_temp_c": float(data.get("core_temp_c", 36.8)),
        "radiation_rate_usv_h": float(data.get("radiation_rate_usv_h", 75.0)),
        "cumulative_radiation_msv": float(data.get("cumulative_radiation_msv", 12.5)),
        "cabin_co2_mmhg": float(data.get("cabin_co2_mmhg", 2.6)),
        "activity_state": str(data.get("activity_state", "DUTY")),
        "status": status,
        "primary_hazard": str(data.get("primary_hazard", "NONE")),
    }

    doc_id = data.get("doc_id") or f"day_{mission_day:03d}_hr_{hour:02d}"
    astro_ref = db.collection("astronauts").document(astro_id)
    log_ref = astro_ref.collection("telemetry_logs").document(doc_id)
    log_ref.set(payload)

    # Keep parent astronaut operational status synchronized
    astro_ref.set(
        {
            "mission_day": mission_day,
            "current_status": status,
        },
        merge=True,
    )

    return {"id": doc_id, "astronaut_id": astro_id, **payload}


def get_recent_telemetry(astro_id: str, limit: int = 48) -> List[Dict[str, Any]]:
    """
    Fetch the most recent `limit` telemetry logs (default 48 hours) for an astronaut,
    returned in chronological order (oldest -> newest) for time-series charting.
    """
    logs_ref = (
        db.collection("astronauts")
        .document(astro_id)
        .collection("telemetry_logs")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    docs = logs_ref.stream()
    records: List[Dict[str, Any]] = []
    for doc in docs:
        item = doc.to_dict() or {}
        item["id"] = doc.id
        records.append(item)

    # Reverse so charts and ML models receive chronological time-series
    records.reverse()
    return records


# =====================================================================
# 2. DAILY CHECK-INS (`daily_checkins/{astroId}_day_{missionDay}`)
# =====================================================================

def save_daily_checkin(checkin_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save an astronaut's subjective daily check-in under `daily_checkins/{astroId}_day_{missionDay}`
    and update `last_checkin` on the parent `astronauts/{astroId}` document.
    """
    astro_id = str(checkin_data["astronaut_id"])
    mission_day = int(checkin_data["mission_day"])
    doc_id = f"{astro_id}_day_{mission_day}"
    submitted_at = checkin_data.get("submitted_at") or _utc_now()

    payload: Dict[str, Any] = {
        "astronaut_id": astro_id,
        "mission_day": mission_day,
        "sleep_hours": float(checkin_data.get("sleep_hours", 6.5)),
        "sleep_quality_score": int(checkin_data.get("sleep_quality_score", 4)),
        "mood_score": int(checkin_data.get("mood_score", 4)),
        "reported_symptoms": list(checkin_data.get("reported_symptoms", [])),
        "notes": str(checkin_data.get("notes", "")),
        "submitted_at": submitted_at,
    }

    db.collection("daily_checkins").document(doc_id).set(payload)

    # Update astronaut's last_checkin timestamp
    db.collection("astronauts").document(astro_id).set(
        {"last_checkin": submitted_at, "mission_day": mission_day},
        merge=True,
    )

    return {"id": doc_id, **payload}


# =====================================================================
# 3. TRIAGE ALERTS (`triage_alerts/{alertId}`)
# =====================================================================

def create_triage_alert(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a real-time clinical triage alert in `triage_alerts`.
    """
    alert_id = str(alert_data.get("alert_id") or f"ALT-{uuid.uuid4().hex[:8].upper()}")
    astro_id = str(alert_data["astronaut_id"])
    severity = str(alert_data.get("severity", "WARNING")).upper()
    is_acknowledged = bool(alert_data.get("is_acknowledged", False))
    status = str(alert_data.get("status", "ACKNOWLEDGED" if is_acknowledged else "ACTIVE")).upper()

    payload: Dict[str, Any] = {
        "alert_id": alert_id,
        "astronaut_id": astro_id,
        "timestamp": alert_data.get("timestamp") or _utc_now(),
        "severity": severity,
        "hazard_type": str(alert_data.get("hazard_type", "SPACE_RADIATION_SPE")),
        "hazard_title": str(alert_data.get("hazard_title", "Clinical Anomaly Detected")),
        "triggering_vitals": dict(alert_data.get("triggering_vitals", {})),
        "is_acknowledged": is_acknowledged,
        "status": status,
    }

    db.collection("triage_alerts").document(alert_id).set(payload)

    # Reflect alert severity on astronaut profile if ACTIVE
    if status == "ACTIVE" and severity in ("WARNING", "CRITICAL"):
        db.collection("astronauts").document(astro_id).set(
            {"current_status": severity},
            merge=True,
        )

    return payload


def acknowledge_triage_alert(alert_id: str) -> Dict[str, Any]:
    """
    Mark a triage alert as acknowledged (`is_acknowledged=True`, `status="ACKNOWLEDGED"`).
    """
    alert_ref = db.collection("triage_alerts").document(alert_id)
    snapshot = alert_ref.get()
    if not snapshot.exists:
        raise ValueError(f"Triage alert '{alert_id}' not found in Firestore.")

    updates: Dict[str, Any] = {
        "is_acknowledged": True,
        "status": "ACKNOWLEDGED",
    }
    alert_ref.update(updates)

    updated_data = snapshot.to_dict() or {}
    updated_data.update(updates)
    return updated_data


# =====================================================================
# 4. CHAT SESSIONS & MESSAGES (`chat_sessions/{sessionId}/messages`)
# =====================================================================

def log_chat_message(session_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store a chat message in `chat_sessions/{session_id}/messages` between the astronaut
    and the AI Flight Surgeon (`astrodoc_agent`), including structured countermeasures
    and NASA references.
    """
    now = message_data.get("timestamp") or _utc_now()
    message_id = str(message_data.get("message_id") or f"MSG-{uuid.uuid4().hex[:8].upper()}")
    sender = str(message_data.get("sender", "astronaut"))

    payload: Dict[str, Any] = {
        "message_id": message_id,
        "sender": sender,
        "timestamp": now,
        "text": str(message_data.get("text", "")),
        "countermeasures": list(message_data.get("countermeasures", [])),
        "nasa_references": list(message_data.get("nasa_references", [])),
    }

    session_ref = db.collection("chat_sessions").document(session_id)
    session_ref.set(
        {
            "session_id": session_id,
            "astronaut_id": message_data.get("astronaut_id", session_id.split("_")[0]),
            "updated_at": now,
            "last_message_preview": payload["text"][:120],
        },
        merge=True,
    )

    session_ref.collection("messages").document(message_id).set(payload)
    return payload


def get_chat_history(session_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve chronological conversation history from `chat_sessions/{session_id}/messages`.
    """
    messages_ref = (
        db.collection("chat_sessions")
        .document(session_id)
        .collection("messages")
        .order_by("timestamp", direction=firestore.Query.ASCENDING)
    )
    docs = messages_ref.stream()
    history: List[Dict[str, Any]] = []
    for doc in docs:
        msg = doc.to_dict() or {}
        msg.setdefault("message_id", doc.id)
        history.append(msg)
    return history


# =====================================================================
# 5. EMERGENCY ESCALATIONS (`emergency_escalations/{astroId}_escalation`)
# =====================================================================

def set_escalation_status(
    astro_id: str,
    state: str,
    recipient_crew_id: Optional[str] = None,
    countdown_seconds_remaining: Optional[int] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create or update the Intra-Crew Dead-Man's Switch record at
    `emergency_escalations/{astro_id}_escalation`.

    Allowed `state` values: "PENDING_ACK" | "ACKNOWLEDGED" | "TRIGGERED"
    """
    normalized_state = state.upper()
    if normalized_state not in ("PENDING_ACK", "ACKNOWLEDGED", "TRIGGERED"):
        raise ValueError(
            f"Invalid escalation_state '{state}'. Must be PENDING_ACK, ACKNOWLEDGED, or TRIGGERED."
        )

    doc_id = f"{astro_id}_escalation"
    doc_ref = db.collection("emergency_escalations").document(doc_id)
    snapshot = doc_ref.get()
    existing = snapshot.to_dict() if snapshot.exists else {}

    if countdown_seconds_remaining is None:
        if normalized_state in ("ACKNOWLEDGED", "TRIGGERED"):
            countdown_seconds_remaining = 0
        else:
            countdown_seconds_remaining = int(existing.get("countdown_seconds_remaining", 180))

    payload: Dict[str, Any] = {
        "astronaut_id": astro_id,
        "recipient_crew_id": recipient_crew_id or existing.get("recipient_crew_id", "ASTRO-02"),
        "alert_level": str(existing.get("alert_level", "CODE_RED_UNRESPONSIVE")),
        "countdown_seconds_remaining": int(countdown_seconds_remaining),
        "escalation_state": normalized_state,
        "reason": reason or existing.get(
            "reason",
            "Unacknowledged critical biometric threshold breach during autonomous monitoring.",
        ),
        "updated_at": _utc_now(),
    }

    doc_ref.set(payload, merge=True)
    return {"id": doc_id, **payload}


# =====================================================================
# 6. HEALTH PREDICTIONS (`health_predictions/{astroId}_trajectory`)
# =====================================================================

def save_prediction_trajectory(astro_id: str, trajectory_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a 7-day vital degradation and cognitive strain forecast to
    `health_predictions/{astro_id}_trajectory`.
    """
    doc_id = f"{astro_id}_trajectory"
    payload: Dict[str, Any] = {
        "astronaut_id": astro_id,
        "generated_at": trajectory_data.get("generated_at") or _utc_now(),
        "prediction_window_days": int(trajectory_data.get("prediction_window_days", 7)),
        "projected_dates": list(trajectory_data.get("projected_dates", [])),
        "projected_risk_scores": [
            round(float(score), 2) for score in trajectory_data.get("projected_risk_scores", [])
        ],
        "dominant_risk": str(trajectory_data.get("dominant_risk", "SPACE_RADIATION_SPE")),
        "clinical_warning": str(trajectory_data.get("clinical_warning", "")),
    }

    db.collection("health_predictions").document(doc_id).set(payload)
    return {"id": doc_id, **payload}


# =====================================================================
# ADDITIONAL CREW & DASHBOARD QUERY HELPERS
# =====================================================================

def get_astronaut_profile(astro_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single astronaut profile document from `astronauts/{astro_id}`."""
    doc = db.collection("astronauts").document(astro_id).get()
    return doc.to_dict() if doc.exists else None


def get_all_astronauts() -> List[Dict[str, Any]]:
    """Retrieve all crew profiles from the `astronauts` collection."""
    return [doc.to_dict() for doc in db.collection("astronauts").stream() if doc.exists]


def get_active_triage_alerts(astro_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve active clinical triage alerts, optionally filtered by astronaut ID."""
    query = db.collection("triage_alerts").where(filter=FieldFilter("status", "==", "ACTIVE"))
    if astro_id:
        query = query.where(filter=FieldFilter("astronaut_id", "==", astro_id))
    return [doc.to_dict() for doc in query.stream() if doc.exists]
