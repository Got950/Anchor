"""Thin LLM client.

One OpenAI-compatible code path (OpenAI, or Groq/Gemini via OPENAI_BASE_URL).

ponytail: when no API key is configured every call falls back to the caller-supplied
deterministic fallback instead of raising, so the whole pipeline is runnable and
testable offline. Ceiling: fallbacks are keyword/regex heuristics, not a model —
set OPENAI_API_KEY to get real LLM behaviour on every path.
"""
from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable

from . import config

log = logging.getLogger(__name__)
_client = None

# /health probe cache: (monotonic_ts, ok, error_reason). TTL avoids hitting the API every curl.
_PROBE_TTL_S = 300.0
_probe_cache: tuple[float, bool, str | None] | None = None


@dataclass
class Usage:
    """Accumulated LLM usage for the current request (prompt/completion tokens).

    Field names stay chat.completions-shaped because the /ask path, the API response
    schema, the UI and stress_pass.py all read them; _record_usage maps the Responses
    API's differently-named fields onto them.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
        }


# Per-request accumulator; begin_usage()/take_usage() from the HTTP layer.
_usage_acc: ContextVar[Usage | None] = ContextVar("llm_usage_acc", default=None)


def begin_usage() -> None:
    """Reset the per-request usage accumulator (call at the start of /ask or /agent)."""
    _usage_acc.set(Usage())


def take_usage() -> dict[str, int]:
    """Return and clear accumulated usage for the current request."""
    acc = _usage_acc.get()
    _usage_acc.set(None)
    return acc.as_dict() if acc is not None else Usage().as_dict()


def _record_usage(resp: Any) -> None:
    """Pull usage from a chat.completions OR Responses API response into the accumulator.

    The two APIs name the same numbers differently — chat.completions returns
    prompt_tokens/completion_tokens, the Responses API returns input_tokens/output_tokens
    (verified live against openai 2.31.0: ResponseUsage(input_tokens=..., output_tokens=...,
    total_tokens=...)). Reading only the chat.completions names would silently log zeros
    for every /agent call, so both shapes are accepted here.
    """
    raw = getattr(resp, "usage", None)
    if raw is None:
        return
    prompt = int(getattr(raw, "prompt_tokens", None) or getattr(raw, "input_tokens", None) or 0)
    completion = int(getattr(raw, "completion_tokens", None) or getattr(raw, "output_tokens", None) or 0)
    total = int(getattr(raw, "total_tokens", 0) or (prompt + completion))
    log.info("llm usage prompt_tokens=%s completion_tokens=%s total_tokens=%s", prompt, completion, total)
    acc = _usage_acc.get()
    if acc is None:
        return
    acc.prompt_tokens += prompt
    acc.completion_tokens += completion
    acc.total_tokens += total
    acc.calls += 1


def available() -> bool:
    return bool(config.LLM_API_KEY) and config.LLM_PROVIDER != "mock"


def _classify_probe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__} {exc}".lower()
    if "401" in text or "invalid_api_key" in text or "incorrect api key" in text or "authentication" in text:
        return "invalid_api_key"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "429" in text or "rate" in text:
        return "rate_limited"
    if "connect" in text or "network" in text:
        return "network_error"
    return "llm_call_failed"


def probe_live() -> tuple[bool, str | None]:
    """Minimal live key check for /health. Cached ~5 min. Does not change call fallbacks."""
    global _probe_cache
    now = time.monotonic()
    if _probe_cache is not None and (now - _probe_cache[0]) < _PROBE_TTL_S:
        return _probe_cache[1], _probe_cache[2]

    if not available():
        reason = "no_api_key" if not config.LLM_API_KEY else "mock_provider"
        _probe_cache = (now, False, reason)
        return False, reason

    try:
        # 1-token completion — cheapest auth + connectivity check
        _get_client().chat.completions.create(
            model=config.LLM_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        _probe_cache = (now, True, None)
        return True, None
    except Exception as exc:
        reason = _classify_probe_error(exc)
        log.warning("LLM health probe failed (%s): %s", reason, exc)
        _probe_cache = (now, False, reason)
        return False, reason


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
    return _client


def _resolve(fallback: Any) -> Any:
    return fallback() if callable(fallback) else fallback


def text(system: str, user: str, *, fallback: Any, temperature: float = 0.0) -> str:
    """Plain completion. Returns the model's text, or the fallback if offline."""
    if not available():
        return _resolve(fallback)
    try:
        resp = _get_client().chat.completions.create(
            model=config.LLM_MODEL,
            temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        _record_usage(resp)
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # network / quota / model errors must not 500 the API
        log.warning("LLM text call failed (%s); using fallback", exc)
        return _resolve(fallback)


def json_object(system: str, user: str, *, fallback: Any, temperature: float = 0.0) -> dict:
    """Completion parsed as a JSON object."""
    raw = text(system, user + "\n\nRespond with strict JSON only.", fallback=fallback, temperature=temperature)
    if isinstance(raw, dict):
        return raw
    return _parse_json(raw, _resolve(fallback))


def _parse_json(raw: str, fallback: Any) -> dict:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
        log.warning("Could not parse JSON from LLM output: %r", raw[:200])
        return fallback if isinstance(fallback, dict) else {}


# A stored turn whose function_call was never answered cannot be resumed: the API rejects
# it with "No tool output found for function call ...". Nothing here ever reports a tool
# result back to the model, so every pending call is closed with this placeholder. The
# model still sees its own question in the stored history, which is the context that matters.
_NO_OUTPUT = json.dumps({"note": "no tool output was recorded for this call"})


def _prior_context(client: Any, previous_response_id: str) -> tuple[list[str], list[str], list[dict]]:
    """Read a stored conversation back: (user messages, tools chosen, unanswered-call stubs).

    Two GETs, and only on a continuation turn: input_items.list() returns the whole resumed
    conversation (every earlier turn, newest first), while retrieve() returns the one
    function_call the previous turn left unanswered — which needs a stub to resume at all.
    """
    messages: list[str] = []
    names: list[str] = []
    # ponytail: one page, newest first. Ceiling: a conversation past 100 items loses its
    # oldest turns, costing only guardrail grounding reach — the clarify cap in router.py
    # ends these chains long before that.
    for item in reversed(list(client.responses.input_items.list(previous_response_id, limit=100))):
        data = item.model_dump()
        if data.get("type") == "message" and data.get("role") == "user":
            messages.append(" ".join(part.get("text") or "" for part in data.get("content") or []).strip())
        elif data.get("type") == "function_call":
            names.append(data.get("name") or "")

    stubs: list[dict] = []
    for item in client.responses.retrieve(previous_response_id).output:
        if item.type == "function_call":
            names.append(item.name)
            stubs.append({"type": "function_call_output", "call_id": item.call_id, "output": _NO_OUTPUT})
    return messages, names, stubs


def _route_call(system: str, user: str, tools: list[dict], previous_response_id: str | None) -> dict:
    """One Responses API call. Raises on API failure so the caller can retry or fall back."""
    client = _get_client()
    history, prior_calls, pending = [], [], []
    if previous_response_id:
        history, prior_calls, pending = _prior_context(client, previous_response_id)

    resp = client.responses.create(
        model=config.LLM_MODEL,
        store=True,
        temperature=0.0,
        tool_choice="required",
        tools=[{"type": "function", **t} for t in tools],
        instructions=system,
        input=[*pending, {"role": "user", "content": user}],
        **({"previous_response_id": previous_response_id} if previous_response_id else {}),
    )
    _record_usage(resp)
    call = next((o for o in resp.output if o.type == "function_call"), None)
    return {
        "name": call.name if call else None,
        "args": _parse_json(call.arguments or "{}", {}) if call else {},
        "response_id": resp.id,
        "history": history,
        "prior_calls": prior_calls,
    }


def tool_use(
    system: str,
    user: str,
    tools: list[dict],
    *,
    fallback: Callable[[], dict],
    previous_response_id: str | None = None,
) -> dict:
    """Native function calling on the Responses API.

    Classification AND argument extraction happen in this single call (plan Section 4.1).
    `store=True` plus `previous_response_id` make a clarifying question and the user's
    answer to it one server-side conversation, so arguments the user spread over two turns
    still resolve instead of looping.

    Returns {"name", "args", "response_id", "history", "prior_calls"}: `history` is the
    earlier user messages of the resumed conversation and `prior_calls` the tools it already
    chose. The router needs both — the first to ground tool args, the second to cap clarifies.
    """
    offline = {"response_id": "", "history": [], "prior_calls": []}
    if not available():
        return {**_resolve(fallback), **offline}
    try:
        return _route_call(system, user, tools, previous_response_id)
    except Exception as exc:
        if previous_response_id:
            # The id comes from the client, so it can be unknown, expired or already
            # consumed. One clean retry beats degrading a live model to the keyword fallback.
            log.warning("router resume on %s failed (%s); retrying fresh", previous_response_id, exc)
            try:
                return _route_call(system, user, tools, None)
            except Exception as retry_exc:
                exc = retry_exc
        log.warning("LLM tool_use call failed (%s); using fallback", exc)
        return {**_resolve(fallback), **offline}


def judge_llm():
    """RAGAS judge, explicitly wrapped (plan Section 1 / 7.2) — never RAGAS's implicit default."""
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    return LangchainLLMWrapper(
        ChatOpenAI(model=config.JUDGE_MODEL, temperature=0.0, api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
    )


def judge_embeddings():
    from langchain_openai import OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    return LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small", api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
    )
