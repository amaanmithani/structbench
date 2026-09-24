from __future__ import annotations

import json
import re

import pytest

from structbench.cli import main
from structbench.client import OllamaClient
from structbench.report import END, START, render_markdown, splice
from structbench.runner import aggregate, load_raw, run_benchmark, summarize
from structbench.tasks import load_tasks
from tests.conftest import FakeClient


def _answer_with_expected(tasks):
    """Fake model that answers each task perfectly, except it uses a code fence
    when no `format` is set (to exercise strict-vs-lenient parsing)."""
    by_text = {t.text: t.expected for t in tasks}

    def reply(messages, fmt):
        user = messages[1]["content"]
        for text, exp in by_text.items():
            if text in user:
                body = json.dumps(exp)
                return body if fmt is not None else f"```json\n{body}\n```"
        raise AssertionError("unknown task")

    return reply


@pytest.fixture
def small_tasks(tasks_path):
    tasks = load_tasks(tasks_path)
    return [tasks[0], tasks[10], tasks[20], tasks[30]]


def test_run_benchmark_resumes_and_rotates(tmp_path, small_tasks):
    raw = tmp_path / "raw.jsonl"
    client = FakeClient(_answer_with_expected(small_tasks))
    methods = ["prompt-only", "json-mode", "schema-constrained", "repair"]
    logs: list[str] = []
    recs = run_benchmark(small_tasks, methods, 2, client, raw, log=logs.append)
    assert len(recs) == 4 * 4 * 2
    assert len(load_raw(raw)) == 32
    assert len(logs) == 32
    # method order is rotated so no method always runs first
    assert client.calls[0][1] is None  # task 0: prompt-only first
    assert client.calls[4][1] == "json"  # task 1: rotated, json-mode first
    n_calls = len(client.calls)
    # resume: nothing re-run
    again = run_benchmark(small_tasks, methods, 2, client, raw, log=logs.append)
    assert len(again) == 32
    assert len(client.calls) == n_calls
    # fresh: raw file discarded and rerun
    fresh = run_benchmark(small_tasks, methods[:1], 1, client, raw, resume=False, log=logs.append)
    assert len(fresh) == 4
    assert len(load_raw(raw)) == 4


def test_record_fields_and_perfect_scores(tmp_path, small_tasks):
    client = FakeClient(_answer_with_expected(small_tasks))
    recs = run_benchmark(
        small_tasks,
        ["prompt-only", "schema-constrained"],
        1,
        client,
        tmp_path / "r.jsonl",
        log=lambda s: None,
    )
    for r in recs:
        assert r["parse_ok"]
        assert r["schema_valid"]
        assert r["field_accuracy"] == 1.0
        assert r["strict_parse_ok"] == (r["method"] != "prompt-only")
        assert r["attempts"][0]["content"] == r["final_content"]


def test_summarize_rates_consistency_and_keywords():
    def rec(task, rep, valid, content, kw=()):
        return {
            "task_id": task,
            "difficulty": 1,
            "method": "m",
            "rep": rep,
            "parse_ok": True,
            "strict_parse_ok": True,
            "schema_valid": valid,
            "first_schema_valid": valid,
            "error_keywords": list(kw),
            "field_accuracy": 1.0 if valid else 0.5,
            "field_correct": 2 if valid else 1,
            "field_total": 2,
            "latency_s": 1.0 + rep,
            "server_latency_s": 0.9,
            "output_tokens": 10,
            "repaired": False,
            "final_content": content,
        }

    recs = [
        rec("a", 0, True, "x"),
        rec("a", 1, True, "x"),
        rec("b", 0, False, "y", ["enum"]),
        rec("b", 1, True, "z"),
    ]
    s = summarize(recs)
    assert s["n"] == 4
    assert s["n_tasks"] == 2
    assert s["schema_valid"]["rate"] == 0.75
    assert s["schema_valid"]["k"] == 3
    lo, hi = s["schema_valid"]["ci"]
    alo, ahi = s["schema_valid"]["ci_attempts"]
    assert (hi - lo) > (ahi - alo)  # task-level CI is the more conservative one
    assert s["consistency"] == 0.5
    assert s["failure_keywords"] == {"enum": 1}
    assert s["field_accuracy_micro"] == pytest.approx(7 / 8)
    assert s["field_accuracy_when_valid"] == 1.0
    assert s["latency_p50_s"] == 1.5
    assert s["server_latency_p50_s"] == pytest.approx(0.9)


def _results(tmp_path, small_tasks):
    client = FakeClient(_answer_with_expected(small_tasks))
    recs = run_benchmark(
        small_tasks,
        ["prompt-only", "json-mode"],
        2,
        client,
        tmp_path / "r.jsonl",
        log=lambda s: None,
    )
    meta = {
        "model": "fake:1b",
        "ollama_version": "x",
        "temperature": 0.0,
        "seed": 42,
        "reps": 2,
        "n_tasks": 4,
    }
    return aggregate(recs, meta)


def test_aggregate_structure(tmp_path, small_tasks):
    res = _results(tmp_path, small_tasks)
    assert res["meta"]["methods"] == ["prompt-only", "json-mode"]
    assert set(res["results"]["json-mode"]) == {"all", "1", "2", "3", "4"}
    assert res["results"]["json-mode"]["all"]["n"] == 8
    # the fake fences prompt-only replies but not json-mode replies
    assert res["results"]["prompt-only"]["all"]["same_output_as_prompt_only"] == 1.0
    assert res["results"]["json-mode"]["all"]["same_output_as_prompt_only"] == 0.0
    assert res["results"]["json-mode"]["all"]["decode_tok_per_s_p50"] > 0


def test_render_markdown_numbers_come_from_json(tmp_path, small_tasks):
    res = _results(tmp_path, small_tasks)
    res["results"]["json-mode"]["all"]["schema_valid"]["rate"] = 0.4321
    md = render_markdown(res)
    assert "43.2%" in md
    assert md.count("| prompt-only |") == 1 + 4 + 1  # overall + 4 levels + secondary
    assert "L4 deep+unions" in md
    assert "fake:1b" in md
    header_cols = md.splitlines()[4].count("|")
    for line in md.splitlines():
        if line.startswith("| prompt-only | L"):
            assert line.count("|") == header_cols
    assert re.search(r"\d+\.\d% \[\d+-\d+\]", md)


def test_splice_replaces_only_between_markers():
    readme = f"intro\n{START}\nold stuff\n{END}\noutro\n"
    out = splice(readme, "NEW")
    assert out == f"intro\n{START}\nNEW\n{END}\noutro\n"
    assert splice(out, "NEWER").count("NEW") == 1
    with pytest.raises(ValueError, match="markers"):
        splice("no markers", "x")


def test_cli_report_and_validate(tmp_path, small_tasks, tasks_path, capsys):
    res = _results(tmp_path, small_tasks)
    rpath = tmp_path / "results.json"
    rpath.write_text(json.dumps(res))
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n{START}\n{END}\n")
    assert main(["report", "--results", str(rpath), "--readme", str(readme)]) == 0
    assert "Schema-valid" in readme.read_text()
    assert main(["report", "--results", str(rpath), "--stdout"]) == 0
    assert "Schema-valid" in capsys.readouterr().out
    assert main(["validate-tasks", "--tasks", str(tasks_path)]) == 0
    bad = tmp_path / "bad.jsonl"
    row = json.loads(tasks_path.read_text().splitlines()[0])
    row["expected"] = {}
    bad.write_text(json.dumps(row) + "\n")
    assert main(["validate-tasks", "--tasks", str(bad)]) == 1


def test_cli_run_with_fake_client(tmp_path, tasks_path, small_tasks):
    from structbench.cli import _parser, cmd_run

    args = _parser().parse_args(
        [
            "run",
            "--tasks",
            str(tasks_path),
            "--limit",
            "2",
            "--reps",
            "1",
            "--methods",
            "json-mode",
            "--raw",
            str(tmp_path / "raw.jsonl"),
            "--out",
            str(tmp_path / "res.json"),
        ]
    )
    tasks = load_tasks(tasks_path)[:2]
    assert cmd_run(args, client=FakeClient(_answer_with_expected(tasks))) == 0
    res = json.loads((tmp_path / "res.json").read_text())
    assert res["meta"]["n_records"] == 2
    assert res["meta"]["ollama_version"] == "fake"


def test_ollama_payload_shape():
    c = OllamaClient("llama3.1:8b", "http://h:1/", seed=7)
    p = c.build_payload([{"role": "user", "content": "hi"}], {"type": "object"})
    assert p["format"] == {"type": "object"}
    assert p["options"]["temperature"] == 0.0
    assert p["options"]["seed"] == 7
    assert p["stream"] is False
    assert "format" not in c.build_payload([], None)
    assert c.build_payload([], "json")["format"] == "json"
    assert c.host == "http://h:1"
