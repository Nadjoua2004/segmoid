"""Voice input: Whisper speech-to-text client, /api/chat/voice and spoken numbers. No network."""
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant.chain import AstroDocAssistant
from app.assistant.extract import extract_measurements, numbers_to_digits
from app.assistant.router import create_assistant_router
from app.assistant.stt import SpeechToText, STTError


def fake_http(responses, seen):
    """httpx client whose transport plays back (status, json) pairs and records requests."""
    queue = list(responses)

    def handler(request: httpx.Request):
        seen.append(request)
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def stt_with(responses, seen=None, **kw):
    seen = [] if seen is None else seen
    return SpeechToText(base_url="https://stt.test/v1", api_key="k", model="whisper-large-v3-turbo",
                        fallback_models=["whisper-large-v3"], http=fake_http(responses, seen), **kw), seen


# ------------------------------------------------------------ STT client ---
def test_transcribe_sends_whisper_request():
    stt, seen = stt_with([(200, {"text": " I slept 5 hours. ", "language": "english", "duration": 3.2})])
    t = stt.transcribe(b"RIFF....", "clip.wav", "audio/wav")
    assert t.text == "I slept 5 hours." and t.model == "whisper-large-v3-turbo"
    req = seen[0]
    assert req.url.path == "/v1/audio/transcriptions" and req.headers["authorization"] == "Bearer k"
    body = req.content.decode("latin-1")
    assert 'name="model"' in body and "whisper-large-v3-turbo" in body
    assert "EVA, SpO2" in body                                   # domain vocabulary prompt
    assert 'filename="speech.wav"' in body


def test_rate_limited_model_falls_back():
    stt, seen = stt_with([(429, {"error": "rate"}), (200, {"text": "hello crew"})])
    assert stt.transcribe(b"x" * 10, "a.webm").model == "whisper-large-v3"
    assert len(seen) == 2


def test_silence_hallucination_rejected():
    stt, _ = stt_with([(200, {"text": " Thank you."})])
    with pytest.raises(STTError) as e:
        stt.transcribe(b"x" * 10, "a.webm")
    assert e.value.status == 422


def test_too_large_and_empty_rejected_locally():
    stt, seen = stt_with([])
    with pytest.raises(STTError):
        stt.transcribe(b"", "a.webm")
    with pytest.raises(STTError) as e:
        stt.transcribe(b"x" * (10 * 1024 * 1024 + 1), "a.webm")
    assert e.value.status == 413 and seen == []


def test_unconfigured_stt_is_unavailable(monkeypatch):
    for v in ("STT_BASE_URL", "LLM_BASE_URL", "STT_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    stt = SpeechToText(http=fake_http([], []))
    assert not stt.available
    with pytest.raises(STTError) as e:
        stt.transcribe(b"x", "a.webm")
    assert e.value.status == 503


def test_extension_from_content_type():
    stt, seen = stt_with([(200, {"text": "ok then"})])
    stt.transcribe(b"x" * 10, "blob", "audio/ogg;codecs=opus")
    assert 'filename="speech.ogg"' in seen[0].content.decode("latin-1")


# ------------------------------------------------------- voice endpoint ---
class FakeSTT:
    available, model = True, "fake-whisper"

    def __init__(self, text):
        self.text = text

    def transcribe(self, audio, filename="", content_type=None):
        from app.assistant.stt import Transcript
        if self.text is None:
            raise STTError("Voice transcription unavailable", 503)
        return Transcript(text=self.text, model=self.model)


def client_for(provider, kb, text):
    app = FastAPI()
    bot = AstroDocAssistant(provider, kb=kb, offline=True)
    app.include_router(create_assistant_router(provider, bot, stt=FakeSTT(text)))
    return TestClient(app)


def test_voice_chest_pain_goes_through_red_flag_path(provider, kb):
    c = client_for(provider, kb, "I have chest pain and my heart rate is 120.")
    r = c.post("/api/chat/voice", data={"astronaut_id": "sara"},
               files={"audio": ("speech.webm", b"\x1aE\xdf\xa3", "audio/webm")})
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == "I have chest pain and my heart rate is 120."
    assert body["mode"] == "redflag" and body["red_flag"]["id"] == "chest_pain"
    assert {"Logged: symptom: Chest pain", "Logged: heart rate 120 bpm"} <= {l["label"] for l in body["logged"]}


def test_voice_with_history_and_offline_answer(provider, kb):
    c = client_for(provider, kb, "Can I still do the EVA tomorrow?")
    r = c.post("/api/chat/voice",
               data={"astronaut_id": "sara", "history": json.dumps([{"role": "assistant", "content": "Hi"}])},
               files={"audio": ("speech.webm", b"abc", "audio/webm")})
    assert r.status_code == 200 and "flight surgeon" in r.json()["reply"]


def test_voice_stt_down_returns_503(provider, kb):
    c = client_for(provider, kb, None)
    r = c.post("/api/chat/voice", data={"astronaut_id": "sara"}, files={"audio": ("s.webm", b"abc", "audio/webm")})
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]


def test_bad_history_is_422(provider, kb):
    c = client_for(provider, kb, "hello")
    r = c.post("/api/chat/voice", data={"astronaut_id": "sara", "history": "not json"},
               files={"audio": ("s.webm", b"abc", "audio/webm")})
    assert r.status_code == 422


def test_transcribe_endpoint_and_status(provider, kb):
    c = client_for(provider, kb, "sleep 6 hours")
    assert c.post("/api/transcribe", files={"audio": ("s.wav", b"abc", "audio/wav")}).json() == {"text": "sleep 6 hours"}
    s = c.get("/api/assistant/status").json()
    assert s["stt_available"] is True and s["stt_model"] == "fake-whisper"


# ----------------------------------------------------- spoken numbers ---
@pytest.mark.parametrize("spoken,digits", [
    ("one hundred and twenty", "120"),
    ("thirty eight point five", "38.5"),
    ("ninety-four", "94"),
    ("five", "5"),
])
def test_numbers_to_digits(spoken, digits):
    assert numbers_to_digits(spoken) == digits


def test_spoken_values_extracted():
    got = {x.metric: x.value for x in extract_measurements(
        "I slept five hours, my heart rate is one hundred and ten and temperature thirty eight point two")}
    assert got == {"sleep_h": 5, "hr": 110, "temp_c": 38.2}
