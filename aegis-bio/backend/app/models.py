"""
SQLAlchemy ORM Models for Aegis-Bio Persistence
"""
from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text
from app.database import Base

class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    astronaut_id = Column(String(64), index=True, nullable=False, default="ASTRO-7702-HELENA")
    mission_day = Column(Integer, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Core Physiological Vitals
    heart_rate = Column(Float, nullable=False)
    bp_sys = Column(Float, nullable=False)
    bp_dia = Column(Float, nullable=False)
    spo2 = Column(Float, nullable=False)
    
    # Environmental & Behavioral
    sleep_hours = Column(Float, nullable=False)
    radiation_msv = Column(Float, nullable=False)
    blood_glucose = Column(Float, default=95.0, nullable=False)
    mood_score = Column(Integer, nullable=False)
    
    # Extended Aerospace Parameters
    core_temp_c = Column(Float, default=36.9)
    hrv_rmssd = Column(Float, default=42.0)
    subjective_notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class EmergencyAlertModel(Base):
    __tablename__ = "emergency_alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alert_id = Column(String(64), unique=True, index=True, nullable=False)
    astronaut_id = Column(String(64), index=True, nullable=False)
    severity = Column(String(32), nullable=False)  # "WARNING", "HIGH_ALERT", "CRITICAL_ESCALATION"
    hazard_origin = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    suggested_crew_actions = Column(Text, nullable=False)  # Stored as JSON or delimited string
    timestamp = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    override_notes = Column(Text, nullable=True)

class ChatHistoryModel(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    astronaut_id = Column(String(64), index=True, nullable=False)
    role = Column(String(16), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    citations = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
