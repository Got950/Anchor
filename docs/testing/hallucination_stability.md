# Hallucination-stability test

**Date:** 2026-09-12  
**Target:** `POST http://127.0.0.1:8000/ask` (`llm: true`, `gpt-4.1-mini`, 20 docs)  
**Harness:** `backend/eval/hallucination_stability.py`  
**Raw results:** `docs/testing/hallucination_stability_raw.json`  
**Scope:** Correctness under concurrent distinct questions + verifier faithfulness under varied single-shot queries. Not a load/throughput test (concurrency fixed at 30).

---

## Part A — Cross-request contamination under concurrency

**Setup:** 30 concurrent `/ask` calls, each with a **different** known-answer question (distinct corpus facts; golden-set + corpus extensions). For each response, checked whether answer/sources match **that** request’s topic (not another in-flight request).

**Wall time:** ~4.1s for the batch (parallel LLM calls).

### Verdict

| Metric | Count |
|---|---|
| Requests | 30 |
| On-topic correct | 24 |
| Wrong / abstain for own question (not peer leak) | 6 |
| **True cross-request contamination** | **0** |

No response contained another concurrent request’s distinct topic (e.g. export-formats answers did not appear on BotW/refund questions, confidence `0.62` did not leak into unrelated answers, etc.). Shared in-memory Chroma/BM25 state did **not** show mix-up under this concurrency.

### Pass/fail per request

| # | Topic | Result | Notes |
|---|---|---|---|
| 1 | export formats | **PASS** | `.schematic` / `.litematic` / `.glb` / `.nbt` via `doc_04` |
| 2 | free tier limits | **PASS** | 10/day, 64³ via `doc_05` |
| 3 | review confidence | **PASS** | `< 0.62` via `doc_07` |
| 4 | API key / Studio | **PASS** | Studio + Account Settings > Developer |
| 5 | custom preset refs | **PASS** | ≥5 builds via `doc_03` |
| 6 | stuck-on-queued multi-hop | **FAIL** (own-Q) | Abstained despite retrieving `ticket_101` + `doc_12` — not contamination |
| 7 | floating coral multi-hop | **PASS** | Known Issue #2 + 128 workaround |
| 8 | refund-eligible failures | **FAIL** (own-Q) | Aggregation diverted to `ticket_105` / `refund_exception` instead of `doc_06` GPU category (3). Wrong for this question; **not** another request’s topic |
| 9 | billing refund window | **FAIL** (own-Q) | Same aggregation trap: cited `ticket_105`, failed to state 7-day / first-cycle rule from `doc_11` |
| 10 | workspace seats | **PASS** | 10 seats via `doc_08` |
| 11 | prompt truncation | **PASS** | >400 chars truncated via `doc_02` |
| 12 | Build of the Week credits | **FAIL** (own-Q) | Aggregation “scan” path; empty answer citing `ticket_105` instead of `doc_13` |
| 13 | copyrighted characters | **PASS** | Rejected per `doc_10` |
| 14 | generation time | **FAIL** (own-Q) | Abstained; missed 15–45s in `doc_01` — not contamination |
| 15 | Pro tier | **PASS** | $15 / 100 per day |
| 16 | no Bedrock add-on | **PASS** | Correct negative via `doc_04` / `ticket_103` |
| 17 | credits rollover | **PASS** | Do not roll over (`doc_11` / `doc_05`) |
| 18 | API poll rate | **PASS** | 1 req / 2s / job |
| 19 | workspace build ownership | **PASS** | Builds remain workspace-owned |
| 20 | negative-constraint rate | **PASS** | ~80% via `doc_02` |
| 21 | Studio tier | **PASS** | $60 / 512³ |
| 22 | policy recheck delay | **PASS** | 5–10s via `doc_10` |
| 23 | no post-hoc transfer | **PASS** | Must regenerate in workspace |
| 24 | Free export formats | **PASS** | `.schematic` + `.glb` only |
| 25 | downgrade timing | **PASS** | End of billing period |
| 26 | Bedrock glass bug | **PASS** | Palette / stained glass issue |
| 27 | workspace sync lag | **PASS** | Up to 10 min, expected |
| 28 | ticket #1058 refund? | **PASS*** | Correct “no refund”; retrieval skewed to `ticket_105` but answer stayed on #1058 |
| 29 | preset tier + fine-tune | **PASS** | Pro, 2–6 hours |
| 30 | cap exceed 429 | **PASS** | 429 + `reset_at` |

\*Soft: retrieval noise under load, but content matched the asked ticket.

### Contamination cases

**None.** The four clear fails (and two soft aggregation misses on refund wording) are **same-request** retrieval/aggregation/routing errors (especially the ticket-set “scan” path latching onto `ticket_105`), not evidence that concurrent requests corrupted each other’s in-memory index state.

---

## Part B — Hallucination rate under repeated/varied querying

**Setup:** 20 diverse queries, **sequential**, one shot each. Mix of golden-set, paraphrases, and new corpus-plausible questions (plus two out-of-corpus traps).

Verifier labels from the API:

- `SUPPORTED` → `verified: true`
- `UNSUPPORTED` → `override_reason: "verifier returned UNSUPPORTED"` (forces abstain)
- `ABSTAINED_NO_VERIFIER_VETO` → abstained without a verifier veto (retrieval / generator self-abstain)

### Results table

| # | Query | Kind | Verifier | Manual spot-check | Agreement |
|---|---|---|---|---|---|
| 1 | What formats can a finished structure be exported as? | golden | SUPPORTED | Matches `doc_04` (four formats) | yes |
| 2 | What confidence score causes a build to be tagged review recommended? | golden | SUPPORTED | Matches `doc_07` (`< 0.62`) | yes |
| 3 | How do I get an API key and which tier is required? | golden | SUPPORTED | Studio + Account Settings > Developer | yes |
| 4 | What uptime SLA does Craftify guarantee on the Studio tier? | golden abstain | ABSTAINED | Correct abstain (not in corpus) | yes |
| 5 | Can I pay for my Craftify subscription with PayPal? | golden abstain | ABSTAINED | Correct abstain | yes |
| 6 | List every file extension Craftify can export a finished build to. | paraphrase | SUPPORTED | All four extensions from `doc_04` | yes |
| 7 | On Free, what's my daily gen cap and the biggest build I can make? | paraphrase | SUPPORTED | 10/day, 64³ | yes |
| 8 | Where do Studio users request developer API credentials? | paraphrase | SUPPORTED | Account Settings > Developer | yes |
| 9 | If the model is unsure about geometry quality, what score threshold triggers the review badge? | paraphrase | SUPPORTED | `< 0.62` | yes |
| 10 | For a refund after signup, what's the window and does it apply to renewals? | paraphrase | SUPPORTED | 7 days, first cycle only, renewals no | yes |
| 11 | Which category of generation failure gets a credit refund? | new | **SUPPORTED** | **Wrong.** Invents / elevates ticket resolution type `refund_exception` from `ticket_105`. Corpus answer (`doc_06`) is only **category (3) transient GPU** failures. | **no** |
| 12 | How many seats does a Team Workspace support? | new | SUPPORTED | Up to 10 (`doc_08`) | yes |
| 13 | What happens if my prompt exceeds 400 characters? | new | SUPPORTED | Truncated (`doc_02`) | yes |
| 14 | How many bonus credits does Build of the Week give, and for how long are they valid? | new | SUPPORTED | Non-answer (“scan did not provide…”); cites `ticket_105` instead of `doc_13` (30 credits / 60 days). **No fabricated numbers**, but failed to answer; verifier rubber-stamped a retrieval miss | soft no* |
| 15 | Are hate symbols or explicit sexual content allowed in prompts? | new | SUPPORTED | Rejected (`doc_10`) | yes |
| 16 | What is the Pro plan price and its daily generation limit? | new | SUPPORTED | $15 / 100 per day | yes |
| 17 | Is there a way to export as a native Bedrock add-on? | new | SUPPORTED | Correct negative + `.nbt` caveat | yes |
| 18 | How long can API polling keep showing queued after a job actually finished? | new | SUPPORTED | Up to 30 seconds (`doc_12`) | yes |
| 19 | Does Craftify support paying with cryptocurrency or Apple Pay? | new hard | ABSTAINED | Correct abstain | yes |
| 20 | What is Craftify's SOC 2 compliance status? | new hard | ABSTAINED | Correct abstain | yes |

\*B14: not a classic fabricated-fact hallucination; still a verifier **pass on an unhelpful wrong-path answer**.

### Verifier catch rate

| Signal | Count |
|---|---|
| `UNSUPPORTED` vetoes (verifier caught an ungrounded generation) | **0** |
| Out-of-corpus traps correctly handled | **4 / 4** (SLA, PayPal, crypto/Apple Pay, SOC 2) — all via **abstain path**, not verifier veto |
| SUPPORTED answers manually grounded | 15 / 16 clear cases (excluding B14 soft) |
| **SUPPORTED but hallucinated / materially wrong** | **1 (B11)** |

In this sample the Self-RAG-lite verifier never returned `UNSUPPORTED`. Ungrounded questions were stopped earlier (abstain). The catch rate for *generated* ungrounded answers is therefore **0 catches / 1 clear miss** in this run (plus one soft non-answer pass).

---

## Summary

**Is there any case of hallucination the verifier missed?**

**Yes — one clear case: Part B #11.** The system answered that generation-credit refunds apply to failures with resolution type `refund_exception` (from `ticket_105`), and the verifier marked it `SUPPORTED`. The documentation answer is that only **transient GPU / category (3)** failures are refund-eligible (`doc_06`). That is the number that matters for “does it hallucinate past the verifier?”

**Concurrency (Part A):** High concurrency did **not** produce cross-request contamination of shared retrieval state. Failures under the 30-way burst were same-request aggregation/retrieval misses (refund wording and BotW latching onto `ticket_105`, plus two abstains on multi-hop / timing), not peer-answer leakage.

**Bottom line:** The hallucination risk here is **not** “the model invents more when busy.” It is **occasional wrong-path answers that still pass the groundedness check** when retrieval surfaces a neighboring ticket/doc and the verifier accepts claims that are locally consistent with those passages but wrong for the question.
