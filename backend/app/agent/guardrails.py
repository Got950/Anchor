"""Guardrails: a tool is only ever called with args that pass its Pydantic schema.
A validation failure becomes a clarifying question naming the missing field.
"""
from __future__ import annotations

import re

from pydantic import ValidationError

from .tools import TOOLS

_QUESTIONS = {
    ("create_support_ticket", ("priority", "summary")): "What should the ticket summary say, and what priority (low/medium/high)?",
    ("create_support_ticket", ("summary",)): "What should the ticket summary say?",
    ("create_support_ticket", ("priority",)): "What priority should this ticket be — low, medium, or high?",
    ("flag_generation_for_review", ("reason",)): "What's the reason for flagging this generation for review?",
}

# Content words that appear in bare "please flag/create a ticket" asks — matching only these
# does not prove the model extracted a real user-stated reason/summary.
_TRIGGER = frozenset(
    "please flag this that generation review for because create file open raise submit log "
    "support ticket about my the a an user requested without specifying reason".split()
)

# Words that count as the user having said something about urgency. `priority` needs its own
# rule because _grounded wants two token hits, which a one-word enum value can never reach.
_URGENCY = re.compile(r"\b(low|medium|normal|high|urgent|critical|asap|emergency|blocker|p[0-3])\b", re.I)


def _grounded(message: str, value: str) -> bool:
    """True iff `value` echoes content words from `message` (not a pure LLM invention).

    ponytail: lexical overlap beat another LLM call. Ceiling: a paraphrase that shares
    no tokens with the user message is rejected and becomes a clarify — fine for tools.
    """
    msg_toks = set(re.findall(r"[a-z0-9]{3,}", message.lower())) - _TRIGGER
    if not msg_toks:
        return False  # bare "flag for review" / "create a ticket" — any reason/summary is invented
    val_toks = set(re.findall(r"[a-z0-9]{3,}", value.lower())) - _TRIGGER
    hits = len(msg_toks & val_toks)
    return hits >= min(2, len(msg_toks))


def validate(tool_name: str, raw_args: dict, message: str = "") -> tuple[object | None, str | None]:
    """Returns (validated_args, None) or (None, clarifying_question)."""
    model, _ = TOOLS[tool_name]
    cleaned = {k: v for k, v in (raw_args or {}).items() if v not in (None, "")}
    # Drop free-text fields the model invented (not present in the user message) before
    # Pydantic sees them — missing required fields then become clarify questions.
    if message:
        for field in ("summary", "reason"):
            if field in cleaned and isinstance(cleaned[field], str) and not _grounded(message, cleaned[field]):
                cleaned.pop(field)
        # The Responses API invents this enum where chat.completions left it unset ("File a
        # ticket about my export failing on Bedrock" -> "medium", 4/4 runs), which would file
        # tickets at a priority the user never chose instead of asking. Presence of an urgency
        # word, not a value match: "urgent"/"critical" legitimately map onto high, so demanding
        # the literal enum value back would reject a correct mapping.
        # ponytail: word list. Ceiling: urgency phrased without one of these words ("this is
        # blocking my launch") reads as unstated and becomes a clarify — the safe direction.
        if "priority" in cleaned and not _URGENCY.search(message):
            cleaned.pop("priority")
    try:
        return model(**cleaned), None
    except ValidationError as exc:
        bad = tuple(sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]}))
        question = _QUESTIONS.get((tool_name, bad))
        if question is None:
            fields = " and ".join(bad) or "the missing details"
            question = f"I need a bit more detail before I can do that — could you give me {fields}?"
        return None, question
