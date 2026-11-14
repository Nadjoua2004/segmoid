"""Filesystem locations used by the assistant and the knowledge base."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.getenv("ASTRODOC_CONFIG_DIR", BACKEND_DIR / "config"))
DATA_DIR = Path(os.getenv("ASTRODOC_DATA_DIR", BACKEND_DIR / "data"))
DOCS_DIR = DATA_DIR / "docs"
EVENTS_DIR = DATA_DIR / "events"
KB_DIR = DATA_DIR / "kb"
CHUNKS_FILE = KB_DIR / "chunks.jsonl"
CHROMA_DIR = KB_DIR / "chroma"
