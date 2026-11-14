"""
Behavioural unit tests for the DEPLOYED daily check-in classifier
(app/services/saved_models/checkin_classifier.joblib).

test_checkin_classifier.py checks the pipeline with a small model trained during the test run;
this module checks that the model actually shipped with the app behaves sensibly:
generalisation to unseen data, monotonicity (worse readings never lower risk), extreme inputs,
safety-rule boundaries, invariances, explanation quality, robustness and latency.
"""
import copy
import time

import joblib
import numpy as np
import pytest

from app.ml.features import CONCERNS, FEATURE_NAMES, NOMINAL_REFERENCE
from app.ml.synthetic import generate_dataset
from app.ml.train import DEFAULT_MODEL_PATH
from app.schemas import DailyCheckInCreate
from app.services import checkin_classifier
from app.services.checkin_classifier import (
    MAX_FACTORS, MIN_FACTOR_IMPACT, _variants, assess, assess_many, safety_floor,
)

pytestmark = pytest.mark.skipif(not DEFAULT_MODEL_PATH.exists(), reason="deployed model not trained yet")

RANK = {"NOMINAL": 0, "WATCH": 1, "CRITICAL": 2}
HEADER = {"astronaut_id": "ASTRO-TEST", "mission_day": 40, "checkin_date": "2026-11-14"}


@pytest.fixture(scope="module", autouse=True)
def deployed_model():
    """Point the service at the real model for this module, then restore whatever was set before."""
    previous = checkin_classifier.MODEL_PATH
    checkin_classifier.MODEL_PATH = DEFAULT_MODEL_PATH
    checkin_classifier.clear_cache()
    yield checkin_classifier.load_bundle()
    checkin_classifier.MODEL_PATH = previous
    checkin_classifier.clear_cache()


def make(**changes):
    p = copy.deepcopy(NOMINAL_REFERENCE)
    p["symptoms"] = []
    for path, val in changes.items():
        if path == "symptoms":
            p["symptoms"] = val
            continue
        section, field = path.split("__")
        p[section][field] = val
    return p


# =============================================================================================
# 1. Generalisation: fresh synthetic data the model never saw (different seed)
# =============================================================================================
@pytest.fixture(scope="module")
def unseen():
    payloads, statuses, concerns = generate_dataset(3000, seed=2026)
    results = assess_many(payloads, explain=False)
    return payloads, np.array(statuses), np.array(concerns), results


def test_unseen_status_accuracy(unseen):
    _, statuses, _, results = unseen
    model = np.array([r.model_status for r in results])
    assert (model == statuses).mean() >= 0.85


def test_unseen_concern_accuracy_per_class(unseen):
    """Every concern must be recognised reasonably well, not just the easy ones."""
    _, statuses, concerns, results = unseen
    pred = np.array([r.primary_concern for r in results])
    abnormal = statuses != "NOMINAL"
    for c in CONCERNS[1:]:
        mask = abnormal & (concerns == c)
        recall = (pred[mask] == c).mean()
        assert recall >= 0.70, f"{c}: recall {recall:.2f}"


def test_unseen_critical_cases_almost_never_called_nominal(unseen):
    """Most important safety property: a truly CRITICAL day must not be reported as NOMINAL."""
    _, statuses, _, results = unseen
    final = np.array([r.status for r in results])
    crit = statuses == "CRITICAL"
    missed = (final[crit] == "NOMINAL").mean()
    assert missed <= 0.01, f"{missed:.2%} of critical days reported NOMINAL"


def test_unseen_nominal_days_rarely_alarm(unseen):
    """False alarms erode trust: healthy days should rarely be flagged CRITICAL."""
    _, statuses, _, results = unseen
    final = np.array([r.status for r in results])
    false_crit = (final[statuses == "NOMINAL"] == "CRITICAL").mean()
    assert false_crit <= 0.03, f"{false_crit:.2%} of healthy days flagged CRITICAL"


def test_confidence_is_calibrated(unseen):
    """When the model says ~90 % confident, it should be right roughly that often."""
    _, statuses, _, results = unseen
    conf = np.array([r.status_confidence for r in results])
    correct = np.array([r.model_status for r in results]) == statuses
    high = conf >= 0.9
    assert high.sum() > 100
    assert correct[high].mean() >= 0.88
    low = conf < 0.7
    if low.sum() > 30:  # uncertain predictions should indeed be less accurate
        assert correct[low].mean() < correct[high].mean()


# =============================================================================================
# 2. Monotonicity: making a reading worse must never make the assessment less severe
# =============================================================================================
@pytest.mark.parametrize(
    "field, values",
    [
        ("environment__radiation_msv", [0.3, 1.0, 3.0, 8.0, 15.0, 25.0, 60.0, 150.0]),
        ("environment__cabin_co2_mmhg", [2.0, 2.8, 3.3, 3.9, 4.6, 6.0, 9.0]),
        ("vitals__core_temp_c", [36.8, 37.3, 37.7, 38.0, 38.3, 39.0, 40.0]),
        ("vitals__heart_rate", [62, 75, 90, 100, 110, 118, 130]),
        ("vitals__spo2", [99.0, 97.0, 95.5, 94.0, 92.5, 90.0, 85.0]),
    ],
)
def test_status_is_monotonic(field, values):
    ranks = [RANK[assess(make(**{field: v})).status] for v in values]
    assert ranks == sorted(ranks), f"{field}: {list(zip(values, ranks))}"
    assert ranks[0] == 0, "the healthy end of the range must be NOMINAL"
    assert ranks[-1] == 2, "the extreme end of the range must be CRITICAL"


def test_less_sleep_never_lowers_risk():
    ranks = []
    for h in [7.5, 6.5, 5.5, 4.6, 4.0, 3.0, 2.0]:
        a = assess(make(sleep__sleep_hours=h, sleep__sleep_quality=4 if h >= 6.5 else 2))
        ranks.append(RANK[a.status])
    assert ranks == sorted(ranks) and ranks[-1] == 2


def test_adding_symptoms_never_lowers_risk():
    base = make(environment__cabin_co2_mmhg=3.6)
    r0 = RANK[assess(base).status]
    r1 = RANK[assess({**base, "symptoms": ["headache", "trouble_concentrating"]}).status]
    assert r1 >= r0


# =============================================================================================
# 3. Extreme / boundary inputs
# =============================================================================================
@pytest.mark.parametrize(
    "changes",
    [
        {"vitals__heart_rate": 240}, {"vitals__heart_rate": 30},
        {"vitals__bp_sys": 250, "vitals__bp_dia": 160}, {"vitals__bp_sys": 60, "vitals__bp_dia": 40},
        {"vitals__spo2": 50.0}, {"vitals__core_temp_c": 42.0}, {"vitals__core_temp_c": 34.0},
        {"vitals__blood_glucose": 400}, {"vitals__blood_glucose": 40},
        {"environment__radiation_msv": 500.0}, {"environment__cabin_co2_mmhg": 15.0},
        {"sleep__sleep_hours": 0.0},
    ],
)
def test_extreme_inputs_are_critical(changes):
    """API min/max values: the model was never trained this far out, the safety floor must catch them."""
    payload = make(**changes)
    DailyCheckInCreate.model_validate({**HEADER, **payload})  # really is a valid API input
    a = assess(payload)
    assert a.status == "CRITICAL"
    assert a.safety_reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"environment__cabin_temp_c": 50.0}, {"environment__cabin_temp_c": 0.0},
        {"nutrition__calories_kcal": 8000}, {"nutrition__water_liters": 10.0},
        {"exercise__cardio_minutes": 600, "exercise__resistance_minutes": 600},
        {"vitals__hrv_rmssd": 200},
    ],
)
def test_out_of_distribution_inputs_return_valid_result(changes):
    """Values beyond the training data must still give a well-formed, coherent assessment."""
    a = assess(make(**changes))
    assert a.status in RANK
    assert 0 <= a.status_confidence <= 1
    assert (a.status == "NOMINAL") == (a.primary_concern == "NONE")


@pytest.mark.parametrize(
    "field, ok, critical",
    [
        ("vitals__spo2", 93.0, 92.9),
        ("vitals__heart_rate", 114, 115),
        ("vitals__core_temp_c", 38.1, 38.2),
        ("environment__radiation_msv", 19.99, 20.0),
        ("environment__cabin_co2_mmhg", 4.4, 4.5),
        ("sleep__sleep_hours", 4.5, 4.4),
        ("vitals__blood_glucose", 54, 53),
        ("vitals__blood_glucose", 249, 250),
    ],
)
def test_safety_floor_boundaries(field, ok, critical):
    """Exact cut-offs of the rule-based safety floor (shared with the triage engine)."""
    assert safety_floor(make(**{field: ok})) == []
    assert safety_floor(make(**{field: critical}))


def test_safety_floor_reports_every_critical_reading():
    hits = safety_floor(make(vitals__spo2=90.0, environment__radiation_msv=30.0, vitals__core_temp_c=39.0))
    assert {c for c, _ in hits} == {"CABIN_ENVIRONMENT", "RADIATION", "INFECTION"}


# =============================================================================================
# 4. Invariance & consistency
# =============================================================================================
def test_deterministic():
    p = make(environment__cabin_co2_mmhg=3.7, symptoms=["headache"])
    assert assess(p) == assess(copy.deepcopy(p))


def test_does_not_mutate_input():
    p = make(environment__radiation_msv=40.0, symptoms=["nausea"])
    before = copy.deepcopy(p)
    assess(p)
    assert p == before


def test_identity_and_date_do_not_affect_result():
    body = make(vitals__heart_rate=104, vitals__hrv_rmssd=25)
    a = DailyCheckInCreate.model_validate({**HEADER, **body}).model_dump(mode="json")
    b = DailyCheckInCreate.model_validate(
        {"astronaut_id": "OTHER-1", "mission_day": 999, "checkin_date": "2030-01-01", **body}
    ).model_dump(mode="json")
    assert assess(a) == assess(b)


def test_time_format_does_not_matter():
    assert assess(make(sleep__bedtime="22:00", sleep__wake_time="06:20")) == \
        assess(make(sleep__bedtime="22:00:00", sleep__wake_time="06:20:00"))


def test_symptom_order_does_not_matter():
    s = ["vision_change", "puffy_face", "headache"]
    assert assess(make(symptoms=s)) == assess(make(symptoms=list(reversed(s))))


def test_status_and_concern_are_always_coherent(unseen):
    for r in unseen[3]:
        assert (r.status == "NOMINAL") == (r.primary_concern == "NONE")
        assert r.safety_override == (bool(r.safety_reasons) and r.model_status != "CRITICAL")
        if r.safety_reasons:
            assert r.status == "CRITICAL"


# =============================================================================================
# 5. Explanations
# =============================================================================================
def test_nominal_reference_has_nothing_to_explain():
    assert _variants(make()) == []


def test_explanations_are_sorted_bounded_and_relevant():
    a = assess(make(environment__radiation_msv=45.0, wellbeing__energy_level=2, symptoms=["nausea", "fatigue"]))
    impacts = [f.impact for f in a.key_factors]
    assert 1 <= len(impacts) <= MAX_FACTORS
    assert impacts == sorted(impacts, reverse=True)
    assert all(i >= MIN_FACTOR_IMPACT for i in impacts)
    assert a.key_factors[0].factor == "Radiation dose"


def test_explanations_only_mention_abnormal_inputs():
    a = assess(make(environment__cabin_co2_mmhg=4.0))
    assert {f.factor for f in a.key_factors} <= {"Cabin CO2"}


@pytest.mark.parametrize(
    "changes, concern, expected_factor",
    [
        ({"environment__radiation_msv": 30.0}, "RADIATION", "Radiation dose"),
        ({"environment__cabin_co2_mmhg": 5.0}, "CABIN_ENVIRONMENT", "Cabin CO2"),
        ({"vitals__core_temp_c": 38.6, "symptoms": ["fatigue"]}, "INFECTION", "Body temperature"),
        ({"symptoms": ["vision_change", "puffy_face"]}, "FLUID_SHIFT_SANS", "Symptom: Vision change"),
        ({"sleep__sleep_hours": 3.5, "sleep__sleep_quality": 1, "wellbeing__stress_level": 1},
         "SLEEP_BEHAVIORAL", "Sleep"),
        ({"nutrition__calories_kcal": 1200, "nutrition__water_liters": 0.9, "nutrition__lunch": False,
          "nutrition__dinner": False}, "NUTRITION_HYDRATION", None),
        ({"vitals__heart_rate": 102, "vitals__bp_sys": 138, "vitals__bp_dia": 88, "vitals__hrv_rmssd": 26,
          "symptoms": ["dizziness"]}, "CARDIOVASCULAR", None),
    ],
)
def test_each_concern_is_detected_and_explained(changes, concern, expected_factor):
    a = assess(make(**changes))
    assert a.status != "NOMINAL"
    assert a.primary_concern == concern
    assert a.key_factors, "an abnormal result must come with at least one explanation"
    if expected_factor:
        assert a.key_factors[0].factor == expected_factor


# =============================================================================================
# 6. Robustness to measurement noise & performance
# =============================================================================================
def test_small_measurement_noise_does_not_flip_clear_cases():
    rng = np.random.default_rng(0)
    for _ in range(25):
        healthy = make(vitals__heart_rate=int(66 + rng.integers(-4, 5)),
                       vitals__spo2=round(97.8 + rng.uniform(-0.5, 0.5), 1),
                       vitals__core_temp_c=round(36.8 + rng.uniform(-0.2, 0.2), 1))
        assert assess(healthy).status == "NOMINAL"
        storm = make(environment__radiation_msv=round(40 + rng.uniform(-5, 5), 2))
        assert assess(storm).status == "CRITICAL"


def test_latency():
    p = make(environment__radiation_msv=30.0, symptoms=["nausea", "fatigue", "headache"])
    assess(p)  # warm-up
    t = time.perf_counter()
    for _ in range(10):
        assess(p)
    per_call_ms = (time.perf_counter() - t) / 10 * 1000
    assert per_call_ms < 150, f"{per_call_ms:.0f} ms per assessment (with explanation)"


def test_bulk_scoring_is_fast_and_matches_single():
    payloads, _, _ = generate_dataset(2000, seed=99)
    t = time.perf_counter()
    bulk = assess_many(payloads, explain=False)
    assert time.perf_counter() - t < 10
    for p, r in zip(payloads[:20], bulk[:20]):
        single = assess(p, explain=False)
        assert (single.status, single.primary_concern) == (r.status, r.primary_concern)


# =============================================================================================
# 7. Model artefact integrity
# =============================================================================================
def test_bundle_matches_code(deployed_model):
    assert deployed_model["feature_names"] == FEATURE_NAMES
    assert list(deployed_model["concern_model"].classes_) == sorted(CONCERNS)
    assert set(deployed_model["status_model"].classes_) == {"NOMINAL", "WATCH", "CRITICAL"}


def test_incompatible_bundle_is_rejected(tmp_path, deployed_model):
    bad = dict(deployed_model, feature_names=FEATURE_NAMES[:-1])
    path = tmp_path / "bad.joblib"
    joblib.dump(bad, path)
    with pytest.raises(checkin_classifier.ModelUnavailableError):
        checkin_classifier.load_bundle(path)


class _ModelWithUnknownLabels:
    """Stand-in model (module level so joblib can pickle it) whose labels the API doesn't know."""
    classes_ = np.array(["NOMINAL", "WATCH", "SEVERE"])


def test_bundle_with_unknown_labels_is_rejected(tmp_path, deployed_model):
    """A model whose labels don't match the API schema must fail clearly at load time."""
    path = tmp_path / "labels.joblib"
    joblib.dump(dict(deployed_model, status_model=_ModelWithUnknownLabels()), path)
    with pytest.raises(checkin_classifier.ModelUnavailableError, match="labels"):
        checkin_classifier.load_bundle(path)


def test_label_narrowing_rejects_unknown_values():
    assert checkin_classifier._as_status("WATCH") == "WATCH"
    assert checkin_classifier._as_concern("RADIATION") == "RADIATION"
    with pytest.raises(checkin_classifier.ModelUnavailableError):
        checkin_classifier._as_status("SEVERE")
    with pytest.raises(checkin_classifier.ModelUnavailableError):
        checkin_classifier._as_concern("ALIEN")
