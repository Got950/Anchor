# PSM Craftify Gaming Productions — AI Engineer Assessment
## Implementation Plan for Direct Code-Level Build (v2 — implementation-ready)

This document is the single source of truth for implementation. Follow it top to bottom. Every design decision below is justified either by the actual corpus content or by a named technique/paper — do not deviate without a reason as strong as the ones given.

---

## 0. Ground Truth: Corpus Facts (already analyzed)

- 20 files total: `doc_01`–`doc_13` (docs) + `ticket_101`–`ticket_107` (support tickets).
- Every file is 60–103 words (~80–140 tokens). Whole corpus ≈ 1,750 words.
- **Docs and tickets explicitly cross-reference each other** (e.g. a ticket says "see Known Issues #4" or "matches Known Issue #2").
- Tickets carry a hidden structured field: **resolution outcome** — most are closed as "expected behavior," a few are refund exceptions, at least one (`ticket_106`) is NOT closed as expected behavior (escalated/bug).
- Implication: **no chunking needed** (files are already sub-chunk-sized), a **metadata layer is needed alongside vector search** to answer aggregation-style questions ("which tickets got refunded") that pure semantic search cannot answer, and the **cross-reference structure must be exploited, not just extracted** — see §3.1 and §7.1.

---

## 1. Final Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend framework | FastAPI | matches candidate's existing stack |
| Vector store | ChromaDB, in-memory (`chromadb.Client()`), **cosine distance space explicitly set** | task explicitly allows in-memory, no persistence needed |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers, local) | free, offline, justified by corpus size — no reason to pay API cost for 20 tiny docs |
| Sparse retrieval | `rank_bm25` (BM25Okapi) | catches exact-term matches (ticket numbers, doc titles) embeddings can miss |
| Rank fusion | Reciprocal Rank Fusion (RRF), hand-rolled (~10 lines) | standard hybrid retrieval pairing per Anthropic's own Contextual Retrieval writeup |
| Metadata store | Chroma's metadata field (no separate DB) | avoids infra the task says not to build |
| Tool schemas | Pydantic | validates tool args at the schema level — doubles as guardrail enforcement |
| Tool-arg extraction | Router LLM call uses **native function calling / tool_use** to extract args in the same call that classifies intent — not a second LLM call | one round-trip, cheaper, and the model's tool schema IS the Pydantic schema (see §4.1) |
| Orchestration | Plain Python router function, NO LangGraph/CrewAI/AutoGen | a 4-branch router doesn't need agent-framework infra; more honest and defensible |
| LLM | Whatever API the candidate already has access to (GPT-4.1 / Gemini / Claude via existing keys) | reuse existing integration code |
| Eval | RAGAS (`ragas` pip package), **judge LLM pinned explicitly** | named, published methodology (Es et al. 2023, arXiv:2309.15217) — satisfies Part 5 requirement with a real framework, not ad hoc scoring |
| Frontend | Next.js + TypeScript, single page | task explicitly says single page is fine, no design exercise |
| Logging | Local JSONL file (`logs/tool_calls.jsonl`) | task explicitly says local file logging is fine, no DB |

**RAGAS judge LLM**: RAGAS's `faithfulness`/`answer_relevancy`/`context_precision`/`context_recall` metrics default to an OpenAI judge model under the hood. If the candidate's available API keys are Gemini/Claude-only, this will silently break or require explicit config. Decision: **wrap whichever LLM is already available (GPT-4.1 / Gemini / Claude) via RAGAS's `LangchainLLMWrapper`** and pass it explicitly to every metric call — do not rely on RAGAS's default. State this explicitly in README §7.3.7 (system prompts / eval config section) so it's not mysterious in the interview.

**Explicitly excluded, with reasons to state in README if asked:**
- Contextual Retrieval (Anthropic's chunk-context technique) — solves context loss from splitting documents; not applicable since nothing is being split.
- GraphRAG / knowledge graph — no evidence it helps at 20-node scale; metadata tagging + reference-expansion (§3.1, §3.2) solves the actual observed failure mode (aggregation + multi-hop queries) more cheaply.
- Multi-agent frameworks (CrewAI, AutoGen, LangGraph) — task is a single small agent with one router; framework overhead unjustified.
- Trained Self-RAG — requires training a custom critic model; instead use a **prompted, single-call approximation** of its groundedness-check idea (see §3.4).

---

## 2. Repo Structure

```
craftify-assessment/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, /ask and /agent endpoints
│   │   ├── config.py                # model names, thresholds, constants
│   │   ├── schemas.py               # Pydantic request/response + tool schemas
│   │   ├── rag/
│   │   │   ├── ingest.py            # load corpus → embed → metadata extraction → Chroma
│   │   │   ├── retriever.py         # hybrid retrieval (dense + BM25 + RRF) + reference expansion
│   │   │   ├── generator.py         # grounded answer generation + abstention
│   │   │   └── verifier.py          # groundedness check (Self-RAG-lite)
│   │   ├── agent/
│   │   │   ├── router.py            # classify + extract tool args in one call: semantic | aggregation | tool_call | clarify
│   │   │   ├── tools.py             # create_support_ticket, flag_generation_for_review
│   │   │   └── guardrails.py        # missing-arg / ambiguous-request checks
│   │   └── logging_utils.py         # JSONL logger with reasoning field
│   ├── data/
│   │   └── corpus/                  # unzipped BlockForge_Corpus contents
│   ├── eval/
│   │   ├── golden_set.json          # 12–16 hand-labeled Q&A pairs, incl. multi-hop
│   │   └── run_eval.py              # runs RAGAS over golden_set against live /ask
│   ├── logs/
│   │   └── tool_calls.jsonl         # created at runtime
│   ├── prompts/
│   │   ├── generation_system.md     # Part 1 system prompt (also pasted in README)
│   │   ├── metadata_extraction.md   # ingest-time extraction prompt
│   │   ├── router_system.md         # Part 2 classification + arg-extraction prompt
│   │   └── verifier_system.md       # groundedness check prompt
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   └── page.tsx                 # single chat page
│   ├── components/
│   │   ├── ChatMessage.tsx          # renders answer / abstain / tool_call variants
│   │   └── SourceSnippets.tsx
│   └── package.json
├── assets/
│   ├── block_texture.png
│   ├── block_model.json
│   └── blockbench_screenshot.png
├── docker-compose.yml               # bonus, only if time remains
└── README.md                        # Part 5 write-up — see §7 for required sections
```

---

## 3. Part 1 — RAG Pipeline (detailed)

### 3.1 Ingestion (`rag/ingest.py`)

For each file in `data/corpus/`:
1. Read raw text. **Do not chunk** — treat the whole file as one chunk (files are 60–103 words, already atomic).
2. Run the metadata extraction LLM call (prompt in `prompts/metadata_extraction.md`) once per file to produce:
   ```json
   {
     "doc_id": "ticket_105",
     "doc_type": "ticket",           // "doc" | "ticket"
     "title": "...",
     "references": ["doc_07", "doc_12"],   // other doc_ids explicitly mentioned
     "resolution_type": "refund_exception", // "expected_behavior" | "bug" | "refund_exception" | null (docs have null)
     "refund_issued": true            // bool, null for docs
   }
   ```
   **`references` is not decorative — it feeds retrieval expansion in §3.2. If this field is dropped, drop its extraction too and note the cut in README §7.3.6; do not build metadata that nothing reads.**
3. Embed the raw text with `all-MiniLM-L6-v2`.
4. Upsert into Chroma: `id=doc_id`, `document=raw_text`, `embedding=vector`, `metadata=<the JSON above>`. **Create the collection with `metadata={"hnsw:space": "cosine"}` explicitly — Chroma's default is L2, and the abstention threshold in §3.2 only holds under cosine distance.**
5. Also build an in-memory BM25 index (`rank_bm25.BM25Okapi`) over the same 20 raw texts, tokenized simply (lowercase, split on whitespace/punctuation) — keep a **`doc_id_by_position: List[str]`** list, where `doc_id_by_position[i]` is the doc_id of the text at BM25 corpus position `i`. This list is required to map BM25 scores back to doc_ids in §3.2 — `get_scores()` returns a plain array indexed by corpus position, not doc_id, so do not index it directly by doc_id.

Metadata extraction prompt (`prompts/metadata_extraction.md`) — key instructions:
- Extract `doc_type` from filename pattern or content.
- Extract `references` by scanning for explicit mentions of other doc titles/numbers (e.g. "Known Issues #4" → map to the doc_id whose title matches "Known Issues").
- Extract `resolution_type` ONLY for tickets, based on how the ticket's resolution is described (working as intended vs bug vs refund).
- Output strict JSON, nothing else.

### 3.2 Hybrid Retrieval (`rag/retriever.py`)

```python
def hybrid_retrieve(query, top_k=4, expand_references=True):
    dense = chroma_collection.query(embed(query), n_results=10)   # ids ranked best-first, cosine space
    dense_ids = dense["ids"][0]

    bm25_scores = bm25_index.get_scores(tokenize(query))          # np.array, indexed by corpus position
    bm25_ranked_positions = sorted(range(len(bm25_scores)), key=lambda i: -bm25_scores[i])[:10]
    bm25_ids = [doc_id_by_position[i] for i in bm25_ranked_positions]   # correct id mapping

    # Reciprocal Rank Fusion, k=60 (standard constant)
    rrf_scores = {}
    for rank, doc_id in enumerate(dense_ids):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (60 + rank)
    for rank, doc_id in enumerate(bm25_ids):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (60 + rank)

    fused = sorted(rrf_scores.items(), key=lambda x: -x[1])[:top_k]   # [(doc_id, fused_score), ...]

    # Reference expansion: pull in explicitly cross-referenced docs so multi-hop
    # questions ("what does the ticket that cites Known Issue #4 say") get the
    # referenced doc in context even if it didn't independently rank high.
    if expand_references:
        expanded_ids = set(doc_id for doc_id, _ in fused)
        for doc_id, _ in fused:
            refs = chroma_collection.get(ids=[doc_id])["metadatas"][0].get("references", [])
            expanded_ids.update(refs)
        fused = [(d, rrf_scores.get(d, 0.0)) for d in expanded_ids]  # referenced-only docs get score 0.0, tagged as "pulled by reference" downstream

    return fused
```

**Confidence / abstention threshold — gate on the FUSED result, not raw dense distance.** Comparing raw dense cosine similarity against a threshold while generation runs on the RRF-fused top_k would mean a doc that won purely via BM25 exact-match (e.g. a ticket number) with weak dense similarity gets wrongly abstained, or a weak fused doc passes on a strong-but-irrelevant dense score. Corrected rule:

- If `fused` (before reference expansion) is empty **or** the top RRF score is below `0.01` (RRF scores at k=60 with two retrievers max out around `2/60 ≈ 0.033` for a rank-0/rank-0 hit; `0.01` is a conservative floor that still requires a reasonably-ranked hit in at least one retriever) → abstain immediately, skip generation (cheap short-circuit).
- This threshold is a starting point — tune it against `eval/golden_set.json` once you have real query results; docs are short and topically distinct so scores should separate cleanly. Document the final tuned value and why in README §7.3.5.
- Reference-expanded docs (score 0.0, pulled in after the threshold check) never count toward the abstention decision — they're context enrichment only, not evidence of relevance.

### 3.3 Generation (`rag/generator.py`)

System prompt (`prompts/generation_system.md`) — must include, verbatim structure:
```
You are a support assistant answering questions ONLY using the provided context documents.

Rules:
1. Answer using ONLY information present in the context below. Do not use outside knowledge.
2. If the context does not contain enough information to answer, respond EXACTLY with:
   ABSTAIN: not covered in the documentation.
3. When you answer, cite which source document each claim comes from using [doc_id] inline.
4. Be concise — 1-3 sentences unless the question requires more detail.

Context:
{retrieved_chunks_with_doc_ids}

Question: {user_query}
```

`/ask` response shape:
```json
{
  "answer": "...",
  "abstained": false,
  "sources": [{"doc_id": "doc_09", "title": "API Access", "snippet": "...", "via_reference": false}],
  "retrieval_confidence": 0.71,
  "verified": true
}
```
`via_reference: true` marks sources pulled in by §3.2's reference expansion rather than ranked directly — surface this distinction in the frontend trace panel too (§5).

### 3.4 Groundedness Verifier (`rag/verifier.py`) — Self-RAG-lite

After generation (and only if NOT abstained), run one more LLM call:
```
System: You are a fact-checker. Given a CLAIM and a set of SOURCE PASSAGES, respond with exactly "SUPPORTED" if every factual statement in the claim is backed by the passages, or "UNSUPPORTED" if any part is not backed.

Passages:
{retrieved_chunks}

Claim:
{generated_answer}
```
If `UNSUPPORTED` → override the response to `abstained=True`, `answer="ABSTAIN: not covered in the documentation."`, log the override reason. Explicitly document in README: this is a **prompted, single-call approximation** of Self-RAG's ISSUP reflection token (Asai et al. 2023) — not the trained mechanism from the paper, adapted for a 5-day, no-training-budget constraint.

---

## 4. Part 2 — Agent (detailed)

### 4.1 Router (`agent/router.py`)

**One LLM call per incoming message, using native function/tool calling** (not plain text classification followed by a second extraction call). Give the model four tool definitions matching the Pydantic schemas below plus a `semantic_lookup`/`aggregation`/`clarify` no-arg selector, and let the model's tool_use output do both classification and arg extraction simultaneously:

| Path | Trigger examples | Handler |
|---|---|---|
| `semantic_lookup` | "what export formats exist", "how do I access the API" | hybrid retrieval → generate → verify (§3) |
| `aggregation` | "which tickets got refunded", "which ticket wasn't closed as expected behavior" | scan Chroma metadata directly (Python filter over ≤20 records, no LLM needed for the scan itself — only for phrasing the final answer) |
| `tool_call` | "file a ticket for X", "flag this generation for review" | model extracts args via tool_use in the same call → validate via Pydantic → call mocked tool → log |
| `clarify` | tool-intent messages missing required info; out-of-scope/ambiguous requests; **or Pydantic validation failure on extracted args** | return a clarifying question or refusal, no tool call |

If the router LLM's provider/SDK doesn't support structured tool_use cleanly (fallback only), use a single prompt that asks for strict JSON output containing both `path` and `extracted_args`, parsed the same way as the metadata extraction call in §3.1 — still one call, not two. Document whichever approach was used in README §7.3.7.

Router output must include a `reasoning` string (one sentence, why this path was chosen) — this gets logged and also surfaced in the frontend trace panel.

### 4.2 Tools (`agent/tools.py`)

```python
class CreateTicketArgs(BaseModel):
    summary: str = Field(min_length=5)
    priority: Literal["low", "medium", "high"]

class FlagReviewArgs(BaseModel):
    reason: str = Field(min_length=5)

def create_support_ticket(args: CreateTicketArgs) -> dict:
    ticket_id = f"TCK-{random.randint(1000,9999)}"
    return {"ticket_id": ticket_id, "status": "created", "summary": args.summary, "priority": args.priority}

def flag_generation_for_review(args: FlagReviewArgs) -> dict:
    return {"flag_id": f"FLG-{random.randint(1000,9999)}", "status": "flagged", "reason": args.reason}
```

These same field definitions are the tool_use schemas passed to the router LLM in §4.1 — one Pydantic model, two uses (LLM-facing schema + runtime validation), no drift risk.

Pydantic validation failure (missing/malformed args) is what feeds the `clarify` path — if the router extracts args and they fail schema validation, do NOT call the tool; return a clarifying question asking for the missing field specifically.

### 4.3 Guardrail (`agent/guardrails.py`)

Required guardrail case per task spec — implement at least this one explicitly and test it:
- User: "create a ticket" (no summary, no priority) → router detects `tool_call` intent but Pydantic validation fails on missing fields → response: `{"type": "clarify", "message": "What should the ticket summary say, and what priority (low/medium/high)?"}`

### 4.4 Logging (`logging_utils.py`)

Append one JSON line per agent interaction to `logs/tool_calls.jsonl`:
```json
{"timestamp": "2026-09-11T10:22:31Z", "path": "tool_call", "reasoning": "user explicitly requested ticket creation with sufficient detail", "tool": "create_support_ticket", "inputs": {"summary": "...", "priority": "high"}, "outputs": {"ticket_id": "TCK-4821", "status": "created"}}
```
For `clarify` events, log `tool: null`, `outputs: null`, and the clarifying question asked.

### 4.5 `/agent` endpoint contract

Request: `{"message": "user text"}`
Response:
```json
{
  "type": "answer" | "abstain" | "tool_call" | "clarify",
  "reasoning": "...",
  "answer": "... (if type=answer/abstain)",
  "sources": [...],
  "tool": "create_support_ticket (if type=tool_call)",
  "tool_args": {...},
  "tool_result": {...},
  "clarifying_question": "... (if type=clarify)"
}
```

---

## 5. Part 3 — Frontend (detailed)

- Next.js + TypeScript, App Router, single page (`app/page.tsx`), plain `fetch` to backend (no state library needed, `useState` is enough).
- Chat-style message list. Each assistant message renders via `ChatMessage.tsx`, branching on `type`:
  - `answer` → normal bubble + `SourceSnippets` component listing `doc_id` + title + snippet underneath, plus a small confidence % badge. Sources with `via_reference: true` (§3.3) get a distinct "referenced" tag vs. directly-retrieved sources.
  - `abstain` → greyed-out bubble, italic "Not covered in the documentation."
  - `tool_call` → highlighted/bordered box showing tool name, formatted args, and the mocked result JSON.
  - `clarify` → bubble styled distinctly (e.g. amber border) showing the clarifying question.
- Also show the router's `reasoning` string in a small collapsible "why" line under each message — this is the visible decision-trace differentiator.
- Basic loading spinner while awaiting fetch; basic error state (red text) if the backend call fails. No auth, no routing, no responsive polish required.

---

## 6. Part 4 — Minecraft Asset (detailed steps)

1. Pick a block concept that **ties back to the corpus** — e.g. name/lore it after a real known issue or ticket (e.g. a "Reinforced Crafting Table" referencing the crafting-table exploit mentioned in the tickets, or similar — check actual corpus content for the best tie-in).
2. Generate a rough texture concept with any AI image tool, then manually clean it up to a strict 16×16 (or 32×32) pixel grid inside Blockbench's texture editor (or Aseprite) — this manual cleanup step is what makes it usable, not just an AI image dump.
3. Build the model in Blockbench using cuboid elements, referencing the texture, export as Minecraft Java-format `block_model.json`.
4. Take a screenshot from Blockbench's preview showing the shape.
5. Commit `block_texture.png`, `block_model.json`, `blockbench_screenshot.png` to `assets/`.
6. In README, write 2–4 sentences: which AI tool was used for the texture concept, what worked, and what's needed to go further (UV mapping, parenting, entity vs block models).

---

## 7. Part 5 — Evaluation & Write-up (detailed)

### 7.1 Golden set (`eval/golden_set.json`)

Build 12–16 pairs directly from the corpus, deliberately covering all query types the system handles:
- 4–5 `semantic_lookup` questions (answerable, straightforward, single-doc)
- **2 multi-hop `semantic_lookup` questions that specifically exercise reference expansion** — e.g. "what does the ticket that cites Known Issue #4 say about the resolution" — where the correct answer requires both the directly-matched doc and its referenced doc to be in context. This is the most distinctive retrieval challenge in the corpus (per §0) and must be represented in eval, not just built and left untested.
- 2–3 `aggregation` questions (e.g. "which tickets resulted in a refund", "which ticket was NOT closed as expected behavior") — this is the type pure vector RAG fails on, make sure it's represented
- 2–3 intentionally unanswerable questions (should trigger `ABSTAIN`)
- 2 `tool_call` scenarios (one complete, one deliberately missing info to test the guardrail)

Format:
```json
[{"question": "...", "expected_type": "answer", "expected_answer_contains": "...", "ground_truth_sources": ["doc_09"], "requires_reference_expansion": false}]
```

### 7.2 Run RAGAS (`eval/run_eval.py`)

For each `answer`-type golden pair, call the live `/ask` endpoint, collect `{question, answer, contexts, ground_truth}`, and run RAGAS's `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall` metrics **using the explicitly-wrapped judge LLM from §1, not RAGAS's default**. For `aggregation` and `abstain` pairs, score pass/fail manually against expected behavior (RAGAS metrics assume a generation task, not the aggregation/abstain paths) — report these separately as "behavioral accuracy." For the two multi-hop pairs, additionally report pass/fail on whether `via_reference` sources were present in the response — a separate line item from RAGAS's context metrics since those don't distinguish primary vs. reference-expanded context.

### 7.3 README.md required sections (max ~2 pages)

1. **Architecture overview** — 1 paragraph, name the orchestrator + specialized handlers pattern explicitly (not "multi-agent").
2. **How I'd evaluate this before shipping** — golden set methodology, RAGAS metrics used, what "good enough to ship" means numerically (e.g. faithfulness > 0.9, abstention accuracy 100% on the unanswerable subset — these are non-negotiable for a support tool).
3. **Evaluation actually run** — paste the RAGAS output table + the behavioral accuracy numbers + the reference-expansion pass/fail from §7.2.
4. **Biggest weakness + fix** — be specific: e.g. "metadata extraction (references, resolution_type) is a single unverified LLM pass — fine at 20 docs, would need human-in-the-loop review or a second extraction pass with disagreement checking before trusting it past a few hundred documents."
5. **Trade-offs made because of the time limit** — no reranker model, no persistent vector store, no auth, thresholds hand-tuned rather than calibrated on a larger eval set, metadata extraction unverified, reference expansion is single-hop only (doesn't chase a reference-of-a-reference).
6. **Techniques considered and explicitly not used**, with one line each: Contextual Retrieval (context-loss problem doesn't exist here since nothing is chunked), GraphRAG (no evidence of benefit at 20-node scale, metadata tagging + single-hop reference expansion solves the actual observed failure mode more cheaply), trained Self-RAG (no training budget — used a prompted single-call approximation instead), multi-agent frameworks (single router with specialized handlers is sufficient and more honest for 4 branches).
7. **System prompts + config** — paste all four prompt files' contents directly (generation, metadata extraction, router, verifier), plus the RAGAS judge-LLM wrapping decision (§1) and the tool-arg extraction approach used (§4.1).
8. **Bonus paragraph (optional)** — multi-modal extension: how ingestion would need to change to accept an image (screenshot of a failed build, or the Part 4 asset itself) as additional context — e.g. a vision-capable model captioning the image into text, then embedding the caption alongside existing text chunks.

---

## 8. Build Order (minimum-viable-first, do not build depth-first)

**Priority principle**: get all 5 parts working end-to-end at a basic level BEFORE adding any of the differentiators (hybrid retrieval, verifier, RAGAS, reference expansion). A finished simple system beats a broken sophisticated one.

**Day 1** — Scaffold repo. Ingestion with plain dense-only retrieval (no BM25/RRF, no reference expansion yet, no metadata extraction yet). **Set Chroma collection to cosine space from the start (§1) — retrofitting this later invalidates any tuned thresholds.** Basic `/ask` endpoint working end-to-end with abstention on empty retrieval.

**Day 2** — Part 2: router with all 4 paths using naive dense retrieval for `semantic_lookup`, hardcoded/simple metadata scan for `aggregation` (metadata can be manually written for 20 files if extraction isn't built yet), tools + Pydantic guardrail via native tool_use (§4.1), JSONL logging.

**Day 3** — Part 3: frontend wired to both endpoints, all 4 message types rendering distinctly.

**Day 4** — Layer in differentiators in this exact priority order, stopping whenever time runs low:
1. Real LLM-based metadata extraction (replacing any manual/hardcoded version) — required for aggregation and reference expansion to be genuinely robust.
2. Hybrid retrieval (BM25 + RRF), with the corrected doc_id-by-position mapping (§3.2) — real implementation.
3. Reference expansion on top of fused retrieval (§3.2) — small addition once RRF is working, high write-up value given §0's corpus facts.
4. RAGAS eval run + golden set, judge LLM explicitly wrapped (§1/§7.2) — high write-up value, moderate effort.
5. Groundedness verifier (Self-RAG-lite) — nice differentiator, optional if time is short.

Also do Part 4 (Minecraft asset) this day — it's independent of the backend work and can be done in parallel/whenever there's a break from coding.

**Day 5** — Buffer. Finish README (Part 5), polish frontend trace panel, bonus items ONLY if everything above is done and working: latency/token instrumentation, `eval/run_eval.py` as a clean re-runnable script, Docker compose, multi-modal paragraph.

**Non-negotiable minimum for submission** (if Day 5 goes badly): Parts 1–4 working end-to-end with basic dense retrieval + metadata-scan aggregation + guardrail + frontend + asset, plus a README covering all of §7.3 even if the "evaluation actually run" section is smaller than planned. A complete, honestly-scoped submission beats an incomplete ambitious one. Reference expansion and the verifier are the first two things to cut if Day 4 runs long — aggregation and hybrid retrieval are not optional, those are the two things §0 explicitly says pure vector search can't handle.

---

## 9. Explicit Non-Goals (do not build these — task says not to)

- No authentication anywhere.
- No cloud deployment / hosting setup.
- No persistent/production database — Chroma in-memory + JSONL log files only.
- No responsive design polish on frontend.
- No real external services for tools — both tools are mocked.
- No multi-hop reference chasing beyond one level deep (a reference's own references are not recursively pulled in) — stated as a trade-off in README §7.3.5, not silently absent.
