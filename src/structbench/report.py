"""Render results.json as markdown and splice it into the README."""

from __future__ import annotations

import math
from typing import Any

START = "<!-- RESULTS:START -->"
END = "<!-- RESULTS:END -->"


def _pct(x: float | None) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{100 * x:.1f}%"


def _rate(block: dict[str, Any]) -> str:
    lo, hi = block["ci"]
    return f"{_pct(block['rate'])} [{100 * lo:.0f}-{100 * hi:.0f}]"


def _num(x: float, digits: int = 1) -> str:
    return "n/a" if math.isnan(x) else f"{x:.{digits}f}"


def _row(method: str, level: str, c: dict[str, Any]) -> str:
    cols = [
        method,
        level,
        str(c["n"]),
        _rate(c["parse"]),
        _rate(c["schema_valid"]),
        _pct(c["field_accuracy"]),
        _num(c["latency_p50_s"]),
        _num(c["latency_p95_s"]),
        _num(c["output_tokens_mean"], 0),
        _pct(c["consistency"]),
    ]
    return "| " + " | ".join(cols) + " |"


def render_markdown(results: dict[str, Any]) -> str:
    meta = results["meta"]
    names: dict[str, str] = meta["difficulty_names"]
    cells: dict[str, dict[str, Any]] = results["results"]
    lines: list[str] = []
    lines.append(
        f"Model `{meta['model']}` via Ollama {meta.get('ollama_version', '?')}, "
        f"temperature {meta['temperature']}, seed {meta['seed']}, "
        f"{meta['reps']} rep(s) per task x method, {meta['n_tasks']} tasks, "
        f"{meta['n_records']} scored runs. Generated {meta['generated_at']}."
    )
    lines.append("")
    lines.append("### Overall, by method")
    lines.append("")
    header = (
        "| Method | Level | n | Parse rate [95% CI] | Schema-valid [95% CI] | Field acc. "
        "| p50 s | p95 s | Out tok (mean) | Consistent across reps |"
    )
    sep = "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines += [header, sep]
    for m, per in cells.items():
        lines.append(_row(m, "all", per["all"]))
    lines.append("")
    lines.append("### By method x difficulty")
    lines.append("")
    lines += [header, sep]
    for m, per in cells.items():
        for d, name in names.items():
            if d in per:
                lines.append(_row(m, name, per[d]))
    lines.append("")
    lines.append("### Secondary metrics")
    lines.append("")
    lines.append(
        "| Method | Strict parse (reply is only JSON) | First-attempt schema-valid "
        "| Repair turn used | Field acc. when schema-valid | Output identical to prompt-only "
        "| Decode tok/s (p50) | Top failure keywords |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for m, per in cells.items():
        c = per["all"]
        kws = ", ".join(f"{k} ({v})" for k, v in list(c["failure_keywords"].items())[:4]) or "-"
        lines.append(
            f"| {m} | {_pct(c['strict_parse']['rate'])} "
            f"| {_pct(c['first_attempt_schema_valid']['rate'])} "
            f"| {_pct(c['repair_rate'])} | {_pct(c['field_accuracy_when_valid'])} "
            f"| {_pct(c.get('same_output_as_prompt_only'))} "
            f"| {_num(c.get('decode_tok_per_s_p50', float('nan')))} | {kws} |"
        )
    lines.append("")
    lines.append(
        "CIs are 95% Wilson intervals computed with one trial per *task* (each task "
        "contributes its mean over reps), because reps at temperature 0 are strongly "
        "correlated. Attempt-level intervals are in `results/results.json` as `ci_attempts`. "
        "Latency is wall-clock per run including the repair turn when used. "
        "Decode tok/s is Ollama's eval_count / eval_duration for the first attempt. "
        "Failure keywords count runs (not errors) whose final output failed that JSON Schema "
        "keyword; `parse` = no JSON object recovered."
    )
    return "\n".join(lines)


def splice(readme: str, block: str) -> str:
    if START not in readme or END not in readme:
        raise ValueError("README is missing the RESULTS markers")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n{block}\n{END}{tail}"
