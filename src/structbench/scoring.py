"""Parsing, schema validation and field-level scoring against ground truth."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class ParseResult:
    value: Any
    ok: bool
    strict_ok: bool  # the raw reply was *only* JSON (after whitespace strip)
    error: str = ""


def _first_json_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` span, respecting strings."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def parse_json(text: str) -> ParseResult:
    """Parse a model reply. Same lenient rules for every method.

    1. Try the whole reply. 2. Try the contents of a ```json fence.
    3. Try the first balanced ``{...}`` span. Only a JSON *object* counts.
    """
    stripped = text.strip()
    try:
        v = json.loads(stripped)
        if isinstance(v, dict):
            return ParseResult(v, ok=True, strict_ok=True)
    except json.JSONDecodeError:
        pass
    candidates: list[str] = [m.group(1).strip() for m in _FENCE.finditer(text)]
    span = _first_json_object(text)
    if span is not None:
        candidates.append(span)
    last_err = "no JSON object found"
    for cand in candidates:
        try:
            v = json.loads(cand)
        except json.JSONDecodeError as exc:
            last_err = f"JSON decode error: {exc.msg} (line {exc.lineno} col {exc.colno})"
            continue
        if isinstance(v, dict):
            return ParseResult(v, ok=True, strict_ok=False)
        last_err = "top-level JSON value is not an object"
    return ParseResult(None, ok=False, strict_ok=False, error=last_err)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    messages: list[str]
    keywords: list[str]  # jsonschema validator keywords that failed, e.g. "required"


def validate(value: Any, schema: dict[str, Any]) -> ValidationResult:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.absolute_path)
    )
    msgs = [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]
    return ValidationResult(
        ok=not errors, messages=msgs, keywords=[str(e.validator) for e in errors]
    )


# ---------------------------------------------------------------- field accuracy

Path = tuple[str | int, ...]


def normalize_str(s: str) -> str:
    """Case/whitespace/punctuation-insensitive form used for free-text fields."""
    s = unicodedata.normalize("NFKC", s).casefold().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .,;:!\"'")
    return s


def flatten(value: Any, prefix: Path = ()) -> dict[Path, Any]:
    """Map every leaf (scalar or empty container) to its path."""
    out: dict[Path, Any] = {}
    if isinstance(value, dict):
        if not value and prefix:
            out[prefix] = {}
        for k, v in value.items():
            out.update(flatten(v, (*prefix, k)))
    elif isinstance(value, list):
        if not value:
            out[prefix] = []
        for i, v in enumerate(value):
            out.update(flatten(v, (*prefix, i)))
    else:
        out[prefix] = value
    return out


def _subschemas(schema: dict[str, Any]) -> list[dict[str, Any]]:
    alts = schema.get("anyOf") or schema.get("oneOf")
    if alts:
        return [s for a in alts for s in _subschemas(a)]
    return [schema]


def leaf_schema(schema: dict[str, Any], path: Path) -> dict[str, Any] | None:
    """Best-effort lookup of the schema that governs ``path``."""
    current = [schema]
    for part in path:
        nxt: list[dict[str, Any]] = []
        for s in current:
            for alt in _subschemas(s):
                if isinstance(part, int) and "items" in alt:
                    nxt.append(alt["items"])
                elif isinstance(part, str) and part in alt.get("properties", {}):
                    nxt.append(alt["properties"][part])
        if not nxt:
            return None
        current = nxt
    return current[0]


def _is_enum(schema: dict[str, Any] | None) -> bool:
    if schema is None:
        return False
    return any("enum" in s or "const" in s for s in _subschemas(schema))


def values_match(expected: Any, actual: Any, *, exact_strings: bool = False) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        return math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-6)
    if isinstance(expected, str) and isinstance(actual, str):
        if exact_strings:
            return expected == actual
        return normalize_str(expected) == normalize_str(actual)
    return bool(expected == actual)


@dataclass(frozen=True)
class FieldScore:
    correct: int
    total: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 1.0


def field_accuracy(expected: dict[str, Any], actual: Any, schema: dict[str, Any]) -> FieldScore:
    """Leaf-level accuracy.

    Denominator = leaves in the ground truth plus any *extra* non-null leaves the
    model invented (hallucinated array items / optional fields are penalised).
    A null/absent pair counts as agreement only when it is in the ground truth.
    Enum fields are compared exactly; other strings after :func:`normalize_str`;
    numbers numerically.
    """
    exp = flatten(expected)
    act = flatten(actual) if isinstance(actual, dict) else {}
    correct = 0
    for path, ev in exp.items():
        if path not in act:
            correct += ev is None  # omitting an expected-null optional field is fine
            continue
        exact = _is_enum(leaf_schema(schema, path))
        if values_match(ev, act[path], exact_strings=exact):
            correct += 1
    extras = [p for p, v in act.items() if p not in exp and v not in (None, [], {})]
    return FieldScore(correct=correct, total=len(exp) + len(extras))
