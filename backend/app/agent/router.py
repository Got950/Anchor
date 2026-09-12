"""Router: ONE LLM call classifies the message and extracts tool args at the same time,
using native function calling. Plain Python dispatch, no agent framework.
"""
from __future__ import annotations

import re

from .. import config, llm, logging_utils
from ..rag import generator
from . import guardrails
from .tools import TOOLS

PATHS = ("semantic_lookup", "aggregation", "create_support_ticket", "flag_generation_for_review", "clarify")
_REASONING = {"type": "string", "description": "One sentence: why this path fits the user's message."}


def _tool_schemas() -> list[dict]:
    """Tool definitions handed to the LLM. Args come straight from the Pydantic models,
    but nothing except `reasoning` is marked required — the model must be free to omit a
    field the user never gave, so that Pydantic validation (not the model) decides whether
    the tool can run (plan Section 4.2).
    """
    schemas = [
        {
            "name": "semantic_lookup",
            "description": "Answer a factual question from the documentation or an individual support ticket.",
            "parameters": {"type": "object", "properties": {"reasoning": _REASONING}, "required": ["reasoning"]},
        },
        {
            "name": "aggregation",
            "description": "Answer a question about the SET of tickets (which/how many were refunded, escalated, closed as expected).",
            "parameters": {"type": "object", "properties": {"reasoning": _REASONING}, "required": ["reasoning"]},
        },
        {
            "name": "clarify",
            "description": "Ask for missing detail, or refuse an out-of-scope request.",
            "parameters": {
                "type": "object",
                "properties": {"reasoning": _REASONING, "clarifying_question": {"type": "string"}},
                "required": ["reasoning", "clarifying_question"],
            },
        },
    ]
    for name, (model, _) in TOOLS.items():
        props = {"reasoning": _REASONING}
        props.update(model.model_json_schema()["properties"])
        schemas.append(
            {
                "name": name,
                "description": f"Call the {name} tool. Include only arguments the user actually stated.",
                "parameters": {"type": "object", "properties": props, "required": ["reasoning"]},
            }
        )
    return schemas


# --- offline fallback classifier ---------------------------------------------

def _keyword_route(message: str) -> dict:
    """ponytail: keyword rules standing in for the router LLM when no API key is set.
    Ceiling: literal trigger words only; set OPENAI_API_KEY for real classification.
    """
    m = message.lower()
    if re.search(r"\bflag\b|\breport\b|\bescalate\b", m) and not re.search(r"\bticket\b", m):
        reason = re.split(r"\bbecause\b|\bsince\b|\bas\b", message, maxsplit=1)
        args = {"reason": reason[1].strip()} if len(reason) > 1 else {}
        return {"name": "flag_generation_for_review", "args": {**args, "reasoning": "user asked to flag a generation for review"}}
    if re.search(r"\b(create|file|open|raise|submit|log)\b[^.]{0,20}\bticket\b", m):
        args: dict = {}
        about = re.split(r"\babout\b|\bfor\b|\bsaying\b|:", message, maxsplit=1)
        if len(about) > 1 and len(about[1].strip()) >= 5:
            args["summary"] = re.sub(r"[,;]?\s*(low|medium|high)\s*priority\s*$", "", about[1].strip(), flags=re.I)
        priority = re.search(r"\b(low|medium|high|urgent|critical)\b", m)
        if priority:
            args["priority"] = {"urgent": "high", "critical": "high"}.get(priority.group(1), priority.group(1))
        return {"name": "create_support_ticket", "args": {**args, "reasoning": "user explicitly asked to create a support ticket"}}
    if re.search(r"\b(which|what|how many|list|any)\b", m) and re.search(r"\btickets?\b", m) and re.search(
        r"\brefund|\bcredit|\bexpected|\bbug|\bescalat|\bclosed|\bhow many", m
    ):
        return {"name": "aggregation", "args": {"reasoning": "question is about the set of tickets, needs a metadata scan"}}
    return {"name": "semantic_lookup", "args": {"reasoning": "factual question, answerable from the documentation"}}


def classify(message: str) -> dict:
    system = (config.PROMPTS_DIR / "router_system.md").read_text(encoding="utf-8")
    choice = llm.tool_use(system, message, _tool_schemas(), fallback=lambda: _keyword_route(message))
    if choice.get("name") not in PATHS:
        choice = _keyword_route(message)
    return choice


# --- dispatch ----------------------------------------------------------------

def handle(message: str) -> dict:
    choice = classify(message)
    path = choice["name"]
    args = dict(choice.get("args") or {})
    reasoning = str(args.pop("reasoning", "") or f"routed to {path}")

    if path in TOOLS:
        validated, question = guardrails.validate(path, args)
        if validated is None:
            logging_utils.log_interaction(
                "clarify", reasoning, message=message, extra={"clarifying_question": question, "intended_tool": path, "rejected_args": args}
            )
            return {"type": "clarify", "reasoning": reasoning, "clarifying_question": question}
        result = TOOLS[path][1](validated)
        inputs = validated.model_dump()
        logging_utils.log_interaction("tool_call", reasoning, message=message, tool=path, inputs=inputs, outputs=result)
        return {"type": "tool_call", "reasoning": reasoning, "tool": path, "tool_args": inputs, "tool_result": result}

    if path == "clarify":
        question = args.get("clarifying_question") or "Could you rephrase that? I can answer questions about Craftify, file a support ticket, or flag a generation for review."
        logging_utils.log_interaction("clarify", reasoning, message=message, extra={"clarifying_question": question})
        return {"type": "clarify", "reasoning": reasoning, "clarifying_question": question}

    res = generator.aggregate_answer(message) if path == "aggregation" else generator.answer_question(message)
    kind = "abstain" if res["abstained"] else "answer"
    logging_utils.log_interaction(
        path,
        reasoning,
        message=message,
        outputs={
            "type": kind,
            "retrieval_confidence": res["retrieval_confidence"],
            "verified": res["verified"],
            "sources": [s["doc_id"] for s in res["sources"]],
            **({"scan": res["scan"]} if "scan" in res else {}),
            **({"override_reason": res["override_reason"]} if "override_reason" in res else {}),
        },
    )
    return {
        "type": kind,
        "reasoning": reasoning,
        "answer": res["answer"],
        "sources": res["sources"],
        "retrieval_confidence": res["retrieval_confidence"],
        "verified": res["verified"],
    }
