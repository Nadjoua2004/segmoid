"""
Aegis-Bio Main Application Entry Point
FastAPI application with CORS, database initialization, and router registrations.
Starts with a clean, empty database (no auto-seeded dummy data).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db

# Import API Routers
from app.api.auth import router as auth_router
from app.api.metrics import router as metrics_router
from app.api.triage import router as triage_router
from app.api.predict import router as predict_router
from app.api.emergency import router as emergency_router
from app.api.chat import router as chat_router
from app.api.otel_routes import router as otel_router
from app.api.checkins import router as checkins_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*"
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    """Initializes database tables without inserting any dummy data."""
    init_db()
    print("[Aegis-Bio Startup] Clean database initialized (no dummy data).")

# Register API Routers
app.include_router(auth_router)
app.include_router(metrics_router)
app.include_router(triage_router)
app.include_router(predict_router)
app.include_router(emergency_router)
app.include_router(chat_router)
app.include_router(otel_router)
app.include_router(checkins_router)

@app.post("/v1/metrics", tags=["OpenTelemetry Collector"])
def otel_v1_metrics(payload: dict):
    from app.services.otel_collector import otel_collector
    otel_collector.ingested_spans_count += 1
    return {"status": "SUCCESS", "message": "OTLP metrics accepted"}

@app.get("/")
def root_status():
    return {
        "system": "Aegis-Bio Autonomous Flight Surgeon",
        "mission": settings.MISSION_NAME,
        "astronaut_callsign": settings.ASTRONAUT_ID,
        "mission_day": settings.MISSION_DAY,
        "comm_latency_minutes": settings.COMM_LATENCY_MINUTES,
        "status": "OPERATIONAL",
        "documentation": "/docs"
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "system": "Aegis-Bio Core",
        "comm_delay": f"{settings.COMM_LATENCY_MINUTES} min to Earth (Autonomous Mode Engaged)"
    }
