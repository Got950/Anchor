"""Corpus ingestion: load -> extract metadata -> embed -> Chroma + BM25.

No chunking: every corpus file is 60-103 words, already an atomic passage.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .. import config, llm

log = logging.getLogger(__name__)

# FastAPI runs sync /ask+/agent in a threadpool. Concurrent SentenceTransformer.encode
# nests OpenMP/torch pools and permanently grows process threads (measured: 16 parallel
# encodes 80→288 threads; stress §4 then leaves /ask 500 while /health stays green).
# Serialize encode so concurrent requests cannot fork that pool. Ceiling: embed throughput
# is one-at-a-time; upgrade path is an async worker process or a proper embedding service.
_EMBED_LOCK = threading.Lock()

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Query-side stoplist for the sparse retriever. Corpus document frequency alone does not
# remove function words: "do" appears in only 2 of 20 files, so BM25 hands it a high idf
# and any question containing it gets a spurious rank-0 hit.
STOPWORDS = frozenset(
    """a an the is are was were be been being do does did done i you we my our it its this that these those
    of in on at to for with without and or but if how what which who whom when where why can could should
    would will shall may might must have has had get got from by as not no any all some so than then there
    their they them he she his her me us your please tell show about into over under out up down again very
    just also more most other only own same too s t don now""".split()
)


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@dataclass
class Doc:
    doc_id: str
    title: str
    text: str
    slug: str
    metadata: dict = field(default_factory=dict)


def load_corpus(corpus_dir: Path | None = None) -> list[Doc]:
    docs: list[Doc] = []
    for path in sorted((corpus_dir or config.CORPUS_DIR).glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        stem = path.stem                                    # e.g. doc_04_export_formats
        parts = stem.split("_")
        doc_id = "_".join(parts[:2])                        # doc_04 / ticket_101
        slug = " ".join(parts[2:])                          # "export formats"
        title_match = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else doc_id
        docs.append(Doc(doc_id=doc_id, title=title, text=text.strip(), slug=slug))
    return docs


# --- metadata extraction -----------------------------------------------------

def _aliases(doc: Doc) -> list[str]:
    """Prose names a doc might be mentioned under: title, filename slug, singular slug."""
    names = {doc.title.lower(), doc.slug.lower()}
    words = doc.slug.split()
    if words and words[-1].endswith("s"):
        names.add(" ".join(words[:-1] + [words[-1][:-1]]))  # "known issues" -> "known issue"
    return [n for n in names if n]


def _heuristic_metadata(doc: Doc, others: list[Doc]) -> dict:
    """Deterministic offline fallback for the extraction LLM call.

    ponytail: keyword/regex heuristics, deliberately shallow. Ceiling: only catches
    references phrased with a doc's title or filename words; the LLM pass catches
    paraphrases. Used only when no API key is configured.
    """
    low = doc.text.lower()
    refs = sorted({o.doc_id for o in others if any(a in low for a in _aliases(o))})
    is_ticket = doc.doc_id.startswith("ticket")
    resolution_type = None
    refund_issued = None
    if is_ticket:
        if "escalated" in low or "not closed" in low:
            resolution_type = "bug"
        elif re.search(r"(issued|granted|granting)[^.]{0,40}refund", low) or "goodwill" in low:
            resolution_type = "refund_exception"
        else:
            resolution_type = "expected_behavior"
        refund_issued = resolution_type == "refund_exception"
    return {
        "doc_id": doc.doc_id,
        "doc_type": "ticket" if is_ticket else "doc",
        "title": doc.title,
        "references": refs,
        "resolution_type": resolution_type,
        "refund_issued": refund_issued,
    }


def extract_metadata(doc: Doc, all_docs: list[Doc]) -> dict:
    others = [d for d in all_docs if d.doc_id != doc.doc_id]
    fallback = _heuristic_metadata(doc, others)
    prompt = (config.PROMPTS_DIR / "metadata_extraction.md").read_text(encoding="utf-8")
    user = (
        prompt.replace("{doc_index}", "\n".join(f"{d.doc_id} -> {d.title}" for d in others))
        .replace("{doc_id}", doc.doc_id)
        .replace("{text}", doc.text)
    )
    raw = llm.json_object("You extract strict JSON metadata. Output JSON only.", user, fallback=fallback)
    valid_ids = {d.doc_id for d in others}
    refs = [r for r in (raw.get("references") or []) if r in valid_ids]
    is_ticket = doc.doc_id.startswith("ticket")
    resolution = raw.get("resolution_type") if is_ticket else None
    if resolution not in {"expected_behavior", "bug", "refund_exception"}:
        resolution = fallback["resolution_type"]
    return {
        "doc_id": doc.doc_id,
        "doc_type": "ticket" if is_ticket else "doc",
        "title": raw.get("title") or doc.title,
        "references": refs,
        "resolution_type": resolution,
        "refund_issued": bool(raw.get("refund_issued")) if is_ticket else None,
    }


# --- index -------------------------------------------------------------------

def _flatten(meta: dict) -> dict:
    """Chroma metadata values must be scalars, so `references` is stored comma-joined."""
    return {
        "doc_id": meta["doc_id"],
        "doc_type": meta["doc_type"],
        "title": meta["title"],
        "references": ",".join(meta["references"]),
        "resolution_type": meta["resolution_type"] or "",
        "refund_issued": bool(meta["refund_issued"]),
    }


def references_of(meta: dict) -> list[str]:
    raw = meta.get("references") or ""
    return [r for r in raw.split(",") if r] if isinstance(raw, str) else list(raw)


@dataclass
class Index:
    collection: object
    bm25: object
    doc_id_by_position: list[str]      # doc_id_by_position[i] == doc_id of BM25 corpus position i
    docs_by_id: dict[str, Doc]
    embedder: object
    doc_freq: dict[str, int]           # token -> number of corpus files containing it

    def embed(self, text: str) -> list[float]:
        with _EMBED_LOCK:
            return self.embedder.encode([text], normalize_embeddings=True)[0].tolist()

    def sparse_query_tokens(self, query: str) -> list[str]:
        """Query tokens rare enough to carry signal (see config.BM25_MAX_DF_RATIO)."""
        cutoff = len(self.doc_id_by_position) * config.BM25_MAX_DF_RATIO
        return [t for t in tokenize(query) if t not in STOPWORDS and self.doc_freq.get(t, 0) <= cutoff]


_INDEX: Index | None = None


def build_index(corpus_dir: Path | None = None) -> Index:
    import chromadb
    from rank_bm25 import BM25Okapi
    from sentence_transformers import SentenceTransformer

    root = corpus_dir or config.CORPUS_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"Corpus directory missing: {root}. Create it and add *.txt files before starting the server.")
    docs = load_corpus(corpus_dir)
    if not docs:
        raise RuntimeError(f"Corpus directory is empty (no *.txt files): {root}. Refusing to start with a broken index.")
    log.info("Ingesting %d corpus files (LLM metadata extraction: %s)", len(docs), llm.available())
    for doc in docs:
        doc.metadata = extract_metadata(doc, docs)

    embedder = SentenceTransformer(config.EMBED_MODEL)
    # Cap intra-op threads so even a single encode cannot spawn a large OpenMP pool.
    try:
        import torch

        torch.set_num_threads(1)
    except Exception:
        pass
    embeddings = embedder.encode([d.text for d in docs], normalize_embeddings=True).tolist()

    client = chromadb.Client()
    try:
        client.delete_collection(config.COLLECTION_NAME)
    except Exception:
        pass
    # Cosine space must be set at creation time — Chroma defaults to L2 and the
    # abstention threshold only holds under cosine (plan Section 3.1).
    collection = client.create_collection(
        name=config.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    collection.upsert(
        ids=[d.doc_id for d in docs],
        documents=[d.text for d in docs],
        embeddings=embeddings,
        metadatas=[_flatten(d.metadata) for d in docs],
    )

    doc_id_by_position = [d.doc_id for d in docs]
    tokenized = [tokenize(d.text) for d in docs]
    bm25 = BM25Okapi(tokenized)
    doc_freq: dict[str, int] = {}
    for tokens in tokenized:
        for token in set(tokens):
            doc_freq[token] = doc_freq.get(token, 0) + 1

    global _INDEX
    _INDEX = Index(
        collection=collection,
        bm25=bm25,
        doc_id_by_position=doc_id_by_position,
        docs_by_id={d.doc_id: d for d in docs},
        embedder=embedder,
        doc_freq=doc_freq,
    )
    return _INDEX


def get_index() -> Index:
    return _INDEX if _INDEX is not None else build_index()
