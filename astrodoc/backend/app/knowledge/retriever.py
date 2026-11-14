"""Search the NASA HRP Knowledge Base.

Uses Chroma (semantic search) when the collection and embedding model are
available, otherwise TF-IDF over data/kb/chunks.jsonl, so retrieval keeps
working with Wi-Fi off. Force a backend with ASTRODOC_RETRIEVER=chroma|tfidf.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Optional

from app.assistant.paths import CHROMA_DIR, CHUNKS_FILE

log = logging.getLogger(__name__)
COLLECTION = "hrp_kb"
MAX_PER_DOC = 2


def embedding_model_ready() -> bool:
    """True when all-MiniLM-L6-v2 is already on disk. The retriever never
    downloads at runtime (that would hang a Wi-Fi-off demo); ingest does."""
    try:
        from pathlib import Path
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2 as M
        return (Path(M.DOWNLOAD_PATH) / M.EXTRACTED_FOLDER_NAME / "model.onnx").exists()
    except Exception:
        return False


class KnowledgeBase:
    def __init__(self, mode: Optional[str] = None):
        self.mode = (mode or os.getenv("ASTRODOC_RETRIEVER", "auto")).lower()
        self._lock = threading.Lock()
        self._ready = False
        self.backend = "empty"
        self._col = None
        self._chunks: list[dict] = []
        self._vec = None
        self._matrix = None

    # ------------------------------------------------------------ setup ---
    def _init(self) -> None:
        with self._lock:
            if self._ready:
                return
            if CHUNKS_FILE.exists():
                self._chunks = [json.loads(ln) for ln in CHUNKS_FILE.read_text(encoding="utf-8").splitlines() if ln]
            if self.mode in ("auto", "chroma") and CHROMA_DIR.exists() and embedding_model_ready():
                try:
                    import chromadb
                    from chromadb.utils import embedding_functions
                    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
                    self._col = client.get_collection(
                        COLLECTION, embedding_function=embedding_functions.DefaultEmbeddingFunction())
                    self._col.query(query_texts=["radiation"], n_results=1)  # warm-up / sanity check
                    self.backend = "chroma"
                except Exception as e:
                    log.warning("Chroma unavailable (%s); falling back to TF-IDF", e)
                    self._col = None
            if self.backend != "chroma" and self._chunks:
                self._build_tfidf()
            self._ready = True

    def _build_tfidf(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        self._matrix = self._vec.fit_transform([f"{c['title']} {c['text']}" for c in self._chunks])
        self.backend = "tfidf"

    @property
    def size(self) -> int:
        self._init()
        return len(self._chunks) if self._chunks else (self._col.count() if self._col else 0)

    # ----------------------------------------------------------- search ---
    def search(self, query: str, k: int = 4, kind: Optional[str] = None) -> list[dict]:
        """Return up to k passages: {id, title, url, page, text, score, kind}."""
        self._init()
        if not query.strip():
            return []
        try:
            if self.backend == "chroma":
                hits = self._search_chroma(query, k * 3, kind)
            elif self.backend == "tfidf":
                hits = self._search_tfidf(query, k * 3, kind)
            else:
                return []
        except Exception as e:
            log.warning("search failed on %s (%s)", self.backend, e)
            if self.backend == "chroma" and self._chunks:
                self._build_tfidf()
                hits = self._search_tfidf(query, k * 3, kind)
            else:
                return []
        out, per_doc = [], {}
        for h in hits:
            key = "cards" if h.get("kind") == "card" else h["title"]
            if per_doc.get(key, 0) >= (1 if key == "cards" else MAX_PER_DOC):
                continue
            per_doc[key] = per_doc.get(key, 0) + 1
            out.append(h)
            if len(out) >= k:
                break
        return out

    def _search_chroma(self, query: str, n: int, kind: Optional[str]) -> list[dict]:
        res = self._col.query(query_texts=[query], n_results=n, where={"kind": kind} if kind else None)
        hits = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            text = doc.split("\n", 1)[1] if "\n" in doc else doc
            hits.append({"id": cid, "title": meta.get("title", ""), "url": meta.get("url", ""),
                         "page": meta.get("page") or None, "text": text, "kind": meta.get("kind", "document"),
                         "score": round(1 - float(dist), 4)})
        return hits

    def _search_tfidf(self, query: str, n: int, kind: Optional[str]) -> list[dict]:
        from sklearn.metrics.pairwise import linear_kernel
        scores = linear_kernel(self._vec.transform([query]), self._matrix).ravel()
        order = scores.argsort()[::-1]
        hits = []
        for i in order:
            if scores[i] <= 0:
                break
            c = self._chunks[i]
            if kind and c.get("kind") != kind:
                continue
            hits.append({**{k: c[k] for k in ("id", "title", "url", "page", "text")},
                         "kind": c.get("kind", "document"), "score": round(float(scores[i]), 4)})
            if len(hits) >= n:
                break
        return hits


_default: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    global _default
    if _default is None:
        _default = KnowledgeBase()
    return _default
