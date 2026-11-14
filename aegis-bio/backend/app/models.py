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
    severity = Column(String(32), nullable=False)  # "WARNING", "HIGH_ALERT", "CRITICAL_ESCALATION", "CRITICAL"
    hazard_origin = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    suggested_crew_actions = Column(Text, nullable=False)  # Stored as JSON or delimited string
    timestamp = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(64), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    override_notes = Column(Text, nullable=True)

    # Alarm escalation & emergency contact routing
    user_id = Column(Integer, nullable=True)
    crew_name = Column(String(64), default="CREW-A", nullable=False)
    station_name = Column(String(120), default="LUNAR-BASE-ALPHA", nullable=False)
    status = Column(String(32), default="PENDING_OWNER", nullable=False)  # PENDING_OWNER, ACKNOWLEDGED_BY_OWNER, SWITCHED_TO_EMERGENCY_CONTACT, ACKNOWLEDGED_BY_CONTACT, RESOLVED
    timeout_seconds = Column(Integer, default=60, nullable=False)
    timeout_at = Column(DateTime, nullable=True)
    emergency_contact_name = Column(String(120), nullable=True)
    emergency_contact_callsign = Column(String(64), nullable=True)
    emergency_contact_email = Column(String(120), nullable=True)
    emergency_contact_phone = Column(String(64), nullable=True)
    emergency_contact_role = Column(String(64), nullable=True)
    emergency_contact_notified_at = Column(DateTime, nullable=True)
    source = Column(String(64), default="SYSTEM", nullable=False)  # HEALTH_PREDICTOR_AGENT, TELEMETRY_TRIAGE, MANUAL_DRILL
    requires_action = Column(Boolean, default=True, nullable=False)
    prediction_data = Column(Text, nullable=True)
    owner_answered = Column(Boolean, default=False, nullable=False)

class UserModel(Base):
    """
    Crew Member & Lead Profile for Offline-First Station Authentication.
    Uses username and key (password secret).
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(120), nullable=True)
    hashed_password = Column(String(255), nullable=False)  # stores hashed key
    callsign = Column(String(64), index=True, nullable=True)
    is_lead = Column(Boolean, default=False)
    crew_name = Column(String(64), index=True, nullable=False, default="CREW-A")
    station_name = Column(String(120), index=True, nullable=False, default="LUNAR-BASE-ALPHA")
    is_active = Column(Boolean, default=True)

    # Configurable dead-man's switch timeout
    alert_timeout_seconds = Column(Integer, default=60, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatHistoryModel(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    astronaut_id = Column(String(64), index=True, nullable=False)
    role = Column(String(16), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    citations = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
