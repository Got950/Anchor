"""JSONL logger: one line per agent interaction, including the router's reasoning."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from . import config


def log_interaction(
    path: str,
    reasoning: str,
    *,
    message: str,
    tool: Optional[str] = None,
    inputs: Optional[dict[str, Any]] = None,
    outputs: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "path": path,
        "message": message,
        "reasoning": reasoning,
        "tool": tool,
        "inputs": inputs,
        "outputs": outputs,
    }
    if extra:
        record.update(extra)
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
