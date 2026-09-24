"""The four structured-output methods.

Every method sends the *same* prompt text (:func:`build_messages`). The only
differences are what the method changes: the ``format`` field sent to Ollama,
and (for ``repair``) a single follow-up turn carrying the validation error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from structbench.client import ChatResult, Format, Message, ModelClient
from structbench.scoring import ParseResult, ValidationResult, parse_json, validate
from structbench.tasks import Task

METHODS: tuple[str, ...] = ("prompt-only", "json-mode", "schema-constrained", "repair")

SYSTEM_PROMPT = (
    "You are an information-extraction engine. Read the input text and extract the "
    "requested information as a single JSON object that conforms exactly to the JSON "
    "Schema provided. Use only information stated in the text. Keep array items in the "
    "order they appear in the text. If an optional field is not mentioned, omit it; if a "
    "required field allows null and the value is not stated, use null. Respond with the "
    "JSON object only: no prose, no markdown, no code fences."
)

REPAIR_TEMPLATE = (
    "Your previous reply was rejected by the validator:\n{errors}\n\n"
    "Reply again with only the corrected JSON object that conforms to the schema."
)


def build_messages(task: Task) -> list[Message]:
    user = (
        f"Task: {task.instruction}\n\n"
        f"JSON Schema:\n{json.dumps(task.schema, indent=2)}\n\n"
        f'Input text:\n"""\n{task.text}\n"""'
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def format_for(method: str, task: Task) -> Format:
    if method in ("prompt-only", "repair"):
        return None
    if method == "json-mode":
        return "json"
    if method == "schema-constrained":
        return task.schema
    raise ValueError(f"unknown method: {method}")


@dataclass
class Attempt:
    content: str
    latency_s: float
    output_tokens: int
    prompt_tokens: int
    server_total_s: float | None = None
    eval_s: float | None = None


@dataclass
class MethodOutcome:
    attempts: list[Attempt]
    parse: ParseResult
    validation: ValidationResult | None
    repaired: bool = False
    first_parse_ok: bool = False
    first_schema_ok: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def final_content(self) -> str:
        return self.attempts[-1].content

    @property
    def latency_s(self) -> float:
        return sum(a.latency_s for a in self.attempts)

    @property
    def server_latency_s(self) -> float | None:
        vals = [a.server_total_s for a in self.attempts]
        return None if any(v is None for v in vals) else sum(v for v in vals if v is not None)

    @property
    def output_tokens(self) -> int:
        return sum(a.output_tokens for a in self.attempts)


def _attempt(r: ChatResult) -> Attempt:
    return Attempt(
        r.content, r.latency_s, r.output_tokens, r.prompt_tokens, r.server_total_s, r.eval_s
    )


def _check(content: str, task: Task) -> tuple[ParseResult, ValidationResult | None]:
    parsed = parse_json(content)
    if not parsed.ok:
        return parsed, None
    return parsed, validate(parsed.value, task.schema)


def _error_text(parsed: ParseResult, v: ValidationResult | None, limit: int = 8) -> str:
    if not parsed.ok:
        return f"- not valid JSON: {parsed.error}"
    assert v is not None
    lines = [f"- {m}" for m in v.messages[:limit]]
    if len(v.messages) > limit:
        lines.append(f"- ... and {len(v.messages) - limit} more")
    return "\n".join(lines)


def run_method(method: str, task: Task, client: ModelClient) -> MethodOutcome:
    messages = build_messages(task)
    first = client.chat(messages, format_for(method, task))
    parsed, v = _check(first.content, task)
    first_ok = parsed.ok and v is not None and v.ok
    outcome = MethodOutcome(
        attempts=[_attempt(first)],
        parse=parsed,
        validation=v,
        first_parse_ok=parsed.ok,
        first_schema_ok=first_ok,
    )
    if method != "repair" or first_ok:
        return outcome
    follow_up: list[Message] = [
        *messages,
        {"role": "assistant", "content": first.content},
        {"role": "user", "content": REPAIR_TEMPLATE.format(errors=_error_text(parsed, v))},
    ]
    second = client.chat(follow_up, None)
    parsed2, v2 = _check(second.content, task)
    outcome.attempts.append(_attempt(second))
    outcome.parse = parsed2
    outcome.validation = v2
    outcome.repaired = True
    return outcome
