"""Pydantic request/response schemas for /ask and /agent."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


class Source(BaseModel):
    doc_id: str
    title: str
    snippet: str
    via_reference: bool = False


class AskResponse(BaseModel):
    answer: str
    abstained: bool
    sources: list[Source] = []
    retrieval_confidence: float
    verified: bool


class AgentRequest(BaseModel):
    message: str = Field(min_length=1)


class AgentResponse(BaseModel):
    type: Literal["answer", "abstain", "tool_call", "clarify"]
    reasoning: str
    answer: Optional[str] = None
    sources: Optional[list[Source]] = None
    tool: Optional[str] = None
    tool_args: Optional[dict[str, Any]] = None
    tool_result: Optional[dict[str, Any]] = None
    clarifying_question: Optional[str] = None
    # Present on the answer/abstain paths only: the UI renders the confidence and
    # groundedness badges from these, so /agent must carry them like /ask does.
    retrieval_confidence: Optional[float] = None
    verified: Optional[bool] = None
