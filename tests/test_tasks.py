"""Audit data/tasks.jsonl: every expected output validates, difficulty labels are honest."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from structbench.tasks import (
    Task,
    classify_difficulty,
    load_tasks,
    schema_features,
    validate_task,
)


def test_suite_size_and_balance(tasks_path):
    tasks = load_tasks(tasks_path)
    assert len(tasks) == 40
    assert Counter(t.difficulty for t in tasks) == {1: 10, 2: 10, 3: 10, 4: 10}
    assert len({t.domain for t in tasks}) >= 10


def test_every_expected_output_validates_against_its_schema(tasks_path):
    for t in load_tasks(tasks_path):
        Draft202012Validator.check_schema(t.schema)
        errors = list(Draft202012Validator(t.schema).iter_errors(t.expected))
        assert not errors, f"{t.id}: {[e.message for e in errors]}"


def test_difficulty_labels_match_schema_structure(tasks_path):
    for t in load_tasks(tasks_path):
        assert classify_difficulty(t.schema) == t.difficulty, t.id
        assert validate_task(t) == []


def test_level_feature_contract(tasks_path):
    for t in load_tasks(tasks_path):
        f = schema_features(t.schema)
        if t.difficulty == 1:
            assert not f.has_nested_object, t.id
            assert not f.has_array, t.id
            assert not f.has_union, t.id
        elif t.difficulty == 2:
            assert f.has_nested_object or f.has_array, t.id
            assert not f.has_union, t.id
        elif t.difficulty == 3:
            assert f.has_enum, t.id
            assert f.has_numeric_range, t.id
            assert not f.has_union, t.id
        else:
            assert f.has_union, t.id
            assert f.has_optional, t.id
            assert f.max_object_depth >= 2, t.id


def test_text_and_ids_are_sane(tasks_path):
    for t in load_tasks(tasks_path):
        assert t.id.startswith(f"l{t.difficulty}-")
        assert 40 <= len(t.text) <= 800, t.id
        assert t.instruction


def test_classifier_levels():
    flat = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    assert classify_difficulty(flat) == 1
    nested = {"type": "object", "properties": {"a": {"type": "array", "items": {"type": "string"}}}}
    assert classify_difficulty(nested) == 2
    l3 = {
        "type": "object",
        "properties": {
            "e": {"type": "string", "enum": ["x"]},
            "n": {"type": "integer", "minimum": 1},
        },
    }
    assert classify_difficulty(l3) == 3


def _write(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n")
    return p


ROW: dict[str, Any] = {
    "id": "l1-x",
    "difficulty": 1,
    "domain": "d",
    "instruction": "i",
    "text": "t",
    "schema": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]},
    "expected": {"a": "x"},
}


def test_load_rejects_duplicates_and_missing_keys(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_tasks(_write(tmp_path, [ROW, ROW]))
    bad = {k: v for k, v in ROW.items() if k != "expected"}
    with pytest.raises(ValueError, match="missing key"):
        load_tasks(_write(tmp_path, [bad]))


def test_validate_task_reports_problems():
    t = Task(
        id="bad",
        difficulty=4,
        domain="d",
        instruction="i",
        text="t",
        schema=ROW["schema"],
        expected={"a": 5},
    )
    problems = validate_task(t)
    assert any("expected output invalid" in p for p in problems)
    assert any("labelled L4" in p for p in problems)
