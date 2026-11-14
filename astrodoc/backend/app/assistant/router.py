"""FastAPI routes for AstroDoc AI. Mount into the main backend:

    from app.assistant.router import create_assistant_router
    app.include_router(create_assistant_router(MyProvider()))
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .chain import AstroDocAssistant
from .contracts import AlertCrewRequest, ChatRequest, ChatResponse, CountermeasureCard, GreetRequest
from .countermeasures import find_cards
from .data_provider import AstroDataProvider


def create_assistant_router(provider: AstroDataProvider, assistant: Optional[AstroDocAssistant] = None,
                            prefix: str = "/api") -> APIRouter:
    bot = assistant or AstroDocAssistant(provider)
    r = APIRouter(prefix=prefix, tags=["AstroDoc AI"])

    def _guard(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

    # Plain `def` endpoints: FastAPI runs them in a worker thread, so the
    # blocking LLM call never stalls the event loop (WebSockets etc.).
    @r.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest):
        """Astronaut message -> {reply, citations[], logged[], countermeasures{}, ...}."""
        return _guard(bot.chat, req.astronaut_id, req.message, req.history, offline=req.offline)

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
                "last_llm_error": bot._last_error, "retriever": bot.kb.backend, "kb_chunks": chunks}

    return r
