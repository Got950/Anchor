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


class TokenUsage(BaseModel):
    """Summed OpenAI usage across all LLM calls for this request.

    Named after chat.completions; /agent's router runs on the Responses API and its
    input_tokens/output_tokens are mapped onto these in llm._record_usage.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0


class AskResponse(BaseModel):
    answer: str
    abstained: bool
    sources: list[Source] = []
    retrieval_confidence: float
    verified: bool
    usage: Optional[TokenUsage] = None


class AgentRequest(BaseModel):
    message: str = Field(min_length=1)
    # `response_id` from the previous /agent turn, echoed back so a clarifying question and
    # the user's answer to it are one Responses API conversation. Omit to start fresh.
    previous_response_id: Optional[str] = None


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
    usage: Optional[TokenUsage] = None
    # Send this back as `previous_response_id` on the NEXT message to resume this
    # conversation. Empty means the conversation is over — the tool ran, the clarify cap
    # gave up, or the router was offline — so the next message must start fresh.
    response_id: str = ""
