"""
Predictive Trajectory API
Calculates 7-day trend regression and strain scores from historical telemetry.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TelemetryLog
from app.schemas import PredictionResult
from app.services.predictor import calculate_trajectory_forecast
from app.services.seeder import seed_initial_telemetry
from app.services.alarm_service import create_alarm_from_prediction

router = APIRouter(prefix="/api/predict", tags=["Predictive Forecasting"])

@router.post("/trajectory", response_model=Optional[PredictionResult])
def predict_7_day_trajectory(
    astronaut_id: Optional[str] = Query(None),
    time_scale: str = Query("WEEKLY", description="DAILY (24-hour intra-sol), WEEKLY (7-day tactical), or MONTHLY (30-day mission)"),
    horizon_days: int = Query(7, ge=1, le=30, description="Forecast steps: 24 for Daily, 7 for Weekly, 30 for Monthly"),
    lookback_days: int = Query(30, ge=1, le=180, description="Historical telemetry window"),
    db: Session = Depends(get_db)
):
    """
    Computes Daily (24h), Weekly (7d), or Monthly (30d) forward trajectory
    using optimized Holt-Winters Damped Time-Series models on historical telemetry logs.
    Identifies early inflection points and upcoming anomalies before they occur.
    """
    query = db.query(TelemetryLog)
    if astronaut_id:
        query = query.filter(TelemetryLog.astronaut_id == astronaut_id)

    records = query.order_by(TelemetryLog.mission_day.asc()).all()
    if not records:
        return None

    records = records[-lookback_days:]
    
    history = [
        {
            "mission_day": r.mission_day,
            "heart_rate": r.heart_rate,
            "bp_sys": r.bp_sys,
            "bp_dia": r.bp_dia,
            "spo2": r.spo2,
            "sleep_hours": r.sleep_hours,
            "radiation_msv": r.radiation_msv,
            "blood_glucose": r.blood_glucose,
            "mood_score": r.mood_score,
            "hrv_rmssd": r.hrv_rmssd or 42.0
        }
        for r in records
    ]
    
    result = calculate_trajectory_forecast(
        history_records=history,
        astronaut_id=astronaut_id,
        horizon_days=horizon_days,
        time_scale=time_scale
    )

    # Check if regression indicates critical strain / dangerous threshold
    if result.cardiovascular_strain_score >= 65.0 or result.cognitive_degradation_risk >= 75.0 or result.critical_inflection_day is not None:
        prediction_dict = {
            "health_outlook": "CRITICAL_DRIFT" if result.critical_inflection_day else "ELEVATED_STRAIN",
            "cardiovascular_strain_score": result.cardiovascular_strain_score,
            "cognitive_fatigue_risk": result.cognitive_degradation_risk,
            "hypoxia_eclss_risk": 0.0,
            "radiation_hazard_index": 0.0,
            "projected_trajectory": [
                {
                    "sol": p.day,
                    "sol_label": f"Sol {p.day}",
                    "status": "CRITICAL" if p.cardiovascular_strain_index >= 65.0 else "NORMAL"
                }
                for p in result.projected_trajectory
            ],
            "clinical_directives": [
                {
                    "category": "Vital Trend Alert",
                    "urgency": "IMMEDIATE",
                    "action": f"Critical inflection projected at Sol {result.critical_inflection_day}. Initiate medical review.",
                    "reference": "NASA SP-2009-3405"
                }
            ] if result.critical_inflection_day else []
        }
        create_alarm_from_prediction(db, astronaut_id or "ASTRO-7702-HELENA", prediction_dict)

    return result
