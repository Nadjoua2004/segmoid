"""Metric labels, units and thresholds the assistant needs (SPEC §4).

The triage engine (owned by the backend) is the source of truth for levels.
This table is only used for wording ("Logged: sleep 5 h"), for validating
values the astronaut types in chat, and by the mock data provider.
"""
from __future__ import annotations

METRICS: dict[str, dict] = {
    "bp_sys": {"name": "systolic blood pressure", "unit": "mmHg", "hazard": "Gravity", "topic": "cardiovascular",
               "warn_low": 90, "warn_high": 140, "crit_low": 80, "crit_high": 160, "range": (50, 260)},
    "bp_dia": {"name": "diastolic blood pressure", "unit": "mmHg", "hazard": "Gravity", "topic": "cardiovascular",
               "warn_low": None, "warn_high": 90, "crit_low": None, "crit_high": 100, "range": (30, 160)},
    "hr": {"name": "heart rate", "unit": "bpm", "hazard": "Gravity", "topic": "cardiovascular",
           "warn_low": 45, "warn_high": 100, "crit_low": 40, "crit_high": 120, "range": (20, 230)},
    "spo2": {"name": "SpO2", "unit": "%", "hazard": "Hostile environment", "topic": "spo2",
             "warn_low": 94, "warn_high": None, "crit_low": 90, "crit_high": None, "range": (50, 100)},
    "sleep_h": {"name": "sleep", "unit": "h", "hazard": "Isolation", "topic": "fatigue",
                "warn_low": 6, "warn_high": None, "crit_low": 4, "crit_high": None, "range": (0, 16)},
    "glucose": {"name": "blood glucose", "unit": "mg/dL", "hazard": "Distance", "topic": "glucose",
                "warn_low": 70, "warn_high": 180, "crit_low": 54, "crit_high": 250, "range": (20, 600)},
    "temp_c": {"name": "body temperature", "unit": "°C", "hazard": "Hostile environment", "topic": "fever",
               "warn_low": 35.5, "warn_high": 38.0, "crit_low": 35.0, "crit_high": 39.5, "range": (30, 43)},
    "rad_msv": {"name": "radiation dose (daily)", "unit": "mSv", "hazard": "Radiation", "topic": "radiation",
                "warn_low": None, "warn_high": None, "crit_low": None, "crit_high": None, "range": (0, 1000)},
    "mood": {"name": "mood", "unit": "/5", "hazard": "Isolation", "topic": "mood",
             "warn_low": 2, "warn_high": None, "crit_low": 1, "crit_high": None, "range": (1, 5)},
    "hrv_ms": {"name": "heart-rate variability (RMSSD)", "unit": "ms", "hazard": "Isolation", "topic": "fatigue",
               "warn_low": None, "warn_high": None, "crit_low": None, "crit_high": None, "range": (5, 250)},
    # NASA-STD-3001 Vol 2 [V2 6004]: 1-hour average ppCO2 in the habitable volume <= 3 mmHg
    "cabin_co2": {"name": "cabin CO2", "unit": "mmHg", "hazard": "Hostile environment", "topic": "co2",
                  "warn_low": None, "warn_high": 3.0, "crit_low": None, "crit_high": 4.5, "range": (0, 20)},
}

# Things the astronaut can report in chat that are not numeric metrics.
SYMPTOM_METRIC = "symptom"
LOGGABLE_METRICS = sorted(METRICS) + [SYMPTOM_METRIC]
FORECAST_TARGETS = sorted(METRICS) + ["readiness"]


def describe_value(metric: str, value: float | None, note: str | None = None) -> str:
    """Short chip text: 'sleep 5 h', 'SpO2 93 %', 'symptom: headache'."""
    if metric == SYMPTOM_METRIC:
        return f"symptom: {note or 'unspecified'}"
    meta = METRICS.get(metric, {"name": metric, "unit": ""})
    if value is None:
        return f"{meta['name']}: {note or 'noted'}"
    v = int(value) if float(value).is_integer() else round(value, 2)
    return f"{meta['name']} {v} {meta['unit']}".strip()


def in_plausible_range(metric: str, value: float) -> bool:
    lo, hi = METRICS[metric]["range"]
    return lo <= value <= hi
