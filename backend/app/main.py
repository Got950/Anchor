"""FastAPI app: /ask (RAG) and /agent (router + tools)."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, llm
from .agent import router
from .rag import generator, ingest
from .schemas import AgentRequest, AgentResponse, AskRequest, AskResponse

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Craftify Support Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    ingest.build_index()


@app.get("/health")
def health() -> dict:
    idx = ingest.get_index()
    # llm is a live probe (cached ~5 min), not a string-presence check: every LLM call
    # degrades to a heuristic fallback rather than erroring, so a non-empty but invalid
    # key would otherwise look healthy while the system is silently on fallbacks.
    ok, err = llm.probe_live()
    out: dict = {
        "status": "ok",
        "documents": len(idx.docs_by_id),
        "llm": ok,
        "model": config.LLM_MODEL if ok else None,
    }
    if err:
        out["llm_error"] = err
    return out


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> dict:
    llm.begin_usage()
    out = generator.answer_question(req.question)
    out["usage"] = llm.take_usage()
    return out


@app.post("/agent", response_model=AgentResponse, response_model_exclude_none=True)
def agent(req: AgentRequest) -> dict:
    llm.begin_usage()
    out = router.handle(req.message, req.previous_response_id)
    out["usage"] = llm.take_usage()
    return out
