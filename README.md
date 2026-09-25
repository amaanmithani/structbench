# structbench

> **Credits.** Built by Amaan Mithani with Claude (Anthropic) as the AI coding assistant.

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
Model `llama3.1:8b` via Ollama 0.24.0, temperature 0.0, seed 42, 2 rep(s) per task x method, 40 tasks, 320 scored runs. Generated 2026-09-24T10:45:03+00:00.

### Headline numbers (auto-generated)

- Schema-valid rate on L4 deep+unions: prompt-only 70.0%, json-mode 70.0%, schema-constrained 100.0%, repair 90.0%.
- Schema-valid rate, all levels: prompt-only 92.5%, json-mode 92.5%, schema-constrained 100.0%, repair 97.5%.
- Field accuracy ranges only from 94.3% to 94.6% across methods.
- json-mode: final output byte-identical to prompt-only in 100.0% of runs.
- schema-constrained: final output byte-identical to prompt-only in 92.5% of runs.
- repair: final output byte-identical to prompt-only in 95.0% of runs.
- repair: follow-up turn used in 7.5% of runs; schema-valid 92.5% after the first turn, 97.5% after repair.
- Lowest cross-rep consistency of any method: 100.0%.

### Overall, by method

| Method | Level | n | Parse rate [95% CI] | Schema-valid [95% CI] | Field acc. | p50 s | p95 s | Out tok (mean) | Consistent across reps |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| prompt-only | all | 80 | 100.0% [91-100] | 92.5% [80-97] | 94.6% | 44.4 | 115.5 | 117 | 100.0% |
| json-mode | all | 80 | 100.0% [91-100] | 92.5% [80-97] | 94.6% | 89.1 | 184.2 | 117 | 100.0% |
| schema-constrained | all | 80 | 100.0% [91-100] | 100.0% [91-100] | 94.4% | 74.0 | 206.7 | 117 | 100.0% |
| repair | all | 80 | 100.0% [91-100] | 97.5% [87-100] | 94.3% | 46.2 | 141.4 | 129 | 100.0% |

### By method x difficulty

| Method | Level | n | Parse rate [95% CI] | Schema-valid [95% CI] | Field acc. | p50 s | p95 s | Out tok (mean) | Consistent across reps |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| prompt-only | L1 flat | 20 | 100.0% [72-100] | 100.0% [72-100] | 95.0% | 25.8 | 140.1 | 60 | 100.0% |
| prompt-only | L2 nested+arrays | 20 | 100.0% [72-100] | 100.0% [72-100] | 96.2% | 46.2 | 72.7 | 148 | 100.0% |
| prompt-only | L3 enums+ranges | 20 | 100.0% [72-100] | 100.0% [72-100] | 91.3% | 33.7 | 58.0 | 95 | 100.0% |
| prompt-only | L4 deep+unions | 20 | 100.0% [72-100] | 70.0% [40-89] | 95.7% | 65.7 | 115.5 | 166 | 100.0% |
| json-mode | L1 flat | 20 | 100.0% [72-100] | 100.0% [72-100] | 95.0% | 78.2 | 293.1 | 60 | 100.0% |
| json-mode | L2 nested+arrays | 20 | 100.0% [72-100] | 100.0% [72-100] | 96.2% | 82.2 | 139.4 | 148 | 100.0% |
| json-mode | L3 enums+ranges | 20 | 100.0% [72-100] | 100.0% [72-100] | 91.3% | 58.0 | 125.6 | 95 | 100.0% |
| json-mode | L4 deep+unions | 20 | 100.0% [72-100] | 70.0% [40-89] | 95.7% | 110.0 | 210.3 | 166 | 100.0% |
| schema-constrained | L1 flat | 20 | 100.0% [72-100] | 100.0% [72-100] | 95.0% | 53.1 | 306.6 | 60 | 100.0% |
| schema-constrained | L2 nested+arrays | 20 | 100.0% [72-100] | 100.0% [72-100] | 96.2% | 81.4 | 118.8 | 148 | 100.0% |
| schema-constrained | L3 enums+ranges | 20 | 100.0% [72-100] | 100.0% [72-100] | 91.3% | 51.9 | 92.5 | 95 | 100.0% |
| schema-constrained | L4 deep+unions | 20 | 100.0% [72-100] | 100.0% [72-100] | 95.2% | 100.7 | 176.2 | 167 | 100.0% |
| repair | L1 flat | 20 | 100.0% [72-100] | 100.0% [72-100] | 95.0% | 26.1 | 161.5 | 60 | 100.0% |
| repair | L2 nested+arrays | 20 | 100.0% [72-100] | 100.0% [72-100] | 96.2% | 51.0 | 79.8 | 148 | 100.0% |
| repair | L3 enums+ranges | 20 | 100.0% [72-100] | 100.0% [72-100] | 91.3% | 32.8 | 53.0 | 95 | 100.0% |
| repair | L4 deep+unions | 20 | 100.0% [72-100] | 90.0% [60-98] | 94.8% | 91.2 | 146.0 | 214 | 100.0% |

### Secondary metrics

| Method | Strict parse (reply is only JSON) | First-attempt schema-valid | Repair turn used | Field acc. when schema-valid | Output identical to prompt-only | Decode tok/s (p50) | Top failure keywords |
|---|---:|---:|---:|---:|---:|---:|---|
| prompt-only | 100.0% | 92.5% | 0.0% | 94.7% | 100.0% | 3.3 | type (4), anyOf (2) |
| json-mode | 100.0% | 92.5% | 0.0% | 94.7% | 100.0% | 5.9 | type (4), anyOf (2) |
| schema-constrained | 100.0% | 100.0% | 0.0% | 94.4% | 92.5% | 6.0 | - |
| repair | 100.0% | 92.5% | 7.5% | 94.5% | 95.0% | 3.4 | type (2) |

CIs are 95% Wilson intervals computed with one trial per *task* (each task contributes its mean over reps), because reps at temperature 0 are strongly correlated. Attempt-level intervals are in `results/results.json` as `ci_attempts`. Latency is wall-clock per run including the repair turn when used. Decode tok/s is Ollama's eval_count / eval_duration for the first attempt. Failure keywords count runs (not errors) whose final output failed that JSON Schema keyword; `parse` = no JSON object recovered.
<!-- RESULTS:END -->

### What the numbers say

All numbers in this section come from the tables above.

- **Getting JSON that parses was never the hard part.** For this model and this prompt,
  every method produced a parseable object on every run, and the replies contained only
  JSON (no prose, no code fences). `json-mode` changed nothing here: its output was
  byte-identical to `prompt-only` in every run, and it failed the same tasks in the same
  way.
- **Schema validity is where the methods differ, and only on the hardest schemas.** L1
  to L3 were schema-valid under every method. On L4 (unions, nullable and optional
  fields), the unconstrained methods failed in one recurring way: the model wrote
  `null` for fields it should have left out or filled in (`details`, `eta_hours`,
  `room`, and on one task the required `slot`), which breaks the non-nullable type or
  the `anyOf` branch. Grammar-constrained decoding
  removed all of these failures. The repair turn fixed some of them, and on one task the
  model repeated the same mistake after seeing the error.
- **Validity is not correctness.** Field accuracy is almost identical across methods.
  The remaining errors are about content, not format: a date left as `17.06.2025`
  instead of ISO, a vendor name with the city appended, an order id with a leading `#`,
  a missing unit. Constrained decoding guarantees the shape. It does not guarantee the
  value. On the L4 tasks where the constraint changed the output, it helped once (it
  recovered a `slot` the unconstrained model had nulled) and hurt twice. With `null`
  unavailable, the model filled the field instead: `"details": ""`, and `"eta_hours": 0`
  for an incident whose text says "no ETA yet". That last one is a valid-looking but
  false value, and it is why schema-constrained's field accuracy comes out marginally
  *lower* even though it is the only method with 100% validity. (See `raw.jsonl` for the
  outputs.)
- **Repetitions at temperature 0 and a fixed seed were deterministic.** Every method
  produced byte-identical output on both reps (the consistency column). This is why the
  run stopped at 2 reps instead of 3, and why the confidence intervals treat tasks, not
  attempts, as the unit.
- **Latency: treat it with suspicion.** `format`-constrained requests (`json-mode`,
  `schema-constrained`) show higher median wall-clock latency but higher decode
  throughput than unconstrained requests. So the extra time is spent outside token
  decoding (prompt processing, sampler or grammar setup, or scheduler wait on a busy
  shared GPU). This benchmark does not record enough to say which. See the caveats.

## Caveats

- **One small local model.** Every number comes from `llama3.1:8b` (Q4_K_M, as Ollama
  ships it) on one Apple M1 Pro laptop. These results do not transfer to larger
  models, to other model families, or to hosted APIs whose structured-output features
  are implemented differently.
- **40 tasks is small.** The intervals are wide, so read differences of a few points as
  noise. For example, the L4 intervals for `prompt-only` and `schema-constrained`
  overlap.
- **2 reps instead of the planned 3.** The machine was shared with other heavy jobs
  during the run (load average often 30 to 160, decode speed around 3 to 6 tok/s instead
  of the usual ~20), and 2 reps of 160 runs took about 4.5 hours. Both reps came out
  byte-identical for every method, so a third rep would almost certainly have added no
  information.
- **I wrote the tasks and the ground truth myself.** Some fields involve judgement, such
  as the unit for "1 lemon", whether an item is a "tool", or a sentiment label. These
  judgement calls weigh equally on every method, so they lower absolute field accuracy
  but shouldn't change the comparison between methods.
- **Latency was measured on a shared, busy machine.** Other processes (including other
  Ollama clients) were running during the benchmark, and load changed over the hours of
  the run. One request timed out after 600 s partway through; the client now retries
  transport errors (with a 30 min timeout), and the run resumed from `raw.jsonl`.
  Transport failures are infrastructure errors, never scored as model failures. Use absolute seconds only as a
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
