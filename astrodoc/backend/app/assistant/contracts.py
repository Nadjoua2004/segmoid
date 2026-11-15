"""Data shapes exchanged between the assistant and the rest of AstroDoc.

The backend team produces Triage / MetricHistory / Forecast objects; the
assistant only reads them. ChatResponse is what the frontend receives.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Level = Literal["Nominal", "Warning", "Critical"]
LEVEL_RANK: dict[str, int] = {"Nominal": 0, "Warning": 1, "Critical": 2}


def worst(*levels: str) -> str:
    return max(levels, key=lambda lv: LEVEL_RANK.get(lv, 0)) if levels else "Nominal"


# ---------------------------------------------------------------- inputs ---
class Astronaut(BaseModel):
    id: str
    name: str
    role: str
    is_cmo: bool = False


class MetricLevel(BaseModel):
    metric: str
    level: Level
    value: Optional[float] = None
    unit: str = ""
    reason: str = ""


class RankedRisk(BaseModel):
    hazard: str                     # Radiation | Isolation | Distance | Gravity | Hostile environment
    level: Level
    score: float                    # 0-100
    reason: str = ""
    top_factors: list[str] = Field(default_factory=list)


class TopFactor(BaseModel):
    feature: str
    label: str                      # e.g. "dosimeter +2.4σ"
    importance: float


class Triage(BaseModel):
    astronaut_id: str
    mission_day: int
    level: Level
    metric_levels: list[MetricLevel] = Field(default_factory=list)
    ranked_risks: list[RankedRisk] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    top_factors: list[TopFactor] = Field(default_factory=list)
    model_probabilities: dict[str, float] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class AlertInfo(BaseModel):
    id: str
    level: Level
    reason: str
    acknowledged: bool = False
    created_at: Optional[str] = None


class AstronautContext(BaseModel):
    astronaut: Astronaut
    mission_day: int
    checkin_status: str = "Due"     # "Done" | "Due in 2 h" | "Overdue" ...
    active_alerts: list[AlertInfo] = Field(default_factory=list)


class HistoryPoint(BaseModel):
    day: int
    value: float


class MetricHistory(BaseModel):
    metric: str
    unit: str = ""
    baseline_mean: Optional[float] = None
    baseline_sd: Optional[float] = None
    points: list[HistoryPoint] = Field(default_factory=list)


class ForecastPoint(BaseModel):
    day: int
    value: float
    lower: Optional[float] = None
    upper: Optional[float] = None


class Forecast(BaseModel):
    target: str                     # metric id or "readiness"
    horizon_days: int
    current: Optional[float] = None
    points: list[ForecastPoint] = Field(default_factory=list)
    days_until_warning: Optional[int] = None
    days_until_critical: Optional[int] = None
    message: str = ""               # always phrased as a projection, never a certainty


# --------------------------------------------------------------- outputs ---
class LoggedMeasurement(BaseModel):
    metric: str
    value: Optional[float] = None
    note: Optional[str] = None
    source: str = "chat"
    label: str = ""                 # chip text: "Logged: sleep 5 h"


class Citation(BaseModel):
    id: str                         # "S1" - matches [S1] markers in the reply
    title: str
    url: str = ""
    page: Optional[int] = None
    snippet: str = ""


class CountermeasureCard(BaseModel):
    id: str
    topic: str
    hazard: str
    level: Level
    group: Literal["protocol", "diet", "shielding"]
    title: str
    steps: list[str]
    source_title: str = ""
    source_url: str = ""
    demo_protocol: bool = False
    priority: int = 5               # lower = shown first within a level


class SuggestedAction(BaseModel):
    id: str                         # "alert_crew" | "acknowledge"
    label: str


class RedFlagInfo(BaseModel):
    id: str
    label: str
    matched: str


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    astronaut_id: str
    message: str
    history: list[ChatTurn] = Field(default_factory=list)
    offline: bool = False           # dashboard "offline mode" toggle
    use_report: bool = True         # False when the astronaut opened the chat directly (no check-in report)


class GreetRequest(BaseModel):
    astronaut_id: str
    use_llm: bool = False           # False: instant template greeting built from triage
    offline: bool = False


class AlertCrewRequest(BaseModel):
    astronaut_id: str
    reason: str = "Astronaut pressed 'Alert crew now' in AstroDoc AI"


class PhotoInfo(BaseModel):
    kind: str                       # device | symptom | food | document | other
    clear: bool = True
    device: str = ""
    description: str = ""           # what the vision model saw (show it under the photo)
    readings: list[str] = Field(default_factory=list)   # "SpO2 91 %": read, not logged until confirmed


class ChatResponse(BaseModel):
    reply: str
    mode: Literal["llm", "offline", "redflag", "template"]
    level: Optional[Level] = None
    citations: list[Citation] = Field(default_factory=list)
    logged: list[LoggedMeasurement] = Field(default_factory=list)
    countermeasures: dict[str, list[CountermeasureCard]] = Field(
        default_factory=lambda: {"protocol": [], "diet": [], "shielding": []})
    actions: list[SuggestedAction] = Field(default_factory=list)
    red_flag: Optional[RedFlagInfo] = None
    crew_alert_triggered: bool = False
    notice: Optional[str] = None    # e.g. "AI wording unavailable - offline mode"
    transcript: Optional[str] = None  # voice messages: what Whisper heard (show it as the user's bubble)
    photo: Optional[PhotoInfo] = None  # photo messages: what was read from it
