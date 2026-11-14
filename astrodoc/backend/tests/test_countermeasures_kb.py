import json

from app.assistant.countermeasures import cards_for_triage, find_cards, group_cards, load_cards
from app.assistant.data_provider import MockDataProvider


def test_every_card_has_source_or_demo_tag():
    for c in load_cards():
        assert c.steps
        assert c.source_url or c.demo_protocol, c.id


def test_sara_day47_cards_cover_three_groups():
    triage = MockDataProvider(day=47).get_triage("sara")
    assert triage.level == "Warning"
    grouped = group_cards(cards_for_triage(triage))
    assert grouped["protocol"] and grouped["diet"] and grouped["shielding"]
    assert all(c.level == "Warning" for g in grouped.values() for c in g)


def test_spe_day120_storm_shelter_for_all_crew():
    p = MockDataProvider(day=120)
    for a in p.list_crew():
        t = p.get_triage(a.id)
        assert t.level == "Critical"
        ids = [c.id for c in cards_for_triage(t)]
        assert ids[0].startswith("rad-crit"), ids
        assert "rad-crit-shelter" in ids


def test_critical_request_includes_warning_cards_after_critical():
    cards = find_cards(topic="radiation", level="Critical")
    levels = [c.level for c in cards]
    assert levels.index("Critical") < levels.index("Warning")


def test_tfidf_retriever(tmp_path, monkeypatch):
    import app.knowledge.retriever as r
    chunks = [
        {"id": "1", "title": "Radiation brief", "url": "u1", "page": 1, "kind": "document",
         "text": "During a solar particle event the crew moves to the storm shelter with water shielding."},
        {"id": "2", "title": "Sleep", "url": "u2", "page": None, "kind": "document",
         "text": "Circadian lighting and protected sleep windows reduce fatigue on long missions."},
    ]
    f = tmp_path / "chunks.jsonl"
    f.write_text("\n".join(json.dumps(c) for c in chunks), encoding="utf-8")
    monkeypatch.setattr(r, "CHUNKS_FILE", f)
    kb = r.KnowledgeBase(mode="tfidf")
    hits = kb.search("what shielding during solar particle event", k=1)
    assert kb.backend == "tfidf" and hits[0]["id"] == "1"
