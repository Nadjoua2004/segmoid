"""AstroDoc AI - the interactive clinical chatbot (SPEC §7).

    assistant = AstroDocAssistant(provider)
    assistant.greet("sara")                     # auto-open assessment on Warning/Critical
    assistant.chat("sara", "Can I still do the EVA tomorrow?")

Order of each chat turn:
  1. red-flag fast path (no LLM, instant)
  2. open-source LLM with tools (Hugging Face Inference API, see llm.py)
  3. offline fallback if there is no HF token, the offline toggle is on,
     or the API fails: triage assessment + countermeasure cards + top 3
     knowledge-base passages, values logged with rule-based extraction.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Optional

from .contracts import (LEVEL_RANK, ChatResponse, ChatTurn, Citation, CountermeasureCard, RedFlagInfo,
                        SuggestedAction, Triage, AstronautContext)
from .countermeasures import card_by_id, cards_for_triage, dedupe, group_cards
from .data_provider import AstroDataProvider
from .extract import extract_measurements
from .llm import DEFAULT_MODEL, HFChatLLM, LLMError
from .prompts import FINAL_CALL, GO_NO_GO_WORDS, HAZARD_WORDS, SYSTEM_PROMPT, address, turn_context
from .redflags import detect
from .tools import ToolSession, tool_definitions

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
HISTORY_TURNS = 12
OFFLINE_COOLDOWN_S = 60
CITE_RE = re.compile(r"\[(S\d+)\]")


class AstroDocAssistant:
    def __init__(self, provider: AstroDataProvider, kb=None, llm: Optional[HFChatLLM] = None,
                 offline: Optional[bool] = None):
        if kb is None:
            from app.knowledge.retriever import get_kb
            kb = get_kb()
        self.provider = provider
        self.kb = kb
        self.force_offline = offline if offline is not None else os.getenv("ASTRODOC_OFFLINE", "") == "1"
        self.llm = llm if llm is not None else (None if self.force_offline else self._make_llm())
        self.model = self.llm.model if self.llm else os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self._down_until = 0.0
        self._last_error: Optional[str] = None
        self._tools = tool_definitions([a.id for a in provider.list_crew()])

    @staticmethod
    def _make_llm() -> Optional[HFChatLLM]:
        if not HFChatLLM.configured():
            log.info("No HF_TOKEN: AstroDoc AI runs in offline mode")
            return None
        try:
            return HFChatLLM()
        except Exception as e:
            log.warning("Hugging Face client unavailable (%s): offline mode", e)
            return None

    @property
    def llm_available(self) -> bool:
        return self.llm is not None and not self.force_offline and time.time() >= self._down_until

    # ================================================================ API ===
    def greet(self, astronaut_id: str, use_llm: bool = False, offline: bool = False) -> ChatResponse:
        """Opening message when the panel auto-opens on a Warning/Critical triage."""
        ctx = self.provider.get_context(astronaut_id)
        triage = self.provider.get_triage(astronaut_id)
        if use_llm and not offline and self.llm_available and triage.level != "Nominal":
            try:
                return self._llm_turn(ctx, triage, "(AstroDoc AI opened automatically because the triage result is "
                                      f"{triage.level}. Give the immediate assessment and what to do now.)", [],
                                      proactive=True)
            except Exception as e:
                self._mark_down(e)
        cards = cards_for_triage(triage) if triage.level != "Nominal" else []
        resp = ChatResponse(reply=self._assessment(ctx, triage, cards), mode="template", level=triage.level)
        self._attach_cards(resp, cards)
        resp.actions = self._actions(ctx, triage)
        return resp

    def chat(self, astronaut_id: str, message: str, history: Optional[list[ChatTurn]] = None,
             offline: bool = False) -> ChatResponse:
        history = history or []
        ctx = self.provider.get_context(astronaut_id)
        triage = self.provider.get_triage(astronaut_id)

        hit = detect(message)
        if hit:
            return self._red_flag(ctx, triage, message, hit)

        if offline or not self.llm_available:
            notice = None if offline or self.force_offline else (
                f"AI wording unavailable ({self._last_error}) - offline mode." if self._last_error
                else "AI wording unavailable - offline mode.")
            return self._offline(ctx, triage, message, notice=notice)
        try:
            return self._llm_turn(ctx, triage, message, history)
        except Exception as e:
            self._mark_down(e)
            why = str(e) if isinstance(e, LLMError) else type(e).__name__
            return self._offline(ctx, triage, message, notice=f"AI wording unavailable ({why}) - offline mode.")

    def alert_crew(self, astronaut_id: str, reason: str) -> dict:
        return self.provider.trigger_crew_alert(astronaut_id, reason)

    # ========================================================= red flags ===
    def _red_flag(self, ctx: AstronautContext, triage: Triage, message: str, hit) -> ChatResponse:
        aid = ctx.astronaut.id
        logged = [self.provider.log_measurement(aid, "symptom", None, hit.label, source="chat")]
        for x in extract_measurements(message):
            if x.metric != "symptom":
                logged.append(self.provider.log_measurement(aid, x.metric, x.value, x.note, source="chat"))
        alert = self.provider.raise_alert(aid, "Critical", f"Red-flag symptom reported in chat: {hit.label}")
        responder = "the commander" if ctx.astronaut.is_cmo else "the crew medical officer"
        reply = (f"{address(ctx)}, {hit.guidance[0].lower()}{hit.guidance[1:]} "
                 f"I have raised a Critical alert: if it is not acknowledged within the safety window, "
                 f"{responder} is alerted automatically. Press \"Alert crew now\" to call them immediately.")
        cards = dedupe(c for c in (card_by_id(i) for i in hit.cards) if c)
        resp = ChatResponse(reply=reply, mode="redflag", level="Critical", logged=logged,
                            red_flag=RedFlagInfo(id=hit.id, label=hit.label, matched=hit.matched),
                            actions=[SuggestedAction(id="alert_crew", label="Alert crew now"),
                                     SuggestedAction(id="acknowledge", label="I'm OK – acknowledged")],
                            notice=f"Alert {alert.id} created")
        self._attach_cards(resp, cards)
        return resp

    # =========================================================== offline ===
    def _offline(self, ctx: AstronautContext, triage: Triage, message: str,
                 notice: Optional[str] = None) -> ChatResponse:
        aid = ctx.astronaut.id
        logged = [self.provider.log_measurement(aid, x.metric, x.value, x.note, source="chat")
                  for x in extract_measurements(message)]
        cards = cards_for_triage(triage) if triage.level != "Nominal" else []
        passages = self.kb.search(message, k=6)
        resp = ChatResponse(reply="", mode="offline", level=triage.level, logged=logged, notice=notice)
        self._attach_cards(resp, cards)
        if _is_go_no_go(message) or triage.level == "Critical":
            parts = [self._assessment(ctx, triage, cards, short=True)]
        else:
            parts = [self._brief(ctx, triage)]
        if passages:
            parts.append("Closest knowledge-base passages:")
            shown: set[str] = set()
            for p in passages:                  # top 3 passages, one per source
                sid = self._cite(resp, p["title"], p.get("url", ""), p.get("page"), p["text"])
                if sid in shown:
                    continue
                shown.add(sid)
                parts.append(f"[{sid}] {p['title']}: {_snippet(p['text'])}")
                if len(shown) == 3:
                    break
        else:
            parts.append("No knowledge-base passage matched your question.")
        if _is_go_no_go(message):
            parts.append(FINAL_CALL)
        resp.reply = "\n\n".join(parts)
        resp.actions = self._actions(ctx, triage)
        return resp

    # =============================================================== LLM ===
    def _llm_turn(self, ctx: AstronautContext, triage: Triage, message: str, history: list[ChatTurn],
                  proactive: bool = False) -> ChatResponse:
        """Open models call tools less reliably than frontier models, so everything the reply
        must rest on (cards, passages, values typed in the message) is prepared up front.
        Tools remain available for history, forecasts, extra searches and crew alerts."""
        aid = ctx.astronaut.id
        session = ToolSession(self.provider, self.kb, aid)
        if not proactive:
            for x in extract_measurements(message):
                session.logged.append(self.provider.log_measurement(aid, x.metric, x.value, x.note, source="chat"))
        cards = cards_for_triage(triage) if triage.level != "Nominal" else []
        session.cards = list(cards)
        passages = self.kb.search(" ".join(triage.reasons) if proactive else message, k=3)
        parts = [turn_context(ctx, triage), knowledge_block(session, cards, passages)]
        if session.logged:
            parts.append("<already_logged>\n" + "\n".join(lm.label for lm in session.logged) + "\n</already_logged>")
        parts.append(f"<astronaut_message>\n{message}\n</astronaut_message>")
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *_history_messages(history),
                    {"role": "user", "content": "\n\n".join(parts)}]

        reply = None
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.llm.complete(messages, self._tools)
            messages.append(reply.assistant_message())
            if not reply.tool_calls:
                break
            for tc in reply.tool_calls:
                if tc.arguments is None:
                    out = json.dumps({"error": "arguments were not valid JSON; call the tool again"})
                else:
                    out, _ = session.run(tc.name, tc.arguments)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
        else:                                   # still calling tools after the last round: ask for the answer
            messages.append({"role": "user", "content": "Answer the astronaut now with the information you have."})
            reply = self.llm.complete(messages, None)
        text = _clean_reply(reply.text if reply else "")
        if not text:
            raise LLMError("the model returned an empty reply")
        return self._finish_llm(ctx, triage, message, text, session)

    def _finish_llm(self, ctx, triage, message, text, session: ToolSession) -> ChatResponse:
        known = {c.id for c in session.citations}
        text = CITE_RE.sub(lambda m: m.group(0) if m.group(1) in known else "", text)
        used = set(CITE_RE.findall(text))
        cites = [c for c in session.citations if c.id in used]
        if not cites and session.citations:
            cites = session.citations[:2]      # every health answer shows at least one source
        resp = ChatResponse(reply=text, mode="llm", level=triage.level, citations=cites, logged=session.logged,
                            crew_alert_triggered=session.crew_alert is not None)
        self._attach_cards(resp, session.cards)
        if _is_go_no_go(message) and "flight surgeon" not in text.lower():
            resp.reply += f"\n\n{FINAL_CALL}"
        resp.actions = self._actions(ctx, triage)
        return resp

    def _mark_down(self, e: Exception) -> None:
        """After a failed call, answer offline for a minute so the UI never waits on a dead API."""
        log.warning("LLM call failed: %r - offline fallback for %ss", e, OFFLINE_COOLDOWN_S)
        self._last_error = str(e)
        self._down_until = time.time() + OFFLINE_COOLDOWN_S

    # =========================================================== helpers ===
    def _assessment(self, ctx: AstronautContext, triage: Triage, cards: list[CountermeasureCard],
                    short: bool = False) -> str:
        who = address(ctx)
        if triage.level == "Nominal":
            return (f"{who}, your triage level is Nominal: all metrics are logged and within your baseline. "
                    f"Daily check-in: {ctx.checkin_status}.")
        flagged = [m for m in triage.metric_levels if m.level != "Nominal"]
        findings = " ".join(m.reason for m in flagged) or " ".join(triage.reasons)
        risky = [r for r in sorted(triage.ranked_risks, key=lambda r: -r.score) if r.level != "Nominal"]
        hazards = " and ".join(HAZARD_WORDS.get(r.hazard, r.hazard.lower()) for r in risky[:2]) or "health"
        text = f"{who}, {findings[0].lower() + findings[1:] if findings else ''} " \
               f"This is flagged {triage.level} for {hazards} risk."
        if triage.top_factors and not short:
            text += " Main factors: " + ", ".join(t.label for t in triage.top_factors[:3]) + "."
        first, topics = [], set()          # most important card per topic, at most 2
        for c in sorted(cards, key=lambda c: (-LEVEL_RANK[c.level], c.priority)):
            if c.topic not in topics and len(first) < 2:
                topics.add(c.topic)
                first.append(c)
        if triage.level == "Critical":     # on Critical give the two first actions of the top card too
            top = sorted(cards, key=lambda c: (-LEVEL_RANK[c.level], c.priority))[:2]
            first = top if top and top[0].topic == top[-1].topic else first
        if first:
            steps = " ".join(c.steps[0] for c in first)
            text += f" Do this now: {steps}"
        if triage.level == "Critical":
            text += " Then acknowledge the alert so the crew knows you are OK."
        return text

    @staticmethod
    def _brief(ctx: AstronautContext, triage: Triage) -> str:
        risky = [r for r in sorted(triage.ranked_risks, key=lambda r: -r.score) if r.level != "Nominal"]
        hazards = " and ".join(HAZARD_WORDS.get(r.hazard, r.hazard.lower()) for r in risky[:2])
        tail = f" for {hazards} risk; your countermeasure cards are below" if hazards else ""
        return f"{address(ctx)}, your triage level is {triage.level}{tail}."

    def _actions(self, ctx: AstronautContext, triage: Triage) -> list[SuggestedAction]:
        acts = []
        if any(not a.acknowledged for a in ctx.active_alerts) or triage.level != "Nominal":
            acts.append(SuggestedAction(id="acknowledge", label="I'm OK – acknowledged"))
        if triage.level == "Critical":
            acts.append(SuggestedAction(id="alert_crew", label="Alert crew now"))
        return acts

    def _attach_cards(self, resp: ChatResponse, cards: list[CountermeasureCard]) -> None:
        resp.countermeasures = group_cards(cards)
        for c in cards:
            if c.source_url:
                self._cite(resp, c.source_title, c.source_url)

    @staticmethod
    def _cite(resp: ChatResponse, title: str, url: str = "", page=None, snippet: str = "") -> str:
        for c in resp.citations:
            if (c.title, c.url, c.page) == (title, url, page):
                return c.id
        sid = f"S{max((int(c.id[1:]) for c in resp.citations if c.id[1:].isdigit()), default=0) + 1}"
        resp.citations.append(Citation(id=sid, title=title, url=url, page=page, snippet=snippet[:300]))
        return sid


def _snippet(text: str, n: int = 320) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def knowledge_block(session: ToolSession, cards: list[CountermeasureCard], passages: list[dict]) -> str:
    """Cards and passages retrieved for this turn, with source ids registered in the session."""
    lines = ["<knowledge>"]
    if cards:
        lines.append("Countermeasure cards for the current triage:")
        for c in cards:
            sid = session.add_source(c.source_title, c.source_url) if c.source_url else None
            tag = f"[{sid}]" if sid else "[demo protocol, no source]"
            lines.append(f"- {tag} {c.level} / {c.group}: {c.title}. Steps: {' '.join(c.steps)}")
    if passages:
        lines.append("Knowledge-base passages for this question:")
        for p in passages:
            sid = session.add_source(p["title"], p.get("url", ""), p.get("page"), p["text"])
            lines.append(f"- [{sid}] {p['title']}: {_snippet(p['text'], 600)}")
    if len(lines) == 1:
        lines.append("Nothing retrieved; use search_hrp_knowledge if you need a source.")
    lines.append("</knowledge>")
    return "\n".join(lines)


def _clean_reply(text: str) -> str:
    """Strip reasoning tags some open models leak and markdown emphasis/headings;
    normalise grouped citations "[S2, S3]" to "[S2][S3]"."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\[(S\d+(?:\s*[,;]\s*S\d+)+)\]",
                  lambda m: "".join(f"[{s.strip()}]" for s in re.split(r"[,;]", m.group(1))), text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _is_go_no_go(message: str) -> bool:
    m = message.lower()
    return any(re.search(rf"\b{re.escape(w)}\b", m) for w in GO_NO_GO_WORDS)


def _history_messages(history: list[ChatTurn]) -> list[dict]:
    """Earlier turns as plain text, alternating roles, starting with a user turn."""
    msgs: list[dict] = []
    for t in history[-HISTORY_TURNS:]:
        if not t.content.strip():
            continue
        if msgs and msgs[-1]["role"] == t.role:
            msgs[-1]["content"] += "\n\n" + t.content
        else:
            msgs.append({"role": t.role, "content": t.content})
    if msgs and msgs[0]["role"] == "assistant":
        msgs.insert(0, {"role": "user", "content": "(AstroDoc AI panel opened)"})
    if msgs and msgs[-1]["role"] == "user":       # the new message must follow an assistant turn
        msgs.append({"role": "assistant", "content": "(no reply)"})
    return msgs
