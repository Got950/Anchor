"""Hybrid retrieval: dense + BM25 fused with RRF, then single-hop reference expansion."""
from __future__ import annotations

from dataclasses import dataclass

from .. import config
from . import ingest


@dataclass
class Retrieved:
    doc_id: str
    title: str
    text: str
    score: float
    via_reference: bool


@dataclass
class Retrieval:
    results: list[Retrieved]
    confidence: float          # top FUSED RRF score (never a raw dense similarity)
    abstain: bool


def hybrid_retrieve(query: str, top_k: int = config.TOP_K, expand_references: bool = config.EXPAND_REFERENCES) -> Retrieval:
    idx = ingest.get_index()

    dense = idx.collection.query(query_embeddings=[idx.embed(query)], n_results=config.DENSE_N)
    dense_ids = [
        doc_id
        for doc_id, distance in zip(dense["ids"][0], dense["distances"][0])
        if distance <= config.DENSE_MAX_DISTANCE
    ]

    bm25_scores = idx.bm25.get_scores(idx.sparse_query_tokens(query))  # indexed by corpus position
    positions = sorted(range(len(bm25_scores)), key=lambda i: -bm25_scores[i])[: config.BM25_N]
    bm25_ids = [idx.doc_id_by_position[i] for i in positions if bm25_scores[i] > 0]

    rrf: dict[str, float] = {}
    for rank, doc_id in enumerate(dense_ids):
        rrf[doc_id] = rrf.get(doc_id, 0.0) + 1 / (config.RRF_K + rank)
    for rank, doc_id in enumerate(bm25_ids):
        rrf[doc_id] = rrf.get(doc_id, 0.0) + 1 / (config.RRF_K + rank)

    fused = sorted(rrf.items(), key=lambda kv: -kv[1])[:top_k]

    # Abstention gates on the fused score, before reference expansion (plan Section 3.2).
    confidence = fused[0][1] if fused else 0.0
    if not fused or confidence < config.ABSTAIN_RRF_THRESHOLD:
        return Retrieval(results=[], confidence=confidence, abstain=True)

    primary_ids = [doc_id for doc_id, _ in fused]
    ordered: list[tuple[str, float, bool]] = [(doc_id, score, False) for doc_id, score in fused]

    if expand_references:
        # Single hop only: a reference's own references are NOT chased (plan Section 9).
        seen = set(primary_ids)
        for doc_id in primary_ids:
            meta = idx.collection.get(ids=[doc_id])["metadatas"][0]
            for ref in ingest.references_of(meta):
                if ref not in seen and ref in idx.docs_by_id:
                    seen.add(ref)
                    ordered.append((ref, rrf.get(ref, 0.0), True))

    results = [
        Retrieved(
            doc_id=doc_id,
            title=idx.docs_by_id[doc_id].title,
            text=idx.docs_by_id[doc_id].text,
            score=round(score, 4),
            via_reference=via_ref,
        )
        for doc_id, score, via_ref in ordered
        if doc_id in idx.docs_by_id
    ]
    return Retrieval(results=results, confidence=round(confidence, 4), abstain=False)


def all_metadata() -> list[dict]:
    """Every record's metadata — the aggregation path scans this in Python (<=20 records)."""
    idx = ingest.get_index()
    got = idx.collection.get()
    return list(got["metadatas"])
