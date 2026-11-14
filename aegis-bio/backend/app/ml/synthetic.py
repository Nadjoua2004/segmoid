"""
Synthetic training data for the daily check-in classifier.

No labelled astronaut check-in dataset is publicly available, so training data is simulated.
Each sample is drawn from a *scenario* (a latent health condition linked to one of NASA's five
spaceflight hazards) at a *severity* (mild -> WATCH, severe -> CRITICAL). A scenario shifts several
correlated inputs at once, following published spaceflight physiology:

  RADIATION            dosimeter dose up; severe: nausea, fatigue, skin effects (acute radiation sickness)
  CARDIOVASCULAR       resting HR and BP up, HRV down, less exercise, dizziness (deconditioning)
  FLUID_SHIFT_SANS     vision change, puffy face, congestion, headache (headward fluid shift / SANS)
  SLEEP_BEHAVIORAL     short, poor sleep, low mood/energy, high stress, sleep aids, low HRV (isolation)
  CABIN_ENVIRONMENT    CO2 or cabin temperature out of range, headache, poor concentration
  INFECTION            fever, raised HR, fatigue, muscle pain (immune changes in a closed habitat)
  NUTRITION_HYDRATION  low calories / water, skipped meals, abnormal glucose (limited food supply)

Mild scenarios overlap heavily with normal days and nominal days carry occasional benign symptoms,
so the model must learn combinations of signals, not single thresholds.

Limitations: labels come from the simulation, not from clinicians. The model demonstrates the
pipeline and should be re-trained on real, clinically labelled data before any operational use.
Generated with AI assistance (Claude); parameters reviewed against NASA HRP / NASA-STD-3001 summaries.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from app.ml.features import CONCERNS, SYMPTOM_KEYS
from app.ml.rules import safety_floor

SEVERITY_FACTOR = {"WATCH": 1.0, "CRITICAL": 2.2}

BASE_SYMPTOM_P = {
    "headache": 0.06, "nasal_congestion": 0.12, "vision_change": 0.02, "back_pain": 0.08, "nausea": 0.02,
    "puffy_face": 0.12, "dizziness": 0.02, "muscle_joint_pain": 0.06, "fatigue": 0.04,
    "trouble_concentrating": 0.03, "shortness_of_breath": 0.005, "skin_irritation": 0.04,
}


def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _clip(x: float, lo: float, hi: float, decimals: int = 0) -> float:
    v = float(np.clip(x, lo, hi))
    return round(v, decimals) if decimals else float(round(v))


def _rating(x: float) -> int:
    return int(np.clip(round(x), 1, 5))


def sample_checkin(rng: np.random.Generator, concern: str, status: str) -> Dict[str, Any]:
    """Draw one check-in payload (API JSON shape) for a scenario."""
    k = SEVERITY_FACTOR.get(status, 0.0)  # 0 for NOMINAL
    sym_p = dict(BASE_SYMPTOM_P)

    # ---- baseline healthy day -------------------------------------------------------------
    hr = rng.normal(66, 7)
    sys_ = rng.normal(116, 8)
    dia = rng.normal(75, 6)
    spo2 = rng.normal(97.8, 0.8)
    temp = rng.normal(36.85, 0.25)
    hrv = rng.normal(52, 12)
    ctx = rng.choice(["fasting", "post_meal", "random"], p=[0.5, 0.3, 0.2])
    glucose = {"fasting": rng.normal(88, 8), "post_meal": rng.normal(120, 18), "random": rng.normal(105, 15)}[ctx]
    tib = rng.normal(8.3, 0.4)
    eff = rng.normal(0.82, 0.06)
    quality = rng.normal(3.7, 0.7)
    med_p = 0.10
    mood, energy, stress = rng.normal(4.0, 0.7), rng.normal(3.9, 0.7), rng.normal(3.7, 0.8)
    cardio, resist = rng.normal(70, 15), rng.normal(60, 12)
    kcal, water = rng.normal(2600, 300), rng.normal(2.4, 0.4)
    meal_p, vitd_p = 0.92, 0.85
    rad = rng.normal(0.38, 0.1)
    badge_p = 0.97
    ctemp, co2 = rng.normal(22.5, 1.3), rng.normal(2.3, 0.4)
    ear_p = 0.85

    # ---- scenario effects ------------------------------------------------------------------
    if concern == "RADIATION":
        rad = rng.uniform(1.2, 15) if status == "WATCH" else rng.uniform(15, 150)
        stress -= 0.5 * k
        energy -= 0.4 * k
        hr += 3 * k
        if status == "CRITICAL":
            sym_p.update(nausea=0.6, fatigue=0.5, headache=0.3, skin_irritation=0.2)
    elif concern == "CARDIOVASCULAR":
        hr += rng.normal(12, 4) * k
        sys_ += rng.normal(10, 4) * k
        dia += rng.normal(6, 3) * k
        hrv -= 12 * k
        cardio *= max(0.15, 1 - 0.3 * k)
        resist *= max(0.15, 1 - 0.3 * k)
        energy -= 0.5 * k
        sym_p.update(dizziness=0.35 * k, fatigue=0.2 * k)
    elif concern == "FLUID_SHIFT_SANS":
        sys_ += 3 * k
        sym_p.update(vision_change=min(0.95, 0.5 * k), puffy_face=min(0.9, 0.45 * k),
                     nasal_congestion=min(0.85, 0.4 * k), headache=min(0.8, 0.35 * k))
    elif concern == "SLEEP_BEHAVIORAL":
        tib -= 0.8 * k
        eff -= 0.1 * k
        quality -= 1.0 * k
        mood -= 0.8 * k
        stress -= 1.0 * k
        energy -= 1.0 * k
        med_p = 0.3 + 0.1 * k
        hrv -= 8 * k
        sym_p.update(trouble_concentrating=0.3 * k, fatigue=0.35 * k, headache=0.1 * k)
    elif concern == "CABIN_ENVIRONMENT":
        if rng.random() < 0.65:  # CO2 build-up
            co2 = rng.uniform(3.0, 4.6) if status == "WATCH" else rng.uniform(4.5, 8.0)
            spo2 -= 0.3 * k
            sym_p.update(headache=min(0.85, 0.4 * k), trouble_concentrating=min(0.7, 0.3 * k))
        else:  # thermal control problem
            hot = rng.random() < 0.7
            if status == "WATCH":
                ctemp = rng.uniform(26.8, 28.5) if hot else rng.uniform(16.0, 17.7)
            else:
                ctemp = rng.uniform(29.0, 33.0) if hot else rng.uniform(12.0, 15.5)
            quality -= 0.5 * k
            sym_p.update(headache=0.2 * k, fatigue=0.2 * k)
    elif concern == "INFECTION":
        temp += rng.normal(0.6, 0.15) * k
        hr += 7 * k
        energy -= 1.0 * k
        mood -= 0.4 * k
        sym_p.update(fatigue=min(0.9, 0.45 * k), muscle_joint_pain=min(0.7, 0.3 * k), headache=0.3 * k,
                     nasal_congestion=0.3, shortness_of_breath=0.08 * k)
    elif concern == "NUTRITION_HYDRATION":
        kcal -= 600 * k
        water -= 0.6 * k
        meal_p = 0.55 if status == "WATCH" else 0.3
        vitd_p = 0.5
        if rng.random() < 0.7:
            glucose -= 12 * k
        else:
            glucose += 40 * k
        energy -= 0.6 * k
        sym_p.update(dizziness=0.2 * k, fatigue=0.25 * k)

    # ---- assemble a schema-valid payload ---------------------------------------------------------
    sys_v = _clip(sys_, 80, 220)
    dia_v = _clip(min(dia, sys_v - 15), 45, 140)
    tib = float(np.clip(tib, 3.0, 11.0))
    sleep_hours = _clip(tib * float(np.clip(eff, 0.4, 1.0)), 0, 24, 1)
    bed = rng.normal(22 * 60, 45)

    symptoms = [s for s in SYMPTOM_KEYS if rng.random() < min(sym_p[s], 0.95)]

    return {
        "vitals": {
            "heart_rate": _clip(hr, 38, 200), "bp_sys": sys_v, "bp_dia": dia_v,
            "spo2": _clip(spo2, 80, 100, 1), "core_temp_c": _clip(temp, 35.0, 41.0, 1),
            "blood_glucose": _clip(glucose, 45, 380), "glucose_context": str(ctx),
            "hrv_rmssd": _clip(hrv, 8, 150),
        },
        "sleep": {
            "bedtime": _hhmm(bed), "wake_time": _hhmm(bed + tib * 60), "sleep_hours": sleep_hours,
            "sleep_quality": _rating(quality), "sleep_medication": bool(rng.random() < med_p),
        },
        "wellbeing": {"mood_score": _rating(mood), "energy_level": _rating(energy), "stress_level": _rating(stress)},
        "exercise": {"cardio_minutes": int(_clip(cardio, 0, 300)), "resistance_minutes": int(_clip(resist, 0, 300))},
        "nutrition": {
            "calories_kcal": int(_clip(kcal, 300, 5000)), "water_liters": _clip(water, 0.2, 6, 1),
            "breakfast": bool(rng.random() < meal_p), "lunch": bool(rng.random() < meal_p),
            "dinner": bool(rng.random() < meal_p), "vitamin_d_taken": bool(rng.random() < vitd_p),
        },
        "environment": {
            "radiation_msv": _clip(rad, 0.05, 400, 2), "radiation_badge_worn": bool(rng.random() < badge_p),
            "cabin_temp_c": _clip(ctemp, 8, 40, 1), "cabin_co2_mmhg": _clip(co2, 0.5, 12, 1),
            "ear_protection_used": bool(rng.random() < ear_p),
        },
        "symptoms": symptoms,
    }


def generate_dataset(n_samples: int, seed: int = 42, nominal_share: float = 0.35
                     ) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """
    Return (payloads, status_labels, concern_labels). Deterministic for a given seed.

    Labels are kept consistent with the clinical safety rules (app/ml/rules.py):
      * a NOMINAL day that happens to contain a critical reading is redrawn
        (otherwise the model learns that e.g. mood 2/5 or HRV 20 ms is "healthy")
      * a WATCH case containing a critical reading is labelled CRITICAL
    """
    rng = np.random.default_rng(seed)
    concerns = [c for c in CONCERNS if c != "NONE"]
    payloads, statuses, labels = [], [], []
    for _ in range(n_samples):
        if rng.random() < nominal_share:
            concern, status = "NONE", "NOMINAL"
        else:
            concern = str(rng.choice(concerns))
            status = "WATCH" if rng.random() < 0.5 else "CRITICAL"
        p = sample_checkin(rng, concern, status)
        if status == "NOMINAL":
            while safety_floor(p):
                p = sample_checkin(rng, concern, status)
        elif status == "WATCH" and safety_floor(p):
            status = "CRITICAL"
        payloads.append(p)
        statuses.append(status)
        labels.append(concern)
    return payloads, statuses, labels
