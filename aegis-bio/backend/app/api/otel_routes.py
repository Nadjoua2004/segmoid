"""
OpenTelemetry & Weekly Telemetry API Routes
Provides endpoints for crew profiles, weekly sliding window telemetry,
OpenTelemetry ResourceMetrics formatted export, and Health Predictor Agent forecasts.
"""
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body

from app.services.data_loader import data_loader
from app.services.otel_collector import otel_collector
from app.services.health_predictor_agent import health_predictor_agent

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
    forecast_days: int = Query(7, ge=1, le=14)
):
    """
    Health Predictor Agent:
    Ingests 7-day historical telemetry + spacecraft environment (stress, oxygen, CO2, radiation).
    Projects the upcoming 7 days of astronaut health and risk outlook.
    """
    weekly_data = data_loader.get_weekly_telemetry(astronaut_id, week_number)
    if not weekly_data:
        raise HTTPException(
            status_code=404,
            detail=f"Cannot run predictor: telemetry not found for astronaut {astronaut_id} on week {week_number}."
        )

    prediction = health_predictor_agent.predict_upcoming_health(weekly_data, forecast_days)
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
