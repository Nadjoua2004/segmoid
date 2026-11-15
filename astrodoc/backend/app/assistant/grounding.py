"""Grounding for each chat turn.

Before the answer - select_relevant(): a small, fast model reads the astronaut's message and the
retrieved candidates (knowledge-base passages, countermeasure cards, today's flagged findings) and
keeps only the ones that actually help answer it. Similarity scores cannot do this: for "I have a
headache, what treatment should I get?" an unrelated bed-rest/vertigo passage scores higher than the
CO2-headache brief. If nothing is relevant, it proposes a better search query for one more try.

After the answer - checks in code, no model:
  unsupported_claims()  the reply calls a metric high/low/elevated that is not a finding
                        ("address the elevated CO2" when CO2 was never measured)
  unrequested_verdict() the reply says "you can stay on duty / go on the mission" when nobody asked
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .metrics_meta import METRICS

log = logging.getLogger(__name__)

HELPER_MODEL = "openai/gpt-oss-20b"

SELECT_PROMPT = """You are the retrieval filter of AstroDoc, the onboard medical assistant of a space crew.
You get the astronaut's newest message and numbered candidates:
P = knowledge-base passages, C = countermeasure cards, F = the astronaut's flagged findings from today's check-in.

1. type, one of:
   greeting (hello, small talk) | thanks | symptom (a symptom or health problem, or what to do about one) |
   log (reporting values or how they feel, no question) | status (how am I doing, my results) |
   go_no_go (can I do a mission, EVA, exercise or duty) | information (a general question about health,
   the body or spaceflight) | other (not about health or the mission)
2. passages, cards: keep only those about the same symptom, condition or question. Sharing a word is not
   enough. When in doubt, leave it out; empty lists are fine.
3. findings: keep those that could explain or affect what the astronaut asks about (for a headache: short
   sleep, high cabin CO2, high blood pressure ...). For status or go_no_go, keep every finding.
4. search_query: 3-8 English words with medical terms that would find knowledge for this message.

Reply with JSON only, no other text:
{"type": "...", "passages": ["P1"], "cards": ["C1"], "findings": ["F1"], "search_query": "..."}"""

MESSAGE_TYPES = {"greeting", "thanks", "symptom", "log", "status", "go_no_go", "information", "other"}


@dataclass
class Selection:
    passages: list = field(default_factory=list)
    cards: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    kind: str = ""                 # one of MESSAGE_TYPES; "" when the filter did not run
    search_query: str = ""
    filtered: bool = True          # False: the filter could not run, candidates were kept unchecked


def _snip(text: str, n: int) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " ..."


def parse_json_object(text: str) -> Optional[dict]:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def finding_label(m) -> str:
    name = METRICS.get(m.metric, {}).get("name", m.metric.replace("_", " "))
    val = f" = {m.value:g} {m.unit}".rstrip() if m.value is not None else ""
    return f"{name}{val} ({m.level})"


def select_relevant(llm, message: str, earlier: list[str], passages: list[dict], cards: list,
                    findings: list) -> Selection:
    """One call to the helper model. Raises on API errors or unreadable output (caller falls back)."""
    lines = [f"Newest message: {message}"]
    if earlier:
        lines.append("Earlier questions in this chat (context for follow-ups only): " + " | ".join(earlier))
    if passages:
        lines.append("Passages:")
        lines += [f"P{i}. {p['title']}: {_snip(p['text'], 450)}" for i, p in enumerate(passages, 1)]
    if cards:
        lines.append("Countermeasure cards:")
        lines += [f"C{i}. {c.title} ({c.topic}): {_snip(' '.join(c.steps), 160)}" for i, c in enumerate(cards, 1)]
    if findings:
        lines.append("Flagged findings:")
        lines += [f"F{i}. {finding_label(m)}" for i, m in enumerate(findings, 1)]
    reply = llm.complete([{"role": "system", "content": SELECT_PROMPT},
                          {"role": "user", "content": "\n".join(lines)}], None)
    data = parse_json_object(reply.text)
    if data is None:
        raise ValueError(f"retrieval filter returned no JSON: {reply.text[:120]!r}")

    def pick(key: str, prefix: str, items: list) -> list:
        out = []
        for ref in data.get(key) or []:
            m = re.fullmatch(rf"{prefix}?(\d+)", str(ref).strip(), flags=re.I)
            if m and 1 <= int(m.group(1)) <= len(items) and items[int(m.group(1)) - 1] not in out:
                out.append(items[int(m.group(1)) - 1])
        return out

    kind = str(data.get("type") or "").strip().lower().replace("-", "_").replace("/", "_")
    return Selection(passages=pick("passages", "P", passages), cards=pick("cards", "C", cards),
                     findings=pick("findings", "F", findings),
                     kind=kind if kind in MESSAGE_TYPES else "information",
                     search_query=str(data.get("search_query") or "").strip())


# ----------------------------------------------- answer quality checks ---
# Run in code on every model answer; no extra model call. Each returns the sentences to remove.
_CITE = re.compile(r"\[S\d+\]")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")
# Sentences that are generic safety advice or meta statements: never removed for lack of a source.
_SAFE = re.compile(r"crew medical officer|\bcmo\b|flight surgeon|mission control|knowledge base|daily check-in|"
                   r"persists?|worse|worsens|logged|recorded|go/no-go", re.I)
_COMMON = set("""about above after again against along already also always another anything around because before
being below between better both cannot could doing during each either enough every first follow following further
going having helps here into itself keeps later least less likely little makes many might more most much must
needs never next often only other others over right same should since small some something still such sure taking
than that their them then there these they things think this those though through today together tomorrow under
until using usually very want well were what when where whether which while within without would your yours
youre important possible general normal level levels value values check right away quickly""".split())


def _numbers(text: str) -> set[str]:
    out = set()
    for n in _NUMBER.findall(text or ""):
        n = n.replace(",", ".")
        try:
            f = float(n)
        except ValueError:
            continue
        out.add(f"{f:g}")
    return out


# Units that make a number a claim; "2 L" must match a "2 L" (or "2 liters") in the sources, not any "2".
_UNITS = {
    "h": r"h|hrs?|hours?", "min": r"min|mins|minutes?", "s": r"s|sec|seconds?", "d": r"days?", "wk": r"weeks?",
    "mo": r"months?", "yr": r"years?", "l": r"l|liters?|litres?", "ml": r"ml|milliliters?|millilitres?",
    "mg": r"mg|milligrams?", "g": r"g|grams?", "kg": r"kg|kilograms?", "kcal": r"kcal|calories?",
    "mmhg": r"mmhg", "msv": r"msv|millisieverts?", "bpm": r"bpm|beats", "pct": r"%|percent",
    "c": r"°c|°|degrees?", "times": r"times|x",
}
_UNIT_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s?(" + "|".join(f"(?:{v})" for v in _UNITS.values()) +
                      r")(?![a-z])", re.I)


def _unit_key(unit: str) -> str:
    u = unit.lower()
    for key, pattern in _UNITS.items():
        if re.fullmatch(pattern, u, re.I):
            return key
    return u


def _numbers_with_units(text: str) -> set[str]:
    out = set()
    for n, unit in _UNIT_RE.findall(text or ""):
        try:
            out.add(f"{float(n.replace(',', '.')):g} {_unit_key(unit)}")
        except ValueError:
            pass
    return out


# "6.5-9.0 hours" and "148/95 mmHg": every number of a range or pair carries the unit
_PAIR = re.compile(r"(\d+(?:\.\d+)?)\s*([-–/])\s*(\d+(?:\.\d+)?)\s*([a-z%°]+)", re.I)


def _spread_units(text: str) -> str:
    return _PAIR.sub(r"\1 \4 \2 \3 \4", text or "")


def unsupported_numbers(text: str, sources: str) -> list[str]:
    """Sentences with a number that is in no source or the message: a number with a unit must appear with the
    same unit ("drink 2 L" needs "2 L" somewhere, not just any 2), a bare number must appear at all ("CO2 28"
    when 26 was given). Citation markers and list numbers are ignored."""
    known, known_units = _numbers(sources), _numbers_with_units(_spread_units(sources))
    out = []
    for line in (text or "").splitlines():
        for sent in split_sentences(line):
            body = _CITE.sub("", re.sub(r"^\s*\d+[.)]\s+", "", sent))
            if _numbers(body) - known or _numbers_with_units(_spread_units(body)) - known_units:
                out.append(sent)
    return out


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{5,}", (text or "").lower())}


# Advice: an imperative ("Use the dental kit") or a sentence telling the astronaut what to do.
_ADVICE = re.compile(
    r"^\W*(?:\d+[.)]\s*)?(?:then,?\s+|also,?\s+|first,?\s+|next,?\s+)?(?:use|apply|take|drink|stay|rest|move|go|"
    r"avoid|increase|reduce|keep|check|verify|ensure|open|relocate|perform|follow|try|put|place|rinse|wash|eat|"
    r"limit|stop|start|call|ask|monitor|wear|adjust|sit|lie|breathe|hydrate|spend|consider|make|set|turn|switch|"
    r"schedule|do|don't|never|always|add|remove|clean|cover|press|hold|repeat|record|measure)\b"
    r"|\byou (?:should|can|could|may|must|need to|might want to)\b|\btry to\b|\bmake sure\b", re.I)


def uncited_specifics(text: str, sources: str, min_novel: int = 3, ratio: float = 0.4,
                      advice_only: bool = False) -> list[str]:
    """Sentences with no citation whose specific words mostly come from nowhere in the sources: advice the
    model made up ("use the antiseptic rinse from the dental kit"). Generic safety lines are kept.
    advice_only: check only sentences that tell the astronaut what to do (for general questions, where a
    plain definition such as "microgravity is free fall" need not be in the knowledge base)."""
    known = _stems(sources)
    out = []
    for line in (text or "").splitlines():
        for sent in split_sentences(line):
            if _CITE.search(sent) or _SAFE.search(sent):
                continue
            if advice_only and not _ADVICE.search(sent):
                continue
            words = [w for w in re.findall(r"[a-z]{5,}", sent.lower()) if w not in _COMMON]
            novel = [w for w in words if w[:5] not in known]
            if len(novel) >= min_novel and len(novel) >= ratio * len(words):
                out.append(sent)
    return out


# --------------------------------------------------------------- checks ---
# Words that name a metric in a reply. bp_dia shares "blood pressure" with bp_sys.
METRIC_WORDS: dict[str, str] = {
    "cabin_co2": r"co2|co₂|carbon dioxide",
    "rad_msv": r"radiation(?: dose| exposure| levels?)?|dosimeter(?: readings?)?",
    "hr": r"heart rate|pulse",
    "spo2": r"spo2|spo₂|oxygen saturation|blood oxygen",
    "bp_sys": r"blood pressure",
    "temp_c": r"(?:body )?temperature",
    "glucose": r"(?:blood )?glucose|blood sugar",
    "sleep_h": r"sleep",
    "mood": r"mood",
    "hrv_ms": r"hrv|heart[- ]rate variability",
}
SAME_METRIC = {"bp_dia": "bp_sys"}

_STATE = (r"elevated|high(?:er)?|low(?:er)?|raised|increased|decreased|reduced|abnormal|out of range|"
          r"outside(?: of)?(?: its| the| your)?(?: normal)? range|above|below|too (?:high|low|much|little)|"
          r"poor|insufficient|deficient|inadequate|short|dropp(?:ed|ing)|rising|spik(?:e|ed|ing)")
# A clause with one of these is general knowledge ("high CO2 can cause headaches"), not a claim.
_GENERAL = re.compile(r"\b(can|could|may|might|if|when|whether|often|usually|typically|commonly|such as|"
                      r"for example|e\.g|risk of|in general|generally|known to|tends? to)\b", re.I)
_CLAUSE_SPLIT = re.compile(r"[,;:()]|\bbut\b|\bwhile\b|\bwhereas\b|\band\b", re.I)


def _near(metric_re: str) -> re.Pattern:
    m, s = rf"(?:{metric_re})", rf"(?:{_STATE})"
    return re.compile(rf"(?<![\w-]){s}(?!\w)\W+(?:[\w-]+\W+){{0,3}}?{m}(?!\w)|"
                      rf"(?<![\w-]){m}(?!\w)\W+(?:[\w-]+\W+){{0,4}}?{s}(?!\w)", re.I)


def _specific(metric_re: str) -> re.Pattern:
    """The clause is about this astronaut's / this cabin's value, not a general fact:
    "your CO2", "you have low SpO2", "the elevated CO2", "CO2 is elevated"."""
    m, s = rf"(?:{metric_re})", rf"(?:{_STATE})"
    return re.compile(
        rf"\b(?:your|you have|you've got|you're|you are)\s+(?:[\w-]+\s+){{0,2}}?{m}(?!\w)|"
        rf"\b(?:the|this|that|current|today's|cabin|module)\s+(?:[\w-]+\s+)?{s}\s+(?:[\w-]+\s+)?{m}(?!\w)|"
        rf"(?<![\w-]){m}(?:\s+[\w-]+){{0,2}}\s+(?:is|are|was|were|has been|have been|remains?|stays?|looks?|"
        rf"reads?|seems?)\s+(?:still\s+|now\s+|currently\s+|very\s+|too\s+|a bit\s+|slightly\s+)?{s}(?!\w)", re.I)


_NEAR = {k: _near(v) for k, v in METRIC_WORDS.items()}
_SPECIFIC = {k: _specific(v) for k, v in METRIC_WORDS.items()}


def mentioned_metrics(text: str) -> set[str]:
    return {k for k, v in METRIC_WORDS.items() if re.search(rf"(?<!\w)(?:{v})(?!\w)", text or "", re.I)}


def allowed_key(metric: str) -> str:
    return SAME_METRIC.get(metric, metric)


_LIST_MARKER = re.compile(r"^(\s*(?:\d+[.)]|[-*•])\s+)")


def split_sentences(line: str) -> list[str]:
    """Sentences of one line. A leading list marker ("1. ", "- ") stays with the first sentence."""
    m = _LIST_MARKER.match(line or "")
    marker, body = (m.group(1), line[m.end():]) if m else ("", line or "")
    sents = [s for s in re.split(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])", body) if s.strip()]
    if sents and marker:
        sents[0] = marker + sents[0]
    return sents


def unsupported_claims(text: str, allowed: set[str]) -> list[tuple[str, str]]:
    """(sentence, metric) for each sentence that states the astronaut's metric is high/low/abnormal
    when that metric is not in `allowed` (flagged findings + values the astronaut gave)."""
    out = []
    for line in (text or "").splitlines():
        for sent in split_sentences(line):
            for metric, near in _NEAR.items():
                if metric in allowed:
                    continue
                for clause in _CLAUSE_SPLIT.split(sent):
                    if not clause or not near.search(clause):
                        continue
                    if _SPECIFIC[metric].search(clause) and not (_GENERAL.search(clause)
                                                                and not re.search(r"\byour?\b", clause, re.I)):
                        out.append((sent, metric))
                        break
    return out


_DUTY = r"(?:duty|duties|missions?|eva|evas|spacewalks?|work|tasks?|shifts?|exercise|workouts?|operations?)"
_POSITIVE_VERDICT = re.compile(
    r"\b(?:yes,?\s+)?(?:you can|you may|you're|you are|you remain|you can still|you may still)\b[^.!?\n]{0,40}?"
    rf"\b(?:stay on|continue(?: with)?|proceed(?: with)?|return to|go on|go ahead(?: with)?|do|carry on with|"
    rf"cleared for|fit for|good to go|ok to|okay to|safe to|ready for)\b[^.!?\n]{{0,25}}?\b{_DUTY}\b", re.I)
_NEGATIVE_VERDICT = re.compile(
    r"\b(?:no,?\s+)?(?:you (?:should not|shouldn't|must not|mustn't|cannot|can't|may not)|you are not|you're not|"
    rf"you aren't)\b[^.!?\n]{{0,40}}?\b{_DUTY}\b", re.I)


_CONDITIONAL = re.compile(r"\b(?:if|once|after|when|unless|as long as)\b", re.I)


def unrequested_verdict(sentence: str, include_negative: bool) -> bool:
    """A go/no-go statement ("Yes, you can stay on duty") nobody asked for. Conditional advice
    ("you can do light exercise once the headache eases") is not a verdict."""
    if _CONDITIONAL.search(sentence):
        return False
    return bool(_POSITIVE_VERDICT.search(sentence)) or (include_negative and bool(_NEGATIVE_VERDICT.search(sentence)))


def drop_sentences(text: str, drop) -> str:
    """Remove every sentence for which drop(sentence) is true; keep line structure."""
    lines = []
    for line in (text or "").splitlines():
        sents = split_sentences(line)
        kept = [s for s in sents if not drop(s)]
        if sents and not kept:
            continue
        lines.append(" ".join(kept) if sents else line)
    # a heading such as "For a SpO2 warning you should:" whose list items were all removed
    is_item = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
    cleaned = []
    for i, line in enumerate(lines):
        if line.rstrip().endswith(":"):
            nxt = next((ln for ln in lines[i + 1:] if ln.strip()), None)
            if nxt is None or not is_item.match(nxt):
                continue
        cleaned.append(line)
    out = "\n".join(cleaned)
    return re.sub(r"\n{3,}", "\n\n", out).strip()
