"""
Metrics API Endpoints
Ingestion and historical retrieval of astronaut physiological telemetry.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models import TelemetryLog
from app.schemas import HealthMetrics, HealthMetricsResponse
from app.services.seeder import seed_initial_telemetry

router = APIRouter(prefix="/api/metrics", tags=["Physiological Telemetry"])

@router.on_event("startup")
def verify_seeded_data_on_startup():
    """Ensure seeded 30-day telemetry exists on application launch."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        seed_initial_telemetry(db)
    finally:
        db.close()

@router.get("/history", response_model=List[HealthMetricsResponse])
def get_metrics_history(
    astronaut_id: Optional[str] = Query("ASTRO-7702-HELENA", description="Astronaut ID filter"),
    limit: int = Query(50, ge=1, le=365, description="Number of past records to return"),
    db: Session = Depends(get_db)
):
    """
    Retrieve historical telemetry. If database is unseeded, automatically seeds
    30 days of realistic Artemis mission telemetry so frontend displays rich charts immediately.
    """
    count = db.query(TelemetryLog).count()
    if count == 0:
        seed_initial_telemetry(db)

    query = db.query(TelemetryLog)
    if astronaut_id:
        query = query.filter(TelemetryLog.astronaut_id == astronaut_id)
        
    records = query.order_by(TelemetryLog.mission_day.asc()).limit(limit).all()
    return records

@router.get("/latest", response_model=HealthMetricsResponse)
def get_latest_metrics(
    astronaut_id: Optional[str] = Query("ASTRO-7702-HELENA"),
    db: Session = Depends(get_db)
):
    """Get the most recent telemetry entry for the astronaut."""
    count = db.query(TelemetryLog).count()
    if count == 0:
        seed_initial_telemetry(db)

    query = db.query(TelemetryLog)
    if astronaut_id:
        query = query.filter(TelemetryLog.astronaut_id == astronaut_id)
        
    latest = query.order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No telemetry records found.")
    return latest

@router.post("/ingest", response_model=HealthMetricsResponse)
def ingest_health_metrics(
    payload: HealthMetrics,
    db: Session = Depends(get_db)
):
    """
    Ingest a new real-time or daily self-check-in biometric entry.
    Saves to SQLite store and returns persisted record.
    """
    new_entry = TelemetryLog(
        astronaut_id=payload.astronaut_id,
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
        core_temp_c=payload.core_temp_c or 36.9,
        hrv_rmssd=payload.hrv_rmssd or 42.0,
        subjective_notes=payload.subjective_notes or ""
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    return new_entry

@router.post("/reset-seed")
def reset_seed_data(db: Session = Depends(get_db)):
    """Force re-seeds the 30-day baseline data."""
    db.query(TelemetryLog).delete()
    db.commit()
    count = seed_initial_telemetry(db, force=True)
    return {"status": "success", "message": f"Successfully reseeded {count} telemetry logs."}
