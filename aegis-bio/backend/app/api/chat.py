"""
Clinical Chat & Flight Surgeon RAG API
Provides interactive queries and proactive autonomous flight surgeon recommendations.
"""
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TelemetryLog, ChatHistoryModel, UserModel
from app.schemas import ChatQuery, ChatMessage, ProactiveChatPayload
from app.services.ai_agent import ai_agent_service
from app.services.auth_service import get_optional_current_user
from app.api.triage import evaluate_multi_hazard_triage
from app.schemas import HealthMetrics

router = APIRouter(prefix="/api/chat", tags=["AI Clinical Flight Surgeon"])


def _resolve_chat_owner(
    current_user: Optional[UserModel],
    fallback_astro_id: Optional[str] = None,
) -> Optional[str]:
    """Scope chat history strictly to the authenticated member's own identity."""
    if current_user is not None:
        return current_user.callsign or current_user.username
    cleaned = (fallback_astro_id or "").strip()
    return cleaned or None


HISTORY_TURNS = 6  # earlier messages given to the assistant so follow-up questions keep their context


def _recent_history(db: Session, chat_owner: str) -> list[dict]:
    rows = (
        db.query(ChatHistoryModel)
        .filter(ChatHistoryModel.astronaut_id == chat_owner)
        .order_by(ChatHistoryModel.timestamp.desc(), ChatHistoryModel.id.desc())
        .limit(HISTORY_TURNS)
        .all()
    )
    return [{"role": r.role, "content": r.content} for r in reversed(rows)
            if r.role in ("user", "assistant") and r.content]


@router.post("/query", response_model=ChatMessage)
def query_flight_surgeon(
    payload: ChatQuery,
    db: Session = Depends(get_db),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
):
    """
    Submits a query to the onboard RAG Flight Surgeon agent.
    Grounds answers in NASA Human Research Program (HRP) guidelines and current astronaut telemetry.
    Chat turns are isolated per member account.
    """
    return _answer_and_record(payload, db, current_user)


@router.post("/voice", response_model=ChatMessage)
def voice_query_flight_surgeon(
    audio: UploadFile = File(..., description="Recorded question (webm, ogg, wav, mp3, m4a)"),
    astronaut_id: str = Form("ASTRO-7702-HELENA"),
    include_current_vitals: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
):
    """
    Voice question: transcribed with open-source Whisper (AstroDoc speech-to-text), then answered
    and stored exactly like a typed question. The response includes `transcript`.
    """
    try:
        text = ai_agent_service.transcribe(audio.file.read(), audio.filename or "speech.webm", audio.content_type)
    except ai_agent_service.SpeechError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    payload = ChatQuery(query=text, astronaut_id=astronaut_id, include_current_vitals=include_current_vitals)
    message = _answer_and_record(payload, db, current_user)
    message.transcript = text
    return message


def _answer_and_record(payload: ChatQuery, db: Session, current_user: Optional[UserModel]) -> ChatMessage:
    chat_owner = _resolve_chat_owner(current_user, payload.astronaut_id) or payload.astronaut_id
    telemetry_target = (
        payload.astronaut_id
        if (current_user is None or current_user.is_lead)
        else chat_owner
    )

    context_vitals = None
    if payload.include_current_vitals and telemetry_target:
        latest = db.query(TelemetryLog).filter(
            TelemetryLog.astronaut_id == telemetry_target
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

    # Earlier turns of this member's thread (read before the new message is stored)
    history = _recent_history(db, chat_owner)

    # Record user message under this member's private thread only
    user_record = ChatHistoryModel(
        astronaut_id=chat_owner,
        role="user",
        content=payload.query
    )
    db.add(user_record)

    # Generate response scoped to this member
    # include_current_vitals=True only when the chat was opened automatically after the daily check-in;
    # from the floating button it is False and AstroDoc answers without the health report.
    result = ai_agent_service.answer_query(payload.query, context_vitals, chat_owner, history=history,
                                           use_report=payload.include_current_vitals)

    # Record assistant message under this member's private thread only
    asst_record = ChatHistoryModel(
        astronaut_id=chat_owner,
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
    db: Session = Depends(get_db),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
):
    """Returns recorded chat messages strictly for the current member's private chat."""
    chat_owner = _resolve_chat_owner(current_user, astronaut_id)
    if not chat_owner:
        return []

    rows = (
        db.query(ChatHistoryModel)
        .filter(ChatHistoryModel.astronaut_id == chat_owner)
        .order_by(ChatHistoryModel.timestamp.desc(), ChatHistoryModel.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
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
    db: Session = Depends(get_db),
    current_user: Optional[UserModel] = Depends(get_optional_current_user),
):
    """
    Generates autonomous proactive clinical dialogue based on current telemetry triage.
    Simulates the AI Flight Surgeon initiating check-in when physiological strain is detected.
    """
    if current_user is not None and not current_user.is_lead:
        astronaut_id = current_user.callsign or current_user.username

    latest = db.query(TelemetryLog).filter(
        TelemetryLog.astronaut_id == astronaut_id
    ).order_by(TelemetryLog.mission_day.desc(), TelemetryLog.id.desc()).first()

    if latest:
        from app.services.telemetry_metrics import health_metrics_from_log
        triage = evaluate_multi_hazard_triage(health_metrics_from_log(db, latest))
        triage_dict = {
            "astronaut_id": triage.astronaut_id,
            "overall_status": triage.overall_status,
            "clinical_flags": triage.clinical_flags
        }
    else:
        triage_dict = {"astronaut_id": astronaut_id, "overall_status": "NOMINAL", "clinical_flags": []}

    alert_data = ai_agent_service.generate_proactive_alert(triage_dict)
    return ProactiveChatPayload(**alert_data)
