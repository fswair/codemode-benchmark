# Codemode Benchmark

CodeMode benchmark runner for comparing spec-generation and exploration model pairs on the same scenario set.

This benchmark runs each scenario with one or more `(spec_model, exploration_model)` pairs and writes per-scenario artifacts plus aggregate summaries.

## Quick Start

From repository root:

```bash
python -m codemode-benchmark
```

If your environment uses the `py` launcher, this is equivalent:

```bash
py -m codemode-benchmark
```

## What It Benchmarks

Current built-in scenarios:
- `group_by`
- `flatten`
- `parse_cron`
- `eval_rpn`
- `levenshtein`

Each scenario is executed for every configured model pair.

## Model Configuration

Two parallel model lists are used:
- `spec_models`: model used for spec generation
- `explore_models`: model used for exploration snippets

The lists must have the same length. Pairing is index-based:
- `spec_models[i]` is paired with `explore_models[i]`

Default pairs come from code defaults unless overridden by CLI or env vars.

## CLI Usage

### Run all scenarios with defaults

```bash
python -m codemode-benchmark
```

### Run only selected scenarios

```bash
python -m codemode-benchmark --only flatten group_by
```

### Provide model pairs from CLI

```bash
python -m codemode-benchmark \
  --spec-models openrouter:google/gemini-3-flash-preview openrouter:google/gemini-3.1-flash-lite-preview \
  --explore-models openrouter:google/gemini-3-flash-preview openrouter:google/gemini-3.1-flash-lite-preview
```

### Show effective model config and exit

```bash
python -m codemode-benchmark --show-config
```

### Set a custom run directory id

```bash
python -m codemode-benchmark --id sonnet46_vs_flash_preview
```

This writes to `codemode-benchmark/sonnet46_vs_flash_preview` instead of `codemode-benchmark/run_<timestamp>`.

## Replay Existing Runs

### Replay one run directly

```bash
python -m codemode-benchmark --replay codemode-benchmark/run_20260312_181510
```

### Pick a run interactively from a directory

```bash
python -m codemode-benchmark --replay-dir codemode-benchmark
```

## Environment Variables

You can configure model lists from environment variables (comma-separated):

- `BENCHMARK_SPEC_MODELS`
- `BENCHMARK_EXPLORATION_MODELS`

Example:

```bash
export BENCHMARK_SPEC_MODELS="openrouter:anthropic/claude-opus-4.1,openrouter:google/gemini-3-flash-preview"
export BENCHMARK_EXPLORATION_MODELS="openrouter:anthropic/claude-sonnet-4.6,openrouter:google/gemini-3.1-flash-lite-preview"
python -m codemode-benchmark
```

CLI args override env vars.

## Output Structure

A run creates a directory under `codemode-benchmark/`:

```text
codemode-benchmark/
  run_YYYYMMDD_HHMMSS/
    meta.json
    summary.json
    comparison.txt
    <scenario>/
      <model_slug>/
        input.json
        result.json
        spec.yml
        exploration.txt
        summary.txt
```

Key files:
- `meta.json`: run metadata (timestamp, model pairs, scenarios, python version)
- `summary.json`: aggregate metrics per model pair + per-scenario rows
- `comparison.txt`: pretty table output snapshot
- `spec.yml`: generated spec for that scenario/model pair
- `result.json`: machine-readable metrics for that scenario/model pair

## Metrics Tracked

Per scenario/model pair:
- success and coverage
- case count and raises case count
- snippet count, error snippet count, refinement rounds
- runtime (seconds)
- cost (USD)
- token usage (input/output) and request count
- evaluator types observed in generated spec

Aggregate summaries include pass-rate, average coverage/time/cases/snippets/tokens, and total/average cost.

## Notes

- If `rich` is installed, tables are rendered with richer formatting; otherwise plain text fallback is used.
- The runner loads `.env` via `dotenv.load_dotenv()`.
- If spec and exploration model counts do not match, the command exits with an error.
