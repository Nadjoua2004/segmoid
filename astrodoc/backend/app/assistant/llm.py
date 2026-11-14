"""Open-source LLM access through the Hugging Face Inference API.

Uses `huggingface_hub.InferenceClient` (OpenAI-style chat + tool calling),
routed by Hugging Face to a provider that serves the open model.

    HF_TOKEN=hf_...                         # https://huggingface.co/settings/tokens ("Make calls to Inference Providers")
    LLM_MODEL=openai/gpt-oss-120b           # Apache-2.0 open weights
    LLM_FALLBACK_MODELS=Qwen/Qwen3.8-27B    # comma-separated, tried in order if the main model fails
    HF_PROVIDER=auto                        # or groq, cerebras, deepinfra, novita, ...
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_FALLBACKS = "Qwen/Qwen3.8-27B"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Optional[dict]          # None when the model produced invalid JSON
    raw_arguments: str = ""


@dataclass
class LLMReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    model: str = ""

    def assistant_message(self) -> dict:
        """The reply in OpenAI message format, to append to the conversation."""
        msg: dict[str, Any] = {"role": "assistant", "content": self.text or ""}
        if self.tool_calls:
            msg["tool_calls"] = [{"id": tc.id, "type": "function",
                                  "function": {"name": tc.name,
                                               "arguments": tc.raw_arguments or json.dumps(tc.arguments or {})}}
                                 for tc in self.tool_calls]
        return msg


class LLMError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, retry_after: Optional[float] = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


MAX_RATE_LIMIT_WAIT_S = 12.0


def _status_of(e: Exception) -> Optional[int]:
    resp = getattr(e, "response", None)
    return getattr(resp, "status_code", None)


def _retry_after(e: Exception) -> float:
    """Seconds the host asks us to wait after a 429 (defaults to 5)."""
    headers = getattr(getattr(e, "response", None), "headers", None) or {}
    try:
        return max(0.0, float(headers.get("retry-after", 5)))
    except (TypeError, ValueError):
        return 5.0


class HFChatLLM:
    def __init__(self, model: Optional[str] = None, fallback_models: Optional[list[str]] = None,
                 provider: Optional[str] = None, token: Optional[str] = None,
                 client=None, timeout: float = 60.0, max_tokens: int = 1500):
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        fb = os.getenv("LLM_FALLBACK_MODELS", DEFAULT_FALLBACKS) if fallback_models is None else ",".join(fallback_models)
        self.fallback_models = [m.strip() for m in fb.split(",") if m.strip() and m.strip() != self.model]
        self.max_tokens = max_tokens
        self.reasoning_effort = os.getenv("LLM_REASONING_EFFORT", "low").strip()
        self.base_url = os.getenv("LLM_BASE_URL", "").strip() or None
        if client is not None:
            self.client = client
        else:
            from huggingface_hub import InferenceClient
            if self.base_url:   # any OpenAI-compatible host serving open models
                self.client = InferenceClient(base_url=self.base_url, timeout=timeout,
                                              api_key=os.getenv("LLM_API_KEY") or token or os.getenv("HF_TOKEN"))
            else:               # Hugging Face Inference Providers
                self.client = InferenceClient(provider=provider or os.getenv("HF_PROVIDER", "auto"),
                                              token=token or os.getenv("HF_TOKEN"), timeout=timeout)

    @staticmethod
    def configured() -> bool:
        if os.getenv("HF_TOKEN") or (os.getenv("LLM_BASE_URL") and os.getenv("LLM_API_KEY")):
            return True
        try:  # token saved by `hf auth login`
            from huggingface_hub import get_token
            return bool(get_token())
        except Exception:
            return False

    def complete(self, messages: list[dict], tools: Optional[list[dict]] = None) -> LLMReply:
        """One chat completion. Tries the main model, then each fallback model.
        If a provider rejects the tool definitions, retries that model without tools."""
        try:
            return self._try_models(messages, tools)
        except LLMError as e:
            # Every model is rate-limited (free tiers): if the host asks for a short wait, wait once and retry.
            if e.retry_after is not None and e.retry_after <= MAX_RATE_LIMIT_WAIT_S:
                log.info("All models rate-limited; waiting %.1fs and retrying once", e.retry_after)
                time.sleep(e.retry_after + 0.5)
                return self._try_models(messages, tools)
            raise

    def _try_models(self, messages: list[dict], tools: Optional[list[dict]]) -> LLMReply:
        errors, waits = [], []
        for model in [self.model, *self.fallback_models]:
            # gpt-oss models accept reasoning_effort; "low" halves hidden reasoning tokens, which matters
            # on free tiers limited in tokens per minute. First attempt: full request; if the host rejects
            # it (400/422), one plainer retry without tools and without reasoning_effort.
            effort = {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort and "gpt-oss" in model else None
            attempts = [(bool(tools), effort)]
            if tools or effort:
                attempts.append((False, None))
            for use_tools, extra in attempts:
                try:
                    out = self.client.chat_completion(
                        messages=messages, model=model, max_tokens=self.max_tokens, temperature=0.2,
                        **({"tools": tools, "tool_choice": "auto"} if use_tools else {}),
                        **({"extra_body": extra} if extra else {}))
                    return self._parse(out, model)
                except Exception as e:
                    status = _status_of(e)
                    if status == 429:
                        waits.append(_retry_after(e))
                    errors.append(f"{model}{'' if use_tools else ' (no tools)'}: {status or type(e).__name__}")
                    log.warning("LLM call failed on %s (tools=%s): %s", model, use_tools, e)
                    if status in (401, 403):            # bad token: no point trying other models
                        raise LLMError("API key rejected (check LLM_API_KEY, or HF_TOKEN if LLM_BASE_URL is empty)",
                                       status) from e
                    if status == 402:
                        raise LLMError("no Inference credits left on this Hugging Face account - add credits at "
                                       "https://huggingface.co/settings/billing", status) from e
                    if status not in (400, 422):
                        break                            # only a 400/422 is worth the plainer retry
        all_limited = bool(waits) and len(waits) == len(errors)
        raise LLMError("All models failed: " + "; ".join(errors),
                       retry_after=min(w for w in waits) if all_limited else None)

    @staticmethod
    def _parse(out, model: str) -> LLMReply:
        choice = out.choices[0]
        msg = choice.message
        calls = []
        for i, tc in enumerate(getattr(msg, "tool_calls", None) or []):
            fn = tc.function
            raw = fn.arguments
            if isinstance(raw, dict):
                args, raw_s = raw, json.dumps(raw)
            else:
                raw_s = raw or "{}"
                try:
                    args = json.loads(raw_s)
                    if not isinstance(args, dict):
                        args = None
                except json.JSONDecodeError:
                    args = None
            calls.append(ToolCall(id=getattr(tc, "id", None) or f"call_{i}", name=fn.name,
                                  arguments=args, raw_arguments=raw_s))
        return LLMReply(text=(msg.content or "").strip(), tool_calls=calls,
                        finish_reason=getattr(choice, "finish_reason", "") or "", model=model)
