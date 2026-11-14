"""
Feature definition for the daily check-in classifier.

ONE function (`extract_features`) turns a check-in payload into the model's feature vector.
It is used both when generating training data and at inference time, so the model always sees
features computed exactly the same way (no train/serve skew).

The payload is the API JSON shape of DailyCheckInCreate (nested dict); times may be "HH:MM"
strings or datetime.time objects.
"""
from __future__ import annotations

from datetime import time
from typing import Any, Dict, List, Tuple, Union

# --- Labels ---------------------------------------------------------------------------------------
STATUSES: List[str] = ["NOMINAL", "WATCH", "CRITICAL"]

CONCERNS: List[str] = [
    "NONE",
    "RADIATION",
    "CARDIOVASCULAR",
    "FLUID_SHIFT_SANS",
    "SLEEP_BEHAVIORAL",
    "CABIN_ENVIRONMENT",
    "INFECTION",
    "NUTRITION_HYDRATION",
]

# Each concern maps to one of NASA HRP's five hazards of human spaceflight.
CONCERN_INFO: Dict[str, Dict[str, str]] = {
    "NONE": {"label": "No specific concern", "hazard": "—"},
    "RADIATION": {"label": "Radiation exposure", "hazard": "Space radiation"},
    "CARDIOVASCULAR": {"label": "Cardiovascular deconditioning", "hazard": "Altered gravity"},
    "FLUID_SHIFT_SANS": {"label": "Fluid shift / eye changes (SANS)", "hazard": "Altered gravity"},
    "SLEEP_BEHAVIORAL": {"label": "Sleep loss and behavioural strain", "hazard": "Isolation & confinement"},
    "CABIN_ENVIRONMENT": {"label": "Cabin air or temperature problem", "hazard": "Hostile closed environment"},
    "INFECTION": {"label": "Possible infection", "hazard": "Hostile closed environment"},
    "NUTRITION_HYDRATION": {"label": "Under-eating or dehydration", "hazard": "Distance from Earth"},
}

SYMPTOM_KEYS: List[str] = [
    "headache", "nasal_congestion", "vision_change", "back_pain", "nausea", "puffy_face",
    "dizziness", "muscle_joint_pain", "fatigue", "trouble_concentrating", "shortness_of_breath",
    "skin_irritation",
]

SYMPTOM_LABELS: Dict[str, str] = {
    "headache": "Headache",
    "nasal_congestion": "Nasal congestion",
    "vision_change": "Vision change",
    "back_pain": "Back pain",
    "nausea": "Nausea",
    "puffy_face": "Puffy face",
    "dizziness": "Dizziness",
    "muscle_joint_pain": "Muscle / joint pain",
    "fatigue": "Unusual fatigue",
    "trouble_concentrating": "Trouble concentrating",
    "shortness_of_breath": "Shortness of breath",
    "skin_irritation": "Skin rash / irritation",
}

GLUCOSE_CONTEXTS: List[str] = ["fasting", "post_meal", "random"]

FEATURE_NAMES: List[str] = [
    # vitals
    "heart_rate", "bp_sys", "bp_dia", "pulse_pressure", "spo2", "core_temp_c", "hrv_rmssd",
    "blood_glucose", *[f"glucose_{c}" for c in GLUCOSE_CONTEXTS],
    # sleep & wellbeing
    "sleep_hours", "time_in_bed_hours", "sleep_efficiency", "sleep_quality", "sleep_medication",
    "mood_score", "energy_level", "stress_level",
    # exercise & nutrition
    "cardio_minutes", "resistance_minutes", "total_exercise_minutes",
    "calories_kcal", "water_liters", "meals_count", "vitamin_d_taken",
    # environment
    "radiation_msv", "radiation_badge_worn", "cabin_temp_c", "cabin_co2_mmhg", "ear_protection_used",
    # symptoms
    *[f"symptom_{s}" for s in SYMPTOM_KEYS], "symptom_count",
]


def _minutes(t: Union[str, time]) -> int:
    if isinstance(t, time):
        return t.hour * 60 + t.minute
    hh, mm = str(t).split(":")[:2]
    return int(hh) * 60 + int(mm)


def time_in_bed_hours(bedtime: Union[str, time], wake_time: Union[str, time]) -> float:
    """Bedtime to wake time in hours, wrapping past midnight."""
    return ((_minutes(wake_time) - _minutes(bedtime)) % 1440) / 60.0


def extract_features(p: Dict[str, Any]) -> List[float]:
    """Return the feature vector (ordered as FEATURE_NAMES) for one check-in payload."""
    v, s, w = p["vitals"], p["sleep"], p["wellbeing"]
    e, n, env = p["exercise"], p["nutrition"], p["environment"]
    symptoms = set(p.get("symptoms") or [])

    tib = time_in_bed_hours(s["bedtime"], s["wake_time"])
    sleep_eff = min(s["sleep_hours"] / tib, 1.5) if tib > 0 else 0.0

    row = [
        v["heart_rate"], v["bp_sys"], v["bp_dia"], v["bp_sys"] - v["bp_dia"], v["spo2"],
        v["core_temp_c"], v["hrv_rmssd"], v["blood_glucose"],
        *[1.0 if v["glucose_context"] == c else 0.0 for c in GLUCOSE_CONTEXTS],
        s["sleep_hours"], tib, sleep_eff, s["sleep_quality"], float(s["sleep_medication"]),
        w["mood_score"], w["energy_level"], w["stress_level"],
        e["cardio_minutes"], e["resistance_minutes"], e["cardio_minutes"] + e["resistance_minutes"],
        n["calories_kcal"], n["water_liters"], float(n["breakfast"]) + float(n["lunch"]) + float(n["dinner"]),
        float(n["vitamin_d_taken"]),
        env["radiation_msv"], float(env["radiation_badge_worn"]), env["cabin_temp_c"], env["cabin_co2_mmhg"],
        float(env["ear_protection_used"]),
        *[1.0 if k in symptoms else 0.0 for k in SYMPTOM_KEYS], float(len(symptoms)),
    ]
    return [float(x) for x in row]


# --- Explanation support --------------------------------------------------------------------------
# A typical healthy check-in. To explain a prediction, each group of inputs is reset to these values
# and the change in the model's confidence is measured (occlusion / "what if this were normal").
NOMINAL_REFERENCE: Dict[str, Any] = {
    "vitals": {"heart_rate": 66, "bp_sys": 116, "bp_dia": 75, "spo2": 97.8, "core_temp_c": 36.8,
               "blood_glucose": 92, "glucose_context": "fasting", "hrv_rmssd": 52},
    "sleep": {"bedtime": "22:00", "wake_time": "06:20", "sleep_hours": 6.9, "sleep_quality": 4,
              "sleep_medication": False},
    "wellbeing": {"mood_score": 4, "energy_level": 4, "stress_level": 4},
    "exercise": {"cardio_minutes": 70, "resistance_minutes": 60},
    "nutrition": {"calories_kcal": 2600, "water_liters": 2.4, "breakfast": True, "lunch": True, "dinner": True,
                  "vitamin_d_taken": True},
    "environment": {"radiation_msv": 0.38, "radiation_badge_worn": True, "cabin_temp_c": 22.5,
                    "cabin_co2_mmhg": 2.3, "ear_protection_used": True},
}

# (display label, list of (section, field) paths). Glucose value and its context move together.
FactorPaths = List[Tuple[str, str]]
FACTOR_GROUPS: List[Tuple[str, FactorPaths]] = [
    ("Heart rate", [("vitals", "heart_rate")]),
    ("Blood pressure", [("vitals", "bp_sys"), ("vitals", "bp_dia")]),
    ("Blood oxygen", [("vitals", "spo2")]),
    ("Body temperature", [("vitals", "core_temp_c")]),
    ("Heart rate variability", [("vitals", "hrv_rmssd")]),
    ("Blood sugar", [("vitals", "blood_glucose"), ("vitals", "glucose_context")]),
    ("Sleep", [("sleep", "bedtime"), ("sleep", "wake_time"), ("sleep", "sleep_hours"),
               ("sleep", "sleep_quality"), ("sleep", "sleep_medication")]),
    ("Mood", [("wellbeing", "mood_score")]),
    ("Energy", [("wellbeing", "energy_level")]),
    ("Stress", [("wellbeing", "stress_level")]),
    ("Exercise", [("exercise", "cardio_minutes"), ("exercise", "resistance_minutes")]),
    ("Food intake", [("nutrition", "calories_kcal"), ("nutrition", "breakfast"), ("nutrition", "lunch"),
                     ("nutrition", "dinner"), ("nutrition", "vitamin_d_taken")]),
    ("Water", [("nutrition", "water_liters")]),
    ("Radiation dose", [("environment", "radiation_msv"), ("environment", "radiation_badge_worn")]),
    ("Cabin CO2", [("environment", "cabin_co2_mmhg")]),
    ("Cabin temperature", [("environment", "cabin_temp_c")]),
]
