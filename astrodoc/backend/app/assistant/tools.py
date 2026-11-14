"""Tools AstroDoc AI can call (SPEC §7.2).

Every tool only READS triage results; none can change a triage level.
A ToolSession lives for one chat turn and collects what the UI needs:
citations (S1, S2 ...), logged measurements, countermeasure cards and
whether a crew alert was triggered.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .contracts import Citation, CountermeasureCard, LoggedMeasurement
from .countermeasures import dedupe, find_cards
from .data_provider import AstroDataProvider
from .metrics_meta import FORECAST_TARGETS, LOGGABLE_METRICS, METRICS, SYMPTOM_METRIC, in_plausible_range

HAZARDS = ["Radiation", "Isolation", "Distance", "Gravity", "Hostile environment"]
TOPICS = ["radiation", "fatigue", "cardiovascular", "spo2", "glucose", "fever", "mood"]


def tool_definitions(crew_ids: list[str]) -> list[dict]:
    """Tools in the OpenAI function-calling format used by Hugging Face Inference Providers."""
    astro = {"type": "string", "enum": crew_ids, "description": "Crew member id, e.g. the one in <turn_context>."}

    def tool(name: str, description: str, props: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required}}}

    return [
        tool("get_triage",
             "Current triage result for an astronaut from the triage engine: overall level, per-metric levels "
             "with reasons, ranked NASA hazard risks with scores, and the classifier's main factors. Read-only.",
             {"astronaut_id": astro}, ["astronaut_id"]),
        tool("get_metric_history",
             "Daily values of one metric over the last N mission days, with the astronaut's pre-flight baseline "
             "mean and standard deviation. Use it to describe trends.",
             {"astronaut_id": astro,
              "metric": {"type": "string", "enum": sorted(METRICS)},
              "days": {"type": "integer", "description": "1-180"}},
             ["astronaut_id", "metric", "days"]),
        tool("get_forecast",
             "Projection of a metric or of the Readiness Index ('readiness') if current trends continue, with "
             "uncertainty band and days until the Warning / Critical threshold. Always present it as a projection.",
             {"astronaut_id": astro,
              "metric_or_readiness": {"type": "string", "enum": FORECAST_TARGETS},
              "horizon_days": {"type": "integer", "enum": [7, 14, 30]}},
             ["astronaut_id", "metric_or_readiness", "horizon_days"]),
        tool("search_hrp_knowledge",
             "Search the NASA Human Research Program knowledge base (NASA, NASA-STD-3001 technical briefs, CSA, "
             "JAXA and peer-reviewed spaceflight papers). Returns passages with source_id, title and URL to cite.",
             {"query": {"type": "string", "description": "What to look up, in plain words."}}, ["query"]),
        tool("get_countermeasures",
             "Onboard countermeasure cards (protocol / diet / shielding) for a NASA hazard or a specific topic at "
             "a triage level. Give hazard or topic. Each card has a source_id to cite.",
             {"hazard": {"type": "string", "enum": HAZARDS},
              "topic": {"type": "string", "enum": TOPICS},
              "level": {"type": "string", "enum": ["Warning", "Critical"]}},
             ["level"]),
        tool("log_measurement",
             "Record a value or symptom the astronaut reported in chat (source = chat). For symptoms use "
             "metric 'symptom' and put the symptom in note. Sleep in hours, temperature in °C.",
             {"astronaut_id": astro,
              "metric": {"type": "string", "enum": LOGGABLE_METRICS},
              "value": {"type": "number"},
              "note": {"type": "string"}},
             ["astronaut_id", "metric"]),
        tool("trigger_crew_alert",
             "Start the Autonomous Intra-Crew Escalation Protocol now: the crew medical officer (or the commander, "
             "if the CMO is affected) gets a full-screen emergency alert. Use on Critical when the astronaut has "
             "not acknowledged, or when the astronaut asks for help from the crew.",
             {"astronaut_id": astro, "reason": {"type": "string"}}, ["astronaut_id", "reason"]),
    ]


class ToolError(Exception):
    pass


class ToolSession:
    def __init__(self, provider: AstroDataProvider, kb, astronaut_id: str):
        self.provider = provider
        self.kb = kb
        self.astronaut_id = astronaut_id
        self.citations: list[Citation] = []
        self._cite_keys: dict[tuple, str] = {}
        self.logged: list[LoggedMeasurement] = []
        self.cards: list[CountermeasureCard] = []
        self.crew_alert: Optional[dict] = None
        self.calls: list[str] = []

    # ---- sources
    def add_source(self, title: str, url: str = "", page: Optional[int] = None, snippet: str = "") -> str:
        key = (title, url, page)
        if key not in self._cite_keys:
            sid = f"S{len(self.citations) + 1}"
            self._cite_keys[key] = sid
            self.citations.append(Citation(id=sid, title=title, url=url, page=page, snippet=snippet[:300]))
        return self._cite_keys[key]

    # ---- dispatch
    def run(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Execute a tool. Returns (json text, is_error)."""
        self.calls.append(name)
        handler = getattr(self, f"_t_{name}", None)
        if handler is None:
            return json.dumps({"error": f"unknown tool {name}"}), True
        try:
            return json.dumps(handler(**args), ensure_ascii=False, default=str), False
        except (ToolError, KeyError, ValueError, TypeError) as e:
            return json.dumps({"error": str(e)}), True
        except Exception as e:  # backend unavailable etc. - report, don't crash the turn
            return json.dumps({"error": f"{type(e).__name__}: {e}"}), True

    # ---- tools
    def _t_get_triage(self, astronaut_id: str):
        return self.provider.get_triage(astronaut_id).model_dump()

    def _t_get_metric_history(self, astronaut_id: str, metric: str, days: int):
        h = self.provider.get_metric_history(astronaut_id, metric, max(1, min(int(days), 180)))
        return h.model_dump()

    def _t_get_forecast(self, astronaut_id: str, metric_or_readiness: str, horizon_days: int):
        if horizon_days not in (7, 14, 30):
            raise ToolError("horizon_days must be 7, 14 or 30")
        f = self.provider.get_forecast(astronaut_id, metric_or_readiness, horizon_days)
        data = f.model_dump()
        data["label"] = "projection if current trends continue - not a certainty or a diagnosis"
        return data

    def _t_search_hrp_knowledge(self, query: str):
        hits = self.kb.search(query, k=4)
        if not hits:
            return {"results": [], "note": "No passages found. Say the knowledge base has no answer; do not guess."}
        results = []
        for h in hits:
            sid = self.add_source(h["title"], h.get("url", ""), h.get("page"), h["text"])
            results.append({"source_id": sid, "title": h["title"], "url": h.get("url", ""),
                            "page": h.get("page"), "text": h["text"]})
        return {"results": results}

    def _t_get_countermeasures(self, level: str = "Warning", hazard: Optional[str] = None,
                                topic: Optional[str] = None):
        if not hazard and not topic:
            raise ToolError("give a hazard or a topic")
        cards = find_cards(hazard=hazard, topic=topic, level=level)
        self.cards = dedupe(self.cards + cards)
        out = []
        for c in cards:
            sid = self.add_source(c.source_title, c.source_url) if c.source_url else None
            out.append({"source_id": sid, "group": c.group, "level": c.level, "title": c.title,
                        "steps": c.steps, "source": c.source_title,
                        "demo_protocol": c.demo_protocol})
        return {"cards": out}

    def _t_log_measurement(self, astronaut_id: str, metric: str, value: Optional[float] = None,
                           note: Optional[str] = None):
        if metric == SYMPTOM_METRIC:
            if not note:
                raise ToolError("symptom needs a note, e.g. 'headache'")
            value = None
        else:
            if value is None:
                raise ToolError(f"{metric} needs a numeric value")
            if not in_plausible_range(metric, float(value)):
                raise ToolError(f"{value} is outside the plausible range for {metric} "
                                f"({METRICS[metric]['unit']}); ask the astronaut to confirm")
        note = note.strip().lower() if note else None
        for prev in self.logged:  # one log per value per turn (also skips values pre-logged from the message)
            if prev.metric == metric and (prev.value == value if value is not None
                                          else (prev.note or "").lower() == note):
                return {"logged": prev.label, "duplicate": True}
        lm = self.provider.log_measurement(astronaut_id, metric, value, note, source="chat")
        self.logged.append(lm)
        return {"logged": lm.label}

    def _t_trigger_crew_alert(self, astronaut_id: str, reason: str):
        if self.crew_alert:
            return {"status": "already triggered this turn", **self.crew_alert}
        self.crew_alert = self.provider.trigger_crew_alert(astronaut_id, reason)
        return {"status": "Intra-Crew Escalation Protocol started", **self.crew_alert}
