"""Run the benchmark and aggregate raw records into results.json."""

from __future__ import annotations

import json
import platform
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from structbench.client import ModelClient
from structbench.methods import run_method
from structbench.scoring import field_accuracy
from structbench.stats import mean, percentile, wilson_interval
from structbench.tasks import DIFFICULTY_NAMES, Task

Record = dict[str, Any]


def run_one(task: Task, method: str, rep: int, client: ModelClient) -> Record:
    out = run_method(method, task, client)
    score = field_accuracy(task.expected, out.parse.value if out.parse.ok else None, task.schema)
    v = out.validation
    return {
        "task_id": task.id,
        "difficulty": task.difficulty,
        "method": method,
        "rep": rep,
        "model": client.model,
        "attempts": [asdict(a) for a in out.attempts],
        "final_content": out.final_content,
        "parse_ok": out.parse.ok,
        "strict_parse_ok": out.parse.strict_ok,
        "parse_error": out.parse.error,
        "schema_valid": bool(v is not None and v.ok),
        "error_keywords": v.keywords if v is not None else ["parse"],
        "error_messages": (v.messages if v is not None else [out.parse.error])[:10],
        "field_correct": score.correct,
        "field_total": score.total,
        "field_accuracy": score.accuracy,
        "latency_s": out.latency_s,
        "server_latency_s": out.server_latency_s,
        "output_tokens": out.output_tokens,
        "repaired": out.repaired,
        "first_parse_ok": out.first_parse_ok,
        "first_schema_valid": out.first_schema_ok,
    }


def _key(r: Record) -> tuple[str, str, int]:
    return (str(r["task_id"]), str(r["method"]), int(r["rep"]))


def load_raw(path: Path) -> list[Record]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_benchmark(
    tasks: list[Task],
    methods: Iterable[str],
    reps: int,
    client: ModelClient,
    raw_path: Path,
    *,
    resume: bool = True,
    log: Callable[[str], None] = lambda s: print(s, file=sys.stderr, flush=True),
) -> list[Record]:
    """Interleave (and rotate) methods per task so machine-load drift and Ollama's
    prompt-prefix cache affect all methods roughly equally."""
    methods = list(methods)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    existing = [r for r in load_raw(raw_path) if r["model"] == client.model] if resume else []
    done = {_key(r) for r in existing}
    if not resume and raw_path.exists():
        raw_path.unlink()
    total = len(tasks) * len(methods) * reps
    i = len(done)
    with raw_path.open("a") as fh:
        for rep in range(reps):
            for t_idx, task in enumerate(tasks):
                # Rotate method order so no method always runs first (cold prompt cache).
                shift = (t_idx + rep) % len(methods)
                for method in methods[shift:] + methods[:shift]:
                    if (task.id, method, rep) in done:
                        continue
                    t0 = time.perf_counter()
                    rec = run_one(task, method, rep, client)
                    fh.write(json.dumps(rec) + "\n")
                    fh.flush()
                    existing.append(rec)
                    i += 1
                    log(
                        f"[{i}/{total}] rep={rep} {task.id} {method}: "
                        f"parse={rec['parse_ok']} valid={rec['schema_valid']} "
                        f"acc={rec['field_accuracy']:.2f} {time.perf_counter() - t0:.1f}s"
                    )
    wanted = {(t.id, m, r) for t in tasks for m in methods for r in range(reps)}
    return [r for r in existing if _key(r) in wanted]


def _rate_block(recs: list[Record], field: str) -> dict[str, Any]:
    """Rate + two 95% Wilson intervals.

    ``ci`` treats each *task* as one trial (its mean over reps) - the honest
    choice because reps at temperature 0 are highly correlated.
    ``ci_attempts`` treats every attempt as independent (optimistic; for reference).
    """
    k = sum(bool(r[field]) for r in recs)
    n = len(recs)
    by_task: dict[str, list[bool]] = defaultdict(list)
    for r in recs:
        by_task[r["task_id"]].append(bool(r[field]))
    task_means = [sum(v) / len(v) for v in by_task.values()]
    lo, hi = wilson_interval(sum(task_means), len(task_means))
    alo, ahi = wilson_interval(k, n)
    return {
        "k": k,
        "n": n,
        "rate": k / n if n else float("nan"),
        "ci": [lo, hi],
        "ci_attempts": [alo, ahi],
    }


def summarize(recs: list[Record]) -> dict[str, Any]:
    lat = [float(r["latency_s"]) for r in recs]
    slat = [float(r["server_latency_s"]) for r in recs if r.get("server_latency_s") is not None]
    toks = [float(r["output_tokens"]) for r in recs]
    by_task: dict[str, list[str]] = defaultdict(list)
    for r in recs:
        by_task[r["task_id"]].append(r["final_content"])
    multi = [v for v in by_task.values() if len(v) > 1]
    consistent = sum(len(set(v)) == 1 for v in multi)
    valid = [r for r in recs if r["schema_valid"]]
    kw: Counter[str] = Counter()
    for r in recs:
        if not r["schema_valid"]:
            kw.update(set(r["error_keywords"]))
    return {
        "n": len(recs),
        "n_tasks": len(by_task),
        "parse": _rate_block(recs, "parse_ok"),
        "strict_parse": _rate_block(recs, "strict_parse_ok"),
        "schema_valid": _rate_block(recs, "schema_valid"),
        "first_attempt_schema_valid": _rate_block(recs, "first_schema_valid"),
        "field_accuracy": mean([float(r["field_accuracy"]) for r in recs]),
        "field_accuracy_micro": (
            sum(r["field_correct"] for r in recs) / max(1, sum(r["field_total"] for r in recs))
        ),
        "field_accuracy_when_valid": mean([float(r["field_accuracy"]) for r in valid]),
        "latency_p50_s": percentile(lat, 50),
        "latency_p95_s": percentile(lat, 95),
        "server_latency_p50_s": percentile(slat, 50),
        "server_latency_p95_s": percentile(slat, 95),
        "output_tokens_mean": mean(toks),
        "output_tokens_p50": percentile(toks, 50),
        "repair_rate": mean([1.0 if r["repaired"] else 0.0 for r in recs]),
        "consistency": consistent / len(multi) if multi else None,
        "failure_keywords": dict(kw.most_common()),
    }


def aggregate(recs: list[Record], meta: dict[str, Any]) -> dict[str, Any]:
    methods = list(dict.fromkeys(r["method"] for r in recs))
    diffs = sorted({int(r["difficulty"]) for r in recs})
    cells: dict[str, dict[str, Any]] = {}
    for m in methods:
        cells[m] = {"all": summarize([r for r in recs if r["method"] == m])}
        for d in diffs:
            sub = [r for r in recs if r["method"] == m and int(r["difficulty"]) == d]
            if sub:
                cells[m][str(d)] = summarize(sub)
    return {
        "meta": {
            **meta,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "python": platform.python_version(),
            "difficulty_names": {str(k): v for k, v in DIFFICULTY_NAMES.items()},
            "methods": methods,
            "n_records": len(recs),
        },
        "results": cells,
    }


def write_results(results: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, sort_keys=False) + "\n")
