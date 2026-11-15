"""
Pydantic Schemas for Aegis-Bio
Data validation for Telemetry, Dual-Classifier Triage, RAG Chat, Forecasting, and Emergency Escalation.
"""
from datetime import date, datetime, time, timedelta
from typing import Annotated, List, Literal, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

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
    cabin_co2_mmhg: Optional[float] = Field(default=2.8, ge=0.0, le=15.0, description="Cabin ppCO2 partial pressure (mmHg)")
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
                "cabin_co2_mmhg": 2.8,
                "subjective_notes": "Mild vestibular adaptation sensation after lunar EVA egress."
            }
        }

class HealthMetricsResponse(HealthMetrics):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ---------------------------------------------------------
# CLASSIFIER 1: Metric-Level Severity Schemas (NORMAL, MEDIUM, CRITICAL)
# ---------------------------------------------------------
class MetricEvaluation(BaseModel):
    metric_name: str
    label: str
    value: float
    unit: str
    status: str = Field(description="'NORMAL', 'MEDIUM', or 'CRITICAL'")
    nominal_range: str
    deviation: str
    clinical_note: str

class MetricClassificationReport(BaseModel):
    astronaut_id: str
    mission_day: int
    highest_severity: str
    metrics: Dict[str, MetricEvaluation]
    critical_count: int
    medium_count: int
    normal_count: int
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

# ---------------------------------------------------------
# CLASSIFIER 2: Multi-Hazard Spaceflight Triage Schemas
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
    category: str
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
    metric_evaluations: Optional[Dict[str, MetricEvaluation]] = None
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

# ---------------------------------------------------------
# Forecasting & Trend Regression Schemas
# ---------------------------------------------------------
class TrajectoryPoint(BaseModel):
    day: int
    time_label: Optional[str] = Field(default=None, description="Granular time label, e.g. 'Hour +14' or 'Sol 35'")
    heart_rate_predicted: float
    spo2_predicted: float
    radiation_cumulative_predicted: float
    sleep_predicted: float
    cardiovascular_strain_index: float
    cognitive_readiness_index: float
    lower_ci_heart_rate: Optional[float] = None
    upper_ci_heart_rate: Optional[float] = None

class PredictionResult(BaseModel):
    model_config = {"protected_namespaces": ()}
    astronaut_id: Optional[str] = "ALL_CREW"
    time_scale: str = Field(default="WEEKLY", description="DAILY (24h), WEEKLY (7d), or MONTHLY (30d)")
    forecast_horizon_days: int = 7
    horizon_steps: int = 7
    model_used: str = "Holt-Winters Damped Time-Series"
    projected_trajectory: List[TrajectoryPoint]
    cardiovascular_strain_score: float = Field(..., ge=0, le=100)
    cognitive_degradation_risk: float = Field(..., ge=0, le=100)
    early_warnings: List[str]
    critical_inflection_day: Optional[int] = None
    r2_fit_quality: float = Field(..., ge=0, le=1)

# ---------------------------------------------------------
# Authentication & Crew Management Schemas
# ---------------------------------------------------------
class CrewLeadRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="Lead astronaut username")
    key: str = Field(..., min_length=4, description="Secret access key")
    station_name: str = Field(..., description="Station or Habitat name (e.g. ARTEMIS-BASE-ALPHA)")
    crew_name: str = Field(..., description="Crew identifier (e.g. CREW-A)")
    environment: Literal["LEO", "LUNAR", "MARS", "DEEP_SPACE"] = Field(
        ..., description="Where the crew operates; every member's metrics are classified against this environment"
    )

class CrewMemberCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="Crew member username")
    key: str = Field(..., min_length=4, description="Secret access key")
    callsign: Optional[str] = Field(default=None, description="Optional telemetry callsign (e.g. ASTRO-02)")

class UserLogin(BaseModel):
    username: str = Field(..., description="Astronaut username")
    key: str = Field(..., description="Secret access key")

class UserResponse(BaseModel):
    id: int
    username: str
    crew_name: str
    station_name: str
    environment: str = "LUNAR"
    is_lead: bool = False
    callsign: Optional[str] = None
    alert_timeout_seconds: int = 60
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# ---------------------------------------------------------
# Intra-Crew Emergency Escalation & Alarm Schemas
# ---------------------------------------------------------
class EmergencyAlert(BaseModel):
    alert_id: str
    astronaut_id: str
    crew_name: str = "CREW-A"
    station_name: str = "LUNAR-BASE-ALPHA"
    severity: str
    hazard_origin: str
    message: str
    suggested_crew_actions: List[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    override_notes: Optional[str] = None

    # Alarm Escalation & Emergency Contact Routing Fields
    status: str = Field(default="PENDING_OWNER", description="PENDING_OWNER, ACKNOWLEDGED_BY_OWNER, SWITCHED_TO_EMERGENCY_CONTACT, ACKNOWLEDGED_BY_CONTACT, RESOLVED")
    timeout_seconds: int = Field(default=60, description="Timeout before escalation to emergency contact")
    timeout_at: Optional[datetime] = Field(default=None, description="Absolute UTC timestamp when alert switches")
    remaining_seconds: Optional[int] = Field(default=None, description="Seconds left before switching to emergency contact")
    emergency_contact_name: Optional[str] = None
    emergency_contact_callsign: Optional[str] = None
    emergency_contact_email: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_role: Optional[str] = None
    emergency_contact_notified_at: Optional[datetime] = None
    source: str = Field(default="SYSTEM", description="Origin of alarm (e.g. HEALTH_PREDICTOR_AGENT)")
    requires_action: bool = True
    owner_answered: bool = False
    prediction_data: Optional[Dict[str, Any]] = None

class EmergencyAckRequest(BaseModel):
    alert_id: str
    crew_member_callsign: str
    override_notes: Optional[str] = None

class EmergencyOwnerAnswerRequest(BaseModel):
    alert_id: str
    notes: Optional[str] = Field(default=None, description="Owner's response/acknowledgment notes")

class EmergencyContactAckRequest(BaseModel):
    alert_id: str
    contact_callsign: str
    intervention_notes: Optional[str] = Field(default=None, description="Emergency contact intervention or rescue notes")

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
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    citations: Optional[List[str]] = None
    transcript: Optional[str] = None  # voice questions: what the speech-to-text heard
    photo_description: Optional[str] = None  # photo questions: what the vision model saw
    photo_readings: Optional[List[str]] = None  # values read from the photo, logged only after "yes"


# =========================================================
# Daily Check-in (full astronaut self-report)
# Mirrors the ISS-style "Daily Health Check-In" sheet: vitals, sleep, wellbeing,
# exercise, nutrition, environment and symptoms.
# =========================================================
GlucoseContext = Literal["fasting", "post_meal", "random"]

Symptom = Literal[
    "headache",
    "nasal_congestion",
    "vision_change",
    "back_pain",
    "nausea",
    "puffy_face",
    "dizziness",
    "muscle_joint_pain",
    "fatigue",
    "trouble_concentrating",
    "shortness_of_breath",
    "skin_irritation",
]

Rating = Annotated[int, Field(ge=1, le=5)]


class _StrictSection(BaseModel):
    """Rejects unknown fields so client typos surface as 422 instead of being silently dropped."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CheckInVitals(_StrictSection):
    heart_rate: float = Field(..., ge=30, le=240, description="Resting heart rate (BPM)")
    bp_sys: float = Field(..., ge=60, le=250, description="Systolic blood pressure (mmHg)")
    bp_dia: float = Field(..., ge=40, le=160, description="Diastolic blood pressure (mmHg)")
    spo2: float = Field(..., ge=50, le=100, description="Blood oxygen saturation (%)")
    core_temp_c: float = Field(..., ge=34.0, le=42.0, description="Body temperature (°C)")
    blood_glucose: float = Field(..., ge=40, le=400, description="Blood glucose (mg/dL)")
    glucose_context: GlucoseContext = Field(..., description="Timing of the glucose sample relative to meals")
    hrv_rmssd: float = Field(..., ge=5.0, le=200.0, description="HRV RMSSD (ms)")

    @model_validator(mode="after")
    def _diastolic_below_systolic(self) -> "CheckInVitals":
        if self.bp_dia >= self.bp_sys:
            raise ValueError("bp_dia must be lower than bp_sys")
        return self


class CheckInSleep(_StrictSection):
    bedtime: time = Field(..., description="Local time went to bed (HH:MM)")
    wake_time: time = Field(..., description="Local wake time (HH:MM)")
    sleep_hours: float = Field(..., ge=0, le=24, description="Actual hours slept (ISS: 8.5 h scheduled, ~6 h typical)")
    sleep_quality: Rating = Field(..., description="1 = very poor, 5 = excellent")
    sleep_medication: bool = Field(..., description="Sleep medication used")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def time_in_bed_hours(self) -> float:
        """Bedtime to wake time, handling sleep periods that cross midnight."""
        start = timedelta(hours=self.bedtime.hour, minutes=self.bedtime.minute)
        end = timedelta(hours=self.wake_time.hour, minutes=self.wake_time.minute)
        minutes = ((end - start).total_seconds() / 60) % (24 * 60)
        return round(minutes / 60, 2)


class CheckInWellbeing(_StrictSection):
    mood_score: Rating = Field(..., description="1 = very low, 5 = great")
    energy_level: Rating = Field(..., description="1 = exhausted, 5 = full energy")
    stress_level: Rating = Field(..., description="1 = very stressed, 5 = calm")


class CheckInExercise(_StrictSection):
    cardio_minutes: int = Field(..., ge=0, le=600, description="Treadmill / cycle ergometer minutes")
    resistance_minutes: int = Field(..., ge=0, le=600, description="Resistance device (weights) minutes")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_minutes(self) -> int:
        return self.cardio_minutes + self.resistance_minutes


class CheckInNutrition(_StrictSection):
    calories_kcal: int = Field(..., ge=0, le=8000, description="Calories eaten (kcal)")
    water_liters: float = Field(..., ge=0, le=10, description="Water drunk (L)")
    breakfast: bool = False
    lunch: bool = False
    dinner: bool = False
    vitamin_d_taken: bool = False


class CheckInEnvironment(_StrictSection):
    radiation_msv: float = Field(..., ge=0, le=500, description="Personal dosimeter dose, last 24 h (mSv)")
    radiation_badge_worn: bool = Field(..., description="Personal dosimeter worn all day")
    cabin_temp_c: float = Field(..., ge=0, le=50, description="Cabin temperature (°C); ISS 17.8–26.7")
    cabin_co2_mmhg: float = Field(..., ge=0, le=15, description="Cabin ppCO2 (mmHg); limit 3 mmHg 1-h avg")
    ear_protection_used: bool = Field(False, description="Ear protection worn in high-noise areas")


class DailyCheckInCreate(_StrictSection):
    astronaut_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    mission_day: int = Field(..., ge=1, le=10000)
    checkin_date: date
    vitals: CheckInVitals
    sleep: CheckInSleep
    wellbeing: CheckInWellbeing
    exercise: CheckInExercise
    nutrition: CheckInNutrition
    environment: CheckInEnvironment
    # No free-text fields: every input is numeric, categorical or boolean so it can feed the classifier.
    symptoms: List[Symptom] = Field(default_factory=list, max_length=20, description="Empty list = no symptoms")

    @field_validator("symptoms")
    @classmethod
    def _dedupe_symptoms(cls, v: List[str]) -> List[str]:
        return list(dict.fromkeys(v))

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "astronaut_id": "ASTRO-7702-HELENA",
                "mission_day": 31,
                "checkin_date": "2026-11-14",
                "vitals": {"heart_rate": 68, "bp_sys": 118, "bp_dia": 76, "spo2": 98, "core_temp_c": 36.8,
                           "blood_glucose": 92, "glucose_context": "fasting", "hrv_rmssd": 48},
                "sleep": {"bedtime": "22:30", "wake_time": "06:30", "sleep_hours": 6.5, "sleep_quality": 3,
                          "sleep_medication": False},
                "wellbeing": {"mood_score": 4, "energy_level": 4, "stress_level": 3},
                "exercise": {"cardio_minutes": 75, "resistance_minutes": 60},
                "nutrition": {"calories_kcal": 2600, "water_liters": 2.2, "breakfast": True, "lunch": True,
                              "dinner": True, "vitamin_d_taken": True},
                "environment": {"radiation_msv": 0.4, "radiation_badge_worn": True, "cabin_temp_c": 22.5,
                                "cabin_co2_mmhg": 2.6, "ear_protection_used": True},
                "symptoms": ["nasal_congestion"],
            }
        },
    )


class CheckInFlag(BaseModel):
    """Rule-based finding on lifestyle / environment data (vitals are covered by triage)."""
    code: str
    severity: Literal["INFO", "MEDIUM", "CRITICAL"]
    message: str


AssessmentStatus = Literal["NOMINAL", "WATCH", "CRITICAL"]
Concern = Literal[
    "NONE", "RADIATION", "CARDIOVASCULAR", "FLUID_SHIFT_SANS", "SLEEP_BEHAVIORAL",
    "CABIN_ENVIRONMENT", "INFECTION", "NUTRITION_HYDRATION",
]


class ConcernProbability(BaseModel):
    concern: Concern
    label: str
    probability: float = Field(..., ge=0, le=1)


class ContributingFactor(BaseModel):
    """An input that pushed the prediction: resetting it to a normal value lowers the model's confidence."""
    factor: str
    value: str
    impact: float = Field(..., description="Drop in predicted probability when this input is set to normal")


class HealthAssessment(BaseModel):
    """Output of the ML daily check-in classifier (plus the rule-based safety floor)."""
    model_config = {"protected_namespaces": ()}
    status: AssessmentStatus = Field(..., description="Final status after the safety floor")
    model_status: AssessmentStatus = Field(..., description="Status predicted by the ML model alone")
    status_confidence: float = Field(..., ge=0, le=1)
    safety_override: bool = Field(..., description="True if a critical rule raised the model's status")
    safety_reasons: List[str]
    primary_concern: Concern
    concern_label: str
    hazard: str = Field(..., description="Related NASA spaceflight hazard")
    concern_confidence: Optional[float] = Field(
        ..., ge=0, le=1, description="Model probability of the concern; null when a safety rule set it"
    )
    top_concerns: List[ConcernProbability]
    key_factors: List[ContributingFactor]
    model_version: str
    disclaimer: str


class ClassifierInfo(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_version: str
    trained_at: str
    sklearn_version: str
    metrics: Dict[str, float]
    concerns: List[str]
    statuses: List[str]
    n_features: int


class DailyCheckInRead(DailyCheckInCreate):
    model_config = ConfigDict(extra="ignore")

    id: int
    telemetry_log_id: int
    created_at: datetime
    flags: List[CheckInFlag]
    assessment: Optional[HealthAssessment] = Field(
        None, description="ML assessment stored at submission; null if the model was unavailable"
    )
