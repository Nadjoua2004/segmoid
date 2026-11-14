"""Standalone AstroDoc AI server on mock data (for developing the chatbot alone).

    cd backend
    .venv/Scripts/python -m uvicorn app.assistant_app:app --port 8001 --reload
    open http://localhost:8001

The real backend mounts the same router with its own data provider instead.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from app.assistant.chain import AstroDocAssistant  # noqa: E402
from app.assistant.data_provider import MockDataProvider  # noqa: E402
from app.assistant.router import create_assistant_router  # noqa: E402

provider = MockDataProvider(day=47)
assistant = AstroDocAssistant(provider)

app = FastAPI(title="AstroDoc AI (standalone, mock data)")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(create_assistant_router(provider, assistant))


class DayRequest(BaseModel):
    day: int


@app.post("/api/mock/day")
def set_day(req: DayRequest):
    """Scrub the mock mission (47 = Sara Warning, 120 = solar particle event, 121 = Tomás overdue)."""
    if not 1 <= req.day <= 180:
        raise HTTPException(400, "day must be 1-180")
    provider.day = req.day
    return {"day": provider.day}


@app.get("/api/mock/state")
def state():
    return {"day": provider.day, "crew": [a.model_dump() for a in provider.list_crew()],
            "triage": {a.id: provider.get_triage(a.id).level for a in provider.list_crew()},
            "measurements": provider.measurements[-20:], "alerts": {k: [a.model_dump() for a in v]
                                                                     for k, v in provider.alerts.items()},
            "escalations": provider.escalations}


@app.get("/", response_class=HTMLResponse)
def dev_page():
    return (Path(__file__).parent / "assistant" / "static" / "chat_dev.html").read_text(encoding="utf-8")
