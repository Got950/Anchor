"""Runnable self-check for the whole backend. `python -m backend.selfcheck` from the repo root.

Asserts the behaviour that would silently rot: metadata extraction, BM25 id mapping,
fused-score abstention, single-hop reference expansion, the aggregation scan, router
paths and the missing-arg guardrail. Runs offline (heuristic fallbacks) or with a key.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import config, llm  # noqa: E402
from backend.app.rag import generator, ingest, retriever  # noqa: E402


def check_ingest(idx):
    assert len(idx.docs_by_id) == 20, len(idx.docs_by_id)
    assert idx.collection.metadata.get("hnsw:space") == "cosine", idx.collection.metadata
    assert len(idx.doc_id_by_position) == 20
    # BM25 positions must map back through doc_id_by_position, not by doc_id.
    scores = idx.bm25.get_scores(ingest.tokenize("bedrock add-on export"))
    best = idx.doc_id_by_position[max(range(len(scores)), key=lambda i: scores[i])]
    assert best in {"doc_04", "ticket_103"}, best

    meta = {m["doc_id"]: m for m in retriever.all_metadata()}
    assert meta["ticket_105"]["resolution_type"] == "refund_exception", meta["ticket_105"]
    assert meta["ticket_105"]["refund_issued"] is True
    assert meta["ticket_106"]["resolution_type"] == "bug", meta["ticket_106"]
    assert meta["doc_04"]["resolution_type"] == "", meta["doc_04"]
    assert "doc_12" in ingest.references_of(meta["ticket_101"]), meta["ticket_101"]
    assert "doc_12" in ingest.references_of(meta["ticket_105"]), meta["ticket_105"]
    print("ok  ingest: 20 docs, cosine space, metadata + references extracted")


def check_retrieval():
    r = retriever.hybrid_retrieve("what export formats are supported")
    assert not r.abstain and r.confidence >= config.ABSTAIN_RRF_THRESHOLD
    assert "doc_04" in [x.doc_id for x in r.results][:2], r.results

    for junk_q in ("zzzqqx wibble frobnicate", "what is the weather in Berlin tomorrow",
                   "how do I install a Kubernetes ingress controller on bare metal"):
        junk = retriever.hybrid_retrieve(junk_q)
        assert junk.abstain and junk.results == [], (junk_q, junk.confidence)

    hop = retriever.hybrid_retrieve("what happened with the ticket about a stuck queued generation")
    by_ref = {x.doc_id: x.via_reference for x in hop.results}
    assert "ticket_101" in by_ref and "doc_12" in by_ref, by_ref   # the cited Known Issues doc is in context
    expanded = [d for d, via in by_ref.items() if via]
    primary_refs = {
        r
        for d, via in by_ref.items()
        if not via
        for r in ingest.references_of(retriever.ingest.get_index().collection.get(ids=[d])["metadatas"][0])
    }
    assert expanded, by_ref                                        # expansion actually fired
    assert set(expanded) <= primary_refs, (expanded, primary_refs)  # single hop only, no strays

    noexp = retriever.hybrid_retrieve("what happened with the ticket about a stuck queued generation", expand_references=False)
    assert not any(x.via_reference for x in noexp.results)
    print("ok  retrieval: RRF fusion, fused-score abstention, reference expansion")


def check_generation():
    res = generator.answer_question("which export formats work with Java Edition")
    assert set(res) >= {"answer", "abstained", "sources", "retrieval_confidence", "verified"}
    assert not res["abstained"] and res["sources"], res
    assert isinstance(res["sources"][0]["via_reference"], bool)

    miss = generator.answer_question("how do I install a Kubernetes ingress controller on bare metal")
    assert miss["abstained"] and miss["answer"] == config.ABSTAIN_TEXT, miss

    agg = generator.aggregate_answer("which tickets resulted in a refund")
    assert [s["doc_id"] for s in agg["sources"]] == ["ticket_105"], agg
    bug = generator.aggregate_answer("which ticket was not closed as expected behavior")
    assert [s["doc_id"] for s in bug["sources"]] == ["ticket_106"], bug
    print("ok  generation: grounded answer, abstention, aggregation scan")


def check_agent():
    from backend.app.agent import router, tools

    full = router.handle("please file a support ticket about floating coral on large underwater builds, high priority")
    assert full["type"] == "tool_call" and full["tool"] == "create_support_ticket", full
    assert full["tool_result"]["ticket_id"].startswith("TCK-"), full
    assert full["reasoning"], full

    guard = router.handle("create a ticket")
    assert guard["type"] == "clarify", guard
    assert "priority" in guard["clarifying_question"].lower(), guard

    flag = router.handle("flag this generation for review because the castle has floating blocks")
    assert flag["type"] == "tool_call" and flag["tool"] == "flag_generation_for_review", flag

    ask = router.handle("how do I get an API key")
    assert ask["type"] == "answer" and ask["sources"], ask
    # The UI's confidence / groundedness badges read these off the /agent payload too,
    # not just /ask, and agent mode is the frontend default.
    assert isinstance(ask["retrieval_confidence"], float) and ask["verified"] is True, ask

    agg = router.handle("which tickets got a refund")
    assert agg["type"] == "answer" and [s["doc_id"] for s in agg["sources"]] == ["ticket_105"], agg

    off = router.handle("what's the weather in Berlin tomorrow")
    assert off["type"] in {"clarify", "abstain"}, off

    assert tools.CreateTicketArgs(summary="floating coral", priority="high").priority == "high"
    print("ok  agent: 4 router paths, tool_use args, Pydantic guardrail")


def check_readme_prompts():
    """README section 7 pastes all four prompt files verbatim; assert they haven't drifted.

    A prompt quoted in the write-up that no longer matches the one the system runs is a
    silent documentation lie, and the ticket_105 precedence rule (section 4) lives in one
    of these files — so this is exactly the line most likely to go stale.
    """
    readme = (config.BACKEND_DIR.parent / "README.md").read_text(encoding="utf-8")
    for name in ("generation_system", "metadata_extraction", "router_system", "verifier_system"):
        body = (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
        assert f"### `prompts/{name}.md`" in readme, f"README missing heading for {name}"
        assert body in readme, f"README copy of prompts/{name}.md has drifted from the file"
    print("ok  README: all 4 prompt files pasted verbatim in section 7")


def check_logs():
    assert config.LOG_PATH.exists(), config.LOG_PATH
    lines = [l for l in config.LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines, "no log lines written"
    import json

    last = json.loads(lines[-1])
    assert {"timestamp", "path", "reasoning"} <= set(last), last
    print(f"ok  logging: {len(lines)} JSONL entries at {config.LOG_PATH.name}")


if __name__ == "__main__":
    print(f"llm available: {llm.available()} (model={config.LLM_MODEL})")
    idx = ingest.build_index()
    check_ingest(idx)
    check_retrieval()
    check_generation()
    if "--rag-only" not in sys.argv:
        check_agent()
        check_readme_prompts()
        check_logs()
    print("ALL CHECKS PASSED")
