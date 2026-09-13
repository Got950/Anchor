# Final comprehensive bench report

**Date:** 2026-09-13 (post-fix re-run)  
**Root-cause fix applied before this run:** serialize `SentenceTransformer.encode` + `torch.set_num_threads(1)` in `backend/app/rag/ingest.py` (see diagnosis below).  
**Backend:** cold-restarted uvicorn on `:8000` (`documents=20`, `llm=true`, `model=gpt-4.1-mini`).

---

## Diagnosis (completed before fix)

| Check | Finding |
|---|---|
| Responses `tool_use` client lifecycle | Module singleton `_get_client()` — **no** per-call `OpenAI()` / httpx leak |
| `previous_response_id` memory | **No** in-process dict; OpenAI `store=True` only |
| Sequential 30× ask/agent | Threads stable (~134); handles/TCP not unbounded |
| Concurrent 10× `/ask` (no Responses) | Threads **134 → 260** and **stayed** elevated |
| Isolated `SentenceTransformer.encode` ×16 | Threads **80 → 288** permanent |
| Same encodes under a lock | Threads **80 → 93** |
| Broken pre-fix PID | **379 threads**, ~2.3 GB private; `/ask` 500 while `/health` 200 |

**Root cause:** concurrent FastAPI sync handlers call `Index.embed()` → nested OpenMP/torch thread pools permanently accumulate until native corruption (ACCESS_VIOLATION / empty RAG / hard 500s).

**Not introduced by the Responses API migration** (migration keeps the same singleton client). Stress §4’s 20-way concurrency on the shared embed path is what poisons a long-lived process; a later sequential pass then collapses.

**Minimal fix:** `_EMBED_LOCK` around `embed()` + `torch.set_num_threads(1)` at index build.

**Post-fix concurrency probe:** threads 111 → 130 under 10+10 ask/agent; all 200s. After full stress_pass: threads **106**.

---

## SECTION A — Core functional regression (`stress_pass.py`)

| Check | Baseline | This run | Verdict |
|---|---|---|---|
| Functional (stress §1) | 72/75 | **73/75** | PASS (≥ baseline) |
| Retrieval edges (stress §2) | 8/8 | **8/8** | PASS |
| Guardrails (stress §3) | 5/5 | **5/5** | PASS |
| Concurrency (stress §4) | 10/10 both | **ask 1.0 / agent 1.0 (10/10)**; `post_load_consistent=true` | PASS |

Functional misses (same known awkward-refund pair as prior reports):

| Case | Notes |
|---|---|
| `1.agg/refund_awkward/ask` | Answers GPU category / doc_06 path; does not mention `ticket_105` |
| `1.agg/refund_awkward/agent` | Same |

---

## SECTION B — RAGAS + behavioral (`run_eval.py`)

| Check | Baseline | This run | Re-check | Verdict |
|---|---|---|---|---|
| Faithfulness | 1.000 | **0.881** | **0.857** | **FLAG** (worse; stable across 2 runs) |
| context_precision | 0.976 | 0.976 | 0.976 | PASS |
| context_recall | 1.000 | 1.000 | 1.000 | PASS |
| answer_relevancy | ~0.76–0.78 | **0.737** | **0.654** | **FLAG** (below band; judge-noisy but below) |
| Behavioral accuracy | 8/8 | **8/8** | **8/8** | PASS |

Note: generator/verifier paths were **not** changed by the embed-lock fix; faithfulness drop matches prior flaky judge behavior seen in `docs/testing/final-check.md` (0.810), but still fails the stated 1.000 baseline.

---

## SECTION C — Hallucination stability (`hallucination_stability.py`)

| Check | Baseline | This run | Verdict |
|---|---|---|---|
| Part A | 28/30, 0 contamination | **29/30**, **0 contamination** (A#14 abstain on known-answer, not contamination) | PASS (≥ baseline) |
| Part B | 0 hallucinations past verifier | **0** past verifier (SUPPORTED or ABSTAINED_NO_VERIFIER_VETO only) | PASS |

---

## SECTION D — Multi-turn Responses API (`agent_multiturn_check.py`)

| # | Case | Verdict |
|---|---|---|
| 1 | Happy path clarify → tool (`Bedrock`, `high`) | **PASS** |
| 2 | `3d asset for a lamp` → `High` → no infinite loop / give-up | **PASS** |
| 3 | Stale clarify id + unrelated formats question → answer, no ticket merge | **PASS** |
| 4 | Post tool_call `response_id=""` then fresh free-tier ask | **PASS** |
| 5 | `/agent` clarify then `/ask` export formats → `/ask` unaffected | **PASS** |
| 6 | Two vague non-answers → cap / give-up, no 3rd asking clarify | **PASS** |
| 7 | Malformed `previous_response_id` (fake / empty / null) → 200, no crash | **PASS** |
| 8 | Two concurrent conversations → zero bleed-through | **PASS** |
| 9 | Usage non-null via Responses field mapping | **PASS** |

Real usage log line (uvicorn / `_record_usage`):

```text
INFO:backend.app.llm:llm usage prompt_tokens=793 completion_tokens=45 total_tokens=838
```

(API `usage` on same call: `prompt_tokens=793`, `completion_tokens=45`, `total_tokens=838`, `calls=1`; est. cost ≈ `$0.000389`.)

---

## SECTION E — Full spec compliance

| Part | Check | Verdict |
|---|---|---|
| 1 | `/ask` goldens: export formats answer; refund answer; confidence 0.62 answer; PayPal abstain | **PASS** |
| 1 | Retriever unmodified vs HEAD; verifier unmodified | **PASS** |
| 1 | `generator.py` / `ingest.py` dirty vs HEAD | **FLAG** (see §F) |
| 2 | Single-message tool call + clarify guardrail | **PASS** |
| 2 | Tool calls logged with timestamp (`tool_calls.jsonl`) | **PASS** |
| 2 | Multi-turn (Section D) | **PASS** |
| 3 | Clarify + tool_call render in UI; sources/loading present in product | **PASS** (live UI) |
| 3 | Network: follow-up POST `/agent` includes `previous_response_id=resp_…`; response returns `response_id=""` after tool | **PASS** |
| 3 | Mode toggle resets `prevResponseId` in `frontend/app/page.tsx` | **PASS** (code) |
| 4 | Assets exist; git blob hashes match HEAD (`block_texture.png`, `block_model.json`, `model_preview.png`) | **PASS** (unmodified) |
| 5 | README documents multi-turn / `previous_response_id` conversation memory | **FLAG** — **missing** (no matches for multi-turn / `previous_response_id` / Responses memory). Not added this pass. |

---

## SECTION F — Scope audit

Files dirty vs git HEAD (working tree), vs migration allowlist  
*(allowed: `router.py`, `schemas.py`, `guardrails.py`, `logging_utils.py`, `llm.py` tool_use/`_record_usage`, frontend `response_id` handling, `main.py` `/agent`)*:

| File | In allowlist? | Notes |
|---|---|---|
| `backend/app/agent/router.py` | yes | migration |
| `backend/app/schemas.py` | yes | migration |
| `backend/app/agent/guardrails.py` | yes | migration |
| `backend/app/llm.py` | yes | migration |
| `backend/app/main.py` | yes | migration |
| `frontend/app/page.tsx`, `types.ts`, related UI | yes | `response_id` handling |
| `backend/app/rag/ingest.py` | **no** | **this pass’s embed-lock fix** (required for A concurrency) |
| `backend/app/rag/generator.py` | **no** | ticket-set `/ask` divert — **scope leakage** vs migration-only claim |
| `README.md`, `.gitignore`, `selfcheck.py`, `package.json`, etc. | **no** | broader repo drift |
| `backend/app/logging_utils.py` | — | clean vs HEAD |

---

## Verdict

NOT READY — (1) RAGAS faithfulness **0.881/0.857** vs baseline **1.000** (confirmed on re-run); (2) answer_relevancy **0.737/0.654** below ~0.76–0.78 band; (3) README still does not document multi-turn conversation memory; (4) scope: `generator.py` (and this fix’s `ingest.py`) sit outside the stated migration allowlist.
