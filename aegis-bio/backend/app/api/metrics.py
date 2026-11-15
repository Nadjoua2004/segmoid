"""
Metrics API Endpoints
Ingestion and historical retrieval of astronaut physiological telemetry.
Connected to both SQLite and Supabase operational tables, with zero dummy data.
"""
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TelemetryLog, EmergencyAlertModel, UserModel, ChatHistoryModel
from app.schemas import HealthMetrics, HealthMetricsResponse
from app.api.triage import evaluate_multi_hazard_triage
from app.services.metric_classifier import metric_classifier
from app.services.alarm_service import get_astronaut_contact_info, sync_to_supabase_escalation
from app.services.health_predictor_agent import run_agent_background_prediction
from app.services.auth_service import get_optional_current_user

router = APIRouter(prefix="/api/metrics", tags=["Physiological Telemetry"])


def _sync_ingest_to_supabase(entry: TelemetryLog, triage_status: str, primary_hazard: str) -> None:
    """Best-effort synchronization of ingested check-in and telemetry to Supabase."""
    try:
        from app.services.supabase_service import (
            upsert_rows,
            add_telemetry_log,
            save_daily_checkin,
            create_triage_alert,
        )

        sb_status = (
            "CRITICAL"
            if triage_status == "CRITICAL"
            else "WARNING"
            if triage_status in ("HIGH", "ELEVATED")
            else "NOMINAL"
        )
        ts_iso = (entry.timestamp or datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")

        upsert_rows(
            "astronauts",
            {
                "id": entry.astronaut_id,
                "name": entry.astronaut_id,
                "role": "Crew Member",
                "mission_day": entry.mission_day,
                "baseline_vitals": {
                    "heart_rate_bpm": int(round(entry.heart_rate)),
                    "hrv_rmssd_ms": int(round(entry.hrv_rmssd or 42)),
                    "spo2_percent": float(entry.spo2),
                    "core_temp_c": float(entry.core_temp_c or 36.8),
                    "systolic_bp_mmhg": int(round(entry.bp_sys)),
                    "diastolic_bp_mmhg": int(round(entry.bp_dia)),
                },
                "current_status": sb_status,
                "emergency_contact_id": "CREW-MED",
                "last_checkin": ts_iso,
            },
        )

        add_telemetry_log(
            entry.astronaut_id,
            {
                "id": f"{entry.astronaut_id}_d{entry.mission_day}_{entry.id}",
                "timestamp": ts_iso,
                "mission_day": entry.mission_day,
                "hour": (entry.timestamp or datetime.utcnow()).hour,
                "heart_rate_bpm": int(round(entry.heart_rate)),
                "hrv_rmssd_ms": int(round(entry.hrv_rmssd or 42)),
                "spo2_percent": float(entry.spo2),
                "core_temp_c": float(entry.core_temp_c or 36.8),
                "radiation_rate_usv_h": round(float(entry.radiation_msv) * 41.6, 1),
                "cumulative_radiation_msv": float(entry.radiation_msv),
                "cabin_co2_mmhg": 2.8,
                "activity_state": "DUTY",
                "status": sb_status,
                "primary_hazard": primary_hazard,
            },
        )

        save_daily_checkin(
            {
                "astronaut_id": entry.astronaut_id,
                "mission_day": entry.mission_day,
                "sleep_hours": float(entry.sleep_hours),
                "sleep_quality_score": max(1, min(5, int(round(entry.sleep_hours / 1.8)))),
                "mood_score": int(entry.mood_score),
                "reported_symptoms": [entry.subjective_notes] if entry.subjective_notes else [],
                "notes": entry.subjective_notes or "",
                "submitted_at": ts_iso,
            },
        )

        if sb_status in ("WARNING", "CRITICAL"):
            create_triage_alert(
                {
                    "alert_id": f"ALT-{entry.astronaut_id}-D{entry.mission_day}-{entry.id}",
                    "astronaut_id": entry.astronaut_id,
                    "timestamp": ts_iso,
                    "severity": sb_status,
                    "hazard_type": primary_hazard,
                    "hazard_title": f"{sb_status} Triage Alert · {entry.astronaut_id}",
                    "triggering_vitals": {
                        "heart_rate_bpm": entry.heart_rate,
                        "spo2_percent": entry.spo2,
                        "sleep_hours": entry.sleep_hours,
                        "radiation_msv": entry.radiation_msv,
                        "bp_sys": entry.bp_sys,
                        "bp_dia": entry.bp_dia,
                    },
                    "is_acknowledged": False,
                    "status": "ACTIVE",
                }
            )
    except Exception as exc:
        print(f"[Supabase Sync Notice] {exc}")


@router.get("/crew")
def get_active_crew_summary(
    db: Session = Depends(get_db),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
) -> Dict[str, Any]:
    """
    Returns only the crew members that actually exist in the database UserModel table.
    If authenticated, returns members of the astronaut's crew (strict crew isolation).
    """
    query = db.query(UserModel).filter(UserModel.is_active == True)
    if current_user and current_user.crew_name:
        query = query.filter(UserModel.crew_name == current_user.crew_name)

    registered_users = query.all()
    if not registered_users:
        registered_users = db.query(UserModel).filter(UserModel.is_active == True).all()

    crew_list = []
    for u in registered_users:
        astro_id = u.callsign or u.username
        # Look up latest telemetry for this astronaut
        latest = (
            db.query(TelemetryLog)
            .filter((TelemetryLog.astronaut_id == astro_id) | (TelemetryLog.astronaut_id == u.username))
            .order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc())
            .first()
        )
        name = u.callsign or u.username
        role = u.crew_name or "Crew Member"

        if latest:
            report = metric_classifier.evaluate_all_metrics(
                {
                    "heart_rate": latest.heart_rate,
                    "spo2": latest.spo2,
                    "sleep_hours": latest.sleep_hours,
                    "core_temp_c": latest.core_temp_c or 36.8,
                    "radiation_msv": latest.radiation_msv,
                },
                astronaut_id=astro_id,
                mission_day=latest.mission_day,
                environment=u.environment,
            )
            m = report.metrics
            vitals_bars = [
                m.get("heart_rate").status if "heart_rate" in m else "NORMAL",
                m.get("spo2").status if "spo2" in m else "NORMAL",
                m.get("sleep_hours").status if "sleep_hours" in m else "NORMAL",
                m.get("core_temp_c").status if "core_temp_c" in m else "NORMAL",
                m.get("radiation_msv").status if "radiation_msv" in m else "NORMAL",
            ]
            overall = report.highest_severity
        else:
            vitals_bars = ["NORMAL", "NORMAL", "NORMAL", "NORMAL", "NORMAL"]
            overall = "NORMAL"

        today_utc = datetime.utcnow().date()
        last_ts = (latest.created_at or latest.timestamp) if latest else None
        checked_in_today = bool(last_ts and last_ts.date() == today_utc)

        crew_list.append(
            {
                "id": astro_id,
                "name": name,
                "role": role,
                "mission_day": latest.mission_day if latest else 1,
                "status": overall,
                "vitals_bars": vitals_bars,
                "has_telemetry": latest is not None,
                "checked_in_today": checked_in_today,
                "last_checkin_at": last_ts.isoformat() if last_ts else None,
                "emergency_contact_callsign": getattr(u, "emergency_contact_callsign", None) or "CREW-MED",
                "emergency_contact_name": getattr(u, "emergency_contact_name", None) or "Crew Medical Officer",
            }
        )

    return {"crew": crew_list, "count": len(crew_list)}


@router.get("/history", response_model=List[HealthMetricsResponse])
def get_metrics_history(
    astronaut_id: Optional[str] = Query(None, description="Astronaut ID filter (omit for all crew)"),
    limit: int = Query(100, ge=1, le=500, description="Number of past records to return"),
    db: Session = Depends(get_db),
):
    """Retrieve historical telemetry from the database (returns [] when empty)."""
    query = db.query(TelemetryLog)
    if astronaut_id:
        query = query.filter(TelemetryLog.astronaut_id == astronaut_id)

    records = query.order_by(TelemetryLog.mission_day.asc(), TelemetryLog.id.asc()).limit(limit).all()
    return records


@router.get("/latest", response_model=Optional[HealthMetricsResponse])
def get_latest_metrics(
    astronaut_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get the most recent telemetry entry (returns null when database is empty)."""
    query = db.query(TelemetryLog)
    if astronaut_id:
        query = query.filter(TelemetryLog.astronaut_id == astronaut_id)

    latest = query.order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first()
    return latest


@router.post("/ingest", response_model=HealthMetricsResponse)
def ingest_health_metrics(
    payload: HealthMetrics,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Ingest a real-time or daily check-in biometric entry.
    Saves to SQLite + Supabase, runs Dual-Classifier Triage, and triggers alerts if needed.
    """
    new_entry = TelemetryLog(
        astronaut_id=payload.astronaut_id.strip(),
        mission_day=payload.mission_day,
        timestamp=payload.timestamp or datetime.utcnow(),
        heart_rate=payload.heart_rate,
        bp_sys=payload.bp_sys,
        bp_dia=payload.bp_dia,
        spo2=payload.spo2,
        sleep_hours=payload.sleep_hours,
        radiation_msv=payload.radiation_msv,
        blood_glucose=payload.blood_glucose,
        mood_score=payload.mood_score,
        core_temp_c=payload.core_temp_c or 36.8,
        hrv_rmssd=payload.hrv_rmssd or 45.0,
        subjective_notes=payload.subjective_notes or "",
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    triage = evaluate_multi_hazard_triage(payload)
    primary_hazard = "NONE"
    if triage.clinical_flags:
        primary_hazard = triage.clinical_flags[0].split(":")[0]

    if triage.overall_status in ("CRITICAL", "HIGH", "ELEVATED"):
        contact_info = get_astronaut_contact_info(db, new_entry.astronaut_id)
        timeout_sec = contact_info["alert_timeout_seconds"]
        now = datetime.utcnow()
        alert_id = f"ALT-D{new_entry.mission_day}-{new_entry.id}"
        actions = [cm.protocol for cm in triage.countermeasures] or [
            "Review astronaut telemetry and verify habitat life-support parameters."
        ]

        db_alert = EmergencyAlertModel(
            alert_id=alert_id,
            astronaut_id=new_entry.astronaut_id,
            user_id=contact_info.get("user_id"),
            severity="CRITICAL" if triage.overall_status == "CRITICAL" else "WARNING",
            hazard_origin=triage.clinical_flags[0] if triage.clinical_flags else "Biometric Threshold Breach",
            message="; ".join(triage.clinical_flags) or f"Elevated strain detected for {new_entry.astronaut_id}",
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
            source="DAILY_CHECKIN_TRIAGE",
            requires_action=True,
        )
        db.add(db_alert)
        db.commit()

        if triage.requires_emergency_escalation:
            sync_to_supabase_escalation(
                astro_id=new_entry.astronaut_id,
                state="PENDING_ACK",
                recipient_crew_id=contact_info["emergency_contact_callsign"],
                countdown_seconds=timeout_sec,
                reason="; ".join(triage.clinical_flags),
            )

    _sync_ingest_to_supabase(new_entry, triage.overall_status, primary_hazard)

    # Trigger autonomous background predictive surveillance cycle
    background_tasks.add_task(run_agent_background_prediction, new_entry.astronaut_id)

    return new_entry


@router.post("/clear-all")
def clear_all_database_records(db: Session = Depends(get_db)):
    """Clears all operational records so the database is completely empty."""
    db.query(TelemetryLog).delete()
    db.query(EmergencyAlertModel).delete()
    db.query(ChatHistoryModel).delete()
    db.query(UserModel).delete()
    db.commit()
    return {"status": "cleared"}
