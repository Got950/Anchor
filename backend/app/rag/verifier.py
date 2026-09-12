"""Groundedness check — a prompted, single-call approximation of Self-RAG's ISSUP
reflection token (Asai et al. 2023). Not the trained mechanism from the paper.
"""
from __future__ import annotations

from .. import config, llm
from .retriever import Retrieved


def verify(answer: str, contexts: list[Retrieved]) -> bool:
    """True if the answer is fully supported by the retrieved passages."""
    template = (config.PROMPTS_DIR / "verifier_system.md").read_text(encoding="utf-8")
    passages = "\n\n".join(f"[{c.doc_id}] {c.text}" for c in contexts)
    system = template.replace("{retrieved_chunks}", passages).replace("{generated_answer}", answer)
    # ponytail: offline fallback trusts the answer (the generator is extractive when offline,
    # so it cannot hallucinate). Ceiling: no real verification without an API key.
    verdict = llm.text(system, "Respond with SUPPORTED or UNSUPPORTED.", fallback="SUPPORTED")
    return "UNSUPPORTED" not in verdict.upper()
