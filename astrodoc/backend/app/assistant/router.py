"""FastAPI routes for AstroDoc AI. Mount into the main backend:

    from app.assistant.router import create_assistant_router
    app.include_router(create_assistant_router(MyProvider()))
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from .chain import AstroDocAssistant
from .contracts import AlertCrewRequest, ChatRequest, ChatResponse, ChatTurn, CountermeasureCard, GreetRequest
from .countermeasures import find_cards
from .data_provider import AstroDataProvider
from .stt import MAX_AUDIO_BYTES, SpeechToText, STTError
from .vision import MAX_IMAGE_BYTES, VisionError


def create_assistant_router(provider: AstroDataProvider, assistant: Optional[AstroDocAssistant] = None,
                            stt: Optional[SpeechToText] = None, prefix: str = "/api") -> APIRouter:
    bot = assistant or AstroDocAssistant(provider)
    speech = stt or SpeechToText()
    r = APIRouter(prefix=prefix, tags=["AstroDoc AI"])

    def _guard(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    def _transcribe(audio: UploadFile) -> str:
        data = audio.file.read(MAX_AUDIO_BYTES + 1)
        try:
            return speech.transcribe(data, audio.filename or "speech.webm", audio.content_type).text
        except STTError as e:
            raise HTTPException(status_code=e.status, detail=str(e))

    # Plain `def` endpoints: FastAPI runs them in a worker thread, so the
    # blocking LLM / speech calls never stall the event loop (WebSockets etc.).
    @r.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest):
        """Astronaut message -> {reply, citations[], logged[], countermeasures{}, ...}."""
        return _guard(bot.chat, req.astronaut_id, req.message, req.history, offline=req.offline,
                      use_report=req.use_report)

    @r.post("/chat/voice", response_model=ChatResponse)
    def chat_voice(audio: UploadFile = File(..., description="Recorded speech (webm, ogg, wav, mp3, m4a...)"),
                   astronaut_id: str = Form(...),
                   history: str = Form("[]", description="JSON list of {role, content} turns"),
                   offline: bool = Form(False),
                   use_report: bool = Form(True, description="False when the chat was opened directly")):
        """Voice message: Whisper transcribes it, then it goes through the normal chat path
        (red flags, knowledge base, logging). The reply carries `transcript`."""
        try:
            turns = [ChatTurn(**t) for t in json.loads(history or "[]")]
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail=f"history must be a JSON list of turns ({e})")
        text = _transcribe(audio)
        resp = _guard(bot.chat, astronaut_id, text, turns, offline=offline, use_report=use_report)
        resp.transcript = text
        return resp

    @r.post("/chat/image", response_model=ChatResponse)
    def chat_image(image: UploadFile = File(..., description="Photo of a device display (JPEG, PNG or WebP)"),
                   astronaut_id: str = Form(...),
                   message: str = Form("", description="Optional text sent with the photo"),
                   history: str = Form("[]", description="JSON list of {role, content} turns"),
                   offline: bool = Form(False),
                   use_report: bool = Form(True, description="False when the chat was opened directly")):
        """Photo message: the vision model reads the display, then the description goes through the normal
        chat path. Readings come back in `photo.readings` and are logged only after the astronaut replies "yes".
        Errors: 413 (over 3 MB), 415 (not an image), 502 (unreadable), 503 (vision model unavailable)."""
        try:
            turns = [ChatTurn(**t) for t in json.loads(history or "[]")]
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail=f"history must be a JSON list of turns ({e})")
        data = image.file.read(MAX_IMAGE_BYTES + 1)
        try:
            return _guard(bot.chat_photo, astronaut_id, data, image.content_type, message, turns,
                          offline=offline, use_report=use_report)
        except VisionError as e:
            raise HTTPException(status_code=e.status, detail=str(e))

    @r.post("/transcribe")
    def transcribe(audio: UploadFile = File(...)):
        """Speech -> text only (e.g. to fill the check-in form by voice)."""
        return {"text": _transcribe(audio)}

    @r.post("/chat/greet", response_model=ChatResponse)
    def greet(req: GreetRequest):
        """Call when the panel auto-opens on a Warning/Critical triage."""
        return _guard(bot.greet, req.astronaut_id, use_llm=req.use_llm, offline=req.offline)

    @r.post("/chat/alert-crew")
    def alert_crew(req: AlertCrewRequest):
        """'Alert crew now' button -> Intra-Crew Escalation Protocol."""
        return _guard(bot.alert_crew, req.astronaut_id, req.reason)

    @r.get("/countermeasures", response_model=list[CountermeasureCard])
    def countermeasures(hazard: Optional[str] = None, level: str = "Warning", topic: Optional[str] = None):
        return find_cards(hazard=hazard, level=level, topic=topic)

    @r.get("/knowledge/search")
    def knowledge_search(q: str = Query(..., min_length=2), k: int = Query(4, ge=1, le=10)):
        return {"backend": bot.kb.backend, "results": bot.kb.search(q, k=k)}

    @r.get("/assistant/status")
    def status():
        chunks = bot.kb.size                      # initialises the knowledge base
        host = getattr(bot.llm, "base_url", None) if bot.llm else None
        provider = host.split("//")[-1].split("/")[0] if host else "huggingface"
        return {"llm_available": bot.llm_available, "llm_provider": provider, "model": bot.model,
                "fallback_models": bot.llm.fallback_models if bot.llm else [],
                "last_llm_error": bot._last_error, "retriever": bot.kb.backend, "kb_chunks": chunks,
                "stt_available": speech.available, "stt_model": speech.model,
                "vision_available": bot.vision.available, "vision_model": bot.vision.model}

    return r
