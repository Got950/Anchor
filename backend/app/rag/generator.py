"""Grounded answer generation, abstention, and the metadata-scan aggregation path."""
from __future__ import annotations

import re

from .. import config, llm
from . import retriever, verifier
from .ingest import tokenize
from .retriever import Retrieved


def _snippet(text: str, limit: int = 220) -> str:
    body = re.sub(r"^(Title|Category):.*$", "", text, flags=re.MULTILINE).strip()
    body = " ".join(body.split())
    return body if len(body) <= limit else body[:limit].rsplit(" ", 1)[0] + "..."


def _sources(results: list[Retrieved]) -> list[dict]:
    return [
        {"doc_id": r.doc_id, "title": r.title, "snippet": _snippet(r.text), "via_reference": r.via_reference}
        for r in results
    ]


def _extractive_fallback(question: str, results: list[Retrieved]) -> str:
    """Offline stand-in for the generation LLM: quote the best-matching sentences verbatim."""
    q = set(tokenize(question))
    scored: list[tuple[int, str, str]] = []
    for r in results:
        if r.via_reference:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", _snippet(r.text, 10_000)):
            overlap = len(q & set(tokenize(sentence)))
            if overlap:
                scored.append((overlap, sentence.strip(), r.doc_id))
    if not scored:
        return config.ABSTAIN_TEXT
    scored.sort(key=lambda s: -s[0])
    return " ".join(f"{text} [{doc_id}]" for _, text, doc_id in scored[:2])


def answer_question(question: str) -> dict:
    """Full RAG path: retrieve -> abstain-or-generate -> verify. Shape matches plan Section 3.3."""
    retrieval = retriever.hybrid_retrieve(question)
    if retrieval.abstain:
        return {
            "answer": config.ABSTAIN_TEXT,
            "abstained": True,
            "sources": [],
            "retrieval_confidence": retrieval.confidence,
            "verified": False,
        }

    template = (config.PROMPTS_DIR / "generation_system.md").read_text(encoding="utf-8")
    context = "\n\n".join(f"[{r.doc_id}] {r.title}\n{r.text}" for r in retrieval.results)
    system = template.replace("{retrieved_chunks_with_doc_ids}", context).replace("{user_query}", question)
    text = llm.text(system, question, fallback=lambda: _extractive_fallback(question, retrieval.results))

    if text.strip().upper().startswith("ABSTAIN"):
        return {
            "answer": config.ABSTAIN_TEXT,
            "abstained": True,
            "sources": _sources(retrieval.results),
            "retrieval_confidence": retrieval.confidence,
            "verified": False,
        }

    verified = verifier.verify(text, retrieval.results)
    if not verified:
        return {
            "answer": config.ABSTAIN_TEXT,
            "abstained": True,
            "sources": _sources(retrieval.results),
            "retrieval_confidence": retrieval.confidence,
            "verified": False,
            "override_reason": "verifier returned UNSUPPORTED",
        }
    return {
        "answer": text,
        "abstained": False,
        "sources": _sources(retrieval.results),
        "retrieval_confidence": retrieval.confidence,
        "verified": True,
    }


# --- aggregation path --------------------------------------------------------

_SCANS = {
    "refund": lambda m: m["refund_issued"] or m["resolution_type"] == "refund_exception",
    "bug": lambda m: m["resolution_type"] == "bug",
    "expected": lambda m: m["resolution_type"] == "expected_behavior",
}


def _select(question: str) -> tuple[str, list[dict]]:
    tickets = [m for m in retriever.all_metadata() if m["doc_type"] == "ticket"]
    q = question.lower()
    negated = any(w in q for w in ("not ", "n't", "wasn", "isn", "except", "other than"))
    if any(w in q for w in ("refund", "credit", "money back", "reimburse")):
        return "refund_issued", [m for m in tickets if _SCANS["refund"](m)]
    if any(w in q for w in ("bug", "escalat", "defect")) or (negated and "expected" in q):
        return "escalated_as_bug", [m for m in tickets if _SCANS["bug"](m)]
    if "expected" in q or "working as intended" in q:
        return "expected_behavior", [m for m in tickets if _SCANS["expected"](m)]
    return "all_tickets", tickets


def aggregate_answer(question: str) -> dict:
    """Answers set-level questions by scanning Chroma metadata in Python — the query
    type pure vector search cannot handle. The LLM only phrases the final sentence.
    """
    scan, matches = _select(question)
    facts = "\n".join(
        f"- {m['doc_id']} ({m['title']}): resolution_type={m['resolution_type'] or 'n/a'}, refund_issued={m['refund_issued']}"
        for m in matches
    ) or "- (no matching tickets)"
    fallback = (
        f"{len(matches)} ticket(s) match ({scan.replace('_', ' ')}): "
        + ", ".join(f"{m['doc_id']} — {m['title']} [{m['doc_id']}]" for m in matches)
        if matches
        else config.ABSTAIN_TEXT
    )
    text = llm.text(
        "You state the result of a database scan in one or two sentences. Use ONLY the rows given. "
        "Cite each ticket id inline in square brackets, e.g. [ticket_105]. Do not add caveats.",
        f"Question: {question}\n\nScan performed: {scan}\nMatching rows:\n{facts}",
        fallback=fallback,
    )
    return {
        "answer": text,
        "abstained": not matches,
        "sources": [
            {"doc_id": m["doc_id"], "title": m["title"], "snippet": f"resolution_type={m['resolution_type']}, refund_issued={m['refund_issued']}", "via_reference": False}
            for m in matches
        ],
        "retrieval_confidence": 1.0 if matches else 0.0,
        "verified": True,
        "scan": scan,
    }
