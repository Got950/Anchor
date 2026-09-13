# Final verification pass — 2026-09-12

Harnesses reused: `backend/eval/stress_pass.py`, `backend/eval/run_eval.py`, `backend/eval/hallucination_stability.py`. Frontend checks via live UI at `http://127.0.0.1:3000` against `http://127.0.0.1:8000`. No application code changed for this pass.

---

## Part 1 — Backend regression

Baseline → this run. **FLAG** = worse than baseline.

| Check | Baseline | This run | Verdict |
|---|---|---|---|
| Functional (stress §1) | 72/75 | **71/75** | **FLAG** |
| Retrieval edges (stress §2) | 8/8 | 8/8 | PASS |
| Guardrails (stress §3) | 5/5 | 5/5 | PASS |
| Concurrency (stress §4) | 10/10 both endpoints | ask 1.0 / agent 1.0 (10/10) | PASS |
| RAGAS faithfulness | 1.000 | **0.810** (confirmed 0.810 on immediate re-run) | **FLAG** |
| RAGAS context_precision | 0.976 | 0.976 | PASS |
| RAGAS context_recall | 1.000 | 1.000 | PASS |
| RAGAS answer_relevancy | ~0.76–0.78 | **0.636** / **0.637** (2 runs) | **FLAG** |
| Behavioural | 8/8 | 8/8 | PASS |
| Hallucination Part A | 28/30, 0 contamination | 28/30, 0 contamination | PASS |
| Hallucination Part B | 0 hallucinations past verifier | 0 past verifier (B11 correctly cites GPU category (3) / `doc_06`) | PASS |

### Functional failures (4)

| Case | Notes |
|---|---|
| `1.multihop/hop_queued_v1/ask` | Abstained despite `via_ref` + `ticket_101`/`doc_12` — known intermittent multihop |
| `1.multihop/hop_queued_v1/agent` | Same abstain on agent path (extra miss vs prior 72/75) |
| `1.agg/refund_awkward/ask` | Answers GPU category path; does not mention `ticket_105` — documented limitation |
| `1.agg/refund_awkward/agent` | Same |

---

## Part 2 — Frontend regression

| Check | /agent | /ask | Verdict |
|---|---|---|---|
| **answer** — material border, sources expand/collapse, legible text | green edge `rgb(74,122,107)`; sources open/close; body readable | same answer styling; sources present; no `why this path` (API has no reasoning) | PASS |
| **abstain** — color + text | terracotta edge; “not covered” / “Not covered in the documentation.” | same | PASS |
| **tool_call** — monospace JSON + color | amber edge; JetBrains Mono args/result | N/A — `/ask` has no tool router (by design) | PASS (/agent) |
| **clarify** — color + question | clay edge; clarifying question renders | N/A — `/ask` has no clarify path (by design) | PASS (/agent) |
| Segmented toggle switches mode (not just visually) | — | mode note updates; `fetch` hits `http://127.0.0.1:8000/ask` | PASS |
| Example chips populate + submit | chips fire `send(q)` and produce turns | chips work in both modes | PASS |
| “why this path” disclosure | opens with router reasoning on agent answers | absent on `/ask` answers (expected) | PASS |
| Mobile width (375px) | no page overflow (`scrollWidth=375`); chips intentional `overflow-x: auto` row | same | PASS |
| Keyboard focus visible | `:focus-visible` charcoal outline rules present in CSS; automation webview did not set `:focus-visible` on Tab | — | PASS* |
| Console / UI errors | no `.status--error`; no failed UI binding | — | PASS |

\*CSS focus rings are shipped; browser automation could not force `:focus-visible` matching.

---

## Part 3 — End-to-end via actual frontend UI

All five sent through the UI (not curl), `/agent` unless noted.

| # | Query | Expected | UI render | Round trip |
|---|---|---|---|---|
| 1 | Which export formats work with Java Edition? | semantic answer | `turn--answer`, sources, Java formats | PASS |
| 2 | Which tickets resulted in a refund? | aggregation answer | `turn--answer`, ticket_105 / #1097 | PASS |
| 3 | Can I pay for my Craftify subscription with PayPal? | abstain | `turn--abstain` | PASS |
| 4 | Flag this generation for review because the castle has floating blocks | tool_call | `turn--tool_call`, monospace args/result | PASS |
| 5 | Create a ticket | clarify | `turn--clarify`, asks for summary/priority | PASS |

Extra: after switching to `/ask`, confidence-score answer and Studio SLA abstain both hit `/ask` and rendered correctly.

---

## Part 4 — Fresh cold-start sanity

| Step | Result |
|---|---|
| Kill listeners on 8000/3000 | ports free |
| Start uvicorn with no shell `OPENAI_API_KEY` (loads `backend/.env` only) | boot clean; ingest 20 docs |
| Start `npm run dev` on 3000 | Ready in ~1.5s |
| `GET /health` | `{"status":"ok","documents":20,"llm":true,"model":"gpt-4.1-mini"}` |
| One UI query (export formats chip) | `turn--answer` with correct Java formats |

---

## Verdict

**NOT READY** — Part 1 regressions vs last recorded numbers: functional **71/75** (was 72/75), RAGAS **faithfulness 0.810** (was 1.000; stable across two runs), **answer_relevancy ~0.64** (was ~0.76–0.78). Parts 2–4 (UI + E2E + cold start) all pass; no frontend binding breakage found.
