"""Red-flag fast path (SPEC §7.2): detect emergency phrases before any LLM call."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from .paths import CONFIG_DIR


@dataclass(frozen=True)
class RedFlagHit:
    id: str
    label: str
    matched: str
    guidance: str
    cards: tuple[str, ...]
    metric_hint: Optional[str]


def _normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text)


@lru_cache(maxsize=1)
def _config() -> tuple[list[dict], list[str]]:
    raw = json.loads((CONFIG_DIR / "redflags.json").read_text(encoding="utf-8"))
    return raw["flags"], [n.lower() for n in raw.get("negations", [])]


def _negated(text: str, start: int, negations: list[str]) -> bool:
    # look at the few words right before the match, within the same clause
    window = text[max(0, start - 30):start]
    window = re.split(r"[.,;!?]| but | and ", window)[-1]
    return any(re.search(rf"\b{re.escape(n)}\b", window) for n in negations)


def detect(text: str) -> Optional[RedFlagHit]:
    """Return the first red flag found in `text`, ignoring negated mentions."""
    norm = _normalize(text)
    flags, negations = _config()
    for flag in flags:
        # literal phrases, plus optional regex "patterns" (typo-tolerant wording, e.g. "spelling blood")
        matchers = [rf"\b{re.escape(p.lower())}\b" for p in flag.get("phrases", [])] + flag.get("patterns", [])
        for rx in matchers:
            for m in re.finditer(rx, norm):
                if not _negated(norm, m.start(), negations):
                    return RedFlagHit(id=flag["id"], label=flag["label"], matched=m.group(0),
                                      guidance=flag["guidance"], cards=tuple(flag.get("cards", [])),
                                      metric_hint=flag.get("metric_hint"))
    return None
