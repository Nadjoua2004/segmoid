"""Build the NASA HRP Knowledge Base (SPEC §6.2).

    python -m app.knowledge.ingest            # from backend/

Loads .pdf/.txt/.md from data/docs, strips web-page boilerplate, splits into
chunks, adds the countermeasure cards, then writes:
  data/kb/chunks.jsonl   - always (used by the offline TF-IDF retriever)
  data/kb/chroma/        - Chroma collection "hrp_kb" (all-MiniLM-L6-v2 embeddings)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from ..assistant.countermeasures import load_cards
from ..assistant.paths import CHROMA_DIR, CHUNKS_FILE, DOCS_DIR, KB_DIR

COLLECTION = "hrp_kb"
# all-MiniLM-L6-v2 truncates input at 256 word pieces, so chunks of ~300 tokens
# embed fully. Raise with --chunk-chars if you switch embedding model.
DEFAULT_CHUNK_CHARS = 1200
DEFAULT_OVERLAP = 150

PDF_SOURCES = {
    "03_NASA-STD-3001_TB_Carbon_Dioxide.pdf": (
        "NASA-STD-3001 Technical Brief - Carbon Dioxide",
        "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf"),
    "04_NASA-STD-3001_TB_Radiation_Protection.pdf": (
        "NASA-STD-3001 Technical Brief - Radiation Protection",
        "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-020-radiation-protection.pdf"),
    "05_NASA-STD-3001_TB_Bone_Loss.pdf": (
        "NASA-STD-3001 Technical Brief - Bone Loss",
        "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-030-bone-loss.pdf"),
}
SECTION_SEP = "\n\n" + "=" * 40 + "\n"
STOP_HEADINGS = re.compile(r"^#*\s*(references|footnotes|acknowledg(e)?ments?|author contributions|"
                           r"competing interests|data availability|associated data|supplementary materials?)\s*$",
                           re.I)
TITLE_SUFFIX = re.compile(r"\s*(-\s*PMC|-\s*NASA|\|.*)\s*(Lock)?\s*$")


def _clean_title(title: str, fallback: str) -> str:
    t = re.sub(r"\s+", " ", title or "").strip()
    t = TITLE_SUFFIX.sub("", t).strip()
    return t or fallback


def load_sections(docs_dir: Path = DOCS_DIR) -> list[dict]:
    sections: list[dict] = []
    for f in sorted(docs_dir.iterdir()):
        if f.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            title, url = PDF_SOURCES.get(f.name, (f.stem.replace("_", " "), ""))
            for i, page in enumerate(PdfReader(str(f)).pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    sections.append({"doc": f.name, "title": title, "url": url, "page": i, "text": text})
        elif f.suffix.lower() in (".txt", ".md"):
            raw = f.read_text(encoding="utf-8", errors="replace")
            for part in raw.split(SECTION_SEP):
                title = re.search(r"^Title:\s*(.*)$", part, re.M)
                url = re.search(r"^Source:\s*(\S+)", part, re.M)
                body = re.sub(r"^(Title|Source):.*$", "", part, count=2, flags=re.M)
                sections.append({"doc": f.name,
                                 "title": _clean_title(title.group(1) if title else "", f.stem.replace("_", " ")),
                                 "url": url.group(1) if url else "", "page": None, "text": body})
    return sections


def strip_boilerplate(sections: list[dict]) -> list[dict]:
    """Drop navigation/footer lines: any short line that repeats across sections."""
    def lines(s):
        return [ln.strip() for ln in s["text"].splitlines()]
    counts = Counter()
    for s in sections:
        counts.update({ln for ln in lines(s) if ln and len(ln) < 160})
    for s in sections:
        kept = []
        for ln in lines(s):
            if STOP_HEADINGS.match(ln):
                break
            if not ln or counts[ln] >= 2 or len(ln) < 3:
                continue
            kept.append(ln)
        text = unicodedata.normalize("NFKC", "\n".join(kept))   # ligatures (ﬀ -> ff), nbsp
        if s["page"] is not None:  # PDF: re-join lines wrapped mid-sentence
            text = re.sub(r"-\n(?=[a-z])", "", text)
            text = re.sub(r"(?<![.:!?])\n(?=[a-z0-9(])", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        s["text"] = text.strip()
    return [s for s in sections if len(s["text"]) > 200]


def _splitter(chunk_chars: int, overlap: int):
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        sp = RecursiveCharacterTextSplitter(chunk_size=chunk_chars, chunk_overlap=overlap,
                                            separators=["\n## ", "\n\n", "\n", ". ", " ", ""])
        return sp.split_text
    except ImportError:  # minimal fallback
        def split(text):
            out, i = [], 0
            while i < len(text):
                out.append(text[i:i + chunk_chars])
                i += chunk_chars - overlap
            return out
        return split


def _useful(chunk: str) -> bool:
    letters = sum(ch.isalpha() for ch in chunk)
    words = len(chunk.split())
    if words < 40 or letters / max(1, len(chunk)) <= 0.6:
        return False
    # skip reference lists: many years / DOIs / "et al." per word
    refs = len(re.findall(r"\b(?:19|20)\d{2}\b", chunk)) + 2 * len(re.findall(r"doi|et al\.", chunk, re.I))
    return refs / words < 0.04


def build_chunks(chunk_chars: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_OVERLAP) -> list[dict]:
    split = _splitter(chunk_chars, overlap)
    chunks: list[dict] = []
    for s in strip_boilerplate(load_sections()):
        for j, piece in enumerate(split(s["text"])):
            piece = piece.strip()
            if _useful(piece):
                cid = f"{Path(s['doc']).stem}-p{s['page'] or 0}-{j}"
                chunks.append({"id": cid, "doc": s["doc"], "title": s["title"], "url": s["url"],
                               "page": s["page"], "text": piece, "kind": "document"})
    # countermeasure cards are retrievable too
    for c in load_cards():
        text = (f"Countermeasure ({c.level}, {c.hazard} / {c.topic}, {c.group}): {c.title}. "
                + " ".join(c.steps))
        chunks.append({"id": f"card-{c.id}", "doc": "countermeasures.json",
                       "title": f"AstroDoc countermeasure card - {c.title}"
                                + (" (demo protocol)" if c.demo_protocol else f" [source: {c.source_title}]"),
                       "url": c.source_url, "page": None, "text": text, "kind": "card"})
    # unique ids
    seen = Counter()
    for ch in chunks:
        seen[ch["id"]] += 1
        if seen[ch["id"]] > 1:
            ch["id"] += f"-{seen[ch['id']]}"
    return chunks


def write_chunks(chunks: list[dict]) -> None:
    KB_DIR.mkdir(parents=True, exist_ok=True)
    with CHUNKS_FILE.open("w", encoding="utf-8") as fh:
        for ch in chunks:
            fh.write(json.dumps(ch, ensure_ascii=False) + "\n")


def build_chroma(chunks: list[dict]) -> None:
    import chromadb
    from chromadb.utils import embedding_functions

    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.create_collection(COLLECTION, embedding_function=embedding_functions.DefaultEmbeddingFunction(),
                                   metadata={"hnsw:space": "cosine"})
    batch = 64
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        col.add(ids=[c["id"] for c in part],
                documents=[f"{c['title']}\n{c['text']}" for c in part],
                metadatas=[{"title": c["title"], "url": c["url"], "page": c["page"] or 0,
                            "doc": c["doc"], "kind": c["kind"]} for c in part])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    ap.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    ap.add_argument("--no-chroma", action="store_true", help="only write chunks.jsonl (TF-IDF retrieval)")
    args = ap.parse_args(argv)

    if not DOCS_DIR.exists() or not any(DOCS_DIR.iterdir()):
        print(f"No documents in {DOCS_DIR}. Run download_resources.py first.")
        return 1
    chunks = build_chunks(args.chunk_chars, args.overlap)
    write_chunks(chunks)
    by_doc = Counter(c["doc"] for c in chunks)
    for doc, n in sorted(by_doc.items()):
        print(f"  {n:4d} chunks  {doc}")
    print(f"Wrote {len(chunks)} chunks -> {CHUNKS_FILE}")
    if args.no_chroma:
        return 0
    try:
        build_chroma(chunks)
        print(f"Chroma collection '{COLLECTION}' -> {CHROMA_DIR}")
    except Exception as e:  # keep the TF-IDF path usable
        shutil.rmtree(CHROMA_DIR, ignore_errors=True)
        print(f"Chroma build failed ({e}); the retriever will use TF-IDF over chunks.jsonl.\n"
              "Re-run this command once the embedding model can be downloaded.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
