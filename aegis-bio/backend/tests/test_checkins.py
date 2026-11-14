"""
Tests for the Daily Check-in API (/api/checkins).
Uses an isolated in-memory SQLite database and a minimal app with only the check-ins router,
so the real database, seeder and RAG stack are never touched.
"""
import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables on Base.metadata)
from app.api.checkins import router as checkins_router
from app.database import Base, get_db
from app.models import TelemetryLog
from app.schemas import DailyCheckInCreate
from app.services.checkin_service import evaluate_checkin_flags

VALID = {
    "astronaut_id": "ASTRO-TEST",
    "mission_day": 31,
    "checkin_date": "2026-11-14",
    "vitals": {"heart_rate": 68, "bp_sys": 118, "bp_dia": 76, "spo2": 98, "core_temp_c": 36.8,
               "blood_glucose": 92, "glucose_context": "fasting", "hrv_rmssd": 48},
    "sleep": {"bedtime": "22:30", "wake_time": "06:30", "sleep_hours": 7.0, "sleep_quality": 4,
              "sleep_medication": False},
    "wellbeing": {"mood_score": 4, "energy_level": 4, "stress_level": 4},
    "exercise": {"cardio_minutes": 75, "resistance_minutes": 60},
    "nutrition": {"calories_kcal": 2600, "water_liters": 2.4, "breakfast": True, "lunch": True, "dinner": True},
    "environment": {"radiation_msv": 0.4, "radiation_badge_worn": True, "cabin_temp_c": 22.5,
                    "cabin_co2_mmhg": 2.4},
    "symptoms": [],
}


def payload(**overrides):
    """Deep-copied VALID payload with dotted-path overrides, e.g. payload(**{"vitals.bp_dia": 130})."""
    data = copy.deepcopy(VALID)
    for path, value in overrides.items():
        target = data
        *parents, leaf = path.split(".")
        for p in parents:
            target = target[p]
        target[leaf] = value
    return data


@pytest.fixture
def db_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


@pytest.fixture
def client(db_session_factory):
    test_app = FastAPI()
    test_app.include_router(checkins_router)

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    test_app.dependency_overrides[get_db] = override_get_db
    return TestClient(test_app)


# --- API -----------------------------------------------------------------------------------------
def test_create_checkin_persists_and_links_telemetry(client, db_session_factory):
    res = client.post("/api/checkins", json=VALID)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["id"] > 0
    assert body["exercise"]["total_minutes"] == 135
    assert body["sleep"]["time_in_bed_hours"] == 8.0  # crosses midnight
    assert body["flags"] == []

    with db_session_factory() as db:
        t = db.get(TelemetryLog, body["telemetry_log_id"])
        assert t.heart_rate == 68 and t.mission_day == 31 and t.mood_score == 4
        assert t.hrv_rmssd == 48
        assert "Glucose: fasting" in t.subjective_notes


def test_duplicate_day_returns_409(client):
    assert client.post("/api/checkins", json=VALID).status_code == 201
    res = client.post("/api/checkins", json=VALID)
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"vitals.bp_dia": 130},                      # diastolic >= systolic
        {"vitals.heart_rate": 900},                  # outside plausible range
        {"vitals.glucose_context": "brunch"},        # unknown enum value
        {"wellbeing.stress_level": 6},               # rating out of 1-5
        {"sleep.bedtime": "25:00"},                  # invalid time
        {"symptoms": ["alien_flu"]},                 # unknown symptom
        {"astronaut_id": "../etc/passwd"},           # disallowed characters
        {"vitals.typo_field": 1},                    # unknown field rejected (extra=forbid)
        {"notes": "free text"},                      # free-text fields removed (structured data only)
        {"exercise.notes": "knee pain"},
    ],
)
def test_invalid_payloads_are_rejected(client, overrides):
    assert client.post("/api/checkins", json=payload(**overrides)).status_code == 422


def test_list_and_get(client):
    client.post("/api/checkins", json=VALID)
    second = client.post("/api/checkins", json=payload(mission_day=32)).json()

    listed = client.get("/api/checkins", params={"astronaut_id": "ASTRO-TEST"}).json()
    assert [c["mission_day"] for c in listed] == [32, 31]  # newest first

    assert client.get(f"/api/checkins/{second['id']}").json()["mission_day"] == 32
    assert client.get("/api/checkins/99999").status_code == 404


@pytest.mark.parametrize(
    "section, field",
    [("vitals", "hrv_rmssd"), ("nutrition", "calories_kcal"), ("environment", "cabin_temp_c"),
     ("environment", "cabin_co2_mmhg"), ("sleep", "bedtime"), ("sleep", "wake_time")],
)
def test_previously_optional_fields_are_required(client, section, field):
    data = payload()
    del data[section][field]
    assert client.post("/api/checkins", json=data).status_code == 422
    data = payload(**{f"{section}.{field}": None})
    assert client.post("/api/checkins", json=data).status_code == 422


def test_symptoms_are_deduplicated(client):
    res = client.post("/api/checkins", json=payload(symptoms=["headache", "headache", "nausea"]))
    assert res.json()["symptoms"] == ["headache", "nausea"]


# --- Rules ---------------------------------------------------------------------------------------
def codes(data) -> set:
    return {f.code for f in evaluate_checkin_flags(DailyCheckInCreate.model_validate(data))}


def test_nominal_day_has_no_flags():
    assert codes(VALID) == set()


def test_lifestyle_flags():
    flagged = codes(payload(**{
        "exercise.cardio_minutes": 30,
        "exercise.resistance_minutes": 20,
        "nutrition.water_liters": 1.0,
        "nutrition.lunch": False,
        "nutrition.dinner": False,
        "environment.radiation_badge_worn": False,
        "symptoms": ["vision_change"],
        "sleep.sleep_medication": True,
    }))
    assert {
        "EXERCISE_BELOW_TARGET", "LOW_HYDRATION", "MEALS_SKIPPED",
        "DOSIMETER_NOT_WORN", "SANS_SCREENING", "SLEEP_MEDICATION_USED",
    } <= flagged


def test_cabin_environment_flags():
    assert "CABIN_CO2_HIGH" in codes(payload(**{"environment.cabin_co2_mmhg": 3.5}))
    assert "CABIN_CO2_CRITICAL" in codes(payload(**{"environment.cabin_co2_mmhg": 5.0}))
    assert "CABIN_TEMP_OUT_OF_RANGE" in codes(payload(**{"environment.cabin_temp_c": 29.0}))
