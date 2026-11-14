"""Speech-to-text for voice check-ins (open-source Whisper).

Sends the recording to an OpenAI-compatible /audio/transcriptions endpoint.
By default that is the same host as the chat model (Groq's free plan serves
whisper-large-v3-turbo and whisper-large-v3).

    STT_MODEL=whisper-large-v3-turbo        # fast; fallback: STT_FALLBACK_MODELS=whisper-large-v3
    STT_LANGUAGE=en                         # empty = auto-detect
    STT_BASE_URL / STT_API_KEY              # default to LLM_BASE_URL / LLM_API_KEY
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_STT_MODEL = "whisper-large-v3-turbo"
DEFAULT_STT_FALLBACKS = "whisper-large-v3"
MAX_AUDIO_BYTES = 10 * 1024 * 1024          # ~5 min of compressed speech; check-ins are seconds long
AUDIO_TYPES = {".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
               ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".flac": "audio/flac", ".mpeg": "audio/mpeg",
               ".mpga": "audio/mpeg"}
# Domain words Whisper should expect (improves "EVA", "SpO2", "mSv"...).
VOCAB_PROMPT = ("Astronaut health check-in aboard a spacecraft. Terms: EVA, SpO2, HRV, dosimeter, mSv, CMO, "
                "storm shelter, solar particle event, Commander, crew medical officer.")
# What Whisper typically "hears" in silence or noise.
SILENCE_HALLUCINATIONS = {"", "you", "thank you", "thank you.", "thanks for watching!", "thanks for watching.",
                          "thank you for watching.", "bye.", "bye", ".", "...", "okay.", "so"}


class STTError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


@dataclass
class Transcript:
    text: str
    model: str
    language: Optional[str] = None
    duration_s: Optional[float] = None


class SpeechToText:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None,
                 fallback_models: Optional[list[str]] = None, http=None, timeout: float = 60.0):
        self.base_url = (base_url or os.getenv("STT_BASE_URL") or os.getenv("LLM_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or os.getenv("STT_API_KEY") or os.getenv("LLM_API_KEY") or ""
        self.model = model or os.getenv("STT_MODEL", DEFAULT_STT_MODEL)
        fb = os.getenv("STT_FALLBACK_MODELS", DEFAULT_STT_FALLBACKS) if fallback_models is None \
            else ",".join(fallback_models)
        self.fallback_models = [m.strip() for m in fb.split(",") if m.strip() and m.strip() != self.model]
        self.language = os.getenv("STT_LANGUAGE", "en").strip() or None
        if http is None:
            import httpx
            http = httpx.Client(timeout=timeout)
        self._http = http

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def transcribe(self, audio: bytes, filename: str = "speech.webm",
                   content_type: Optional[str] = None) -> Transcript:
        if not self.available:
            raise STTError("Voice transcription is not configured (set LLM_BASE_URL and LLM_API_KEY, "
                           "or STT_BASE_URL and STT_API_KEY).", 503)
        if not audio:
            raise STTError("The recording is empty.", 400)
        if len(audio) > MAX_AUDIO_BYTES:
            raise STTError(f"The recording is too large ({len(audio) // 1024} KB, max "
                           f"{MAX_AUDIO_BYTES // 1024 // 1024} MB). Keep voice messages short.", 413)
        ext = Path(filename or "").suffix.lower()
        if ext not in AUDIO_TYPES:
            base = (content_type or "").split(";")[0].strip()
            ext = next((e for e, t in AUDIO_TYPES.items() if t == base), ".webm")
        ctype = (content_type or AUDIO_TYPES[ext]).split(";")[0]
        name = f"speech{ext}"

        errors = []
        for model in [self.model, *self.fallback_models]:
            data = {"model": model, "response_format": "verbose_json", "temperature": "0", "prompt": VOCAB_PROMPT}
            if self.language:
                data["language"] = self.language
            try:
                r = self._http.post(f"{self.base_url}/audio/transcriptions",
                                    headers={"Authorization": f"Bearer {self.api_key}"},
                                    files={"file": (name, audio, ctype)}, data=data)
            except Exception as e:      # network down
                errors.append(f"{model}: {type(e).__name__}")
                log.warning("STT request failed on %s: %s", model, e)
                continue
            if r.status_code == 200:
                body = r.json()
                text = re.sub(r"\s+", " ", body.get("text", "")).strip()
                if text.lower() in SILENCE_HALLUCINATIONS:
                    raise STTError("No speech detected. Hold the microphone closer and try again.", 422)
                return Transcript(text=text, model=model, language=body.get("language"),
                                  duration_s=body.get("duration"))
            errors.append(f"{model}: {r.status_code}")
            log.warning("STT failed on %s: %s %s", model, r.status_code, r.text[:200])
            if r.status_code in (401, 403):
                raise STTError("Speech-to-text API key rejected (check LLM_API_KEY / STT_API_KEY).", 502)
            if r.status_code in (400, 413, 415):
                raise STTError(f"The speech service could not read this recording ({r.status_code}).", 422)
        raise STTError("Voice transcription unavailable (" + "; ".join(errors) + "). Please type your message.", 503)
