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
    # llm is reported because every LLM call degrades to a heuristic fallback rather than
    # erroring: without this, a keyless server looks identical to a configured one.
    return {
        "status": "ok",
        "documents": len(idx.docs_by_id),
        "llm": llm.available(),
        "model": config.LLM_MODEL if llm.available() else None,
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> dict:
    return generator.answer_question(req.question)


@app.post("/agent", response_model=AgentResponse, response_model_exclude_none=True)
def agent(req: AgentRequest) -> dict:
    return router.handle(req.message)
