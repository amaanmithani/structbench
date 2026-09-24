from __future__ import annotations

from typing import Any

import pytest

from structbench.scoring import (
    field_accuracy,
    flatten,
    leaf_schema,
    normalize_str,
    parse_json,
    validate,
    values_match,
)
from tests.conftest import SIMPLE_SCHEMA

UNION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contact": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {"kind": {"const": "email"}, "address": {"type": "string"}},
                },
                {
                    "type": "object",
                    "properties": {"kind": {"const": "phone"}, "number": {"type": "string"}},
                },
            ]
        },
        "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}},
        "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
}


class TestParse:
    def test_plain_json_is_strict(self):
        r = parse_json('  {"a": 1}\n')
        assert r.ok
        assert r.strict_ok
        assert r.value == {"a": 1}

    def test_code_fence_is_lenient_not_strict(self):
        r = parse_json('Here you go:\n```json\n{"a": [1, 2]}\n```\nHope it helps')
        assert r.ok
        assert not r.strict_ok
        assert r.value == {"a": [1, 2]}

    def test_embedded_object_with_braces_in_strings(self):
        r = parse_json('Sure! {"msg": "use } and { carefully", "n": 2} done')
        assert r.ok
        assert r.value == {"msg": "use } and { carefully", "n": 2}

    def test_escaped_quote_in_string(self):
        r = parse_json('x {"q": "say \\"hi\\" {"} y')
        assert r.ok
        assert r.value == {"q": 'say "hi" {'}

    def test_top_level_array_is_rejected(self):
        r = parse_json("[1, 2, 3]")
        assert not r.ok
        assert "not an object" in r.error or "no JSON object" in r.error

    def test_garbage(self):
        r = parse_json("I cannot help with that.")
        assert not r.ok
        assert r.value is None
        assert r.error == "no JSON object found"

    def test_truncated_json_reports_decode_error(self):
        r = parse_json('```json\n{"a": 1,\n```')
        assert not r.ok
        assert "JSON decode error" in r.error

    def test_fenced_array_then_object(self):
        r = parse_json('```\n[1]\n``` and {"b": 2}')
        assert r.ok
        assert r.value == {"b": 2}


class TestValidate:
    def test_valid(self):
        v = validate({"name": "x", "level": "low", "count": 1}, SIMPLE_SCHEMA)
        assert v.ok
        assert v.messages == []

    def test_errors_carry_keywords_and_paths(self):
        v = validate({"name": "x", "level": "LOW", "count": 11, "extra": 1}, SIMPLE_SCHEMA)
        assert not v.ok
        assert set(v.keywords) == {"enum", "maximum", "additionalProperties"}
        assert any(m.startswith("level:") for m in v.messages)
        assert any(m.startswith("<root>:") for m in v.messages)


class TestNormalize:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("  Priya   Raman ", "priya raman"),
            ("Acme Office Supply Co.", "acme office supply co"),
            ("Tomás", "TOMÁS"),
            ('"quoted"', "quoted"),
        ],
    )
    def test_equivalent(self, a, b):
        assert normalize_str(a) == normalize_str(b)

    def test_not_equivalent(self):
        assert normalize_str("San Francisco") != normalize_str("San Francisco, CA")


class TestValuesMatch:
    def test_numbers_int_float(self):
        assert values_match(5, 5.0)
        assert values_match(263.41, 263.41000000001)
        assert not values_match(263.41, 263.4)

    def test_bool_is_not_number(self):
        assert not values_match(1, True)
        assert values_match(False, False)
        assert not values_match(True, False)

    def test_strings(self):
        assert values_match("High", "high")
        assert not values_match("High", "high", exact_strings=True)

    def test_type_mismatch(self):
        assert not values_match("5", 5)
        assert values_match(None, None)


class TestFlattenAndLeafSchema:
    def test_flatten(self):
        flat = flatten({"a": {"b": [1, {"c": 2}]}, "d": [], "e": {}})
        assert flat == {("a", "b", 0): 1, ("a", "b", 1, "c"): 2, ("d",): [], ("e",): {}}

    def test_leaf_schema_through_union_and_array(self):
        assert leaf_schema(UNION_SCHEMA, ("contact", "number")) == {"type": "string"}
        tag = leaf_schema(UNION_SCHEMA, ("tags", 0))
        assert tag is not None
        assert tag["enum"] == ["a", "b"]
        assert leaf_schema(UNION_SCHEMA, ("missing",)) is None


class TestFieldAccuracy:
    def test_perfect(self):
        exp = {"name": "Alice", "level": "high", "count": 3}
        s = field_accuracy(exp, {"name": " alice.", "level": "high", "count": 3.0}, SIMPLE_SCHEMA)
        assert (s.correct, s.total) == (3, 3)
        assert s.accuracy == 1.0

    def test_enum_is_exact(self):
        exp = {"name": "Alice", "level": "high", "count": 3}
        s = field_accuracy(exp, {"name": "Alice", "level": "High", "count": 3}, SIMPLE_SCHEMA)
        assert (s.correct, s.total) == (2, 3)

    def test_missing_and_wrong(self):
        exp = {"name": "Alice", "level": "high", "count": 3}
        s = field_accuracy(exp, {"name": "Bob"}, SIMPLE_SCHEMA)
        assert (s.correct, s.total) == (0, 3)

    def test_unparsed_output_scores_zero(self):
        exp = {"name": "Alice", "level": "high", "count": 3}
        s = field_accuracy(exp, None, SIMPLE_SCHEMA)
        assert s.accuracy == 0.0
        assert s.total == 3

    def test_hallucinated_extras_are_penalised(self):
        exp = {"tags": ["a"]}
        s = field_accuracy(exp, {"tags": ["a", "b"], "note": "invented"}, UNION_SCHEMA)
        assert (s.correct, s.total) == (1, 3)

    def test_null_and_empty_extras_are_ignored(self):
        exp = {"tags": ["a"]}
        s = field_accuracy(exp, {"tags": ["a"], "note": None, "other": []}, UNION_SCHEMA)
        assert (s.correct, s.total) == (1, 1)

    def test_expected_null_may_be_omitted(self):
        exp = {"note": None, "tags": ["b"]}
        assert field_accuracy(exp, {"tags": ["b"]}, UNION_SCHEMA).accuracy == 1.0
        assert field_accuracy(exp, {"tags": ["b"], "note": None}, UNION_SCHEMA).accuracy == 1.0
        assert field_accuracy(exp, {"tags": ["b"], "note": "x"}, UNION_SCHEMA).accuracy == 0.5

    def test_array_order_matters(self):
        exp = {"tags": ["a", "b"]}
        assert field_accuracy(exp, {"tags": ["b", "a"]}, UNION_SCHEMA).accuracy == 0.0

    def test_empty_expected(self):
        assert field_accuracy({}, {}, UNION_SCHEMA).accuracy == 1.0
