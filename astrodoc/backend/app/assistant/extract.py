"""Rule-based extraction of values from chat text ("slept 5 hours, headache").

Used in offline mode (no LLM) and for the red-flag path. When the LLM is
available it logs values itself through the `log_measurement` tool.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .metrics_meta import SYMPTOM_METRIC, in_plausible_range

NUM = r"(\d{1,3}(?:[.,]\d{1,2})?)"


@dataclass
class Extracted:
    metric: str
    value: Optional[float]
    note: Optional[str] = None


_PATTERNS: list[tuple[str, str]] = [
    ("sleep_h", rf"\bslept\s+(?:only\s+|about\s+|around\s+)?{NUM}\s*(?:h\b|hrs?\b|hours?\b)"),
    ("sleep_h", rf"\b{NUM}\s*(?:h|hrs?|hours?)\s+(?:of\s+)?sleep\b"),
    ("sleep_h", rf"\bsleep\s*(?:was|of|:|=)?\s*{NUM}\s*(?:h\b|hrs?\b|hours?\b)"),
    ("hr", rf"\b(?:heart\s*rate|hr|pulse)\s*(?:is|was|of|at|:|=)?\s*{NUM}\b"),
    ("hr", rf"\b{NUM}\s*bpm\b"),
    ("spo2", rf"\b(?:spo2|sp02|oxygen(?:\s+saturation)?|o2\s*sat|sats?)\s*(?:is|was|of|at|:|=)?\s*{NUM}\s*%?"),
    ("temp_c", rf"\b(?:temp(?:erature)?|fever(?:\s+of)?)\s*(?:is|was|of|at|:|=)?\s*{NUM}\s*(?:°\s*c|c\b|degrees)?"),
    ("glucose", rf"\b(?:glucose|blood\s*sugar|sugar)\s*(?:is|was|of|at|:|=)?\s*{NUM}\b"),
    ("mood", rf"\bmood\s*(?:is|was|of|at|:|=)?\s*([1-5])(?:\s*/\s*5)?\b"),
    ("hrv_ms", rf"\bhrv\s*(?:is|was|of|at|:|=)?\s*{NUM}\s*(?:ms)?\b"),
    ("cabin_co2", rf"\b(?:cabin\s+)?(?:co2|co₂|carbon\s+dioxide)\s*(?:level)?\s*(?:is|was|of|at|:|=)?\s*{NUM}\s*(?:mm\s*hg)?"),
    ("rad_msv", rf"\b(?:dosimeter|dose|radiation)\s*(?:reading)?\s*(?:is|was|of|at|:|=)?\s*{NUM}\s*msv\b"),
]
_BP = re.compile(r"\b(?:bp|blood\s*pressure)\s*(?:is|was|of|at|:|=)?\s*(\d{2,3})\s*/\s*(\d{2,3})\b")

SYMPTOMS = ["headache", "nausea", "dizzy", "dizziness", "vomiting", "back pain", "congestion", "stuffy nose",
            "blurry vision", "fatigue", "tired", "exhausted", "insomnia", "anxious", "anxiety", "cough",
            "sore throat", "muscle pain", "chills", "rash", "eye pain", "chest pain", "short of breath"]


_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), start=2)}
_NUM_WORD = "|".join(list(_UNITS) + list(_TENS) + ["hundred"])
_NUM_PHRASE = re.compile(rf"\b(?:{_NUM_WORD})(?:(?:[\s-]+(?:and[\s-]+)?|[\s-]+point[\s-]+)(?:{_NUM_WORD}))*\b")


def _phrase_to_number(phrase: str) -> str:
    whole, decimals, in_decimal = 0, "", False
    for w in re.split(r"[\s-]+", phrase):
        if w == "and":
            continue
        if w == "point":
            in_decimal = True
        elif in_decimal:
            decimals += str(_UNITS.get(w, 0))
        elif w in _UNITS:
            whole += _UNITS[w]
        elif w in _TENS:
            whole += _TENS[w]
        elif w == "hundred":
            whole = (whole or 1) * 100
    return f"{whole}.{decimals}" if decimals else str(whole)


def numbers_to_digits(text: str) -> str:
    """'one hundred and twenty' -> '120', 'thirty eight point five' -> '38.5' (speech transcripts)."""
    return _NUM_PHRASE.sub(lambda m: _phrase_to_number(m.group(0)), text)


def extract_measurements(text: str) -> list[Extracted]:
    t = numbers_to_digits(text.lower().replace("’", "'"))
    found: dict[str, Extracted] = {}
    m = _BP.search(t)
    if m:
        sys_, dia = float(m.group(1)), float(m.group(2))
        if in_plausible_range("bp_sys", sys_) and in_plausible_range("bp_dia", dia):
            found["bp_sys"] = Extracted("bp_sys", sys_)
            found["bp_dia"] = Extracted("bp_dia", dia)
    for metric, pat in _PATTERNS:
        if metric in found:
            continue
        m = re.search(pat, t)
        if not m:
            continue
        value = float(m.group(1).replace(",", "."))
        if metric == "temp_c" and value > 50:          # Fahrenheit typed by habit
            value = round((value - 32) * 5 / 9, 1)
        if in_plausible_range(metric, value):
            found[metric] = Extracted(metric, value)
    out = list(found.values())
    for s in SYMPTOMS:
        if re.search(rf"\b{re.escape(s)}\b", t) and not re.search(rf"\b(?:no|not|without)\s+(?:\w+\s+)?{re.escape(s)}\b", t):
            out.append(Extracted(SYMPTOM_METRIC, None, s))
    return out
