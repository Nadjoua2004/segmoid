"""
Tests for the daily check-in ML classifier: synthetic data, features, training, inference,
safety floor, explanations and API integration.

A small model is trained once per test session into a temp folder (fast mode), so the tests do not
depend on the committed model file.
"""
import copy
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.checkins import router as checkins_router
from app.database import Base, get_db
from app.ml.features import FEATURE_NAMES, NOMINAL_REFERENCE, extract_features, time_in_bed_hours
from app.ml.synthetic import generate_dataset
from app.ml.train import train
from app.schemas import DailyCheckInCreate
from app.services import checkin_classifier

HEADER = {"astronaut_id": "ASTRO-TEST", "mission_day": 40, "checkin_date": "2026-11-14"}


def make(**changes):
    """Nominal check-in payload with section__field overrides (or symptoms=[...])."""
    p = copy.deepcopy(NOMINAL_REFERENCE)
    p["symptoms"] = []
    for path, val in changes.items():
        if path == "symptoms":
            p["symptoms"] = val
            continue
        section, field = path.split("__")
        p[section][field] = val
    return p


@pytest.fixture(scope="session")
def trained_model(tmp_path_factory):
    path = tmp_path_factory.mktemp("model") / "clf.joblib"
    report = train(n_samples=3000, seed=7, model_path=path, data_path=None, fast=True)
    original = checkin_classifier.MODEL_PATH
    checkin_classifier.MODEL_PATH = path
    checkin_classifier.clear_cache()
    yield {"path": path, "report": report}
    checkin_classifier.MODEL_PATH = original
    checkin_classifier.clear_cache()


# --- Data & features -----------------------------------------------------------------------------
def test_synthetic_payloads_pass_api_validation():
    payloads, statuses, concerns = generate_dataset(400, seed=3)
    for p in payloads:
        DailyCheckInCreate.model_validate({**HEADER, **p})
    assert set(statuses) == {"NOMINAL", "WATCH", "CRITICAL"}
    assert len(set(concerns)) == 8


def test_synthetic_data_is_deterministic():
    assert generate_dataset(50, seed=11) == generate_dataset(50, seed=11)


def test_feature_vector_shape_and_derived_values():
    p = make(sleep__bedtime="23:30", sleep__wake_time="06:30", symptoms=["headache", "nausea"])
    f = dict(zip(FEATURE_NAMES, extract_features(p)))
    assert len(extract_features(p)) == len(FEATURE_NAMES)
    assert f["time_in_bed_hours"] == 7.0  # crosses midnight
    assert f["total_exercise_minutes"] == 130
    assert f["pulse_pressure"] == 41
    assert f["symptom_count"] == 2 and f["symptom_headache"] == 1.0
    assert time_in_bed_hours("22:00:00", "06:00:00") == 8.0  # API "HH:MM:SS" form


def test_features_identical_for_api_payload_and_raw_dict():
    """Same features whether the payload comes from the API model or a plain dict (no train/serve skew)."""
    raw = make()
    via_api = DailyCheckInCreate.model_validate({**HEADER, **raw}).model_dump(mode="json")
    assert extract_features(raw) == extract_features(via_api)


# --- Training --------------------------------------------------------------------------------------
def test_training_writes_bundle_and_report(trained_model):
    report = json.loads(trained_model["path"].with_suffix(".report.json").read_text())
    assert report["n_features"] == len(FEATURE_NAMES)
    assert report["status"]["test_macro_f1"] > 0.75
    assert report["concern"]["test_macro_f1"] > 0.75
    assert report["status"]["critical_recall"] > 0.85
    assert "synthetic" in report["data"]["source"]


# --- Inference -------------------------------------------------------------------------------------
def test_nominal_day(trained_model):
    a = checkin_classifier.assess(make())
    assert a.status == "NOMINAL" and a.primary_concern == "NONE"
    assert a.key_factors == [] and not a.safety_override


def test_solar_particle_event(trained_model):
    a = checkin_classifier.assess(make(environment__radiation_msv=60.0, symptoms=["nausea", "fatigue"]))
    assert a.status == "CRITICAL"
    assert a.primary_concern == "RADIATION" and a.hazard == "Space radiation"
    assert a.key_factors[0].factor == "Radiation dose"


def test_sleep_deprivation(trained_model):
    a = checkin_classifier.assess(make(
        sleep__sleep_hours=3.5, sleep__sleep_quality=1, wellbeing__mood_score=2,
        wellbeing__stress_level=1, wellbeing__energy_level=1,
    ))
    assert a.status != "NOMINAL" and a.primary_concern == "SLEEP_BEHAVIORAL"


def test_safety_floor_overrides_model(trained_model):
    """A single critical reading the model may not weigh heavily must still produce CRITICAL."""
    a = checkin_classifier.assess(make(vitals__spo2=90.0))
    assert a.status == "CRITICAL"
    assert any("Oxygen" in r or "SpO2" in r for r in a.safety_reasons)
    assert a.safety_override == (a.model_status != "CRITICAL")
    if a.safety_override:
        assert a.concern_confidence is None  # concern came from the rule, not the model


def test_probabilities_are_valid(trained_model):
    a = checkin_classifier.assess(make(environment__cabin_co2_mmhg=3.9, symptoms=["headache"]))
    assert 0 <= a.status_confidence <= 1
    probs = [c.probability for c in a.top_concerns]
    assert len(probs) == 3 and probs == sorted(probs, reverse=True)
    assert sum(probs) <= 1.0 + 1e-3  # top-3 of a probability distribution
    assert a.top_concerns[0].concern == a.primary_concern


def test_missing_model_raises(tmp_path):
    checkin_classifier.clear_cache()
    with pytest.raises(checkin_classifier.ModelUnavailableError):
        checkin_classifier.load_bundle(tmp_path / "nope.joblib")


# --- API integration ---------------------------------------------------------------------------------
@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    api = FastAPI()
    api.include_router(checkins_router)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    api.dependency_overrides[get_db] = override
    yield TestClient(api)
    engine.dispose()


def test_create_stores_assessment(trained_model, client):
    body = {**HEADER, **make(environment__radiation_msv=60.0, symptoms=["nausea"])}
    created = client.post("/api/checkins", json=body).json()
    assert created["assessment"]["primary_concern"] == "RADIATION"
    fetched = client.get(f"/api/checkins/{created['id']}").json()
    assert fetched["assessment"] == created["assessment"]  # persisted, not recomputed


def test_classify_endpoint_does_not_save(trained_model, client):
    res = client.post("/api/checkins/classify", json={**HEADER, **make()})
    assert res.status_code == 200 and res.json()["status"] == "NOMINAL"
    assert client.get("/api/checkins", params={"astronaut_id": "ASTRO-TEST"}).json() == []


def test_classifier_info_endpoint(trained_model, client):
    info = client.get("/api/checkins/classifier").json()
    assert info["n_features"] == len(FEATURE_NAMES) and "status_critical_recall" in info["metrics"]


def test_without_model_checkin_still_saves(client, tmp_path, monkeypatch):
    monkeypatch.setattr(checkin_classifier, "MODEL_PATH", tmp_path / "missing.joblib")
    checkin_classifier.clear_cache()
    res = client.post("/api/checkins", json={**HEADER, **make()})
    assert res.status_code == 201 and res.json()["assessment"] is None
    assert client.post("/api/checkins/classify", json={**HEADER, **make()}).status_code == 503
    checkin_classifier.clear_cache()
