"""
Supabase Operational Database Service Layer for Aegis-Bio.

Provides clean, typed helper functions for FastAPI routes backed by Supabase PostgreSQL:
- add_telemetry_log(astro_id: str, data: dict)
- get_recent_telemetry(astro_id: str, limit: int = 48)
- save_daily_checkin(checkin_data: dict)
- create_triage_alert(alert_data: dict)
- acknowledge_triage_alert(alert_id: str)
- log_chat_message(session_id: str, message_data: dict)
- get_chat_history(session_id: str)
- set_escalation_status(astro_id: str, state: str)
- save_prediction_trajectory(astro_id: str, trajectory_data: dict)
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import uuid

from app.supabase_config import REST_V1_URL, get_supabase_headers, session


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_rows(table: str, rows: Union[Dict[str, Any], List[Dict[str, Any]]], on_conflict: Optional[str] = None) -> List[Dict[str, Any]]:
    """Upsert one or more rows into a Supabase table via PostgREST."""
    try:
        conflict_col = on_conflict or ("alert_id" if table == "triage_alerts" else ("session_id" if table == "chat_sessions" else ("message_id" if table == "chat_messages" else "id")))
        resp = session.post(
            f"{REST_V1_URL}/{table}?on_conflict={conflict_col}",
            headers=get_supabase_headers("return=representation,resolution=merge-duplicates"),
            json=rows,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]
    except Exception as e:
        print(f"[Supabase Upsert Warning] table={table}: {e}")
        return []


def update_rows(table: str, match_params: Dict[str, str], updates: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Update matching rows in a Supabase table."""
    try:
        resp = session.patch(
            f"{REST_V1_URL}/{table}",
            headers=get_supabase_headers("return=representation"),
            params=match_params,
            json=updates,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]
    except Exception as e:
        print(f"[Supabase Update Warning] table={table}: {e}")
        return []


def select_rows(table: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Query rows from a Supabase table."""
    try:
        resp = session.get(
            f"{REST_V1_URL}/{table}",
            headers=get_supabase_headers("return=representation"),
            params=params or {},
            timeout=5,
        )
        resp.raise_for_status()
        return list(resp.json() or [])
    except Exception as e:
        print(f"[Supabase Select Warning] table={table}: {e}")
        return []


# =====================================================================
# 1. ASTRONAUTS & TELEMETRY LOGS
# =====================================================================

def add_telemetry_log(astro_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a telemetry row into `telemetry_logs` and synchronize `astronauts` status."""
    now_iso = _utc_now_iso()
    mission_day = int(data.get("mission_day", 112))
    hour = int(data.get("hour", 0))
    status = str(data.get("status", "NOMINAL")).upper()
    doc_id = str(data.get("id") or data.get("doc_id") or f"{astro_id}_day_{mission_day:03d}_hr_{hour:02d}")

    payload: Dict[str, Any] = {
        "id": doc_id,
        "astronaut_id": astro_id,
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

    upsert_rows("telemetry_logs", payload)
    update_rows("astronauts", {"id": f"eq.{astro_id}"}, {"mission_day": mission_day, "current_status": status})
    return payload


def get_recent_telemetry(astro_id: str, limit: int = 48) -> List[Dict[str, Any]]:
    """Fetch the most recent `limit` telemetry logs for an astronaut in chronological order."""
    records = select_rows(
        "telemetry_logs",
        {
            "astronaut_id": f"eq.{astro_id}",
            "order": "timestamp.desc",
            "limit": str(limit),
        },
    )
    records.reverse()
    return records


# =====================================================================
# 2. DAILY CHECK-INS
# =====================================================================

def save_daily_checkin(checkin_data: Dict[str, Any]) -> Dict[str, Any]:
    """Save an astronaut's subjective daily check-in and update `astronauts.last_checkin`."""
    astro_id = str(checkin_data["astronaut_id"])
    mission_day = int(checkin_data["mission_day"])
    doc_id = f"{astro_id}_day_{mission_day}"
    submitted_at = str(checkin_data.get("submitted_at") or _utc_now_iso())

    payload: Dict[str, Any] = {
        "id": doc_id,
        "astronaut_id": astro_id,
        "mission_day": mission_day,
        "sleep_hours": float(checkin_data.get("sleep_hours", 6.5)),
        "sleep_quality_score": int(checkin_data.get("sleep_quality_score", 4)),
        "mood_score": int(checkin_data.get("mood_score", 4)),
        "reported_symptoms": list(checkin_data.get("reported_symptoms", [])),
        "notes": str(checkin_data.get("notes", "")),
        "submitted_at": submitted_at,
    }

    upsert_rows("daily_checkins", payload)
    update_rows("astronauts", {"id": f"eq.{astro_id}"}, {"last_checkin": submitted_at, "mission_day": mission_day})
    return payload


# =====================================================================
# 3. TRIAGE ALERTS
# =====================================================================

def create_triage_alert(alert_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a real-time clinical triage alert in `triage_alerts`."""
    alert_id = str(alert_data.get("alert_id") or f"ALT-{uuid.uuid4().hex[:8].upper()}")
    astro_id = str(alert_data["astronaut_id"])
    severity = str(alert_data.get("severity", "WARNING")).upper()
    is_acknowledged = bool(alert_data.get("is_acknowledged", False))
    status = str(alert_data.get("status", "ACKNOWLEDGED" if is_acknowledged else "ACTIVE")).upper()

    payload: Dict[str, Any] = {
        "alert_id": alert_id,
        "astronaut_id": astro_id,
        "timestamp": str(alert_data.get("timestamp") or _utc_now_iso()),
        "severity": severity,
        "hazard_type": str(alert_data.get("hazard_type", "SPACE_RADIATION_SPE")),
        "hazard_title": str(alert_data.get("hazard_title", "Clinical Anomaly Detected")),
        "triggering_vitals": dict(alert_data.get("triggering_vitals", {})),
        "is_acknowledged": is_acknowledged,
        "status": status,
    }

    upsert_rows("triage_alerts", payload)
    if status == "ACTIVE" and severity in ("WARNING", "CRITICAL"):
        update_rows("astronauts", {"id": f"eq.{astro_id}"}, {"current_status": severity})
    return payload


def acknowledge_triage_alert(alert_id: str) -> Dict[str, Any]:
    """Acknowledge a triage alert (`is_acknowledged=True`, `status='ACKNOWLEDGED'`)."""
    updated = update_rows(
        "triage_alerts",
        {"alert_id": f"eq.{alert_id}"},
        {"is_acknowledged": True, "status": "ACKNOWLEDGED"},
    )
    return updated[0] if updated else {"alert_id": alert_id, "is_acknowledged": True, "status": "ACKNOWLEDGED"}


# =====================================================================
# 4. CHAT SESSIONS & MESSAGES
# =====================================================================

def log_chat_message(session_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """Store a chat message in `chat_sessions` and `chat_messages`."""
    now_iso = str(message_data.get("timestamp") or _utc_now_iso())
    message_id = str(message_data.get("message_id") or f"MSG-{uuid.uuid4().hex[:8].upper()}")
    astro_id = str(message_data.get("astronaut_id") or session_id.split("_")[0])
    text = str(message_data.get("text", ""))

    upsert_rows(
        "chat_sessions",
        {
            "session_id": session_id,
            "astronaut_id": astro_id,
            "updated_at": now_iso,
            "last_message_preview": text[:120],
        },
    )

    payload: Dict[str, Any] = {
        "message_id": message_id,
        "session_id": session_id,
        "sender": str(message_data.get("sender", "astronaut")),
        "timestamp": now_iso,
        "text": text,
        "countermeasures": list(message_data.get("countermeasures", [])),
        "nasa_references": list(message_data.get("nasa_references", [])),
    }

    upsert_rows("chat_messages", payload)
    return payload


def get_chat_history(session_id: str) -> List[Dict[str, Any]]:
    """Retrieve chronological conversation history for `session_id`."""
    return select_rows(
        "chat_messages",
        {
            "session_id": f"eq.{session_id}",
            "order": "timestamp.asc",
        },
    )


# =====================================================================
# 5. EMERGENCY ESCALATIONS
# =====================================================================

def set_escalation_status(
    astro_id: str,
    state: str,
    recipient_crew_id: Optional[str] = None,
    countdown_seconds_remaining: Optional[int] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update the Intra-Crew Dead-Man's Switch record in `emergency_escalations`."""
    normalized_state = state.upper()
    doc_id = f"{astro_id}_escalation"

    if countdown_seconds_remaining is None:
        countdown_seconds_remaining = 0 if normalized_state in ("ACKNOWLEDGED", "TRIGGERED") else 180

    payload: Dict[str, Any] = {
        "id": doc_id,
        "astronaut_id": astro_id,
        "recipient_crew_id": recipient_crew_id or "ASTRO-02",
        "alert_level": "CODE_RED_UNRESPONSIVE",
        "countdown_seconds_remaining": int(countdown_seconds_remaining),
        "escalation_state": normalized_state,
        "reason": reason or "Unacknowledged critical biometric threshold breach during autonomous monitoring.",
        "updated_at": _utc_now_iso(),
    }

    upsert_rows("emergency_escalations", payload)
    return payload


# =====================================================================
# 6. HEALTH PREDICTIONS
# =====================================================================

def save_prediction_trajectory(astro_id: str, trajectory_data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a 7-day vital degradation and cognitive strain forecast in `health_predictions`."""
    doc_id = f"{astro_id}_trajectory"
    payload: Dict[str, Any] = {
        "id": doc_id,
        "astronaut_id": astro_id,
        "generated_at": str(trajectory_data.get("generated_at") or _utc_now_iso()),
        "prediction_window_days": int(trajectory_data.get("prediction_window_days", 7)),
        "projected_dates": list(trajectory_data.get("projected_dates", [])),
        "projected_risk_scores": [
            round(float(s), 2) for s in trajectory_data.get("projected_risk_scores", [])
        ],
        "dominant_risk": str(trajectory_data.get("dominant_risk", "SPACE_RADIATION_SPE")),
        "clinical_warning": str(trajectory_data.get("clinical_warning", "")),
    }

    upsert_rows("health_predictions", payload)
    return payload
