"""AstroDoc AI - the interactive clinical chatbot (SPEC §7).

    assistant = AstroDocAssistant(provider)
    assistant.greet("sara")                     # auto-open assessment on Warning/Critical
    assistant.chat("sara", "Can I still do the EVA tomorrow?")

Order of each chat turn:
  1. red-flag fast path (no LLM, instant)
  2. open-source LLM, two calls at most (see llm.py, grounding.py):
       call 1  small model: message type (greeting, symptom, log, status, go/no-go,
               information, other) + only the passages, cards and findings that help
       fixed   replies that need no model: greetings, off-topic, nothing in the knowledge
               base, go/no-go or status without a health report
       call 2  main model: short core prompt + the <task> for this message type only, and
               only the tools that type needs
       checks  in code: invented findings ("your CO2 is elevated"), numbers in no source,
               uncited advice made of words in no source, unrequested duty verdicts,
               go/no-go verdicts that contradict the triage
  3. offline fallback if there is no HF token, the offline toggle is on,
     or the API fails: triage assessment + countermeasure cards + top 3
     knowledge-base passages, values logged with rule-based extraction.

Two kinds of chat (use_report):
  True   opened automatically after the daily check-in: today's health report (triage,
         flagged metrics, alerts) is part of every answer in that chat.
  False  opened directly by the astronaut: no health report, no triage tools; answers come
         from the question and the knowledge base only, and go/no-go needs a check-in.
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
from .grounding import (HELPER_MODEL, Selection, allowed_key, drop_sentences, mentioned_metrics, select_relevant,
                        split_sentences, uncited_specifics, unrequested_verdict, unsupported_claims,
                        unsupported_numbers)
from .llm import DEFAULT_MODEL, HFChatLLM, LLMError
from .prompts import (FINAL_CALL, GO_NO_GO_ACTIVITY, GO_NO_GO_INTENT, GO_NO_GO_PHRASES, HAZARD_WORDS,
                      NO_REPORT_GO_NO_GO, NO_REPORT_STATUS, NO_SUPPORTED_ANSWER, NOT_COVERED, NOT_COVERED_INFO,
                      SYSTEM_PROMPT, address, brief_context, direct_context, facts_block, go_no_go, go_no_go_block,
                      greeting_reply, no_report_go_no_go_block, task_block, turn_context)
from .redflags import detect
from .tools import ToolSession, tool_definitions

log = logging.getLogger(__name__)

# Tools that do not read the health report: the only ones offered when the chat was opened directly.
DIRECT_TOOLS = {"search_hrp_knowledge", "get_countermeasures", "log_measurement", "trigger_crew_alert"}
CANDIDATE_PASSAGES = 6      # retrieved per message, before the relevance filter
MAX_PASSAGES = 4            # kept after it
# Tools each message type may use (None: every tool of the chat mode). Knowledge is already searched and
# filtered before the answer call, so general questions get no tools at all.
KIND_TOOLS: dict[str, Optional[set]] = {
    "information": set(),
    "symptom": {"log_measurement", "get_metric_history"},     # + trigger_crew_alert when Critical
    "log": {"log_measurement"},
    "status": None,
    "go_no_go": None,
}
MAX_TOOL_ROUNDS = 6
HISTORY_TURNS = 12
OFFLINE_COOLDOWN_S = 60
CITE_RE = re.compile(r"\[(S\d+)\]")


class AstroDocAssistant:
    def __init__(self, provider: AstroDataProvider, kb=None, llm: Optional[HFChatLLM] = None,
                 offline: Optional[bool] = None, selector: Optional[HFChatLLM] = None):
        if kb is None:
            from ..knowledge.retriever import get_kb
            kb = get_kb()
        self.provider = provider
        self.kb = kb
        self.force_offline = offline if offline is not None else os.getenv("ASTRODOC_OFFLINE", "") == "1"
        self.llm = llm if llm is not None else (None if self.force_offline else self._make_llm())
        self.model = self.llm.model if self.llm else os.getenv("LLM_MODEL", DEFAULT_MODEL)
        # Retrieval filter (small, fast model). Built automatically with the main model; a caller that
        # injects its own `llm` (tests) passes `selector` too, or runs without the filter.
        self.selector = selector if selector is not None else (
            self._make_selector(self.llm) if llm is None and self.llm is not None else None)
        self._down_until = 0.0
        self._last_error: Optional[str] = None
        self._tools = tool_definitions([a.id for a in provider.list_crew()])
        self._tools_direct = [t for t in self._tools if t["function"]["name"] in DIRECT_TOOLS]

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

    @staticmethod
    def _make_selector(main: HFChatLLM) -> Optional[HFChatLLM]:
        model = os.getenv("LLM_HELPER_MODEL", HELPER_MODEL).strip()
        if not model or model.lower() == "off":
            return None
        try:
            return HFChatLLM(model=model, fallback_models=[main.model], max_tokens=800)
        except Exception as e:
            log.warning("Retrieval filter model unavailable (%s): passages are used unchecked", e)
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
             offline: bool = False, use_report: bool = True) -> ChatResponse:
        """use_report=True: chat opened after the daily check-in, today's health report is used.
        use_report=False: chat opened directly, answers come from the question and the knowledge base."""
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
            return self._offline(ctx, triage, message, notice=notice, use_report=use_report)
        try:
            return self._llm_turn(ctx, triage, message, history, use_report=use_report)
        except Exception as e:
            self._mark_down(e)
            why = str(e) if isinstance(e, LLMError) else type(e).__name__
            return self._offline(ctx, triage, message, notice=f"AI wording unavailable ({why}) - offline mode.",
                                 use_report=use_report)

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
                            notice=f"Alert {alert.id} active: acknowledge it or the crew is alerted")
        self._attach_cards(resp, cards)
        return resp

    # =========================================================== offline ===
    def _offline(self, ctx: AstronautContext, triage: Triage, message: str,
                 notice: Optional[str] = None, use_report: bool = True) -> ChatResponse:
        aid = ctx.astronaut.id
        logged = [self.provider.log_measurement(aid, x.metric, x.value, x.note, source="chat")
                  for x in extract_measurements(message)]
        # cards for any flagged metric, even when overall Nominal - only when the health report is used
        cards = cards_for_triage(triage) if use_report else []
        passages = self.kb.search(message, k=6)
        resp = ChatResponse(reply="", mode="offline", level=triage.level, logged=logged, notice=notice)
        self._attach_cards(resp, cards)
        go = _is_go_no_go(message)
        if not use_report:
            parts = [NO_REPORT_GO_NO_GO] if go else [
                f"{address(ctx)}, here is what the onboard knowledge base has on your question."]
        elif go:
            parts = [go_no_go(triage)[1], self._assessment(ctx, triage, cards, short=True)]
        elif triage.level == "Critical":
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
        if go and use_report:
            parts.append(FINAL_CALL)
        resp.reply = "\n\n".join(parts)
        resp.actions = self._actions(ctx, triage) if use_report else []
        return resp

    # =============================================================== LLM ===
    def _llm_turn(self, ctx: AstronautContext, triage: Triage, message: str, history: list[ChatTurn],
                  proactive: bool = False, use_report: bool = True) -> ChatResponse:
        """Two model calls at most, then quality checks in code:
          call 1  (small model) message type + only the relevant passages, cards and findings
          -       fixed replies that need no model (greeting, nothing in the knowledge base, no report ...)
          call 2  (main model) short core prompt + the instructions for this message type only
          checks  invented findings, numbers not in the sources, uncited made-up advice, unrequested verdicts
        Values typed in the message are logged up front; open models call tools less reliably."""
        aid = ctx.astronaut.id
        session = ToolSession(self.provider, self.kb, aid)
        if not proactive:
            for x in extract_measurements(message):
                session.logged.append(self.provider.log_measurement(aid, x.metric, x.value, x.note, source="chat"))
        flagged = [m for m in triage.metric_levels if m.level != "Nominal"] if use_report else []
        all_cards = cards_for_triage(triage) if use_report else []   # flagged metrics, even when overall Nominal
        if proactive:
            sel = Selection(passages=self.kb.search(" ".join(triage.reasons), k=3), cards=all_cards,
                            findings=flagged, filtered=False, kind="status")
        else:
            sel = self._select(message, history, all_cards, flagged)
        go = not proactive and (_is_go_no_go(message) or sel.kind == "go_no_go")
        kind = "go_no_go" if go else sel.kind
        if use_report:      # Critical cards always stay: the first actions are given whatever the question
            sel.cards = dedupe([*sel.cards, *(c for c in all_cards if c.level == "Critical")])
        session.cards = list(sel.cards)

        if not proactive:
            fixed = self._fixed_reply(ctx, triage, kind, sel, session, use_report)
            if fixed:
                log.info("message type %s: fixed reply, no answer call", kind)
                resp = ChatResponse(reply=fixed, mode="template", level=triage.level, logged=session.logged)
                self._attach_cards(resp, session.cards)
                resp.actions = self._actions(ctx, triage) if use_report else []
                return resp

        general = kind in ("information", "greeting", "thanks", "other") and triage.level != "Critical"
        context = (direct_context(ctx) if not use_report else
                   brief_context(ctx, triage) if general else turn_context(ctx, triage))
        parts = [context, facts_block(triage if use_report else None, sel.findings, sel.filtered),
                 knowledge_block(session, sel.cards, sel.passages, sel.filtered), task_block(kind)]
        if session.logged:
            parts.append("<already_logged>\n" + "\n".join(lm.label for lm in session.logged) + "\n</already_logged>")
        if go:
            parts.append(go_no_go_block(triage) if use_report else no_report_go_no_go_block())
        earlier = _earlier_questions(history)
        if earlier:
            parts.append(earlier)
        parts.append(f"<astronaut_message>\n{message}\n</astronaut_message>")
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "\n\n".join(parts)}]

        tools = self._tools_for(kind, use_report, triage)
        reply = None
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.llm.complete(messages, tools)
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
            messages.append(reply.assistant_message())
        text = _clean_reply(reply.text if reply else "")
        if not text:
            raise LLMError("the model returned an empty reply")
        if not proactive:
            text = self._quality_check(messages, text, triage, message, session, use_report, go, kind)
        return self._finish_llm(ctx, triage, message, text, session, use_report=use_report)

    def _fixed_reply(self, ctx: AstronautContext, triage: Triage, kind: str, sel: Selection,
                     session: ToolSession, use_report: bool) -> Optional[str]:
        """Replies that need no model call: the answer is fixed, or there is nothing reliable to answer from."""
        logged = ("I've logged " + ", ".join(lm.label.replace("Logged: ", "") for lm in session.logged) + ". "
                  if session.logged else "")
        if not use_report and kind == "go_no_go":
            return logged + NO_REPORT_GO_NO_GO
        if not use_report and kind == "status":
            return logged + NO_REPORT_STATUS
        if not sel.filtered:                    # the filter did not run: the model answers as before
            return None
        if kind in ("greeting", "thanks", "other") and not session.logged:
            return greeting_reply(ctx, kind)
        nothing = not sel.passages and not sel.cards and not sel.findings
        if kind == "symptom" and nothing:
            return logged + NOT_COVERED
        if kind == "information" and nothing:
            return NOT_COVERED_INFO
        if kind == "log" and nothing and session.logged:
            return f"{logged.strip()} Ask me if you'd like to know what it means for you."
        return None

    def _tools_for(self, kind: str, use_report: bool, triage: Triage) -> Optional[list[dict]]:
        """Only the tools this message type needs: fewer tokens and fewer pointless tool rounds."""
        allowed = KIND_TOOLS.get(kind)                       # None: every tool of this chat mode
        base = self._tools if use_report else self._tools_direct
        if allowed is None:
            return base
        if use_report and triage.level == "Critical":
            allowed = allowed | {"trigger_crew_alert"}
        tools = [t for t in base if t["function"]["name"] in allowed]
        return tools or None

    def _select(self, message: str, history: list[ChatTurn], cards: list[CountermeasureCard],
                findings: list) -> Selection:
        """Call 1: retrieve candidates for the message, then the small model gives the message type and keeps
        only what helps answer it (grounding.py). If no passage is relevant to a symptom or information
        question, one more search with the filter's own query. If the filter cannot run, the top passages are
        used unchecked rather than failing the turn."""
        candidates = self.kb.search(message, k=CANDIDATE_PASSAGES)
        unchecked = Selection(passages=candidates[:3], cards=cards, findings=findings, filtered=False)
        if self.selector is None:
            return unchecked
        earlier = _earlier_list(history)
        try:
            sel = select_relevant(self.selector, message, earlier, candidates, cards, findings)
            query = sel.search_query
            if (sel.kind in ("symptom", "information") and not sel.passages and query
                    and _norm(query) != _norm(message)):
                seen = {_passage_key(p) for p in candidates}
                more = [p for p in self.kb.search(query, k=CANDIDATE_PASSAGES) if _passage_key(p) not in seen]
                if more:
                    sel.passages = select_relevant(self.selector, message, earlier, more, [], []).passages
            sel.passages = sel.passages[:MAX_PASSAGES]
            log.info("retrieval filter (%s): kept %d/%d passages, %d/%d cards, %d/%d findings", sel.kind,
                     len(sel.passages), len(candidates), len(sel.cards), len(cards), len(sel.findings), len(findings))
            return sel
        except Exception as e:
            log.warning("retrieval filter unavailable (%s): using the top passages unchecked", e)
            return unchecked

    def _quality_check(self, messages: list[dict], text: str, triage: Triage, message: str, session: ToolSession,
                       use_report: bool, go: bool, kind: str = "") -> str:
        """Checks in code on the model's answer (grounding.py), no extra model call. Removes sentences that:
        claim a finding that does not exist, use a number found in no source, give uncited advice made of words
        found in no source, or give a duty verdict nobody asked for."""
        sources = "\n\n".join([messages[1]["content"],
                               *(str(m.get("content", "")) for m in messages if m.get("role") == "tool")])
        allowed = {allowed_key(m.metric) for m in triage.metric_levels if m.level != "Nominal"} if use_report else set()
        allowed |= {allowed_key(lm.metric) for lm in session.logged}     # values the astronaut just gave
        allowed |= mentioned_metrics(message)                            # "is my CO2 too high?"
        checks = {
            "invented finding": {s for s, _ in unsupported_claims(text, allowed)},
            "number not in sources": set(unsupported_numbers(text, sources)),
            "uncited advice not in sources": set(uncited_specifics(text, sources, advice_only=kind == "information")),
            "unrequested verdict": set() if go else {
                s for line in text.splitlines() for s in split_sentences(line)
                if unrequested_verdict(s, include_negative=not use_report)},
        }
        bad = set().union(*checks.values())
        if not bad:
            return text
        for name, sents in checks.items():
            for s in sents:
                log.info("quality check removed (%s): %s", name, s[:120])
        return drop_sentences(text, lambda s: s in bad) or NO_SUPPORTED_ANSWER

    def _finish_llm(self, ctx, triage, message, text, session: ToolSession, use_report: bool = True) -> ChatResponse:
        known = {c.id for c in session.citations}
        text = CITE_RE.sub(lambda m: m.group(0) if m.group(1) in known else "", text)
        used = set(CITE_RE.findall(text))
        cites = [c for c in session.citations if c.id in used]     # only sources the answer actually cites
        resp = ChatResponse(reply=text, mode="llm", level=triage.level, citations=cites, logged=session.logged,
                            crew_alert_triggered=session.crew_alert is not None)
        self._attach_cards(resp, session.cards)
        if _is_go_no_go(message) and not use_report:
            # No health report: no verdict can be given - say so first, drop any yes/no the model made up.
            if not _norm(text).startswith(_norm(NO_REPORT_GO_NO_GO)[:40]):
                body = drop_sentences(resp.reply, lambda s: unrequested_verdict(s, include_negative=True)
                                      or bool(re.match(r"(yes|no|not yet|not today)\b", s.strip().lower())))
                resp.reply = f"{NO_REPORT_GO_NO_GO}\n\n{body}".strip()
        elif _is_go_no_go(message):
            # The question must get a clear answer that matches the triage: if the model did not open with
            # one, put the verdict first; if its yes/no contradicts the triage, replace that sentence.
            verdict, sentence = go_no_go(triage)
            answer_re = r"(yes|no|not yet|not today)\b"
            start = text.strip().lower()
            after_name = re.sub(r"^[^,:]{0,40}[,:]\s*", "", start, count=1)      # "Commander, yes ..."
            said = re.match(answer_re, start) or re.match(answer_re, after_name)
            if not said:
                resp.reply = f"{sentence}\n\n{resp.reply}"
            elif (said.group(1) == "yes") != verdict.startswith("YES"):
                rest = _drop_first_sentence(resp.reply)
                resp.reply = f"{sentence}\n\n{rest}".strip()
            if "flight surgeon" not in resp.reply.lower():
                resp.reply += f"\n\n{FINAL_CALL}"
        resp.actions = self._actions(ctx, triage) if use_report else []
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


def knowledge_block(session: ToolSession, cards: list[CountermeasureCard], passages: list[dict],
                    filtered: bool = False) -> str:
    """Cards and passages for this turn, with source ids registered in the session.
    filtered=True: they passed the relevance filter, so an empty block means nothing relevant exists."""
    lines = ["<knowledge>"]
    if cards:
        lines.append("Countermeasure cards relevant to this message:" if filtered
                     else "Countermeasure cards for the current triage:")
        for c in cards:
            sid = session.add_source(c.source_title, c.source_url) if c.source_url else None
            tag = f"[{sid}]" if sid else "[demo protocol, no source]"
            lines.append(f"- {tag} {c.level} / {c.group}: {c.title}. Steps: {' '.join(c.steps)}")
    if passages:
        lines.append("Knowledge-base passages checked as relevant to this question:" if filtered
                     else "Knowledge-base passages for this question:")
        for p in passages:
            sid = session.add_source(p["title"], p.get("url", ""), p.get("page"), p["text"])
            lines.append(f"- [{sid}] {p['title']}: {_snippet(p['text'], 600)}")
    if len(lines) == 1:
        lines.append("Nothing relevant was found in the onboard knowledge base for this message." if filtered
                     else "Nothing retrieved; use search_hrp_knowledge if you need a source.")
    lines.append("</knowledge>")
    return "\n".join(lines)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("’", "'")).strip(" ?.!")


def _passage_key(p: dict) -> tuple:
    return p.get("title", ""), re.sub(r"\s+", " ", p.get("text", ""))[:80]


def _drop_first_sentence(text: str) -> str:
    first, _, rest = (text or "").strip().partition("\n")
    sents = split_sentences(first)
    return (" ".join(sents[1:]) + ("\n" + rest if rest else "")).strip()


def _clean_reply(text: str) -> str:
    """Strip reasoning tags some open models leak and markdown emphasis/headings;
    normalise grouped citations "[S2, S3]" to "[S2][S3]"."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    # gpt-oss writes citations in its own style: 【S2】, 【S2†L3-L5】 -> [S2]
    text = re.sub(r"【\s*(S\d+)[^】]*】", r"[\1]", text)
    # tool calls an open model wrote as text instead of calling the tool: <trigger_crew_alert .../>,
    # <tool_call>...</tool_call>, "(triggering crew alert ...)" - the astronaut must never see these
    text = re.sub(r"<(tool_call|function_call|function)[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    text = re.sub(r"</?[a-z_]+(?:\s+[a-z_]+=\"[^\"]*\")*\s*/?>", "", text, flags=re.I)
    text = re.sub(r"^\s*\((?:calling|triggering|invoking|using|running)\b[^)\n]*\)\s*$", "", text, flags=re.M | re.I)
    # filler countermeasure lines such as "Shielding - No additional shielding needed."
    text = re.sub(r"^[ \t]*[*\-•]?[ \t]*\**(?:protocols?|diet|shielding)\**[ \t]*[–—:\-][ \t]*(?:no|none|not)\b[^\n]*"
                  r"(?:needed|required|necessary|changes?)[^\n]*$", "", text, flags=re.M | re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"\1", text)   # *italic*
    text = re.sub(r"(?<!\w)_(?=\S)([^_\n]+?)(?<=\S)_(?!\w)", r"\1", text)           # _italic_
    text = re.sub(r"\[(S\d+(?:\s*[,;]\s*S\d+)+)\]",
                  lambda m: "".join(f"[{s.strip()}]" for s in re.split(r"[,;]", m.group(1))), text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def _is_go_no_go(message: str) -> bool:
    m = " " + re.sub(r"\s+", " ", message.lower().replace("’", "'")) + " "

    def has(words):
        return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", m) for w in words)
    return has(GO_NO_GO_PHRASES) or (has(GO_NO_GO_INTENT) and has(GO_NO_GO_ACTIVITY))


EARLIER_QUESTIONS = 3


def _earlier_list(history: list[ChatTurn]) -> list[str]:
    return [re.sub(r"\s+", " ", t.content).strip()[:200] for t in history[-HISTORY_TURNS:]
            if t.role == "user" and t.content.strip()][-EARLIER_QUESTIONS:]


def _earlier_questions(history: list[ChatTurn]) -> str:
    """The astronaut's previous questions only, as context for follow-ups.
    Earlier *answers* are deliberately left out: open models copy their own old wording
    (verdicts, filler, wrong numbers) into answers to new, unrelated questions."""
    questions = _earlier_list(history)
    if not questions:
        return ""
    lines = "\n".join(f"- {q}" for q in questions)
    return ("<earlier_questions>\nContext only (for follow-ups like \"and tomorrow?\"); do not answer these again:\n"
            f"{lines}\n</earlier_questions>")
