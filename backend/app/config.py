"""Model names, thresholds and paths. Single place to tune the system."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

CORPUS_DIR = BACKEND_DIR / "data" / "corpus"
PROMPTS_DIR = BACKEND_DIR / "prompts"
LOG_PATH = BACKEND_DIR / "logs" / "tool_calls.jsonl"
GOLDEN_SET_PATH = BACKEND_DIR / "eval" / "golden_set.json"

# --- retrieval ---
EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "craftify_corpus"
DENSE_N = 10          # candidates pulled from Chroma before fusion
BM25_N = 10           # candidates pulled from BM25 before fusion
# Candidate admission only, NOT the abstention rule: Chroma returns n_results docs
# however unrelated they are, so rank-based RRF alone can never signal "nothing matched".
# Measured on this corpus: on-topic queries land at cosine distance 0.40-0.53, off-topic
# ones at 0.76+, so 0.75 separates them with margin. BM25 candidates are admitted on
# score > 0. Abstention still gates on the fused score below.
DENSE_MAX_DISTANCE = float(os.getenv("CRAFTIFY_DENSE_MAX_DISTANCE", "0.75"))
# BM25 exists here to catch exact/rare terms (ticket numbers, format names, doc titles),
# so query terms occurring in more than this share of the corpus are dropped before
# scoring. Without it, filler words ("how", "do", "on") give every off-topic query a
# positive BM25 hit, which would put a rank-0 doc into the fusion and defeat abstention.
BM25_MAX_DF_RATIO = float(os.getenv("CRAFTIFY_BM25_MAX_DF_RATIO", "0.2"))
TOP_K = 4             # fused docs handed to the generator
RRF_K = 60            # standard RRF constant
# Gate on the FUSED RRF score, never on raw dense similarity (plan Section 3.2).
# Two retrievers at k=60 cap out near 2/60 = 0.033 for a rank-0/rank-0 hit;
# 0.0155 (~= 1/(60+4)) requires a top-5 hit in at least one retriever.
ABSTAIN_RRF_THRESHOLD = float(os.getenv("CRAFTIFY_ABSTAIN_THRESHOLD", "0.0155"))
EXPAND_REFERENCES = True

# --- llm ---
# One OpenAI-compatible code path. OPENAI_BASE_URL lets the same client talk to
# Groq / Gemini's OpenAI-compat endpoints without a second SDK integration.
LLM_PROVIDER = os.getenv("CRAFTIFY_LLM_PROVIDER", "").strip().lower()
LLM_MODEL = os.getenv("CRAFTIFY_LLM_MODEL", "gpt-4.1-mini")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL") or None
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
JUDGE_MODEL = os.getenv("CRAFTIFY_JUDGE_MODEL", LLM_MODEL)

ABSTAIN_TEXT = "ABSTAIN: not covered in the documentation."
