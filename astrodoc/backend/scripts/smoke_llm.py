"""Live check of AstroDoc AI against the Hugging Face Inference API (needs HF_TOKEN in backend/.env).

    .venv/Scripts/python scripts/smoke_llm.py

Runs SPEC acceptance criteria 3, 4, 5 on mock data with the open-source model
from LLM_MODEL and prints PASS/FAIL per check. Uses a few small requests.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.assistant.chain import AstroDocAssistant  # noqa: E402
from app.assistant.cli import show  # noqa: E402
from app.assistant.contracts import ChatTurn  # noqa: E402
from app.assistant.data_provider import MockDataProvider  # noqa: E402

results = []


def check(name, ok):
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


provider = MockDataProvider(day=47)
bot = AstroDocAssistant(provider)
if not bot.llm_available:
    sys.exit("No Hugging Face token found: put HF_TOKEN in backend/.env (or run `hf auth login`).")
print(f"model: {bot.model} (fallbacks: {', '.join(bot.llm.fallback_models) or 'none'}), "
      f"retriever: {bot.kb.backend}\n")

print("== AC3 proactive assessment (LLM wording)")
g = bot.greet("sara", use_llm=True)
show(g)
check("mode llm", g.mode == "llm")
check("level reported as Warning", g.level == "Warning" and "warning" in g.reply.lower())
check("cards in all three groups", all(g.countermeasures[k] for k in ("protocol", "diet", "shielding")))
check("at least one citation", bool(g.citations))

print("\n== AC4 EVA go/no-go")
r = bot.chat("sara", "Can I still do the EVA tomorrow?", [ChatTurn(role="assistant", content=g.reply)])
show(r)
check("mode llm", r.mode == "llm")
check("mentions flight surgeon / mission control", "flight surgeon" in r.reply.lower())
check("cites a source", bool(r.citations))

print("\n== Chat logging")
r = bot.chat("sara", "I only slept 5 hours and I have a headache")
show(r)
check("sleep logged", any(lm.metric == "sleep_h" and lm.value == 5 for lm in r.logged))
check("headache logged", any(lm.metric == "symptom" for lm in r.logged))

print("\n== Tool use: forecast")
r = bot.chat("sara", "What will my readiness look like over the next week if nothing changes?")
show(r)
check("mentions a projection", any(w in r.reply.lower() for w in ("project", "if current", "trend")))

print("\n== AC5 red flag (must not call the LLM)")
r = bot.chat("sara", "I have chest pain")
check("red-flag fast path", r.mode == "redflag" and r.level == "Critical")

print("\n== Day 120 solar particle event")
provider.day = 120
r = bot.chat("tomas", "What should I do right now?")
show(r)
check("Critical reported", r.level == "Critical" and "critical" in r.reply.lower())
check("storm shelter mentioned", "shelter" in r.reply.lower())

print("\n== Voice (Whisper speech-to-text)")
from app.assistant.stt import SpeechToText  # noqa: E402

stt = SpeechToText()
if stt.available:
    clip = ROOT / "tests" / "audio" / "eva_question.wav"
    t = stt.transcribe(clip.read_bytes(), clip.name, "audio/wav")
    print(f"  heard ({t.model}): {t.text}")
    check("transcript mentions EVA", "eva" in t.text.lower())
    provider.day = 47
    r = bot.chat("sara", t.text)
    check("voice question answered, sleep logged", any(lm.metric == "sleep_h" for lm in r.logged))
else:
    print("  skipped: no speech-to-text host configured")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
