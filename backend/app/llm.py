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
from typing import Any, Callable

from . import config

log = logging.getLogger(__name__)
_client = None


def available() -> bool:
    return bool(config.LLM_API_KEY) and config.LLM_PROVIDER != "mock"


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


def tool_use(
    system: str,
    user: str,
    tools: list[dict],
    *,
    fallback: Callable[[], dict],
) -> dict:
    """Native function calling. Returns {"name": str, "args": dict}.

    Classification AND argument extraction happen in this single call (plan Section 4.1).
    """
    if not available():
        return _resolve(fallback)
    try:
        resp = _get_client().chat.completions.create(
            model=config.LLM_MODEL,
            temperature=0.0,
            tool_choice="required",
            tools=[{"type": "function", "function": t} for t in tools],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        calls = resp.choices[0].message.tool_calls or []
        if not calls:
            return _resolve(fallback)
        return {
            "name": calls[0].function.name,
            "args": _parse_json(calls[0].function.arguments or "{}", {}),
        }
    except Exception as exc:
        log.warning("LLM tool_use call failed (%s); using fallback", exc)
        return _resolve(fallback)


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
