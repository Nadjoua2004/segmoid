"""
Daily Check-in Classifier: inference service.

Given one check-in payload it returns a HealthAssessment:
  * status (NOMINAL / WATCH / CRITICAL) and primary concern, predicted by the trained ML models
  * a deterministic SAFETY FLOOR: if any reading crosses a critical clinical threshold
    (metric_classifier rules), the final status is CRITICAL regardless of the model
  * key factors: occlusion-based explanation. Each input group is reset to a typical healthy value
    and the drop in the model's confidence is measured; the largest drops are reported.

The model bundle is produced by app/ml/train.py and loaded lazily (once per process).
"""
from __future__ import annotations

import copy
import logging
import threading
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast, get_args

import joblib
import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from app.ml.features import (
    CONCERN_INFO, FACTOR_GROUPS, FEATURE_NAMES, NOMINAL_REFERENCE, SYMPTOM_LABELS, extract_features,
)
from app.ml.train import DEFAULT_MODEL_PATH
from app.ml.rules import safety_floor
from app.services.metric_classifier import resolve_environment
from app.schemas import (
    AssessmentStatus, ClassifierInfo, Concern, ConcernProbability, ContributingFactor, HealthAssessment,
)

logger = logging.getLogger(__name__)

# Allowed label values, taken from the API schema's Literal types (single source of truth).
_STATUS_VALUES = frozenset(get_args(AssessmentStatus))
_CONCERN_VALUES = frozenset(get_args(Concern))

MODEL_PATH: Path = DEFAULT_MODEL_PATH
MIN_FACTOR_IMPACT = 0.05
MAX_FACTORS = 3
SMALL_BATCH_ROWS = 2000
DISCLAIMER = (
    "Machine-learning estimate from a model trained on simulated data. Not a diagnosis: "
    "confirm with the Crew Medical Officer or flight surgeon."
)

_lock = threading.Lock()
_cache: Dict[str, Dict[str, Any]] = {}


class ModelUnavailableError(RuntimeError):
    """The classifier bundle is missing or incompatible (re-run train_checkin_classifier.py)."""


def load_bundle(path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(path or MODEL_PATH)
    key = str(path.resolve())
    with _lock:
        if key in _cache:
            return _cache[key]
        if not path.exists():
            raise ModelUnavailableError(f"Classifier model not found at {path}. Run train_checkin_classifier.py.")
        bundle = joblib.load(path)
        if bundle.get("feature_names") != FEATURE_NAMES:
            raise ModelUnavailableError("Classifier was trained with a different feature set. Re-train it.")
        if (set(map(str, bundle["status_model"].classes_)) != _STATUS_VALUES
                or set(map(str, bundle["concern_model"].classes_)) != _CONCERN_VALUES):
            raise ModelUnavailableError("Classifier labels don't match the API schema. Re-train it.")
        if bundle.get("sklearn_version") != sklearn.__version__:
            logger.warning("Classifier trained with scikit-learn %s, running %s. Consider re-training.",
                           bundle.get("sklearn_version"), sklearn.__version__)
        _cache[key] = bundle
        return bundle


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def classifier_info() -> ClassifierInfo:
    b = load_bundle()
    return ClassifierInfo(
        model_version=b["model_version"], trained_at=b["trained_at"], sklearn_version=b["sklearn_version"],
        metrics=b["metrics"], concerns=b["concerns"], statuses=b["statuses"], n_features=len(b["feature_names"]),
    )


# --- Explanation ----------------------------------------------------------------------------------
_FORMAT: Dict[str, Callable[[Dict[str, Any]], str]] = {
    "Heart rate": lambda p: f"{p['vitals']['heart_rate']:g} BPM",
    "Blood pressure": lambda p: f"{p['vitals']['bp_sys']:g}/{p['vitals']['bp_dia']:g} mmHg",
    "Blood oxygen": lambda p: f"{p['vitals']['spo2']:g} %",
    "Body temperature": lambda p: f"{p['vitals']['core_temp_c']:g} °C",
    "Heart rate variability": lambda p: f"{p['vitals']['hrv_rmssd']:g} ms",
    "Blood sugar": lambda p: f"{p['vitals']['blood_glucose']:g} mg/dL ({p['vitals']['glucose_context'].replace('_', ' ')})",
    "Sleep": lambda p: (f"{p['sleep']['sleep_hours']:g} h, quality {p['sleep']['sleep_quality']}/5"
                        + (", sleep aid used" if p['sleep']['sleep_medication'] else "")),
    "Mood": lambda p: f"{p['wellbeing']['mood_score']}/5",
    "Energy": lambda p: f"{p['wellbeing']['energy_level']}/5",
    "Stress": lambda p: f"{p['wellbeing']['stress_level']}/5 (1 = very stressed)",
    "Exercise": lambda p: f"{p['exercise']['cardio_minutes'] + p['exercise']['resistance_minutes']} min",
    "Food intake": lambda p: (f"{p['nutrition']['calories_kcal']} kcal, "
                              f"{sum(bool(p['nutrition'][m]) for m in ('breakfast', 'lunch', 'dinner'))}/3 meals"),
    "Water": lambda p: f"{p['nutrition']['water_liters']:g} L",
    "Radiation dose": lambda p: (f"{p['environment']['radiation_msv']:g} mSv"
                                 + ("" if p['environment']['radiation_badge_worn'] else ", badge not worn")),
    "Cabin CO2": lambda p: f"{p['environment']['cabin_co2_mmhg']:g} mmHg",
    "Cabin temperature": lambda p: f"{p['environment']['cabin_temp_c']:g} °C",
}


def _reference() -> Dict[str, Any]:
    return {**copy.deepcopy(NOMINAL_REFERENCE), "symptoms": []}


def _variants(p: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any], Dict[str, Any]]]:
    """
    For each input group: (label, displayed value, OCCLUDED payload, INSERTED payload).
      occluded = the real check-in with this group reset to normal   -> how much does confidence DROP?
      inserted = a normal day with only this group set to the real value -> how much does it RISE?
    Using both handles redundant signals (e.g. HR, BP and HRV all pointing to deconditioning), where
    resetting any single one barely changes the prediction.
    """
    out = []
    for label, paths in FACTOR_GROUPS:
        if all(p[sec][f] == NOMINAL_REFERENCE[sec][f] for sec, f in paths):
            continue
        occl, ins = copy.deepcopy(p), _reference()
        for section, field in paths:
            occl[section][field] = NOMINAL_REFERENCE[section][field]
            ins[section][field] = p[section][field]
        out.append((label, _FORMAT[label](p), occl, ins))
    for s in p.get("symptoms") or []:
        occl, ins = copy.deepcopy(p), _reference()
        occl["symptoms"] = [x for x in occl["symptoms"] if x != s]
        ins["symptoms"] = [s]
        out.append((f"Symptom: {SYMPTOM_LABELS.get(s, s)}", "reported", occl, ins))
    return out


def _proba(model: Any, X: np.ndarray) -> Tuple[np.ndarray, List[str]]:
    return model.predict_proba(X), [str(c) for c in model.classes_]


# --- Main entry points ----------------------------------------------------------------------------
def assess(payload: Dict[str, Any], explain: bool = True) -> HealthAssessment:
    """Classify one check-in (API JSON shape, e.g. DailyCheckInCreate.model_dump(mode='json'))."""
    return assess_many([payload], explain=explain)[0]


def assess_many(payloads: List[Dict[str, Any]], explain: bool = True) -> List[HealthAssessment]:
    """
    Classify several check-ins. Each model call has a fixed overhead that dominates its cost, so all
    rows are batched: one status-model call for the payloads, and one concern-model call for the
    payloads plus every explanation variant. With explain=False (bulk scoring) no variants are built.
    """
    if not payloads:
        return []
    b = load_bundle()
    variants = [_variants(p) if explain else [] for p in payloads]

    rows = [extract_features(p) for p in payloads]
    ref_row = len(rows)
    rows.append(extract_features(_reference()))
    starts = []
    for vs in variants:
        starts.append(len(rows))
        rows += [extract_features(v[2]) for v in vs] + [extract_features(v[3]) for v in vs]
    X = np.asarray(rows, dtype=float)

    n = len(payloads)
    # For small batches, spinning up the OpenMP thread pool costs more than the prediction itself
    # (measured: 203 ms -> 72 ms per assessment). Large bulk batches keep all threads.
    limit = threadpool_limits(1) if len(X) < SMALL_BATCH_ROWS else nullcontext()
    with limit:
        sp, s_classes = _proba(b["status_model"], X[:n])
        cp, c_classes = _proba(b["concern_model"], X)
    return [
        _build(b, payloads[i], sp[i], s_classes, cp, c_classes, i, ref_row, variants[i], starts[i])
        for i in range(n)
    ]


def _as_status(label: str) -> AssessmentStatus:
    """Narrow a model/rule label (typed str) to the API's status literal, rejecting unknown labels."""
    if label not in _STATUS_VALUES:
        raise ModelUnavailableError(f"Model returned unknown status {label!r}. Re-train the classifier.")
    return cast(AssessmentStatus, label)


def _as_concern(label: str) -> Concern:
    """Narrow a model/rule label (typed str) to the API's concern literal, rejecting unknown labels."""
    if label not in _CONCERN_VALUES:
        raise ModelUnavailableError(f"Model returned unknown concern {label!r}. Re-train the classifier.")
    return cast(Concern, label)


def _build(b: Dict[str, Any], payload: Dict[str, Any], s_row: np.ndarray, s_classes: List[str],
           cp: np.ndarray, c_classes: List[str], i: int, ref_row: int,
           variants: List[Tuple[str, str, Dict[str, Any], Dict[str, Any]]], start: int) -> HealthAssessment:
    s_i = int(np.argmax(s_row))
    model_status = _as_status(s_classes[s_i])
    c_row = cp[i]
    c_order = np.argsort(c_row)[::-1]
    concern = _as_concern(c_classes[int(c_order[0])])

    # Safety floor: critical readings can only raise the status, never lower it.
    hits = safety_floor(payload, resolve_environment(payload.get("astronaut_id")))
    status: AssessmentStatus = "CRITICAL" if hits else model_status

    # Keep status and concern coherent. If a safety rule had to supply the concern, the model's
    # probability for it is not meaningful, so no confidence is reported.
    concern_from_rule = False
    if status == "NOMINAL":
        concern = "NONE"
    elif concern == "NONE":
        if hits:
            concern, concern_from_rule = _as_concern(hits[0][0]), True
        else:
            concern = _as_concern(next(c_classes[int(j)] for j in c_order if c_classes[int(j)] != "NONE"))
    c_i = c_classes.index(concern)

    # Explanation: score = max(drop when the input is reset to normal, rise when only it is abnormal).
    factors: List[ContributingFactor] = []
    k = len(variants)
    if status != "NOMINAL" and k:
        drops = c_row[c_i] - cp[start:start + k, c_i]
        rises = cp[start + k:start + 2 * k, c_i] - cp[ref_row, c_i]
        impact = np.maximum(drops, rises)
        for j in np.argsort(impact)[::-1][:MAX_FACTORS]:
            if impact[j] < MIN_FACTOR_IMPACT:
                break
            label, value, _, _ = variants[int(j)]
            factors.append(ContributingFactor(factor=label, value=value, impact=round(float(impact[j]), 3)))

    top = [
        ConcernProbability(concern=_as_concern(c_classes[int(j)]), label=CONCERN_INFO[c_classes[int(j)]]["label"],
                           probability=round(float(c_row[int(j)]), 3))
        for j in c_order[:3]
    ]
    return HealthAssessment(
        status=status,
        model_status=model_status,
        status_confidence=round(float(s_row[s_i]), 3),
        safety_override=bool(hits) and model_status != "CRITICAL",
        safety_reasons=[r for _, r in hits],
        primary_concern=concern,
        concern_label=CONCERN_INFO[concern]["label"],
        hazard=CONCERN_INFO[concern]["hazard"],
        concern_confidence=None if concern_from_rule else round(float(c_row[c_i]), 3),
        top_concerns=top,
        key_factors=factors,
        model_version=b["model_version"],
        disclaimer=DISCLAIMER,
    )
