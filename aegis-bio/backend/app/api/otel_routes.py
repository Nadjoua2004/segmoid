"""
OpenTelemetry & Weekly Telemetry API Routes
Provides endpoints for crew profiles, weekly sliding window telemetry,
OpenTelemetry ResourceMetrics formatted export, and Health Predictor Agent forecasts.
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.data_loader import data_loader
from app.services.otel_collector import otel_collector
from app.services.health_predictor_agent import health_predictor_agent
from app.services.alarm_service import create_alarm_from_prediction, model_to_emergency_alert_schema

router = APIRouter(prefix="/api/otel", tags=["OpenTelemetry & Weekly Health"])

@router.get("/crew")
def get_crew_list():
    """Returns all available astronauts from the deep space telemetry dataset."""
    members = data_loader.get_crew_members()
    if not members:
        raise HTTPException(status_code=503, detail="Telemetry dataset not loaded.")
    return {"crew": members, "count": len(members)}

@router.get("/week/{astronaut_id}/{week_number}")
def get_weekly_metrics(astronaut_id: str, week_number: int):
    """
    Returns weekly sliding window telemetry for the specified astronaut.
    Resets every 7 sols (e.g. Week 1 = Sol 1-7, Week 2 = Sol 8-14).
    Contains:
      - Continuous Hourly Vitals (for Line Chart)
      - Ship Environment Metrics (for Area Chart)
      - Health Status Distribution (for Donut/Pie Chart)
      - Stress vs Sleep Recovery (for Grouped Bar Chart)
      - OpenTelemetry ResourceMetrics Data
    """
    weekly_data = data_loader.get_weekly_telemetry(astronaut_id, week_number)
    if not weekly_data:
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry not found for astronaut {astronaut_id} on week {week_number}."
        )

    # Attach OpenTelemetry standard metric formatting
    otel_formatted = otel_collector.format_otel_metrics(weekly_data)
    weekly_data["otel_telemetry"] = otel_formatted

    return weekly_data

@router.post("/predict")
def predict_upcoming_health(
    astronaut_id: str = Query("ASTRO-01"),
    week_number: int = Query(1),
    forecast_days: int = Query(7, ge=1, le=14),
    db: Session = Depends(get_db)
):
    """
    Health Predictor Agent:
    Ingests 7-day historical telemetry + spacecraft environment (stress, oxygen, CO2, radiation).
    Projects the upcoming 7 days of astronaut health and risk outlook.
    If the agent predicts a dangerous or critical condition that requires action,
    it autonomously creates and sends an intra-crew alarm with a dead-man's switch
    that will escalate to the chosen emergency contact if not answered in time.
    """
    weekly_data = data_loader.get_weekly_telemetry(astronaut_id, week_number)
    if not weekly_data:
        raise HTTPException(
            status_code=404,
            detail=f"Cannot run predictor: telemetry not found for astronaut {astronaut_id} on week {week_number}."
        )

    prediction = health_predictor_agent.predict_upcoming_health(weekly_data, forecast_days)

    # Autonomous Alarm Dispatch on Dangerous/Critical Prediction
    alarm = create_alarm_from_prediction(db, astronaut_id, prediction)
    if alarm:
        prediction["alarm_triggered"] = True
        prediction["alarm_id"] = alarm.alert_id
        prediction["alarm_details"] = model_to_emergency_alert_schema(alarm).model_dump()
    else:
        prediction["alarm_triggered"] = False
        prediction["alarm_id"] = None
        prediction["alarm_details"] = None

    return prediction

@router.post("/ingest", summary="OpenTelemetry Metrics Receiver")
def ingest_otel_metrics(payload: Dict[str, Any] = Body(...)):
    """
    Standard OpenTelemetry HTTP collector endpoint for incoming metric spans.
    """
    otel_collector.ingested_spans_count += 1
    return {
        "status": "ACCEPTED",
        "protocol": "OTLP/HTTP v1",
        "processed_spans": otel_collector.ingested_spans_count
    }
