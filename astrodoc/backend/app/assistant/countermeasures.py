"""Countermeasure cards (config/countermeasures.json): lookup and grouping."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Iterable, Optional

from .contracts import LEVEL_RANK, CountermeasureCard, Triage
from .metrics_meta import METRICS
from .paths import CONFIG_DIR

GROUPS = ("protocol", "diet", "shielding")

# hazard (from the ranked risk list) -> card topics that treat it
HAZARD_TOPICS = {
    "radiation": ["radiation"],
    "isolation": ["fatigue", "mood"],
    "gravity": ["cardiovascular"],
    "hostile environment": ["co2", "spo2", "fever"],
    "distance": ["glucose"],
}


@lru_cache(maxsize=1)
def load_cards() -> tuple[CountermeasureCard, ...]:
    raw = json.loads((CONFIG_DIR / "countermeasures.json").read_text(encoding="utf-8"))
    sources = raw.get("sources", {})
    cards = []
    for c in raw["cards"]:
        src = sources.get(c.get("source", ""), {})
        cards.append(CountermeasureCard(
            id=c["id"], topic=c["topic"], hazard=c["hazard"], level=c["level"], group=c["group"],
            title=c["title"], steps=c["steps"], source_title=src.get("title", "demo protocol"),
            source_url=src.get("url", ""), demo_protocol=bool(c.get("demoProtocol", not src)),
            priority=int(c.get("priority", 5))))
    return tuple(cards)


def card_by_id(card_id: str) -> Optional[CountermeasureCard]:
    return next((c for c in load_cards() if c.id == card_id), None)


def find_cards(hazard: Optional[str] = None, level: Optional[str] = None,
               topic: Optional[str] = None) -> list[CountermeasureCard]:
    """Cards for a hazard or topic. A Critical request also returns the Warning
    cards for the same topic (Critical cards first)."""
    topics: set[str] = set()
    if topic:
        topics.add(topic.lower())
    if hazard:
        h = hazard.lower()
        topics.update(HAZARD_TOPICS.get(h, [h]))
    want = LEVEL_RANK.get(level or "Warning", 1)
    out = [c for c in load_cards()
           if (not topics or c.topic in topics)
           and c.topic != "redflag"
           and 1 <= LEVEL_RANK[c.level] <= max(want, 1)]
    return sorted(out, key=lambda c: (-LEVEL_RANK[c.level], c.priority, GROUPS.index(c.group)))


def cards_for_triage(triage: Triage) -> list[CountermeasureCard]:
    """Pick cards from the metric levels first (most precise), then from ranked risks."""
    picked: list[CountermeasureCard] = []
    for ml in triage.metric_levels:
        if ml.level != "Nominal" and ml.metric in METRICS:
            picked += find_cards(topic=METRICS[ml.metric]["topic"], level=ml.level)
    if not picked:
        for r in triage.ranked_risks:
            if r.level != "Nominal":
                picked += find_cards(hazard=r.hazard, level=r.level)
    return dedupe(picked)


def dedupe(cards: Iterable[CountermeasureCard]) -> list[CountermeasureCard]:
    seen, out = set(), []
    for c in cards:
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
    return out


def group_cards(cards: Iterable[CountermeasureCard]) -> dict[str, list[CountermeasureCard]]:
    grouped: dict[str, list[CountermeasureCard]] = {g: [] for g in GROUPS}
    for c in cards:
        grouped[c.group].append(c)
    return grouped
