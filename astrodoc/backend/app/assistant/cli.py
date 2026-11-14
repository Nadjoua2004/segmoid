"""Chat with AstroDoc AI in the terminal on mock data.

    python -m app.assistant.cli --astronaut sara --day 47 [--offline]
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from .chain import AstroDocAssistant
from .contracts import ChatResponse, ChatTurn
from .data_provider import MockDataProvider


def show(res: ChatResponse) -> None:
    flag = f" RED FLAG: {res.red_flag.label}" if res.red_flag else ""
    print(f"\n[{res.level} | {res.mode}{flag}]")
    print(res.reply)
    for lm in res.logged:
        print(f"  ({lm.label})")
    for group, cards in res.countermeasures.items():
        for c in cards:
            tag = " [demo protocol]" if c.demo_protocol else ""
            print(f"  {group.upper():9s} {c.level:8s} {c.title}{tag}")
    for c in res.citations:
        print(f"  [{c.id}] {c.title} {c.url}")
    if res.notice:
        print(f"  ! {res.notice}")
    if res.actions:
        print("  actions: " + " | ".join(a.label for a in res.actions))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--astronaut", default="sara")
    ap.add_argument("--day", type=int, default=47)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    bot = AstroDocAssistant(MockDataProvider(day=args.day), offline=args.offline or None)
    print(f"AstroDoc AI - LLM {'on: ' + bot.model if bot.llm_available else 'off (offline mode)'}; "
          f"retriever: {bot.kb.backend}. Ctrl+C to quit.")
    res = bot.greet(args.astronaut)
    show(res)
    history = [ChatTurn(role="assistant", content=res.reply)]
    while True:
        try:
            msg = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg:
            continue
        res = bot.chat(args.astronaut, msg, history)
        history += [ChatTurn(role="user", content=msg), ChatTurn(role="assistant", content=res.reply)]
        show(res)


if __name__ == "__main__":
    main()
