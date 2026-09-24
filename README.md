# structbench

**How reliably does a local LLM produce JSON that matches a schema, and how much does the
method you use to ask for it matter?**

structbench runs 40 hand-written extraction tasks against a model served by
[Ollama](https://ollama.com) with four ways of getting structured output, then scores
every reply for parseability, schema validity and field-level correctness against ground
truth. Every number in the results section below is rendered from `results/results.json`
by `structbench report`. None are typed by hand.

## Methods

All four methods send **the same prompt text**: one system prompt plus a user message
with the instruction, the JSON Schema and the input text (`structbench/methods.py`,
`build_messages`). A test (`test_prompt_text_is_identical_across_methods`) enforces this.
The methods differ only in what they change:

| Method | What changes | Ollama request |
|---|---|---|
| `prompt-only` | nothing: parse whatever comes back | no `format` |
| `json-mode` | the decoder may only emit syntactically valid JSON | `format: "json"` |
| `schema-constrained` | grammar-constrained decoding against the task's JSON Schema | `format: <schema>` |
| `repair` | `prompt-only`, then if the reply does not parse or fails validation, the validator's errors go back as one follow-up turn and the second reply is final | no `format`, max 2 calls |

Settings for every call: `temperature 0`, `seed 42`, `num_ctx 4096`, `num_predict 1024`.
Methods are interleaved per task, and their order rotates from task to task. That way
machine-load drift and Ollama's prompt-prefix cache don't consistently favour one method.

Every method's reply goes through the same parser. It tries the whole reply, then a
` ```json ` fence, then the first balanced `{...}` span. The *strict parse* column also
reports how often the reply was nothing but JSON.

## Task design

`data/tasks.jsonl` has 40 tasks, 10 per difficulty level. The inputs are short, realistic
texts (email signatures, invoices, event notices, recipes, job posts, order
confirmations, bug reports, product reviews, flight bookings, incident reports, payment
receipts, conference schedules). I wrote them all by hand, along with their ground-truth
outputs. `scripts/build_tasks.py` generates the file.

| Level | Schema shape | Example domains |
|---|---|---|
| L1 flat | a single object with scalar fields | contact, invoice summary, event, book |
| L2 nested+arrays | nested objects, arrays of objects | recipe, job post, order |
| L3 enums+ranges | enums, all fields required, numeric `minimum`/`maximum`, `pattern`, enums inside arrays | bug triage, product review, flight booking |
| L4 deep+unions | 3+ levels deep, `anyOf` unions (discriminated by `const`), nullable fields, optional fields | incident report, payment record, conference schedule |

The task suite is audited by tests (`tests/test_tasks.py`). Every expected output
validates against its schema, and each task's difficulty label must match a structural
classifier (L4 requires a union, an optional field and nesting depth ≥ 2, L3 requires
enums and numeric ranges, and so on). Every object sets `additionalProperties: false`,
so extra keys are schema violations.

### Metrics

Metrics are computed per method × difficulty and overall:

- **Parse rate**: a JSON object was recovered from the reply.
- **Schema-valid rate**: the recovered object passes JSON Schema (Draft 2020-12) validation.
- **Field accuracy**: leaf-level agreement with ground truth. Enum fields must match
  exactly, numbers match numerically, and other strings match after case, whitespace and
  edge-punctuation normalisation. Array items are compared by position. The denominator
  is the ground-truth leaves plus any extra non-null leaves the model invented, so
  hallucinated array items and optional fields are penalised. Replies that don't parse
  score 0.
- **Latency** p50/p95: wall-clock seconds per run, including the repair turn when one is
  used. **Output tokens**: Ollama's `eval_count`, summed over turns.
- **Consistency**: the share of tasks where every repetition produced byte-identical output.
- **95% Wilson intervals** on the rates. Each task counts as one trial (its mean over
  repetitions). At temperature 0 the repetitions are close to copies of each other, so
  treating every attempt as independent would overstate precision. `results.json` also
  stores the attempt-level interval (`ci_attempts`) for reference.

## Results

<!-- RESULTS:START -->
(run `structbench run` then `structbench report`)
<!-- RESULTS:END -->

## Caveats

- **One small local model.** Every number comes from `llama3.1:8b` (Q4_K_M, as Ollama
  ships it) on one Apple M1 Pro laptop. These results do not transfer to larger
  models, to other model families, or to hosted APIs whose structured-output features
  are implemented differently.
- **40 tasks is small.** The intervals are wide, so read differences of a few points as
  noise. Repetitions at temperature 0 with a fixed seed add almost no new information,
  and the "consistency" column shows that directly.
- **I wrote the tasks and the ground truth myself.** Some fields involve judgement, such
  as the unit for "1 lemon", whether an item is a "tool", or a sentiment label. These
  judgement calls weigh equally on every method, so they lower absolute field accuracy
  but shouldn't change the comparison between methods.
- **Latency was measured on a shared, busy machine.** Other processes (including other
  Ollama clients) were running during the benchmark. Use absolute seconds only as a
  rough guide. Relative comparisons are fairer, because methods were interleaved and
  rotated per task. Server-side timings (`server_latency_*`) are also in `results.json`.
- **Grammar-constrained decoding depends on the Ollama version.** How much of JSON Schema
  gets enforced (for example `minimum`/`maximum` on numbers, or `pattern`) depends on
  Ollama and llama.cpp's schema-to-grammar conversion. The Ollama version used is
  recorded in `results.json`.
- **The repair loop gets exactly one retry**, fed back as plain text, without JSON mode or
  constrained decoding. Other repair designs (more retries, or repair combined with JSON
  mode) could do better.

## Rerun it

```bash
uv sync
ollama pull llama3.1:8b          # if you don't have it
uv run structbench validate-tasks
uv run structbench run --model llama3.1:8b --reps 3    # writes results/raw.jsonl + results/results.json (resumable)
uv run structbench report                              # re-renders the table above from results.json
```

Useful flags: `--methods prompt-only schema-constrained`, `--limit 8` for a quick
check, and `--fresh` to discard `raw.jsonl` instead of resuming from it. Every model
reply, including both turns of a repair, is stored verbatim in `results/raw.jsonl`.

Development gates (CI runs the same ones, and never calls Ollama):

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

`pytest` enforces coverage ≥ 75% (`--cov-fail-under=75`).
