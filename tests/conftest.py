from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from structbench.client import ChatResult, Format, Message
from structbench.tasks import Task

ROOT = Path(__file__).resolve().parent.parent


class FakeClient:
    """Scripted model client: returns queued replies and records every call."""

    def __init__(self, replies: list[str] | Callable[[list[Message], Format], str]) -> None:
        self.model = "fake:1b"
        self._replies = replies
        self.calls: list[tuple[list[Message], Format]] = []

    def chat(self, messages: list[Message], fmt: Format = None) -> ChatResult:
        self.calls.append((messages, fmt))
        replies = self._replies
        content = replies(messages, fmt) if callable(replies) else replies.pop(0)
        return ChatResult(
            content=content,
            latency_s=0.5,
            output_tokens=len(content) // 4,
            prompt_tokens=10,
            server_total_s=0.4,
            eval_s=0.25,
        )


SIMPLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "level": {"type": "string", "enum": ["low", "high"]},
        "count": {"type": "integer", "minimum": 0, "maximum": 10},
    },
    "required": ["name", "level", "count"],
    "additionalProperties": False,
}


@pytest.fixture
def simple_task() -> Task:
    return Task(
        id="t-1",
        difficulty=3,
        domain="test",
        instruction="Extract it.",
        text="Alice, high, 3",
        schema=SIMPLE_SCHEMA,
        expected={"name": "Alice", "level": "high", "count": 3},
    )


@pytest.fixture
def tasks_path() -> Path:
    return ROOT / "data" / "tasks.jsonl"
