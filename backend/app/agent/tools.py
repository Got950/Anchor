"""Mocked tools. One Pydantic model per tool, used twice: as the LLM-facing tool_use
schema (see router.py) and as the runtime validator. No drift possible.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field


class CreateTicketArgs(BaseModel):
    summary: str = Field(min_length=5, description="One-line description of the user's problem, in the user's own words.")
    priority: Literal["low", "medium", "high"] = Field(description="Urgency the user indicated. Omit if they did not indicate one.")


class FlagReviewArgs(BaseModel):
    reason: str = Field(min_length=5, description="Why the generation should be reviewed.")


def create_support_ticket(args: CreateTicketArgs) -> dict:
    return {
        "ticket_id": f"TCK-{random.randint(1000, 9999)}",
        "status": "created",
        "summary": args.summary,
        "priority": args.priority,
    }


def flag_generation_for_review(args: FlagReviewArgs) -> dict:
    return {"flag_id": f"FLG-{random.randint(1000, 9999)}", "status": "flagged", "reason": args.reason}


TOOLS = {
    "create_support_ticket": (CreateTicketArgs, create_support_ticket),
    "flag_generation_for_review": (FlagReviewArgs, flag_generation_for_review),
}
