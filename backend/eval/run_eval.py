"""Evaluation harness: RAGAS on the generation pairs, behavioural pass/fail on the rest.

Usage (backend running on :8000):
    python backend/eval/run_eval.py               # full run
    python backend/eval/run_eval.py --no-ragas    # behavioural checks only

Writes backend/eval/results.md, which is pasted into README section "Evaluation actually run".
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import config, llm  # noqa: E402
from backend.app.rag import ingest  # noqa: E402

API = "http://127.0.0.1:8000"

# /ask returns a 220-char display snippet per source, which is what the UI needs but is
# the wrong thing to score: judging faithfulness/context_recall against truncated evidence
# marks a grounded claim unsupported purely because the sentence backing it was cut off.
# RAGAS gets the full corpus text for the doc_ids the API actually retrieved.
FULL_TEXT = {d.doc_id: d.text for d in ingest.load_corpus()}


def _import_ragas():
    """ragas 0.4.x still does `from langchain_community.chat_models.vertexai import ChatVertexAI`,
    a module that langchain-community 0.4 removed. Stub it so the rest of ragas imports.
    """
    if "langchain_community.chat_models.vertexai" not in sys.modules:
        stub = types.ModuleType("langchain_community.chat_models.vertexai")
        stub.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules["langchain_community.chat_models.vertexai"] = stub
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    return EvaluationDataset, evaluate, [faithfulness, answer_relevancy, context_precision, context_recall]


def post(path: str, payload: dict) -> dict:
    res = requests.post(f"{API}{path}", json=payload, timeout=120)
    res.raise_for_status()
    return res.json()


def run(no_ragas: bool = False) -> str:
    golden = json.loads(config.GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    lines: list[str] = []

    # --- generation pairs -> RAGAS -------------------------------------------
    gen_pairs = [g for g in golden if g["expected_type"] == "answer"]
    samples, retrieval_rows = [], []
    for g in gen_pairs:
        res = post("/ask", {"question": g["question"]})
        contexts = [FULL_TEXT.get(s["doc_id"], s["snippet"]) for s in res["sources"]]
        samples.append(
            {
                "user_input": g["question"],
                "response": res["answer"],
                "retrieved_contexts": contexts or ["(no context retrieved)"],
                "reference": g["ground_truth"],
            }
        )
        got = {s["doc_id"] for s in res["sources"]}
        via_ref = {s["doc_id"] for s in res["sources"] if s["via_reference"]}
        retrieval_rows.append(
            {
                "question": g["question"],
                "expected_sources": g["ground_truth_sources"],
                "hit": set(g["ground_truth_sources"]) <= got,
                "multi_hop": g["requires_reference_expansion"],
                "via_reference_used": bool(via_ref),
                "confidence": res["retrieval_confidence"],
                "abstained": res["abstained"],
            }
        )

    lines.append("### RAGAS (generation pairs)\n")
    if no_ragas or not llm.available():
        lines.append("_Skipped: no judge LLM configured (set OPENAI_API_KEY in backend/.env)._\n")
    else:
        EvaluationDataset, evaluate, metrics = _import_ragas()
        result = evaluate(
            dataset=EvaluationDataset.from_list(samples),
            metrics=metrics,
            llm=llm.judge_llm(),               # explicitly wrapped judge, never RAGAS's default
            embeddings=llm.judge_embeddings(),
        )
        scores = result._repr_dict if hasattr(result, "_repr_dict") else dict(result)
        lines.append(f"Judge LLM: `{config.JUDGE_MODEL}` (LangchainLLMWrapper). Pairs scored: {len(samples)}\n")
        lines.append("| metric | score |\n|---|---|")
        for name, value in scores.items():
            lines.append(f"| {name} | {value:.3f} |" if isinstance(value, float) else f"| {name} | {value} |")
        lines.append("")
        result.to_pandas().to_csv(Path(__file__).parent / "ragas_per_sample.csv", index=False)

    # --- retrieval / reference expansion ------------------------------------
    lines.append("\n### Retrieval (ground-truth sources present in context)\n")
    lines.append("| question | expected | hit | multi-hop | via_reference present | confidence |\n|---|---|---|---|---|---|")
    for r in retrieval_rows:
        lines.append(
            f"| {r['question'][:60]} | {', '.join(r['expected_sources'])} | {'PASS' if r['hit'] else 'FAIL'} "
            f"| {'yes' if r['multi_hop'] else 'no'} | {'yes' if r['via_reference_used'] else 'no'} | {r['confidence']} |"
        )
    hops = [r for r in retrieval_rows if r["multi_hop"]]
    hop_pass = sum(1 for r in hops if r["hit"] and r["via_reference_used"])
    lines.append(f"\nReference-expansion pairs passing (both docs in context AND a via_reference source): {hop_pass}/{len(hops)}\n")

    # --- behavioural pairs ---------------------------------------------------
    behaviour = [g for g in golden if g["expected_type"] != "answer"]
    lines.append("\n### Behavioural accuracy (aggregation / abstain / tool paths, via /agent)\n")
    lines.append("| question | expected | got | pass |\n|---|---|---|---|")
    passes = 0
    for g in behaviour:
        res = post("/agent", {"message": g["question"]})
        got = res["type"]
        if g["expected_type"] == "aggregation":
            ok = got == "answer" and g["expected_answer_contains"] in json.dumps(res)
        elif g["expected_type"] == "abstain":
            ok = got == "abstain"
        elif g["expected_type"] == "tool_call":
            ok = got == "tool_call" and res.get("tool") == g["expected_tool"]
        else:  # clarify
            ok = got == "clarify"
        passes += ok
        lines.append(f"| {g['question'][:60]} | {g['expected_type']} | {got} | {'PASS' if ok else 'FAIL'} |")
    lines.append(f"\nBehavioural accuracy: {passes}/{len(behaviour)} = {passes / len(behaviour):.0%}\n")

    abstain_pairs = [g for g in behaviour if g["expected_type"] == "abstain"]
    abstain_pass = sum(
        1 for g in abstain_pairs if post("/agent", {"message": g["question"]})["type"] == "abstain"
    )
    lines.append(f"Abstention accuracy on unanswerable subset: {abstain_pass}/{len(abstain_pairs)}\n")

    report = "\n".join(lines)
    out = Path(__file__).parent / "results.md"
    out.write_text(f"# Evaluation results\n\nGolden set: {len(golden)} pairs "
                   f"({len(gen_pairs)} generation, {len(behaviour)} behavioural)\n\n{report}", encoding="utf-8")
    print(report)
    print(f"\nwritten to {out}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ragas", action="store_true")
    run(parser.parse_args().no_ragas)
