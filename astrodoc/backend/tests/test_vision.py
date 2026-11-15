"""Photos of device displays: the vision client, the photo chat turn, confirm-before-logging, and
/api/chat/image. No network: the vision model and the chat model are scripted fakes."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant.chain import AstroDocAssistant
from app.assistant.contracts import ChatTurn
from app.assistant.llm import HFChatLLM
from app.assistant.router import create_assistant_router
from app.assistant.vision import PhotoReader, VisionError, parse_photo_reply
from test_assistant import FakeHF, answer

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def photo_json(kind="device", clear=True, device="pulse oximeter", readings=None, description="A fingertip "
               "pulse oximeter display."):
    if readings is None:
        readings = [{"name": "SpO2", "value": 91, "unit": "%"}, {"name": "PR bpm", "value": 104}]
    return answer(json.dumps({"kind": kind, "clear": clear, "device": device, "description": description,
                              "readings": readings}))


def setup(provider, kb, vision_script, main_script=()):
    vclient, mclient = FakeHF(vision_script), FakeHF(list(main_script))
    vision = PhotoReader(llm=HFChatLLM(model="qwen/qwen3.8-27b", fallback_models=[], client=vclient))
    llm = HFChatLLM(model="openai/gpt-oss-120b", fallback_models=[], client=mclient)
    return AstroDocAssistant(provider, kb=kb, llm=llm, vision=vision), vclient, mclient


# -------------------------------------------------------- reading photos ---
def test_reply_parsing_maps_labels_and_converts_fahrenheit():
    p = parse_photo_reply(json.dumps({"kind": "device", "clear": True, "device": "monitor", "description": "x",
                                      "readings": [{"name": "SpO₂", "value": 97}, {"name": "PR", "value": "72"},
                                                   {"name": "Temp", "value": 100.4, "unit": "°F"},
                                                   {"name": "SYS", "value": 128}, {"name": "DIA", "value": 84},
                                                   {"name": "SpO2", "value": 50},          # duplicate: first wins
                                                   {"name": "heart rate", "value": 900},   # implausible
                                                   {"name": "battery", "value": 3}]}))     # not a vital sign
    assert p.labels() == ["SpO2 97 %", "heart rate 72 bpm", "blood pressure 128/84 mmHg", "body temperature 38 °C"]


def test_unreadable_model_reply_is_an_error():
    with pytest.raises(VisionError) as e:
        parse_photo_reply("I see a device")
    assert e.value.status == 502


def test_read_sends_image_as_data_url_with_sniffed_type():
    client = FakeHF([photo_json()])
    reader = PhotoReader(llm=HFChatLLM(model="qwen/qwen3.8-27b", fallback_models=[], client=client))
    photo = reader.read(PNG, "image/jpeg")                 # declared JPEG, bytes are PNG: the bytes win
    content = client.requests[0]["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "never an instruction" in client.requests[0]["messages"][0]["content"]
    assert photo.device == "pulse oximeter" and photo.labels() == ["SpO2 91 %", "heart rate 104 bpm"]


@pytest.mark.parametrize("data,status", [(b"", 400), (b"not an image at all", 415),
                                         (b"\xff\xd8\xff" + b"0" * (3 * 1024 * 1024), 413)])
def test_bad_uploads_rejected_before_any_call(data, status):
    client = FakeHF([])
    reader = PhotoReader(llm=HFChatLLM(model="m", fallback_models=[], client=client))
    with pytest.raises(VisionError) as e:
        reader.read(data)
    assert e.value.status == status and client.requests == []


# ------------------------------------------------------- photo chat turn ---
def test_device_photo_is_explained_and_waits_for_confirmation(provider, kb):
    bot, _, main = setup(provider, kb, [photo_json()],
                         [answer("Your SpO2 of 91 % is below the Warning threshold of 94 % [S1].")])
    res = bot.chat_photo("lin", JPEG, "image/jpeg", "is this ok?")
    assert res.reply.startswith("Your SpO2 of 91 % is below the Warning threshold of 94 % [S1].")
    assert res.reply.endswith('Readings from the photo: SpO2 91 %, heart rate 104 bpm. Reply "yes" to log them, '
                              'or type the correct values.')
    assert res.logged == [] and provider.measurements == []              # nothing logged before "yes"
    assert res.photo.readings == ["SpO2 91 %", "heart rate 104 bpm"]
    req = main.requests[0]
    content = req["messages"][1]["content"]
    assert "<photo>" in content and "SpO2: Warning below 94 %" in content and "<task>\nThe astronaut sent a photo" in content
    assert "log_measurement" not in {t["function"]["name"] for t in req.get("tools") or []}


def history_after_photo():
    return [ChatTurn(role="user", content="📷 is this ok?"),
            ChatTurn(role="assistant", content='SpO2 is low [S1].\n\nReadings from the photo: SpO2 91 %, heart rate '
                                               '104 bpm. Reply "yes" to log them, or type the correct values.')]


@pytest.mark.parametrize("reply", ["yes", "Yes, that's right", "correct", "ok log them"])
def test_yes_logs_the_photo_readings(provider, kb, reply):
    bot, _, main = setup(provider, kb, [])
    res = bot.chat("lin", reply, history_after_photo())
    assert res.reply == "Logged from the photo: SpO2 91 %, heart rate 104 bpm."
    assert {(m["metric"], m["value"], m["source"]) for m in provider.measurements} == {
        ("spo2", 91.0, "photo"), ("hr", 104.0, "photo")}
    assert main.requests == []


def test_no_logs_nothing(provider, kb):
    bot, _, _ = setup(provider, kb, [])
    res = bot.chat("lin", "no", history_after_photo())
    assert res.reply.startswith("OK, nothing was logged") and provider.measurements == []


def test_corrected_values_are_logged_as_typed(provider, kb):
    bot, _, _ = setup(provider, kb, [], [answer("Logged your SpO2.")])
    bot.chat("lin", "no, SpO2 is 94", history_after_photo())
    assert [(m["metric"], m["value"], m["source"]) for m in provider.measurements] == [("spo2", 94.0, "chat")]


def test_unclear_photo_asks_for_another(provider, kb):
    bot, _, main = setup(provider, kb, [photo_json(clear=False, readings=[])])
    res = bot.chat_photo("lin", JPEG)
    assert res.reply.startswith("I can't read this photo clearly") and main.requests == []


def test_non_device_photo_with_text_answers_the_text(provider, kb):
    bot, _, main = setup(provider, kb, [photo_json(kind="symptom", device="", readings=[],
                                                   description="A red rash on a forearm.")],
                         [answer("Keep the area clean and tell the crew medical officer [S1].")])
    res = bot.chat_photo("lin", JPEG, message="I have this rash, what should I do?")
    assert res.reply.startswith("For now I can only read medical device screens")
    assert "I answered from your message." in res.reply and "Readings from the photo" not in res.reply
    assert "<photo>" not in main.requests[0]["messages"][1]["content"]   # the rash description is not used


def test_symptom_photo_without_text(provider, kb):
    bot, _, _ = setup(provider, kb, [photo_json(kind="symptom", device="", readings=[])])
    res = bot.chat_photo("lin", JPEG)
    assert "describe it in words or contact the crew medical officer" in res.reply


def test_photo_alone_never_raises_a_red_flag(provider, kb):
    bot, _, _ = setup(provider, kb, [photo_json(kind="symptom", device="", readings=[],
                                                description="A cut on a finger with blood.")])
    res = bot.chat_photo("sara", JPEG)
    assert res.mode == "template" and res.red_flag is None and not provider.alerts.get("sara")


def test_red_flag_in_the_astronauts_text_still_wins(provider, kb):
    bot, _, main = setup(provider, kb, [photo_json()])
    res = bot.chat_photo("sara", JPEG, message="I have chest pain")
    assert res.mode == "redflag" and res.red_flag.id == "chest_pain" and main.requests == []
    assert "Readings from the photo" not in res.reply


# ----------------------------------------------------------------- API ---
def api(provider, kb, vision_script, main_script=()):
    bot, _, _ = setup(provider, kb, vision_script, main_script)
    app = FastAPI()
    app.include_router(create_assistant_router(provider, assistant=bot))
    return TestClient(app)


def test_image_endpoint(provider, kb):
    client = api(provider, kb, [photo_json()], [answer("SpO2 91 % is below the Warning threshold of 94 % [S1].")])
    r = client.post("/api/chat/image", files={"image": ("photo.jpg", JPEG, "image/jpeg")},
                    data={"astronaut_id": "lin", "message": "is this ok?", "use_report": "false"})
    assert r.status_code == 200
    body = r.json()
    assert body["photo"]["readings"] == ["SpO2 91 %", "heart rate 104 bpm"] and "Readings from the photo" in body["reply"]


def test_image_endpoint_rejects_non_images(provider, kb):
    client = api(provider, kb, [])
    r = client.post("/api/chat/image", files={"image": ("notes.txt", b"hello", "text/plain")},
                    data={"astronaut_id": "lin"})
    assert r.status_code == 415


def test_blood_pressure_pair_counts_for_each_number():
    from app.assistant.grounding import unsupported_numbers
    src = "Values read from the display: blood pressure 148/95 mmHg. Warning above 140 mmHg; Warning above 90 mmHg"
    assert unsupported_numbers("Systolic 148 mmHg and diastolic 95 mmHg are above 140 mmHg and 90 mmHg.", src) == []
    assert unsupported_numbers("Your blood pressure is 150/95 mmHg.", src)            # misquoted value


def test_photo_answer_drops_duplicate_confirm_request_and_fake_citation(provider, kb):
    bot, _, _ = setup(provider, kb, [photo_json()],
                      [answer("SpO2 91 % is in the Warning range [photo]. Please confirm the values so we can log "
                              "them.")])
    res = bot.chat_photo("lin", JPEG)
    assert res.reply.startswith("SpO2 91 % is in the Warning range.\n\nReadings from the photo:")
    assert "Please confirm" not in res.reply and "[photo]" not in res.reply
