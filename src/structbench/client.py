"""Model client interface and the Ollama implementation.

Everything that talks to a model goes through :class:`ModelClient`, so the
benchmark logic can be tested with a fake client and never touches the network.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

Message = dict[str, str]
# ``None`` = free text, ``"json"`` = JSON mode, dict = JSON schema (constrained decoding).
Format = str | dict[str, Any] | None


@dataclass(frozen=True)
class ChatResult:
    """One model call."""

    content: str
    latency_s: float
    output_tokens: int
    prompt_tokens: int = 0
    # Server-side timings reported by Ollama (seconds). total_duration is measured inside
    # the server, so it excludes HTTP/client overhead but can still include scheduler wait.
    server_total_s: float | None = None
    eval_s: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class ModelClient(Protocol):
    """Anything that can run a chat completion with an optional output format."""

    model: str

    def chat(self, messages: list[Message], fmt: Format = None) -> ChatResult: ...


def _ns(v: Any) -> float | None:
    return float(v) / 1e9 if isinstance(v, int | float) else None


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    """Minimal client for Ollama's ``/api/chat`` (stdlib only, no streaming)."""

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        *,
        temperature: float = 0.0,
        seed: int = 42,
        num_ctx: int = 4096,
        num_predict: int = 1024,
        timeout_s: float = 600.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.options: dict[str, Any] = {
            "temperature": temperature,
            "seed": seed,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        }
        self.timeout_s = timeout_s

    def build_payload(self, messages: list[Message], fmt: Format = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": dict(self.options),
            "keep_alive": "30m",
        }
        if fmt is not None:
            payload["format"] = fmt
        return payload

    def chat(self, messages: list[Message], fmt: Format = None) -> ChatResult:  # pragma: no cover
        body = json.dumps(self.build_payload(messages, fmt)).encode()
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data: dict[str, Any] = json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise OllamaError(f"Ollama request failed: {exc}") from exc
        latency = time.perf_counter() - start
        return ChatResult(
            content=str(data.get("message", {}).get("content", "")),
            latency_s=latency,
            output_tokens=int(data.get("eval_count", 0)),
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            server_total_s=_ns(data.get("total_duration")),
            eval_s=_ns(data.get("eval_duration")),
            raw={k: v for k, v in data.items() if k != "message"},
        )
