import pytest

from app.assistant.extract import extract_measurements
from app.assistant.redflags import detect


@pytest.mark.parametrize("text,flag", [
    ("I have chest pain", "chest_pain"),
    ("there's a tight chest feeling since the EVA", "chest_pain"),
    ("I can’t breathe properly", "breathing"),
    ("Tomás passed out in node 2", "loss_of_consciousness"),
    ("suddenly I can't see out of my left eye", "vision"),
    ("worst headache of my life", "severe_headache"),
    ("I feel confused and dizzy", "confusion"),
])
def test_red_flags_detected(text, flag):
    hit = detect(text)
    assert hit is not None and hit.id == flag


@pytest.mark.parametrize("text", [
    "no chest pain today, just tired",
    "I do not have chest pain",
    "slept 5 hours, headache",
    "Can I still do the EVA tomorrow?",
    "what does severe mean for radiation?",
])
def test_no_false_red_flags(text):
    assert detect(text) is None


def test_extract_sleep_and_symptom():
    got = {(x.metric, x.value, x.note) for x in extract_measurements("slept 5 hours, headache")}
    assert ("sleep_h", 5.0, None) in got
    assert ("symptom", None, "headache") in got


def test_extract_vitals():
    got = {x.metric: x.value for x in extract_measurements(
        "HR 118, SpO2 93%, temp 38.4, BP 145/92, glucose 65, mood 2/5")}
    assert got == {"hr": 118, "spo2": 93, "temp_c": 38.4, "bp_sys": 145, "bp_dia": 92, "glucose": 65, "mood": 2}


def test_extract_rejects_implausible_and_negated():
    got = extract_measurements("heart rate 900, no headache")
    assert got == []


def test_extract_fahrenheit_converted():
    (x,) = extract_measurements("temperature 101.3")
    assert x.metric == "temp_c" and x.value == pytest.approx(38.5, abs=0.1)


@pytest.mark.parametrize("text", [
    "i am spelling blood what does that mean",       # typo of "spitting"
    "I am spitting blood", "coughing up blood since this morning", "I threw up blood",
    "there is blood in my urine", "my spit has blood", "my hand is bleeding a lot",
])
def test_bleeding_red_flags(text):
    hit = detect(text)
    assert hit is not None and hit.id == "bleeding"


@pytest.mark.parametrize("text", [
    "what is my blood pressure", "blood sugar is 90", "blood glucose 65",
    "I donated blood before the mission", "no coughing blood, just a cough",
])
def test_blood_words_that_are_not_red_flags(text):
    assert detect(text) is None
