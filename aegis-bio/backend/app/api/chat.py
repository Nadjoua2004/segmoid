"""
Clinical Chat & Flight Surgeon RAG API
Provides interactive queries and proactive autonomous flight surgeon recommendations.
"""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TelemetryLog, ChatHistoryModel
from app.schemas import ChatQuery, ChatMessage, ProactiveChatPayload
from app.services.ai_agent import ai_agent_service
from app.api.triage import evaluate_multi_hazard_triage
from app.schemas import HealthMetrics

router = APIRouter(prefix="/api/chat", tags=["AI Clinical Flight Surgeon"])

@router.post("/query", response_model=ChatMessage)
def query_flight_surgeon(payload: ChatQuery, db: Session = Depends(get_db)):
    """
    Submits a query to the onboard RAG Flight Surgeon agent.
    Grounds answers in NASA Human Research Program (HRP) guidelines and current astronaut telemetry.
    """
    context_vitals = None
    if payload.include_current_vitals:
        latest = db.query(TelemetryLog).filter(
            TelemetryLog.astronaut_id == payload.astronaut_id
        ).order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first()
        
        if latest:
            context_vitals = {
                "heart_rate": latest.heart_rate,
                "bp_sys": latest.bp_sys,
                "bp_dia": latest.bp_dia,
                "spo2": latest.spo2,
                "sleep_hours": latest.sleep_hours,
                "radiation_msv": latest.radiation_msv,
                "mood_score": latest.mood_score
            }

    # Record user message
    user_record = ChatHistoryModel(
        astronaut_id=payload.astronaut_id,
        role="user",
        content=payload.query
    )
    db.add(user_record)

    # Generate response
    result = ai_agent_service.answer_query(payload.query, context_vitals, payload.astronaut_id)

    # Record assistant message
    asst_record = ChatHistoryModel(
        astronaut_id=payload.astronaut_id,
        role="assistant",
        content=result["answer"],
        citations="; ".join(result["citations"])
    )
    db.add(asst_record)
    db.commit()

    return ChatMessage(
        role="assistant",
        content=result["answer"],
        citations=result["citations"]
    )

@router.get("/history")
def get_chat_history_records(
    astronaut_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Returns real recorded chat messages from the database."""
    query = db.query(ChatHistoryModel)
    if astronaut_id:
        query = query.filter(ChatHistoryModel.astronaut_id == astronaut_id)
    rows = query.order_by(ChatHistoryModel.timestamp.asc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "astronaut_id": r.astronaut_id,
            "role": r.role,
            "content": r.content,
            "citations": r.citations.split("; ") if r.citations else [],
            "timestamp": r.timestamp,
        }
        for r in rows
    ]

@router.post("/proactive", response_model=ProactiveChatPayload)
def get_proactive_clinical_dialogue(
    astronaut_id: Optional[str] = "ASTRO-7702-HELENA",
    db: Session = Depends(get_db)
):
    """
    Generates autonomous proactive clinical dialogue based on current telemetry triage.
    Simulates the AI Flight Surgeon initiating check-in when physiological strain is detected.
    """
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
        triage_dict = {
            "astronaut_id": triage.astronaut_id,
            "overall_status": triage.overall_status,
            "clinical_flags": triage.clinical_flags
        }
    else:
        triage_dict = {"astronaut_id": astronaut_id, "overall_status": "NOMINAL", "clinical_flags": []}

    alert_data = ai_agent_service.generate_proactive_alert(triage_dict)
    return ProactiveChatPayload(**alert_data)
