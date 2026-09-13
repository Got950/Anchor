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

# A clarify is allowed to fire twice on one pending tool intent; a third time is a loop.
MAX_CLARIFY_ATTEMPTS = 2
GAVE_UP = (
    "I wasn't able to get enough detail to file this — try describing it as one message, "
    "e.g. 'create a ticket, export failing on Bedrock, priority high'"
)

# "Call the create_support_ticket tool" told the model nothing about when NOT to, so
# "create a 3D asset for a lamp" read as a create-something request and landed on ticket
# filing. Naming the exclusion fixes that (lamp -> clarify, 6/6 runs), but the exclusion
# alone also scared the model off a bare "create a ticket" — which IS a ticket request and
# belongs on the tool path so the Pydantic guardrail is the one asking for the missing
# fields. Both halves are needed: with the positive case spelled out too, "create a ticket"
# routes to the tool 6/6 and the lamp still routes to clarify 6/6.
_TOOL_SCOPE = {
    "create_support_ticket": (
        " Choose this whenever the user asks for a support TICKET, even with no other detail "
        '("create a ticket", "file a support ticket about X") — the missing fields are collected '
        "downstream. Do NOT choose it for a request to create, generate, make or build CONTENT — "
        "a 3D asset, a model, a mesh, a structure — which is not a support ticket; use clarify there."
    ),
}


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
            "description": (
                "Ask for missing detail, or refuse an out-of-scope request. Also the right choice "
                "when the user wants something none of the other paths cover — ask what they "
                "actually want help with, and never assume they meant to file a support ticket."
            ),
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
                "description": f"Call the {name} tool.{_TOOL_SCOPE.get(name, '')} Include only arguments the user actually stated.",
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


def classify(message: str, previous_response_id: str | None = None) -> dict:
    system = (config.PROMPTS_DIR / "router_system.md").read_text(encoding="utf-8")
    choice = llm.tool_use(
        system, message, _tool_schemas(),
        fallback=lambda: _keyword_route(message),
        previous_response_id=previous_response_id,
    )
    if choice.get("name") not in PATHS:
        # Merge, don't replace: the fallback only knows the path, not the conversation state.
        choice = {**choice, **_keyword_route(message)}
    return choice


def _clarify_streak(prior_calls: list[str]) -> int:
    """How many clarify attempts the resumed conversation has already spent.

    Derived from the stored conversation instead of trusted from the client: /agent returns an
    empty response_id the moment a tool actually runs, so a chain that is still being resumed
    ends in turns that asked a question. Counting trailing clarify/tool-intent turns therefore
    counts attempts, and mis-counting can only end a chain early — never loop it.
    """
    streak = 0
    for name in reversed(prior_calls):
        if name != "clarify" and name not in TOOLS:
            break
        streak += 1
    return streak


# --- dispatch ----------------------------------------------------------------

def handle(message: str, previous_response_id: str | None = None) -> dict:
    choice = classify(message, previous_response_id)
    path = choice["name"]
    args = dict(choice.get("args") or {})
    reasoning = str(args.pop("reasoning", "") or f"routed to {path}")
    response_id = choice.get("response_id") or ""
    history: list[str] = choice.get("history") or []
    spent = _clarify_streak(choice.get("prior_calls") or [])

    def clarify(question: str, **extra) -> dict:
        """Ask, and keep the conversation resumable — unless that would be the third ask."""
        attempt = spent + 1
        keep = attempt <= MAX_CLARIFY_ATTEMPTS
        question, next_id = (question, response_id) if keep else (GAVE_UP, "")
        logging_utils.log_interaction(
            "clarify", reasoning, message=message,
            extra={"clarifying_question": question, "clarify_attempt": attempt, "response_id": next_id, **extra},
        )
        return {"type": "clarify", "reasoning": reasoning, "clarifying_question": question, "response_id": next_id}

    if path in TOOLS:
        # Ground tool args against the WHOLE resumed conversation, not just this message: a
        # summary the user gave two turns ago is user-stated, so validating against `message`
        # alone would drop it as invented and ask for it again forever. Validation itself is
        # untouched — Pydantic still decides whether the tool may run.
        validated, question = guardrails.validate(path, args, message="\n".join([*history, message]))
        if validated is None:
            return clarify(question, intended_tool=path, rejected_args=args)
        result = TOOLS[path][1](validated)
        inputs = validated.model_dump()
        logging_utils.log_interaction("tool_call", reasoning, message=message, tool=path, inputs=inputs, outputs=result)
        # Request resolved: an empty response_id tells the frontend not to resume this
        # conversation, so the next message is not read as more of a ticket that already exists.
        return {"type": "tool_call", "reasoning": reasoning, "tool": path, "tool_args": inputs, "tool_result": result, "response_id": ""}

    if path == "clarify":
        return clarify(args.get("clarifying_question") or "Could you rephrase that? I can answer questions about Craftify, file a support ticket, or flag a generation for review.")

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
        "response_id": response_id,
    }
