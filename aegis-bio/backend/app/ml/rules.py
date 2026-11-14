"""
Deterministic clinical safety rules shared by the data generator and the inference service.

`safety_floor` lists every reading in the critical range of the rule-based metric classifier
(the same thresholds the triage engine uses). It is used:
  * at inference: a critical reading forces the final status to CRITICAL, whatever the model says
  * when generating training data: labels must never contradict these rules
    (a "healthy" day cannot contain a critical reading)
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.services.metric_classifier import metric_classifier

# (section, field, concern if critical)
RULE_METRICS: List[Tuple[str, str, str]] = [
    ("vitals", "heart_rate", "CARDIOVASCULAR"),
    ("vitals", "bp_sys", "CARDIOVASCULAR"),
    ("vitals", "bp_dia", "CARDIOVASCULAR"),
    ("vitals", "spo2", "CABIN_ENVIRONMENT"),
    ("vitals", "core_temp_c", "INFECTION"),
    ("vitals", "hrv_rmssd", "SLEEP_BEHAVIORAL"),
    ("sleep", "sleep_hours", "SLEEP_BEHAVIORAL"),
    ("wellbeing", "mood_score", "SLEEP_BEHAVIORAL"),
    ("environment", "radiation_msv", "RADIATION"),
    ("environment", "cabin_co2_mmhg", "CABIN_ENVIRONMENT"),
]

GLUCOSE_CRITICAL_LOW = 54
GLUCOSE_CRITICAL_HIGH = 250


def safety_floor(p: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(concern, reason) for every reading in the critical range. Empty list = no critical reading."""
    hits: List[Tuple[str, str]] = []
    for section, field, concern in RULE_METRICS:
        ev = metric_classifier.classify_single_metric(field, float(p[section][field]))
        if ev.status == "CRITICAL":
            hits.append((concern, f"{ev.label}: {ev.value:g} {ev.unit}".strip()))
    g = float(p["vitals"]["blood_glucose"])
    if g < GLUCOSE_CRITICAL_LOW or g >= GLUCOSE_CRITICAL_HIGH:
        hits.append(("NUTRITION_HYDRATION", f"Blood glucose: {g:g} mg/dL"))
    return hits
