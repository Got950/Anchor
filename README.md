# Craftify Support Assistant

Technical assessment for PSM Craftify Gaming Productions. RAG over the provided BlockForge /
Craftify corpus (20 short docs + tickets), a small agent with mocked tools, a Next.js chat UI,
one Minecraft block asset, and a short evaluation write-up.

```
backend/   FastAPI — POST /ask (RAG), POST /agent (router + tools)
frontend/  Next.js chat UI (+ /gallery)
corpus/    20 files from Craftify_test_task_Corpus.zip / BlockForge_Corpus.zip
assets/
  gallery/   all block/item assets — Part 4 = 01_ember_lantern/
```

## Run

```bash
cd backend && pip install -r requirements.txt
cp .env.example .env          # set OPENAI_API_KEY
cd .. && python -m uvicorn backend.app.main:app --port 8000

cd frontend && npm install && npm run dev   # http://127.0.0.1:3000

python backend/selfcheck.py
python backend/eval/run_eval.py            # writes backend/eval/results.md
```

Check `GET /health` — you want `"llm": true` before trusting eval numbers. Without a key the
code falls back to local heuristics.

---

## Part 5 — Evaluation & write-up

### How I’d evaluate before shipping

I’d treat this like a small support bot, not a generic chatbot.

**Golden set.** About 15 hand-labeled pairs covering what actually breaks RAG agents: single-doc
lookups, a couple of multi-hop “ticket ↔ known issue” questions, set-style ticket questions
(“which tickets got a refund”), unanswerable / off-topic prompts that must abstain, and tool
paths (create ticket / flag generation) including a missing-arg case that should clarify instead
of inventing fields. Ours lives in `backend/eval/golden_set.json`.

**Metrics.** For generation answers I use RAGAS (`faithfulness`, `answer_relevancy`,
`context_precision`, `context_recall`) plus a simple check that expected `doc_id`s showed up in
retrieved context. For abstention, tools, and guardrails I use pass/fail behavioural checks —
RAGAS isn’t the right tool there.

**Ship bar.** I’d ship only if: faithfulness stays above **0.9**, abstention is **100%** on the
unanswerable set, tool + guardrail cases are **100%**, and both multi-hop pairs retrieve the
linked docs. Answer relevancy > 0.8 is a want, not a hard gate on a 15-item set.

### What I actually ran

`python backend/eval/run_eval.py` against the 15-pair golden set (`gpt-4.1-mini` as system +
judge). Latest headline numbers:

| check | result |
|---|---|
| faithfulness | **0.845–1.0** across runs (gate > 0.9 is intermittent) |
| answer_relevancy | ~0.65–0.78 |
| context precision / recall | **0.976** / **1.0** |
| expected sources in context | **7/7** generation pairs |
| multi-hop | **2/2** |
| behavioural (abstain + tools) | **8/8** |

| ship gate | target | this run | |
|---|---|---|---|
| faithfulness | > 0.9 | 0.845 | fail |
| abstention | 100% | 3/3 | pass |
| tools / guardrails | 100% | 2/2 | pass |
| multi-hop | 2/2 | 2/2 | pass |

**I would not ship on faithfulness alone.** At n=7 the judge is noisy on short cited answers; I’d
grow the generation set before retuning prompts. Full notes: `backend/eval/results.md`.

### Biggest weakness (and a one-day fix)

Ticket metadata is extracted once by an LLM at ingest (`resolution_type`, `refund_issued`, …).
Aggregation questions trust those fields without re-reading the ticket text.

`ticket_105` is both a goodwill credit *and* an acknowledged bug. The model sometimes labeled it
`bug` instead of `refund_exception`. Both readings are fair from the prose, but our taxonomy
only allows one label — so “which ticket was *not* closed as expected behavior?” quietly grew
from `ticket_106` alone to two tickets.

**One-day fix:** keep the prompt precedence we already added (refund/credit wins over bug), and
add a hard ingest check: if `refund_issued` is true, force `resolution_type == refund_exception`.
That’s cheaper and more reliable than a second LLM pass.

### Trade-offs (time limit vs production)

I stayed inside the brief’s infra rules: in-memory Chroma, local JSONL logs, no auth/hosting.

Shortcuts I’d undo in production: no cross-encoder reranker; thresholds tuned on the golden set
rather than held-out phrasings; single-hop reference expansion only; re-ingest on every startup;
no Docker one-liner. I’d also add a small canary set of paraphrases so we don’t overfit wording,
and I’d stop treating unverified ingest metadata as ground truth (see above).

### System prompts

Prompts are in the repo (linked rather than pasted so this write-up stays short):

- [`backend/prompts/generation_system.md`](backend/prompts/generation_system.md) — answer only from
  retrieved context; abstain with a fixed line when context isn’t enough; cite `[doc_id]`.
- [`backend/prompts/router_system.md`](backend/prompts/router_system.md) — pick exactly one path;
  never invent missing tool args (missing → clarify).
- [`backend/prompts/verifier_system.md`](backend/prompts/verifier_system.md) — groundedness check;
  unsupported answers become abstentions.
- [`backend/prompts/metadata_extraction.md`](backend/prompts/metadata_extraction.md) — ticket/doc
  fields at ingest, including refund-over-bug precedence.

Tool calling uses native function schemas; Pydantic validates args before a mocked tool runs.
Tool calls are logged with timestamp, inputs, and outputs in `backend/logs/tool_calls.jsonl`.

### Bonus (optional)

- Frontend shows rough latency, token usage, and estimated cost on answers/tool calls.
- Re-runnable harness: `backend/eval/run_eval.py` + `backend/selfcheck.py`.
- No Docker (skipped under the time budget).
- **Multi-modal:** for a failed-build screenshot I’d caption it with a vision model, embed the
  caption into the same Chroma collection, and keep the image for the UI. Retrieval stays text;
  for anything high-stakes I’d also pass the image back at answer time so we don’t trust captions
  alone.

---

## Part 4 — Minecraft asset

![Ember Lantern](assets/gallery/01_ember_lantern/preview.png)

**Ember Lantern** — `assets/gallery/01_ember_lantern/` (`texture.png` 16×16, `model.json` with 8
cuboids: base, posts, flame, roof, hook, `preview.png`). Open the preview, not the tiny texture.

I designed the silhouette/palette with AI assistance, then built the pixel sheet and multi-cuboid
model in `assets/gallery/build_gallery.py` (Blockbench wasn’t available here; the JSON still
imports into Blockbench). AI helped with the look; the script did the grid discipline and geometry.
To go further I’d learn proper per-face UVs, parenting/animation, and packing a resource pack so
it loads in-game.

Everything Minecraft-related lives under `assets/gallery/` (see [`assets/README.md`](assets/README.md)).
Browse the pack in the app at `/gallery`.
