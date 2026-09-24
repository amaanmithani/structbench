"""Task suite loading and schema-difficulty classification."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

DIFFICULTY_NAMES: dict[int, str] = {
    1: "L1 flat",
    2: "L2 nested+arrays",
    3: "L3 enums+ranges",
    4: "L4 deep+unions",
}


@dataclass(frozen=True)
class Task:
    id: str
    difficulty: int
    domain: str
    instruction: str
    text: str
    schema: dict[str, Any]
    expected: dict[str, Any]


def load_tasks(path: Path) -> list[Task]:
    tasks: list[Task] = []
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            d = json.loads(line)
            try:
                tasks.append(
                    Task(
                        id=d["id"],
                        difficulty=int(d["difficulty"]),
                        domain=d["domain"],
                        instruction=d["instruction"],
                        text=d["text"],
                        schema=d["schema"],
                        expected=d["expected"],
                    )
                )
            except KeyError as exc:
                raise ValueError(f"{path}:{lineno}: missing key {exc}") from exc
    ids = [t.id for t in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task ids")
    return tasks


def _walk(schema: Any, depth: int = 0) -> Iterator[tuple[dict[str, Any], int]]:
    """Yield every sub-schema with its object-nesting depth."""
    if not isinstance(schema, dict):
        return
    yield schema, depth
    for key in ("properties",):
        for sub in schema.get(key, {}).values():
            child_depth = depth + (1 if sub.get("type") == "object" else 0)
            yield from _walk(sub, child_depth)
    if "items" in schema:
        items = schema["items"]
        yield from _walk(items, depth + (1 if items.get("type") == "object" else 0))
    for key in ("anyOf", "oneOf"):
        for sub in schema.get(key, []):
            yield from _walk(sub, depth + (1 if sub.get("type") == "object" else 0))


@dataclass(frozen=True)
class SchemaFeatures:
    max_object_depth: int
    has_array: bool
    has_nested_object: bool
    has_enum: bool
    has_numeric_range: bool
    has_union: bool
    has_optional: bool


def schema_features(schema: dict[str, Any]) -> SchemaFeatures:
    subs = list(_walk(schema))
    max_depth = max(d for _, d in subs)
    has_optional = False
    for s, _ in subs:
        props = set(s.get("properties", {}))
        if props and not props <= set(s.get("required", [])):
            has_optional = True
    return SchemaFeatures(
        max_object_depth=max_depth,
        has_array=any(s.get("type") == "array" for s, _ in subs),
        has_nested_object=max_depth >= 1,
        has_enum=any("enum" in s for s, _ in subs),
        has_numeric_range=any(
            k in s for s, _ in subs for k in ("minimum", "maximum", "exclusiveMinimum")
        ),
        has_union=any(("anyOf" in s or "oneOf" in s) for s, _ in subs),
        has_optional=has_optional,
    )


def classify_difficulty(schema: dict[str, Any]) -> int:
    """Infer the difficulty level from schema structure (used to audit the labels)."""
    f = schema_features(schema)
    if f.has_union and f.max_object_depth >= 2 and f.has_optional:
        return 4
    if f.has_enum and f.has_numeric_range:
        return 3
    if f.has_nested_object or f.has_array:
        return 2
    return 1


def validate_task(task: Task) -> list[str]:
    """Return problems with a task (empty list = OK)."""
    problems: list[str] = []
    Draft202012Validator.check_schema(task.schema)
    errs = list(Draft202012Validator(task.schema).iter_errors(task.expected))
    problems += [f"{task.id}: expected output invalid: {e.message}" for e in errs]
    inferred = classify_difficulty(task.schema)
    if inferred != task.difficulty:
        problems.append(f"{task.id}: labelled L{task.difficulty} but schema looks like L{inferred}")
    return problems
