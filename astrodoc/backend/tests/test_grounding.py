"""Grounding: the two chat modes (with / without the check-in health report), the retrieval
filter that skips irrelevant knowledge, and the code checks on the model's answer."""
import json

import pytest

from app.assistant.chain import AstroDocAssistant
from app.assistant.grounding import unrequested_verdict, unsupported_claims
from app.assistant.llm import HFChatLLM
from app.assistant.prompts import NO_REPORT_GO_NO_GO
from test_assistant import FakeHF, answer


def bots(provider, kb, main_script, selector_script=None):
    main = FakeHF(main_script)
    llm = HFChatLLM(model="openai/gpt-oss-120b", fallback_models=[], client=main)
    sel_client = FakeHF(selector_script) if selector_script is not None else None
    selector = HFChatLLM(model="openai/gpt-oss-20b", fallback_models=[], client=sel_client) if sel_client else None
    return AstroDocAssistant(provider, kb=kb, llm=llm, selector=selector), main, sel_client


def pick(**kw):
    data = {"type": "symptom", "passages": [], "cards": [], "findings": [], "search_query": ""}
    data.update(kw)
    return answer(json.dumps(data))


# ------------------------------------------------------- code checks ---
@pytest.mark.parametrize("sentence,claim", [
    ("Yes, you can stay on duty, but address the elevated CO₂ now.", True),
    ("Your sleep was short last night (3.4 h).", True),
    ("Your blood pressure is elevated.", True),
    ("You have low oxygen saturation.", True),
    ("The cabin CO2 is elevated, so ventilate the module.", True),
    ("Ventilate the area; if the reading remains high, move to another module [S1].", False),
    ("Headaches can also come from high CO₂ [S2], but there is no CO₂ reading for you.", False),
    ("High radiation exposure increases cancer risk over a lifetime.", False),
    ("Elevated CO2 is a known cause of headaches on the ISS [S1].", False),
    ("Move your sleep station to the most shielded area [S1].", False),
    ("Low SpO2 can cause dizziness.", False),
])
def test_unsupported_claim_detection(sentence, claim):
    assert bool(unsupported_claims(sentence, set())) is claim


def test_gpt_oss_citation_style_is_normalised(provider, kb):
    bot, _, _ = bots(provider, kb, [answer("High CO2 can cause headaches 【S1】 and 【S2†L3-L5】.")])
    res = bot.chat("lin", "why do I get headaches?", use_report=False)
    assert res.reply == "High CO2 can cause headaches [S1] and [S2]."
    assert [c.id for c in res.citations] == ["S1", "S2"]


def test_flagged_metric_may_be_called_low():
    assert unsupported_claims("Your sleep was short last night.", {"sleep_h"}) == []


@pytest.mark.parametrize("sentence,verdict", [
    ("Yes, you can stay on duty, but address the CO2.", True),
    ("You are fit for duty today.", True),
    ("You can continue with the EVA tomorrow.", True),
    ("Rest for 12 hours before any EVA.", False),
    ("You can do light exercise once the headache eases.", False),
])
def test_unrequested_verdict_detection(sentence, verdict):
    assert unrequested_verdict(sentence, include_negative=False) is verdict


# --------------------------------------- chat opened directly: no report ---
def test_direct_chat_has_no_health_report(provider, kb):
    bot, main, _ = bots(provider, kb, [answer("Sleep loss can cause headaches [S1]. Rest and drink water.")])
    res = bot.chat("sara", "I have a headache, what should I do?", use_report=False)
    content = main.requests[0]["messages"][1]["content"]
    assert "Health report: not attached" in content
    assert "Triage level" not in content and "Flagged metrics" not in content
    assert "Countermeasure cards" not in content                     # cards come from the report
    tools = {t["function"]["name"] for t in main.requests[0]["tools"]}
    assert "get_triage" not in tools and "get_forecast" not in tools and "search_hrp_knowledge" in tools
    assert res.mode == "llm" and res.actions == [] and not any(res.countermeasures.values())


def test_direct_offline_has_no_triage(provider, kb):
    bot = AstroDocAssistant(provider, kb=kb, offline=True)
    res = bot.chat("sara", "what helps with sleep in space?", use_report=False)
    assert "Warning" not in res.reply and "triage" not in res.reply.lower()
    assert not any(res.countermeasures.values())
    assert bot.chat("sara", "can i do the EVA?", use_report=False).reply.startswith(NO_REPORT_GO_NO_GO)


# ------------------------------------- after the check-in: report used ---
def test_report_chat_drops_unrequested_duty_verdict(provider, kb):
    bot, _, _ = bots(provider, kb, [answer("Yes, you can stay on duty. Rest now and limit screen time [S1].")])
    res = bot.chat("sara", "I have a headache. What treatment should I get?")
    assert res.reply == "Rest now and limit screen time [S1]."


def test_go_no_go_contradicting_the_triage_is_replaced(provider, kb):
    bot, _, _ = bots(provider, kb, [answer("Yes, you can go. Shield your sleep station [S1].")])
    res = bot.chat("sara", "can I go on the EVA tomorrow?")           # sara's triage is Warning
    assert res.reply.startswith("Not yet: your triage is Warning")
    assert "Yes, you can go" not in res.reply and "Shield your sleep station [S1]." in res.reply


def test_report_chat_flagged_metric_can_be_named(provider, kb):
    bot, main, _ = bots(provider, kb, [answer("Your sleep was short (5 h), which can cause headaches [S1].")])
    res = bot.chat("sara", "I have a headache")
    assert len(main.requests) == 1 and res.reply.startswith("Your sleep was short")       # flagged: no rewrite
    content = main.requests[0]["messages"][1]["content"]
    assert "Not measured today" in content and "cabin CO2" in content


# ------------------------------------------------- retrieval filter ---
def test_filter_keeps_only_relevant_knowledge(provider, kb):
    bot, main, sel = bots(provider, kb, [answer("Short sleep can cause headaches [S1].")],
                          [pick(passages=["P2"], cards=["C4"], findings=["F3"])])
    bot.chat("sara", "I have a headache")
    content = main.requests[0]["messages"][1]["content"]
    assert "Sleep loss and circadian misalignment" in content            # P2 kept
    assert "solar particle event" not in content and "exercise about two hours" not in content
    assert "Findings related to this message: sleep = 4.96 h (Warning)" in content
    assert content.count("Steps:") == 1                                  # only the fatigue card C4
    assert "Newest message: I have a headache" in sel.requests[0]["messages"][1]["content"]
    assert sel.requests[0]["model"] == "openai/gpt-oss-20b"


def test_filter_failure_falls_back_to_unchecked_passages(provider, kb):
    bot, main, _ = bots(provider, kb, [answer("Shelter in the shielded area [S1].")], [answer("not json at all")])
    res = bot.chat("lin", "what about solar storms?")
    assert res.mode == "llm"
    assert "Knowledge-base passages for this question" in main.requests[0]["messages"][1]["content"]


# ------------------------------- two calls at most + code quality checks ---
def test_invented_finding_is_removed_without_extra_call(provider, kb):
    bot, main, _ = bots(provider, kb, [answer("Your CO2 is elevated, ventilate now. Sleep loss can cause headaches [S2].")])
    res = bot.chat("sara", "I have a headache", use_report=False)
    assert len(main.requests) == 1                                       # no rewrite call any more
    assert res.reply == "Sleep loss can cause headaches [S2]."


def test_number_not_in_sources_is_removed(provider, kb):
    bot, _, _ = bots(provider, kb, [answer("Shelter in the most shielded area [S1]. Stay there for 48 hours.")])
    res = bot.chat("lin", "what do I do in a solar storm?", use_report=False)
    assert res.reply == "Shelter in the most shielded area [S1]."


def test_uncited_made_up_advice_is_removed(provider, kb):
    reply = ("Shelter in the most shielded area [S1]. Apply antiseptic rinse with sterile gauze from the dental kit. "
             "If it gets worse, contact the crew medical officer.")
    bot, _, _ = bots(provider, kb, [answer(reply)])
    res = bot.chat("lin", "what do I do in a solar storm?", use_report=False)
    assert "dental kit" not in res.reply
    assert res.reply == "Shelter in the most shielded area [S1]. If it gets worse, contact the crew medical officer."


def test_nothing_supported_gives_honest_reply(provider, kb):
    bot, _, _ = bots(provider, kb, [answer("Apply antiseptic rinse with sterile gauze from the dental kit.")])
    res = bot.chat("lin", "what do I do in a solar storm?", use_report=False)
    assert res.reply.startswith("I couldn't find a reliable answer")


def test_direct_go_no_go_is_a_fixed_reply_without_answer_call(provider, kb):
    bot, main, _ = bots(provider, kb, [])
    res = bot.chat("sara", "am i allowed to go in a mission ?", use_report=False)
    assert res.reply == NO_REPORT_GO_NO_GO and res.mode == "template" and main.requests == []


def test_direct_status_question_is_a_fixed_reply(provider, kb):
    bot, main, _ = bots(provider, kb, [], [pick(type="status")])
    res = bot.chat("sara", "how am I doing?", use_report=False)
    assert res.reply.startswith("This chat has no health report attached") and main.requests == []


@pytest.mark.parametrize("kind,start", [("greeting", "Hi Commander"), ("thanks", "You're welcome"),
                                        ("other", "Commander, I can only help")])
def test_greeting_thanks_off_topic_need_no_answer_call(provider, kb, kind, start):
    bot, main, _ = bots(provider, kb, [], [pick(type=kind)])
    res = bot.chat("sara", "hello there")
    assert res.reply.startswith(start) and main.requests == []


def test_symptom_not_in_knowledge_base_needs_no_answer_call(provider, kb):
    bot, main, sel = bots(provider, kb, [], [pick(type="symptom", search_query="toothache dental pain treatment")])
    res = bot.chat("lin", "my tooth hurts")
    assert kb.queries == ["my tooth hurts", "toothache dental pain treatment"]
    assert len(sel.requests) == 1          # the second search found only rejected passages: no second filter call
    assert main.requests == [] and res.reply.startswith("The onboard knowledge base doesn't cover this")


def test_information_not_in_knowledge_base(provider, kb):
    bot, main, _ = bots(provider, kb, [], [pick(type="information")])
    res = bot.chat("lin", "who built the first space station?")
    assert res.reply.startswith("The onboard knowledge base doesn't cover that topic") and main.requests == []


def test_logged_values_confirmed_without_answer_call(provider, kb):
    bot, main, _ = bots(provider, kb, [], [pick(type="log")])
    res = bot.chat("lin", "slept 7 hours")
    assert res.reply.startswith("I've logged sleep 7 h.") and main.requests == []


def test_task_instructions_and_tools_follow_the_message_type(provider, kb):
    bot, main, _ = bots(provider, kb, [answer("Microgravity is free fall [S1].")],
                        [pick(type="information", passages=["P1"])])
    bot.chat("sara", "what is microgravity?")
    req = main.requests[0]
    content = req["messages"][1]["content"]
    assert "<task>\nA general question" in content
    assert "Today's triage level: Warning" in content and "Ranked risks" not in content    # brief report only
    assert "tools" not in req                                                            # no tools needed


def test_symptom_in_check_in_chat_gets_full_report_and_few_tools(provider, kb):
    bot, main, _ = bots(provider, kb, [answer("Short sleep can cause headaches [S1].")],
                        [pick(type="symptom", passages=["P2"], findings=["F3"])])
    bot.chat("sara", "I have a headache")
    req = main.requests[0]
    assert "<task>\nA symptom" in req["messages"][1]["content"] and "Ranked risks" in req["messages"][1]["content"]
    assert {t["function"]["name"] for t in req["tools"]} == {"log_measurement", "get_metric_history"}


def test_system_prompt_is_short():
    from app.assistant.prompts import SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) < 3200


SRC = ("Sleep: 3.4 Hours, normal range 6.5 - 9.0 Hours. Mood 1/5. CO2 limit 3 mmHg. Exercise 2 hours a day. "
       "Stand down for 12 hours. [S2] Score 30.9/100, Sol 36.")


@pytest.mark.parametrize("sentence,removed", [
    ("Ensure adequate hydration (aim for 2 L fluid intake) and rest [S1].", True),       # "2" exists, "2 L" does not
    ("Avoid caffeine within 6 hours of sleep [S2].", True),
    ("Your CO2 reading is 28 mmHg [S1].", True),
    ("You slept 3.4 h, below the 6.5-9 hours range [S1].", False),
    ("Exercise about 2 hours a day [S1].", False),
    ("Keep cabin CO2 under 3 mmHg [S2].", False),
    ("Your mood is 1/5 [S3].", False),
])
def test_numbers_must_match_with_their_unit(sentence, removed):
    from app.assistant.grounding import unsupported_numbers
    assert bool(unsupported_numbers(sentence, SRC)) is removed


def test_information_answers_keep_plain_definitions():
    from app.assistant.grounding import uncited_specifics
    definition = "Microgravity is the condition of near-weightlessness experienced in free fall aboard the station."
    advice = "Apply antiseptic rinse with sterile gauze from the dental kit."
    assert uncited_specifics(definition, "microgravity", advice_only=True) == []
    assert uncited_specifics(advice, "microgravity", advice_only=True) == [advice]


@pytest.mark.parametrize("name,role,expected", [("ASTRO-7702-HELENA", "Flight Engineer", "Helena"),
                                                ("LEAD-COMMANDER", "Commander", "Commander"),
                                                ("Sara Okafor", "Mission Specialist", "Sara")])
def test_address_from_id_like_names(name, role, expected):
    from app.assistant.contracts import Astronaut, AstronautContext
    from app.assistant.prompts import address
    assert address(AstronautContext(astronaut=Astronaut(id="x", name=name, role=role), mission_day=1)) == expected
