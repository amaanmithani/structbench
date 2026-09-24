from __future__ import annotations

import json

import pytest

from structbench.methods import (
    METHODS,
    REPAIR_TEMPLATE,
    SYSTEM_PROMPT,
    _error_text,
    build_messages,
    format_for,
    run_method,
)
from structbench.scoring import ParseResult, ValidationResult
from tests.conftest import FakeClient

GOOD = json.dumps({"name": "Alice", "level": "high", "count": 3})
BAD_ENUM = json.dumps({"name": "Alice", "level": "HIGH", "count": 3})


def test_prompt_text_is_identical_across_methods(simple_task):
    """Honesty check: only the `format` field differs between single-turn methods."""
    seen = []
    for m in METHODS:
        client = FakeClient([GOOD])
        run_method(m, simple_task, client)
        seen.append(client.calls[0][0])
    assert all(msgs == seen[0] for msgs in seen)
    assert seen[0][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert json.dumps(simple_task.schema, indent=2) in seen[0][1]["content"]
    assert simple_task.text in seen[0][1]["content"]


def test_format_per_method(simple_task):
    assert format_for("prompt-only", simple_task) is None
    assert format_for("repair", simple_task) is None
    assert format_for("json-mode", simple_task) == "json"
    assert format_for("schema-constrained", simple_task) == simple_task.schema
    with pytest.raises(ValueError, match="unknown method"):
        format_for("magic", simple_task)


def test_build_messages_shape(simple_task):
    msgs = build_messages(simple_task)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[1]["content"].startswith("Task: Extract it.")


@pytest.mark.parametrize("method", ["prompt-only", "json-mode", "schema-constrained"])
def test_single_turn_methods_never_retry(method, simple_task):
    client = FakeClient([BAD_ENUM])
    out = run_method(method, simple_task, client)
    assert len(client.calls) == 1
    assert out.parse.ok
    assert out.validation is not None
    assert not out.validation.ok
    assert not out.repaired


class TestRepairLoop:
    def test_no_retry_when_first_attempt_valid(self, simple_task):
        client = FakeClient([GOOD])
        out = run_method("repair", simple_task, client)
        assert len(client.calls) == 1
        assert not out.repaired
        assert out.first_schema_ok
        assert out.validation is not None
        assert out.validation.ok

    def test_schema_error_is_fed_back_once(self, simple_task):
        client = FakeClient([BAD_ENUM, GOOD])
        out = run_method("repair", simple_task, client)
        assert len(client.calls) == 2
        follow_up, fmt = client.calls[1]
        assert fmt is None
        # original conversation is preserved, then the bad reply, then the error
        assert follow_up[:2] == build_messages(simple_task)
        assert follow_up[2] == {"role": "assistant", "content": BAD_ENUM}
        assert follow_up[3]["role"] == "user"
        assert "level: 'HIGH' is not one of ['low', 'high']" in follow_up[3]["content"]
        assert follow_up[3]["content"].startswith(REPAIR_TEMPLATE.split("{")[0])
        assert out.repaired
        assert not out.first_schema_ok
        assert out.validation is not None
        assert out.validation.ok
        assert out.final_content == GOOD
        assert out.latency_s == pytest.approx(1.0)
        assert out.server_latency_s == pytest.approx(0.8)
        assert out.output_tokens == len(BAD_ENUM) // 4 + len(GOOD) // 4

    def test_parse_error_is_fed_back(self, simple_task):
        client = FakeClient(["Sure, here is the data: name Alice", GOOD])
        out = run_method("repair", simple_task, client)
        assert "not valid JSON" in client.calls[1][0][3]["content"]
        assert out.first_parse_ok is False
        assert out.parse.ok

    def test_only_one_retry_even_if_still_invalid(self, simple_task):
        client = FakeClient([BAD_ENUM, BAD_ENUM, GOOD])
        out = run_method("repair", simple_task, client)
        assert len(client.calls) == 2
        assert out.repaired
        assert out.validation is not None
        assert not out.validation.ok

    def test_error_list_is_truncated(self):
        parsed = ParseResult({"a": 1}, ok=True, strict_ok=True)
        v = ValidationResult(ok=False, messages=[f"e{i}" for i in range(12)], keywords=[])
        text = _error_text(parsed, v, limit=8)
        assert text.count("\n- ") == 8
        assert text.endswith("- ... and 4 more")
