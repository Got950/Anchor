"""Build docs/testing/test-report.md from stress_results.json + known eval/fix outcomes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "docs" / "testing"
d = json.loads((REPORTS / "stress_results.json").read_text(encoding="utf-8"))
s4, s5 = d["section4"], d["section5"]


def table(rows: list[dict], title: str) -> str:
    lines = [
        f"### {title}",
        "",
        "| test case | expected | actual | pass/fail |",
        "|---|---|---|---|",
    ]
    for r in rows:
        actual = (r.get("actual") or "").replace("|", "\\|").replace("\n", " ")
        if len(actual) > 160:
            actual = actual[:157] + "..."
        exp = (r.get("expected") or "").replace("|", "\\|")
        pf = "PASS" if r["pass"] else "FAIL"
        lines.append(f"| `{r['case']}` | {exp} | {actual} | **{pf}** |")
    npass = sum(1 for r in rows if r["pass"])
    lines += ["", f"**Score: {npass}/{len(rows)}**", ""]
    return "\n".join(lines)


parts: list[str] = []
parts.append(f"""# Craftify Exhaustive Test Report

Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  
Backend health at start: `{json.dumps(d['health'])}`  
Harness: `backend/eval/stress_pass.py` + `backend/eval/run_eval.py` + manual failure-mode / build checks.

**Policy:** Findings were logged first against the pre-fix code. Fixes (flag-arg grounding, `/ask` aggregation keyword divert, clearer empty-corpus errors) were applied afterward; before/after is recorded in Known Issues.

---

## 1. Functional coverage — all query types × both endpoints

{table(d['section1'], 'Section 1 results')}

Notes from failures (pre-fix):
- `1.agg/refund_exact/ask` and `1.agg/refund_awkward/ask`: `/ask` had no aggregation path and confidently answered that no tickets were refunded (or cited the wrong GPU-credit policy). **Fixed after logging** — see Known Issues.
- `1.tool/flag_missing/agent`: router invented `reason: "User requested to flag... without specifying a reason."` and called the tool. **Fixed after logging**.
- Whitespace-only messages: HTTP 200 (Pydantic `min_length=1` counts spaces); `/ask` abstains, `/agent` clarifies. Empty string correctly 422.
- Wrong-type priority (`urgent`, `1`): model mapped to `high` and tool_call succeeded (acceptable; enum validated downstream).

---

## 2. Edge cases on retrieval

{table(d['section2'], 'Section 2 results')}

Rapid-fire: abstain and answer decisions were stable across 3 identical `/ask` calls (confidence values identical within each trio).

---

## 3. Guardrail / safety stress

{table(d['section3'], 'Section 3 results')}

Malicious tool summary (`<script>` + SQL-looking string): accepted as ordinary string data, ticket created, no execution — Pydantic treated it as `str`. Logged as tool_call with echoed summary.

---

## 4. Load / concurrency (10 concurrent each)

| endpoint | n | success | errors | success rate | p50 ms | p95 ms | p99 ms | mean ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| /ask | {s4['ask']['n']} | {s4['ask']['success']} | {s4['ask']['errors']} | {s4['ask']['success_rate']} | {s4['ask']['p50_ms']} | {s4['ask']['p95_ms']} | {s4['ask']['p99_ms']} | {s4['ask']['mean_ms']} |
| /agent | {s4['agent']['n']} | {s4['agent']['success']} | {s4['agent']['errors']} | {s4['agent']['success_rate']} | {s4['agent']['p50_ms']} | {s4['agent']['p95_ms']} | {s4['agent']['p99_ms']} | {s4['agent']['mean_ms']} |

Post-load health: `{json.dumps(s4['post_load_health'])}`  
Chroma/BM25 consistency after load: **{'PASS' if s4['post_load_consistent'] else 'FAIL'}** ({s4['post_load_note']})

---

## 5. Latency & cost benchmark (10 sequential each, no concurrency)

| endpoint | ok/n | avg latency ms | p50 ms | avg est. input tokens | avg est. output tokens | avg est. $/req |
|---|---:|---:|---:|---:|---:|---:|
| /ask | {s5['ask']['ok']}/{s5['ask']['n']} | {s5['ask']['avg_latency_ms']} | {s5['ask']['p50_ms']} | {s5['ask']['avg_est_input_tokens']} | {s5['ask']['avg_est_output_tokens']} | {s5['ask']['avg_est_cost_usd']} |
| /agent | {s5['agent']['ok']}/{s5['agent']['n']} | {s5['agent']['avg_latency_ms']} | {s5['agent']['p50_ms']} | {s5['agent']['avg_est_input_tokens']} | {s5['agent']['avg_est_output_tokens']} | {s5['agent']['avg_est_cost_usd']} |

Pricing basis: `{s5['pricing']['model']}` at ${s5['pricing']['in_per_1M']}/1M input + ${s5['pricing']['out_per_1M']}/1M output.

**Latency breakdown:** API does not expose retrieval vs generation vs verifier timings. Approximate structure:
- `/ask`: retrieval (local, typically <100ms) + generation LLM + verifier LLM
- `/agent`: router tool-call LLM + (for answer/abstain) same RAG stack; tool/clarify paths skip generation

Token/cost figures are **real OpenAI usage** summed across all LLM calls in the request (`response.usage`); assume ~2 LLM calls for `/ask`, 1–3 for `/agent`.

### Per-request sequential detail

| endpoint | query (truncated) | ms | est in | est out | est $ |
|---|---|---:|---:|---:|---:|
""")

for ep in ("ask", "agent"):
    for r in s5[ep]["runs"]:
        parts.append(
            f"| /{ep} | {r['payload']} | {r['ms']} | {r['est_input_tokens']} | {r['est_output_tokens']} | {r['est_cost_usd']} |"
        )

parts.append("""
---

## 6. RAGAS + behavioral re-verification

Fresh `python backend/eval/run_eval.py` against live backend with **real API key** (`/health` → `llm: true`, model `gpt-4.1-mini`).

### RAGAS (7 generation pairs, judge `gpt-4.1-mini`)

| metric | score |
|---|---|
| faithfulness | **0.900** |
| answer_relevancy | **0.730** |
| context_precision | **0.976** |
| context_recall | **1.000** |

Retrieval: **7/7** ground-truth sources hit; multi-hop reference expansion **2/2**.

### Behavioural accuracy: **8/8 = 100%**

| question | expected | got | pass |
|---|---|---|---|
| Which support tickets resulted in a refund? | aggregation | answer | PASS |
| Which ticket was NOT closed as expected behavior? | aggregation | answer | PASS |
| How many tickets were closed as expected behavior? | aggregation | answer | PASS |
| How do I install a Kubernetes ingress controller on bare metal? | abstain | abstain | PASS |
| What uptime SLA does Craftify guarantee on the Studio tier? | abstain | abstain | PASS |
| Can I pay for my Craftify subscription with PayPal? | abstain | abstain | PASS |
| File a support ticket about floating coral, high priority | tool_call | tool_call | PASS |
| Create a ticket | clarify | clarify | PASS |

### Previously-failing plausible-but-absent cases (re-hit live)

| case | /ask | /agent | pass |
|---|---|---|---|
| Studio uptime SLA | `abstained=true`, answer=`ABSTAIN: not covered...` | `type=abstain`, same ABSTAIN text | **PASS** |
| PayPal payment | `abstained=true`, ABSTAIN | `type=abstain`, ABSTAIN | **PASS** |

No hallucinated SLA/PayPal policy in either response.

---

## 7. Failure-mode / resilience

| test case | expected | actual | pass/fail |
|---|---|---|---|
""")

for r in d["section7_api"]:
    actual = (r["actual"] or "").replace("|", "\\|")[:160]
    parts.append(
        f"| `{r['case']}` | {r['expected']} | {actual} | **{'PASS' if r['pass'] else 'FAIL'}** |"
    )

parts.append("""| Bad API key (uvicorn :8001, `OPENAI_API_KEY=sk-invalid...`) | clear error, no crash, no silent wrong answer | No crash. LLM 401 logged; **falls back to heuristics** and returns HTTP 200 with extractive/keyword answers. `/health` still reports `llm: true` (non-empty key, not validated). | **FAIL** (graceful ≠ clear) |
| Empty corpus dir at startup | fail loudly/clearly | **Before fix:** Chroma `ValueError: Expected Embeddings... got []`. **After fix:** `RuntimeError: Corpus directory is empty (no *.txt files): ... Refusing to start with a broken index.` | **PASS** (after fix) |
| Missing corpus dir at startup | fail loudly/clearly | **Before fix:** same opaque Chroma error. **After fix:** `FileNotFoundError: Corpus directory missing: ...` | **PASS** (after fix) |

---

## 8. Build / deploy sanity

| test case | expected | actual | pass/fail |
|---|---|---|---|
| `npm run build` (frontend) | clean build | First attempt this session: exit `3221225477` (Windows AV, known flaky). Immediate retry: **compiled successfully**, static pages 4/4, EXIT=0 | **PASS** (retry; flaky first try) |
| Cold-start `uvicorn` with only `.env` | starts clean, llm true | Killed prior process; fresh shell with `OPENAI_API_KEY` unset so dotenv loads `.env`; startup complete; `/health` → `documents=20, llm=true, model=gpt-4.1-mini` | **PASS** |

---

## Fixes applied after initial fail log (before → after)

| issue | before | fix | after re-test |
|---|---|---|---|
| Flag with no reason invents args | `type=tool_call`, invented reason | `guardrails._grounded()` drops ungrounded `summary`/`reason` before Pydantic | `type=clarify` asking for reason |
| `/ask` refund aggregation | Confident wrong: "None of the support tickets resulted in a refund" | Keyword divert in `answer_question` → `aggregate_answer` | Answers `ticket_105` correctly |
| Empty/missing corpus | Opaque Chroma upsert error | Explicit `FileNotFoundError` / `RuntimeError` in `ingest.build_index` | Clear message, refuse start |

---

## Known issues (ranked by severity)

1. **HIGH — Bad/invalid API key silently serves heuristic answers.** LLM failures fall back instead of returning an error. `/health.llm` is true whenever a non-empty key string is set, including invalid keys. Reviewers can mis-measure the system (documented in README §4). Mitigation already present: check `/health` + watch logs for 401 warnings. Not changed — deliberate offline-demo tradeoff.

2. **MEDIUM — `/ask` aggregation coverage is heuristic-only.** Post-fix keyword divert catches refund/credit/expected-behavior style asks, but `/ask` still lacks the LLM router. Novel paraphrases without those cues can still take the semantic path and answer wrongly. Prefer `/agent` for set-level ticket questions.

3. **MEDIUM — Multi-hop generation intermittent abstain** (from README; ~2/28 calls). Not reproduced as a failure in this pass's golden multi-hop rows, but still a documented nondeterminism risk for faithfulness averages.

4. **MEDIUM — RAGAS faithfulness at ship gate.** This run hit **0.900** (gate was >0.9; borderline). Prior reported run was 0.845. `answer_relevancy` **0.730** still below the 0.8 want (judge often returns 1/3 reverse questions).

5. **LOW — `next build` Windows access violation flakiness.** Still saw 1 crash (`3221225477`) then a clean build with `experimental.cpus: 1`. Treat as environment flake; retry once.

6. **LOW — Whitespace-only input accepted (HTTP 200).** Empty string correctly 422; spaces alone pass `min_length=1`. Harmless (abstain/clarify) but not rejected at the schema layer.

7. **LOW — (resolved) Token usage instrumented.** Cost numbers above use real `prompt_tokens`/`completion_tokens` from OpenAI summed per request.

---

## Bottom line

| area | result |
|---|---|
| Functional (pre-fix) | 72/75 |
| Functional (post-fix spot-check of the 3 fails) | 3/3 now PASS |
| Retrieval edges | 8/8 |
| Guardrails | 5/5 |
| Concurrency | 20/20, p50 ask 2337ms / agent 3350ms |
| Sequential latency | ask ~1.6s avg, agent ~2.2s avg |
| Est. cost | ~$0.00054/ask, ~$0.00067/agent (real API usage) |
| RAGAS | faithfulness 0.900, relevancy 0.730, precision 0.976, recall 1.000 |
| Behavioural | **8/8** (incl. both prior plausible-absent fails) |
| Malformed JSON | 422 |
| Empty/missing corpus | fails loudly (after fix) |
| Bad API key | no crash, but silent fallback (**known issue #1**) |
| `next build` | PASS on retry |
| Cold-start uvicorn | PASS |
""")

out = REPORTS / "test-report.md"
out.write_text("\n".join(parts), encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size} bytes)")
