"""Assistant behaviour without network: offline mode, red flags, and the
LLM tool loop driven by a scripted fake Hugging Face InferenceClient."""
from types import SimpleNamespace as NS

from app.assistant.chain import AstroDocAssistant
from app.assistant.contracts import ChatTurn


def offline_bot(provider, kb):
    return AstroDocAssistant(provider, kb=kb, offline=True)


# ------------------------------------------------------------ greeting ---
def test_greet_warning_is_instant_template_with_cards(provider, kb):
    res = offline_bot(provider, kb).greet("sara")
    assert res.mode == "template" and res.level == "Warning"
    assert res.reply.startswith("Commander,")
    assert "2.4 times your mission average" in res.reply
    assert "flagged Warning for radiation and fatigue" in res.reply
    assert all(res.countermeasures[g] for g in ("protocol", "diet", "shielding"))
    assert res.citations                                 # each card source is cited


def test_greet_nominal(provider, kb):
    res = offline_bot(provider, kb).greet("lin")
    assert res.level == "Nominal" and "Nominal" in res.reply
    assert not any(res.countermeasures.values())


def test_greet_spe_day120_critical(kb):
    from app.assistant.data_provider import MockDataProvider
    res = offline_bot(MockDataProvider(day=120), kb).greet("tomas")
    assert res.level == "Critical"
    assert "storm shelter" in res.reply.lower()
    assert any(a.id == "alert_crew" for a in res.actions)


# ----------------------------------------------------------- red flags ---
def test_chest_pain_fast_path_raises_alert(provider, kb):
    bot = offline_bot(provider, kb)
    res = bot.chat("sara", "I have chest pain")
    assert res.mode == "redflag" and res.level == "Critical"
    assert res.red_flag.id == "chest_pain"
    assert [a.id for a in res.actions][0] == "alert_crew"
    assert provider.alerts["sara"] and provider.alerts["sara"][-1].level == "Critical"
    assert res.logged[0].note == "Chest pain"
    assert kb.queries == []                              # no retrieval/LLM on the fast path


def test_cmo_red_flag_escalates_to_commander(provider, kb):
    res = offline_bot(provider, kb).chat("amina", "I passed out for a moment")
    assert "the commander" in res.reply
    assert offline_bot(provider, kb).alert_crew("amina", "test")["notified"] == "sara"


# ------------------------------------------------------------- offline ---
def test_offline_eva_question(provider, kb):
    res = offline_bot(provider, kb).chat("sara", "Can I still do the EVA tomorrow?")
    assert res.mode == "offline" and res.level == "Warning"
    assert "flight surgeon / mission control" in res.reply
    assert "[S" in res.reply and len(res.citations) >= 3
    assert res.countermeasures["shielding"]


def test_offline_logs_chat_values(provider, kb):
    res = offline_bot(provider, kb).chat("sara", "slept 5 hours, headache")
    labels = [l.label for l in res.logged]
    assert "Logged: sleep 5 h" in labels and "Logged: symptom: headache" in labels
    assert {m["metric"] for m in provider.measurements} == {"sleep_h", "symptom"}
    assert all(m["source"] == "chat" for m in provider.measurements)



def test_no_hf_token_means_offline(provider, kb, monkeypatch):
    import app.assistant.llm as llm
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(llm.HFChatLLM, "configured", staticmethod(lambda: False))
    bot = AstroDocAssistant(provider, kb=kb)
    assert not bot.llm_available
    assert bot.chat("sara", "what is my radiation risk?").mode == "offline"


# ----------------------------------------------------------- LLM loop ---
import json  # noqa: E402

import pytest  # noqa: E402

from app.assistant.llm import HFChatLLM, LLMError  # noqa: E402


def answer(text):
    return NS(choices=[NS(message=NS(content=text, tool_calls=None), finish_reason="stop")])


def calls(*specs):
    tcs = [NS(id=f"c{i}", function=NS(name=name, arguments=args if isinstance(args, str) else json.dumps(args)))
           for i, (name, args) in enumerate(specs)]
    return NS(choices=[NS(message=NS(content="", tool_calls=tcs), finish_reason="tool_calls")])


class HTTPErr(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.response = NS(status_code=status)


class FakeHF:
    """Stands in for huggingface_hub.InferenceClient: plays back scripted outputs."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def chat_completion(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def llm_bot(provider, kb, script, fallbacks=()):
    client = FakeHF(script)
    llm = HFChatLLM(model="openai/gpt-oss-120b", fallback_models=list(fallbacks), client=client)
    return AstroDocAssistant(provider, kb=kb, llm=llm), client


def test_llm_tool_loop_logs_cites_and_keeps_level(provider, kb):
    bot, client = llm_bot(provider, kb, [
        calls(("log_measurement", {"astronaut_id": "sara", "metric": "sleep_h", "value": 5}),
              ("search_hrp_knowledge", {"query": "radiation shielding sleep station"}),
              ("get_countermeasures", {"hazard": "Radiation", "level": "Warning"})),
        answer("Commander, your triage is Warning. Move your sleep station to the most shielded area [S1]. "
               "Bogus [S9]. Next step: log your dosimeter in 2 hours."),
    ])
    res = bot.chat("sara", "slept 5 hours. what should I do about radiation?",
                   history=[ChatTurn(role="assistant", content="Commander, ...")])
    assert res.mode == "llm" and res.level == "Warning"
    assert [l.label for l in res.logged] == ["Logged: sleep 5 h"]       # pre-logged once, tool call deduped
    assert "[S9]" not in res.reply and "[S1]" in res.reply
    assert res.citations[0].id == "S1"
    assert res.countermeasures["shielding"]
    first = client.requests[0]
    assert first["messages"][0]["role"] == "system"
    assert first["messages"][1]["role"] == "user"                      # history starts with a user turn
    user = first["messages"][-1]["content"]
    assert "<turn_context>" in user and "<knowledge>" in user and "<already_logged>" in user
    assert all(t["type"] == "function" for t in first["tools"])
    second = client.requests[1]["messages"]
    assert [m["role"] for m in second[-4:]] == ["assistant", "tool", "tool", "tool"]
    assert second[-4]["tool_calls"][0]["function"]["name"] == "log_measurement"


def test_llm_answer_without_tools_still_cites_and_logs(provider, kb):
    """Open models often skip tools: pre-retrieved cards/passages and extraction cover it."""
    bot, _ = llm_bot(provider, kb, [answer("Rest and shield your sleep area [S1]. Logged your headache.")])
    res = bot.chat("sara", "headache today, what now?")
    assert res.citations and res.citations[0].id == "S1"
    assert [l.label for l in res.logged] == ["Logged: symptom: headache"]


def test_llm_eva_answer_gets_final_call_line(provider, kb):
    bot, _ = llm_bot(provider, kb, [answer("Your radiation and fatigue risks are flagged Warning; rest first.")])
    res = bot.chat("sara", "Can I still do the EVA tomorrow?")
    assert res.reply.startswith("Not yet: your triage is Warning")               # verdict forced first
    assert res.reply.endswith("the flight surgeon / mission control confirms the final go/no-go.")
    assert res.countermeasures["protocol"]


def test_invalid_tool_json_reported_to_model(provider, kb):
    bot, client = llm_bot(provider, kb, [calls(("get_triage", "{not json")), answer("Your level is Warning.")])
    res = bot.chat("sara", "status?")
    tool_msg = client.requests[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "not valid JSON" in tool_msg["content"]
    assert res.mode == "llm"


def test_tool_error_is_reported_not_raised(provider, kb):
    bot, client = llm_bot(provider, kb, [
        calls(("log_measurement", {"astronaut_id": "sara", "metric": "hr", "value": 900})),
        answer("Could you re-check that heart rate value?")])
    res = bot.chat("sara", "please log it")
    assert "error" in client.requests[1]["messages"][-1]["content"] and res.logged == []


def test_crew_alert_tool(provider, kb):
    bot, _ = llm_bot(provider, kb, [
        calls(("trigger_crew_alert", {"astronaut_id": "tomas", "reason": "Critical, not acknowledged"})),
        answer("Amina has been alerted.")])
    res = bot.chat("tomas", "help")
    assert res.crew_alert_triggered and provider.escalations[-1]["notified"] == "amina"


def test_reasoning_tags_and_headings_stripped(provider, kb):
    bot, _ = llm_bot(provider, kb, [answer("<think>internal</think>\n## Plan\nRest now [S1].")])
    assert bot.chat("lin", "how am I doing?").reply == "Plan\nRest now [S1]."


# ------------------------------------------------- HF client behaviour ---
def test_fallback_model_used_when_main_fails(provider, kb):
    bot, client = llm_bot(provider, kb, [HTTPErr(503), answer("Fine.")], fallbacks=["Qwen/Qwen3.8-27B"])
    assert bot.chat("lin", "hello").mode == "llm"
    assert [r["model"] for r in client.requests] == ["openai/gpt-oss-120b", "Qwen/Qwen3.8-27B"]


def test_retry_without_tools_on_400(provider, kb):
    bot, client = llm_bot(provider, kb, [HTTPErr(400), answer("Fine.")])
    assert bot.chat("lin", "hello").mode == "llm"
    assert "tools" in client.requests[0] and "tools" not in client.requests[1]


def test_out_of_credits_falls_back_offline_with_notice(provider, kb):
    bot, client = llm_bot(provider, kb, [HTTPErr(402)], fallbacks=["Qwen/Qwen3.8-27B"])
    res = bot.chat("sara", "how is my sleep?")
    assert res.mode == "offline" and "credits" in res.notice
    assert len(client.requests) == 1 and not bot.llm_available     # cool-down: next turns go offline at once


def test_bad_token_raises_llm_error():
    llm = HFChatLLM(model="m", fallback_models=["other"], client=FakeHF([HTTPErr(401)]))
    with pytest.raises(LLMError, match="API key"):
        llm.complete([{"role": "user", "content": "hi"}])


def test_bold_and_grouped_citations_cleaned(provider, kb):
    bot, _ = llm_bot(provider, kb, [answer("**Protocol:** rest [S1, S2]. Hydrate [S9].")])
    res = bot.chat("sara", "what now?")
    assert res.reply == "Protocol: rest [S1][S2]. Hydrate ."
    assert [c.id for c in res.citations][:2] == ["S1", "S2"]          # then the card sources


def test_rate_limited_everywhere_waits_once_then_succeeds(provider, kb, monkeypatch):
    import app.assistant.llm as llm
    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    err = HTTPErr(429)
    err.response.headers = {"retry-after": "3"}
    bot, client = llm_bot(provider, kb, [err, err, answer("Fine now.")], fallbacks=["openai/gpt-oss-20b"])
    assert bot.chat("lin", "hello").reply == "Fine now."
    assert slept == [3.5] and len(client.requests) == 3


def test_long_rate_limit_goes_offline(provider, kb, monkeypatch):
    import app.assistant.llm as llm
    monkeypatch.setattr(llm.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("must not sleep")))
    err = HTTPErr(429)
    err.response.headers = {"retry-after": "60"}
    bot, _ = llm_bot(provider, kb, [err])
    assert bot.chat("lin", "hello").mode == "offline"


def test_reasoning_effort_sent_to_gpt_oss_only(provider, kb):
    bot, client = llm_bot(provider, kb, [HTTPErr(503), answer("ok")], fallbacks=["qwen/qwen3.8-27b"])
    bot.chat("lin", "hello")
    assert client.requests[0]["extra_body"] == {"reasoning_effort": "low"}       # gpt-oss
    assert "extra_body" not in client.requests[1]                              # qwen


def test_400_retry_drops_tools_and_reasoning_effort(provider, kb):
    bot, client = llm_bot(provider, kb, [HTTPErr(400), answer("ok")])
    bot.chat("lin", "hello")
    assert "tools" in client.requests[0] and "extra_body" in client.requests[0]
    assert "tools" not in client.requests[1] and "extra_body" not in client.requests[1]


def test_tool_call_written_as_text_is_removed(provider, kb):
    leaked = ("Stand down from the EVA [S1].\n\n(triggering crew alert for unacknowledged critical alert)\n"
              '<trigger_crew_alert alert_id="ALT-D35-1"/>\n\nNext step: rest now.')
    bot, _ = llm_bot(provider, kb, [answer(leaked)])
    reply = bot.chat("sara", "status?").reply
    assert "<" not in reply and "triggering" not in reply
    assert reply.startswith("Stand down from the EVA [S1].") and "Next step: rest now." in reply


# ---------------------------------------------------------- go / no-go ---
from app.assistant.chain import _is_go_no_go  # noqa: E402
from app.assistant.contracts import MetricLevel, Triage  # noqa: E402
from app.assistant.prompts import go_no_go  # noqa: E402


@pytest.mark.parametrize("q,expected", [
    ("am i allowed to go in a mission ?", True),
    ("Can I still do the EVA tomorrow?", True),
    ("is it safe to exercise today", True),
    ("Am I fit for duty?", True),
    ("what is my mission average dose?", False),
    ("I have a headache", False),
])
def test_go_no_go_detection(q, expected):
    assert _is_go_no_go(q) is expected


def test_go_no_go_verdicts():
    co2 = MetricLevel(metric="cabin_co2", level="Warning", value=2.6, unit="mmHg")
    assert go_no_go(Triage(astronaut_id="a", mission_day=1, level="Nominal"))[0] == "YES"
    v, s = go_no_go(Triage(astronaut_id="a", mission_day=1, level="Nominal", metric_levels=[co2]))
    assert v == "YES, WITH A CONDITION" and s.startswith("Yes, you can go") and "cabin CO2" in s
    assert go_no_go(Triage(astronaut_id="a", mission_day=1, level="Warning"))[0] == "NOT YET"
    assert go_no_go(Triage(astronaut_id="a", mission_day=1, level="Critical"))[1].startswith("No, not today")


def test_mission_question_gets_verdict_block_and_clear_answer(provider, kb):
    bot, client = llm_bot(provider, kb, [answer("Commander, not yet: rest and shield first [S1].")])
    res = bot.chat("sara", "am i allowed to go in a mission ?")
    assert "<go_no_go>" in client.requests[0]["messages"][-1]["content"]
    assert res.reply.startswith("Commander, not yet")                      # model answered: nothing prepended
    assert "flight surgeon" in res.reply


def test_offline_mission_question_starts_with_verdict(provider, kb):
    res = offline_bot(provider, kb).chat("sara", "am i allowed to go in a mission ?")
    assert res.reply.startswith("Not yet: your triage is Warning")


def test_italic_asterisks_removed(provider, kb):
    bot, _ = llm_bot(provider, kb, [answer("*Protocols* - ventilate the module [S1].")])
    assert bot.chat("lin", "what now?").reply.startswith("Protocols - ventilate")


def test_answer_starting_with_yes_is_not_duplicated(provider, kb):
    bot, _ = llm_bot(provider, kb, [answer("Yes, you can go once you rest [S1].")])
    reply = bot.chat("lin", "am i allowed to go in a mission ?").reply
    assert reply.startswith("Yes, you can go once you rest") and reply.count("Yes, you can go") == 1


def test_only_earlier_questions_are_sent_not_old_answers(provider, kb):
    bot, client = llm_bot(provider, kb, [answer("Rest now [S1].")])
    history = [ChatTurn(role="user", content="am i allowed to go in a mission ?"),
               ChatTurn(role="assistant", content="Yes, you can go. Shielding - No extra shielding needed.")]
    bot.chat("lin", "and what about tomorrow?", history)
    msgs = client.requests[0]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user"]
    content = msgs[1]["content"]
    assert "<earlier_questions>" in content and "am i allowed to go in a mission ?" in content
    assert "Yes, you can go" not in content and "No extra shielding" not in content


def test_filler_countermeasure_lines_removed(provider, kb):
    reply = ("Ventilate the module [S1].\n\nCountermeasures\nProtocols - Check the scrubber [S1].\n"
             "Shielding – No additional radiation shielding needed.\nDiet – No specific dietary changes required.")
    bot, _ = llm_bot(provider, kb, [answer(reply)])
    out = bot.chat("lin", "what now?").reply
    assert "Shielding" not in out and "Diet" not in out and "Protocols - Check the scrubber [S1]." in out


def test_spitting_blood_goes_to_red_flag_not_llm(provider, kb):
    bot, client = llm_bot(provider, kb, [])
    res = bot.chat("sara", "i am spelling blood what does that mean")
    assert res.mode == "redflag" and res.level == "Critical" and res.red_flag.id == "bleeding"
    assert client.requests == [] and "Yes, you can" not in res.reply
