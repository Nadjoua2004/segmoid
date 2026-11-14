"""
Pydantic Schemas for Aegis-Bio
Data validation for Telemetry, Triage, RAG Chat, Forecasting, and Emergency Escalation.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ---------------------------------------------------------
# Health Metrics Schemas
# ---------------------------------------------------------
class HealthMetrics(BaseModel):
    astronaut_id: str = Field(default="ASTRO-7702-HELENA", description="Astronaut callsign/ID")
    mission_day: int = Field(default=34, ge=1, description="Sol or Mission Day number")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Measurement UTC timestamp")
    
    # Core Vitals
    heart_rate: float = Field(..., ge=30, le=240, description="Resting Heart Rate in BPM")
    bp_sys: float = Field(..., ge=60, le=250, description="Systolic Blood Pressure in mmHg")
    bp_dia: float = Field(..., ge=40, le=160, description="Diastolic Blood Pressure in mmHg")
    spo2: float = Field(..., ge=50, le=100, description="Blood Oxygen Saturation (%)")
    
    # Environmental & Sleep
    sleep_hours: float = Field(..., ge=0, le=24, description="Sleep duration in preceding 24h")
    radiation_msv: float = Field(..., ge=0, description="Cumulative daily ionizing radiation dose (mSv)")
    blood_glucose: float = Field(default=95.0, ge=40, le=400, description="Fasting/postprandial glucose (mg/dL)")
    mood_score: int = Field(..., ge=1, le=5, description="Subjective psychological well-being (1=Distressed, 5=Optimal)")
    
    # Extended Aerospace Biometrics
    core_temp_c: Optional[float] = Field(default=36.9, ge=34.0, le=42.0, description="Core body temperature in Celsius")
    hrv_rmssd: Optional[float] = Field(default=42.0, ge=5.0, le=200.0, description="Heart Rate Variability RMSSD (ms)")
    subjective_notes: Optional[str] = Field(default="", description="Astronaut reported symptoms or notes")

    class Config:
        json_schema_extra = {
            "example": {
                "astronaut_id": "ASTRO-7702-HELENA",
                "mission_day": 34,
                "heart_rate": 78.5,
                "bp_sys": 128.0,
                "bp_dia": 82.0,
                "spo2": 97.4,
                "sleep_hours": 6.2,
                "radiation_msv": 0.85,
                "blood_glucose": 96.0,
                "mood_score": 4,
                "core_temp_c": 36.8,
                "hrv_rmssd": 45.2,
                "subjective_notes": "Mild vestibular adaptation sensation after lunar EVA egress."
            }
        }

class HealthMetricsResponse(HealthMetrics):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ---------------------------------------------------------
# NASA 5 Hazard & Triage Schemas
# ---------------------------------------------------------
class HazardBreakdown(BaseModel):
    radiation_score: float = Field(..., ge=0, le=100, description="Risk Score: Space Radiation (GCR + SPE)")
    microgravity_score: float = Field(..., ge=0, le=100, description="Risk Score: Gravity Field & Fluid Shifts")
    isolation_score: float = Field(..., ge=0, le=100, description="Risk Score: Isolation & Confinement / Circadian")
    distance_score: float = Field(..., ge=0, le=100, description="Risk Score: Distance from Earth & Comm Delay")
    hostile_env_score: float = Field(..., ge=0, le=100, description="Risk Score: Hostile Closed Habitat / Toxicities")

class Countermeasure(BaseModel):
    id: str
    title: str
    category: str  # "Radiation Protection", "Cardiovascular Reconditioning", "Circadian/Sleep", "Clinical Pharma"
    urgency: str   # "IMMEDIATE", "WITHIN_4H", "ROUTINE"
    protocol: str
    nasa_hrp_reference: str

class TriageResult(BaseModel):
    astronaut_id: str
    mission_day: int
    overall_status: str  # "NOMINAL", "ELEVATED", "HIGH", "CRITICAL"
    overall_risk_score: float = Field(..., ge=0, le=100)
    hazards: HazardBreakdown
    clinical_flags: List[str]
    countermeasures: List[Countermeasure]
    requires_emergency_escalation: bool
    ai_rationale: str
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

# ---------------------------------------------------------
# Forecasting & Trend Regression Schemas
# ---------------------------------------------------------
class TrajectoryPoint(BaseModel):
    day: int
    heart_rate_predicted: float
    spo2_predicted: float
    radiation_cumulative_predicted: float
    sleep_predicted: float
    cardiovascular_strain_index: float
    cognitive_readiness_index: float

class PredictionResult(BaseModel):
    astronaut_id: str
    forecast_horizon_days: int = 7
    projected_trajectory: List[TrajectoryPoint]
    cardiovascular_strain_score: float = Field(..., ge=0, le=100)
    cognitive_degradation_risk: float = Field(..., ge=0, le=100)
    early_warnings: List[str]
    critical_inflection_day: Optional[int] = None
    r2_fit_quality: float = Field(..., ge=0, le=1)

# ---------------------------------------------------------
# Intra-Crew Emergency Escalation Schemas
# ---------------------------------------------------------
class EmergencyAlert(BaseModel):
    alert_id: str
    astronaut_id: str
    severity: str  # "WARNING", "HIGH_ALERT", "CRITICAL_ESCALATION"
    hazard_origin: str
    message: str
    suggested_crew_actions: List[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None

class EmergencyAckRequest(BaseModel):
    alert_id: str
    crew_member_callsign: str
    override_notes: Optional[str] = None

# ---------------------------------------------------------
# Interactive RAG Chat Schemas
# ---------------------------------------------------------
class ChatQuery(BaseModel):
    query: str
    astronaut_id: str = "ASTRO-7702-HELENA"
    include_current_vitals: bool = True

class ProactiveChatPayload(BaseModel):
    astronaut_id: str
    trigger_reason: str
    clinical_summary: str
    recommended_dialogue: str
    suggested_actions: List[str]
    reference_guidelines: List[str]
    generated_at: datetime = Field(default_factory=datetime.utcnow)

class ChatMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    citations: Optional[List[str]] = None
