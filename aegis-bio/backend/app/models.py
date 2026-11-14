"""
SQLAlchemy ORM Models for Aegis-Bio Persistence
"""
from datetime import datetime
from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint,
)
from sqlalchemy.orm import relationship
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
    # Nullable with no synthetic default: NULL means "not measured" (callers pass explicit values).
    core_temp_c = Column(Float, nullable=True)
    hrv_rmssd = Column(Float, nullable=True)
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


class DailyCheckIn(Base):
    """
    Full daily self-report (lifestyle, environment, symptoms).
    Vitals live in the linked TelemetryLog row so triage/forecasting keep working unchanged.
    One check-in per astronaut per mission day.
    """
    __tablename__ = "daily_checkins"
    __table_args__ = (
        UniqueConstraint("astronaut_id", "mission_day", name="uq_daily_checkin_astronaut_day"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    telemetry_log_id = Column(
        Integer, ForeignKey("telemetry_logs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    astronaut_id = Column(String(64), nullable=False, index=True)
    mission_day = Column(Integer, nullable=False, index=True)
    checkin_date = Column(Date, nullable=False)

    # Vitals context not stored on TelemetryLog
    glucose_context = Column(String(16), nullable=False)

    # Sleep
    bedtime = Column(Time, nullable=False)
    wake_time = Column(Time, nullable=False)
    sleep_quality = Column(Integer, nullable=False)
    sleep_medication = Column(Boolean, nullable=False, default=False)

    # Wellbeing (mood_score is on TelemetryLog)
    energy_level = Column(Integer, nullable=False)
    stress_level = Column(Integer, nullable=False)

    # Exercise
    cardio_minutes = Column(Integer, nullable=False)
    resistance_minutes = Column(Integer, nullable=False)

    # Nutrition
    calories_kcal = Column(Integer, nullable=False)
    water_liters = Column(Float, nullable=False)
    breakfast = Column(Boolean, nullable=False, default=False)
    lunch = Column(Boolean, nullable=False, default=False)
    dinner = Column(Boolean, nullable=False, default=False)
    vitamin_d_taken = Column(Boolean, nullable=False, default=False)

    # Environment (radiation_msv is on TelemetryLog)
    radiation_badge_worn = Column(Boolean, nullable=False)
    cabin_temp_c = Column(Float, nullable=False)
    cabin_co2_mmhg = Column(Float, nullable=False)
    ear_protection_used = Column(Boolean, nullable=False, default=False)

    symptoms = Column(JSON, nullable=False, default=list)
    # ML classifier output (HealthAssessment JSON incl. model_version); NULL if the model was unavailable
    assessment = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    telemetry = relationship("TelemetryLog", lazy="joined")
