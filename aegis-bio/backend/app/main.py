"""
Aegis-Bio Main Application Entry Point
FastAPI application with CORS, database initialization, and router registrations.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, SessionLocal
from app.services.seeder import seed_initial_telemetry

# Import API Routers
from app.api.metrics import router as metrics_router
from app.api.triage import router as triage_router
from app.api.predict import router as predict_router
from app.api.emergency import router as emergency_router
from app.api.chat import router as chat_router
from app.api.otel_routes import router as otel_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Explicit CORS configuration for Next.js frontend (http://localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    """Initializes SQLite database tables and seeds baseline 30-day Artemis telemetry."""
    init_db()
    db = SessionLocal()
    try:
        count = seed_initial_telemetry(db)
        print(f"[Aegis-Bio Startup] Database ready. Active telemetry records: {count}")
    finally:
        db.close()

# Register API Routers
app.include_router(metrics_router)
app.include_router(triage_router)
app.include_router(predict_router)
app.include_router(emergency_router)
app.include_router(chat_router)
app.include_router(otel_router)

# OpenTelemetry Standard V1 Collector endpoint alias
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
