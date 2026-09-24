"""Command-line entry point: ``structbench run | report | validate-tasks``."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from structbench.client import ModelClient, OllamaClient
from structbench.methods import METHODS
from structbench.report import render_markdown, splice
from structbench.runner import aggregate, run_benchmark, write_results
from structbench.tasks import load_tasks, validate_task


def _ollama_version(host: str) -> str:  # pragma: no cover - network
    try:
        with urllib.request.urlopen(f"{host}/api/version", timeout=5) as r:
            return str(json.loads(r.read()).get("version", "?"))
    except OSError:
        return "?"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="structbench", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run the benchmark against Ollama")
    run.add_argument("--model", default="llama3.1:8b")
    run.add_argument("--methods", nargs="+", default=list(METHODS), choices=list(METHODS))
    run.add_argument("--reps", type=int, default=3)
    run.add_argument("--tasks", type=Path, default=Path("data/tasks.jsonl"))
    run.add_argument("--limit", type=int, default=None, help="only the first N tasks")
    run.add_argument("--host", default="http://localhost:11434")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--raw", type=Path, default=Path("results/raw.jsonl"))
    run.add_argument("--out", type=Path, default=Path("results/results.json"))
    run.add_argument("--fresh", action="store_true", help="discard raw.jsonl instead of resuming")

    rep = sub.add_parser("report", help="render results.json into README.md")
    rep.add_argument("--results", type=Path, default=Path("results/results.json"))
    rep.add_argument("--readme", type=Path, default=Path("README.md"))
    rep.add_argument("--stdout", action="store_true", help="print instead of editing README")

    val = sub.add_parser("validate-tasks", help="check every task's expected output")
    val.add_argument("--tasks", type=Path, default=Path("data/tasks.jsonl"))
    return p


def cmd_run(args: argparse.Namespace, client: ModelClient | None = None) -> int:
    tasks = load_tasks(args.tasks)[: args.limit]
    if client is None:  # pragma: no cover - real network client
        client = OllamaClient(args.model, args.host, temperature=args.temperature, seed=args.seed)
        version = _ollama_version(args.host)
    else:
        version = "fake"
    recs = run_benchmark(tasks, args.methods, args.reps, client, args.raw, resume=not args.fresh)
    meta = {
        "model": args.model,
        "ollama_version": version,
        "temperature": args.temperature,
        "seed": args.seed,
        "reps": args.reps,
        "n_tasks": len(tasks),
    }
    write_results(aggregate(recs, meta), args.out)
    print(f"wrote {args.out} ({len(recs)} runs)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    results = json.loads(args.results.read_text())
    block = render_markdown(results)
    if args.stdout:
        print(block)
        return 0
    args.readme.write_text(splice(args.readme.read_text(), block))
    print(f"updated {args.readme}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    problems = [p for t in load_tasks(args.tasks) for p in validate_task(t)]
    for p in problems:
        print(p, file=sys.stderr)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "report":
        return cmd_report(args)
    return cmd_validate(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
