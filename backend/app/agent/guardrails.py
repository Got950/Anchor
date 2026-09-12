"""Guardrails: a tool is only ever called with args that pass its Pydantic schema.
A validation failure becomes a clarifying question naming the missing field.
"""
from __future__ import annotations

from pydantic import ValidationError

from .tools import TOOLS

_QUESTIONS = {
    ("create_support_ticket", ("priority", "summary")): "What should the ticket summary say, and what priority (low/medium/high)?",
    ("create_support_ticket", ("summary",)): "What should the ticket summary say?",
    ("create_support_ticket", ("priority",)): "What priority should this ticket be — low, medium, or high?",
    ("flag_generation_for_review", ("reason",)): "What's the reason for flagging this generation for review?",
}


def validate(tool_name: str, raw_args: dict) -> tuple[object | None, str | None]:
    """Returns (validated_args, None) or (None, clarifying_question)."""
    model, _ = TOOLS[tool_name]
    try:
        return model(**{k: v for k, v in (raw_args or {}).items() if v not in (None, "")}), None
    except ValidationError as exc:
        bad = tuple(sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]}))
        question = _QUESTIONS.get((tool_name, bad))
        if question is None:
            fields = " and ".join(bad) or "the missing details"
            question = f"I need a bit more detail before I can do that — could you give me {fields}?"
        return None, question
