#!/usr/bin/env python3.11
"""CodeModeGenerator — Model comparison benchmark.

Runs the same scenarios through CodeModeGenerator with two different models
and records results in the same VCR-style structure as benchmark_v1.

Each model gets its own subdirectory under the run directory:
    codemode_benchmark/run_<timestamp>/
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

Usage:
    python3.11 codemode_benchmark/run_benchmark.py
    python3.11 codemode_benchmark/run_benchmark.py --only flatten group_by
    python3.11 codemode_benchmark/run_benchmark.py --spec-models gemini-3-flash gemini-3.1-flash --explore-models gemini-3-flash gemini-3.1-flash
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import dotenv
import yaml

from vowel.codemode import CodeModeGenerator, CodeModeResult
from vowel.runner import Function, RunEvals

# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────

dotenv.load_dotenv()

BENCHMARK_DIR = Path(__file__).parent

DEFAULT_SPEC_MODELS = [
    "openrouter:google/gemini-3-flash-preview",
    "openrouter:google/gemini-3.1-flash-lite-preview",
]
DEFAULT_EXPLORE_MODELS = [
    "openrouter:google/gemini-3-flash-preview",
    "openrouter:google/gemini-3.1-flash-lite-preview",
]


# Model naming helpers
def _model_short(model: str) -> str:
    return model.split("/")[-1]


def _combo_name(spec: str, exp: str) -> str:
    s_short = _model_short(spec)
    e_short = _model_short(exp)
    return f"{s_short} | {e_short}" if s_short != e_short else s_short


def _combo_slug(spec: str, exp: str) -> str:
    s_slug = _model_short(spec).replace(":", "_").replace("-", "_")
    e_slug = _model_short(exp).replace(":", "_").replace("-", "_")
    return f"{s_slug}_{e_slug}" if s_slug != e_slug else s_slug


def _normalize_models_to_pairs(models_data: dict | list | None) -> list[tuple[str, str]]:
    """Normalize model metadata to ordered (spec, exploration) pairs."""
    if not models_data:
        return []

    if isinstance(models_data, list):
        pairs: list[tuple[str, str]] = []
        for item in models_data:
            if not isinstance(item, str):
                continue
            if " | " in item:
                spec, exploration = item.split(" | ", 1)
            else:
                spec, exploration = item, item
            pairs.append((spec, exploration))
        return pairs

    if isinstance(models_data, dict):
        case_keys = sorted(
            [k for k in models_data if isinstance(k, str) and k.startswith("case_")],
            key=lambda k: int(k.split("_", 1)[1]) if k.split("_", 1)[1].isdigit() else 9999,
        )
        pairs = []
        for case_key in case_keys:
            case_data = models_data.get(case_key)
            if isinstance(case_data, dict):
                pairs.append((case_data.get("spec", ""), case_data.get("exploration", "")))
        return pairs

    return []


# ─────────────────────────────────────────────────────────────────────
# Scenario definitions (reference implementations included)
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Scenario:
    name: str
    description: str
    difficulty: str
    code: str

    def to_function(self) -> Function:
        """
        Convert scenario to vowel.runner.Function
        """
        return Function(name=self.name, description=self.description, code=self.code)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="group_by",
        difficulty="intermediate",
        description="Group a list of dicts by the value of a given key. Dicts missing the key go under the None group.",
        code='''
def group_by(items: list[dict], key: str) -> dict:
    """Group a list of dicts by the value of a given key.

    Dicts missing the key go under the None group.
    """
    result: dict = {}
    for item in items:
        group_key = item.get(key)
        if group_key not in result:
            result[group_key] = []
        result[group_key].append(item)
    return result
''',
    ),
    Scenario(
        name="flatten",
        difficulty="intermediate",
        description="Recursively flatten an arbitrarily nested list. Non-list elements kept as-is. Raise TypeError if input is not a list.",
        code='''
def flatten(lst: list) -> list:
    """Recursively flatten an arbitrarily nested list."""
    if not isinstance(lst, list):
        raise TypeError(f"Expected list, got {type(lst).__name__}")
    result = []
    for item in lst:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result
''',
    ),
    Scenario(
        name="parse_cron",
        difficulty="advanced",
        description="Parse a 5-field cron expression into a dict of sorted int lists. Supports wildcards, ranges, steps, commas. Raises ValueError for invalid expressions.",
        code='''
def parse_cron(expression: str) -> dict:
    """Parse a 5-field cron expression into a dict of sorted int lists.

    Fields: minute(0-59) hour(0-23) day_of_month(1-31) month(1-12) day_of_week(0-6).
    Supports: single values, ranges (1-5), steps (*/15, 1-10/2), commas (1,3,5), wildcards (*).
    Raises ValueError for invalid expressions.
    """
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    names = ["minute", "hour", "day_of_month", "month", "day_of_week"]
    ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    result = {}

    for field, name, (lo, hi) in zip(fields, names, ranges):
        values = set()
        for part in field.split(","):
            if "/" in part:
                range_part, step_str = part.split("/", 1)
                step = int(step_str)
                if step <= 0:
                    raise ValueError(f"Step must be positive, got {step}")
                if range_part == "*":
                    start, end = lo, hi
                elif "-" in range_part:
                    start, end = map(int, range_part.split("-", 1))
                else:
                    start, end = int(range_part), hi
                if start < lo or end > hi:
                    raise ValueError(f"{name}: {start}-{end} out of range {lo}-{hi}")
                values.update(range(start, end + 1, step))
            elif part == "*":
                values.update(range(lo, hi + 1))
            elif "-" in part:
                start, end = map(int, part.split("-", 1))
                if start < lo or end > hi or start > end:
                    raise ValueError(f"{name}: invalid range {start}-{end} (valid: {lo}-{hi})")
                values.update(range(start, end + 1))
            else:
                val = int(part)
                if val < lo or val > hi:
                    raise ValueError(f"{name}: {val} out of range {lo}-{hi}")
                values.add(val)
        result[name] = sorted(values)

    return result
''',
    ),
    Scenario(
        name="eval_rpn",
        difficulty="advanced",
        description="Evaluate a Reverse Polish Notation expression. Supports +, -, *, /. Division truncates toward zero. Raises ValueError for invalid expressions.",
        code='''
def eval_rpn(tokens: list[str]) -> int:
    """Evaluate a Reverse Polish Notation expression.

    Supports +, -, *, /. Division truncates toward zero.
    Raises ValueError for invalid expressions.
    """
    if not tokens:
        raise ValueError("Empty expression")

    stack: list[int] = []
    operators = {"+", "-", "*", "/"}

    for token in tokens:
        if token in operators:
            if len(stack) < 2:
                raise ValueError(f"Not enough operands for \'{token}\'")
            b, a = stack.pop(), stack.pop()
            if token == "+":
                stack.append(a + b)
            elif token == "-":
                stack.append(a - b)
            elif token == "*":
                stack.append(a * b)
            elif token == "/":
                if b == 0:
                    raise ZeroDivisionError("Division by zero")
                stack.append(int(a / b))
        else:
            try:
                stack.append(int(token))
            except ValueError:
                raise ValueError(f"Invalid token: \'{token}\'")

    if len(stack) != 1:
        raise ValueError(f"Invalid expression: {len(stack)} values remaining on stack")

    return stack[0]
''',
    ),
    Scenario(
        name="levenshtein",
        difficulty="advanced",
        description="Calculate the Levenshtein edit distance between two strings using dynamic programming. Raise TypeError for non-string inputs.",
        code='''
def levenshtein(s: str, t: str) -> int:
    """Calculate Levenshtein edit distance between two strings.

    Returns the minimum number of single-character edits (insert, delete,
    substitute) to transform s into t. Raises TypeError for non-string inputs.
    """
    if not isinstance(s, str) or not isinstance(t, str):
        raise TypeError("Both arguments must be strings")
    m, n = len(s), len(t)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if s[i - 1] == t[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]
''',
    ),
]


# ─────────────────────────────────────────────────────────────────────
# Result model
# ─────────────────────────────────────────────────────────────────────


@dataclass
class BenchmarkResult:
    scenario_name: str
    spec_model: str
    exploration_model: str
    model_slug: str
    success: bool = False
    coverage: float = 0.0
    total_time_s: float = 0.0
    case_count: int = 0
    raises_count: int = 0
    snippet_count: int = 0
    error_snippet_count: int = 0
    refinement_rounds: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0
    price_sources: list[str] = field(default_factory=list)
    function_count: int = 1
    evaluator_types: list[str] = field(default_factory=list)
    error: str | None = None
    yaml_spec: str = ""
    exploration_results: list = field(default_factory=list)

    @property
    def passed(self) -> int:
        return int(self.coverage * self.case_count) if self.success else 0

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "spec_model": self.spec_model,
            "exploration_model": self.exploration_model,
            "model_slug": self.model_slug,
            "success": self.success,
            "coverage": f"{self.coverage * 100:.1f}%",
            "time_s": round(self.total_time_s, 2),
            "cases": self.case_count,
            "raises_cases": self.raises_count,
            "snippets": self.snippet_count,
            "error_snippets": self.error_snippet_count,
            "refinements": self.refinement_rounds,
            "cost_usd": round(self.cost_usd, 8),
            "cost_cents": round(self.cost_usd * 100, 4),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "requests": self.request_count,
            "price_sources": self.price_sources,
            "function_count": self.function_count,
            "cost_per_function_usd": round(
                self.cost_usd / max(self.function_count, 1),
                8,
            ),
            "evaluator_types": self.evaluator_types,
            "error": self.error,
        }


def _extract_cost_stats(
    gen: CodeModeGenerator, run_id: str
) -> tuple[float, int, int, int, list[str]]:
    """Read run-level cost stats from generator's CostManager store."""
    cm = getattr(gen, "cost_manager", None)
    if cm is None:
        return 0.0, 0, 0, 0, []

    records = getattr(cm, "_cost_records", {})
    generations = records.get("generations", {}) if isinstance(records, dict) else {}
    generation = generations.get(cm.generation_id, {}) if isinstance(generations, dict) else {}
    runs = generation.get("runs", {}) if isinstance(generation, dict) else {}
    run = runs.get(run_id, {}) if isinstance(runs, dict) else {}

    totals = run.get("totals", {}) if isinstance(run, dict) else {}
    usd = float(totals.get("usd", 0.0) or 0.0)
    input_tokens = int(totals.get("input_tokens", 0) or 0)
    output_tokens = int(totals.get("output_tokens", 0) or 0)
    requests = int(totals.get("requests", 0) or 0)

    sources: set[str] = set()
    steps = run.get("steps", {}) if isinstance(run, dict) else {}
    if isinstance(steps, dict):
        for step_data in steps.values():
            usages = step_data.get("usages", []) if isinstance(step_data, dict) else []
            for item in usages:
                if isinstance(item, dict):
                    src = item.get("price_source")
                    if isinstance(src, str) and src:
                        sources.add(src)

    return usd, input_tokens, output_tokens, requests, sorted(sources)


# ─────────────────────────────────────────────────────────────────────
# VCR helpers
# ─────────────────────────────────────────────────────────────────────


def _init_run_dir(
    model_pairs: list[tuple[str, str]], scenarios: list[str], run_id: str | None = None
) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dir_name = run_id.replace(" ", "_").strip().lower() if run_id else f"run_{ts}"

    run_dir = BENCHMARK_DIR / dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    models_dict = {}
    for i, (s, e) in enumerate(model_pairs, 1):
        models_dict[f"case_{i}"] = {"spec": s, "exploration": e}

    meta = {
        "id": dir_name,
        "timestamp": ts,
        "iso": datetime.now(UTC).isoformat(),
        "models": models_dict,
        "scenarios": scenarios,
        "python": sys.version,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return run_dir


def _record_result(run_dir: Path, br: BenchmarkResult) -> None:
    out = run_dir / br.scenario_name / br.model_slug
    out.mkdir(parents=True, exist_ok=True)

    # input.json
    (out / "input.json").write_text(
        json.dumps(
            {
                "scenario": br.scenario_name,
                "spec_model": br.spec_model,
                "exploration_model": br.exploration_model,
            },
            indent=2,
        )
    )

    # result.json
    (out / "result.json").write_text(json.dumps(br.to_dict(), indent=2))

    # spec.yml
    if br.yaml_spec:
        (out / "spec.yml").write_text(br.yaml_spec)

    # exploration.txt
    if br.exploration_results:
        lines = []
        for i, snip in enumerate(br.exploration_results, 1):
            lines.append(
                f"--- Snippet {i} [{('error' if not snip.success else 'normal')}]: {snip.description} ---"
            )
            lines.append(f"Code: {snip.code.strip()}")
            if snip.success:
                lines.append(f"Output: {snip.output!r}")
            else:
                lines.append(f"RAISED {snip.error_type}: {snip.error}")
            lines.append("")
        (out / "exploration.txt").write_text("\n".join(lines))

    # summary.txt
    lines = [
        f"Scenario : {br.scenario_name}",
        f"Spec Model : {br.spec_model}",
        f"Expl Model : {br.exploration_model}",
        f"Success  : {br.success}",
        f"Coverage : {br.coverage * 100:.1f}%",
        f"Cases    : {br.case_count}  (raises={br.raises_count})",
        f"Snippets : {br.snippet_count}  (error_snippets={br.error_snippet_count})",
        f"Refines  : {br.refinement_rounds}",
        f"Cost USD : {br.cost_usd:.8f}",
        f"Cost/Fn  : {br.cost_usd / max(br.function_count, 1):.8f}",
        f"Tokens   : in={br.input_tokens} out={br.output_tokens} req={br.request_count}",
        f"Pricing  : {', '.join(br.price_sources) if br.price_sources else '-'}",
        f"Time     : {br.total_time_s:.1f}s",
        f"Evals    : {', '.join(br.evaluator_types) or '-'}",
    ]
    if br.error:
        lines.append(f"Error    : {br.error}")
    (out / "summary.txt").write_text("\n".join(lines))


def _record_comparison(
    run_dir: Path, results: list[BenchmarkResult], model_pairs: list[tuple[str, str]]
) -> None:
    try:
        from rich.console import Console

        buf = io.StringIO()
        console = Console(file=buf, force_terminal=False, width=160)
        _print_comparison_to(console, results, model_pairs)
        (run_dir / "comparison.txt").write_text(buf.getvalue())
    except ImportError:
        pass

    # summary.json — keyed by model slug
    slugs = [_combo_slug(s, e) for s, e in model_pairs]
    per_model: dict[str, dict] = {}
    for slug in slugs:
        model_results = [r for r in results if r.model_slug == slug]

        # Determine model info
        spec_m = next((r.spec_model for r in model_results), slug)
        exp_m = next((r.exploration_model for r in model_results), slug)

        per_model[slug] = {
            "spec_model": spec_m,
            "exploration_model": exp_m,
            "pass_rate": f"{sum(1 for r in model_results if r.success)}/{len(model_results)}",
            "function_count": len(model_results),
            "avg_coverage": round(
                sum(r.coverage for r in model_results) / max(len(model_results), 1), 4
            ),
            "avg_time_s": round(
                sum(r.total_time_s for r in model_results) / max(len(model_results), 1), 2
            ),
            "total_cost_usd": round(sum(r.cost_usd for r in model_results), 8),
            "avg_cost_usd": round(
                sum(r.cost_usd for r in model_results) / max(len(model_results), 1), 8
            ),
            "cost_per_function_usd": round(
                sum(r.cost_usd for r in model_results) / max(len(model_results), 1), 8
            ),
            "avg_input_tokens": round(
                sum(r.input_tokens for r in model_results) / max(len(model_results), 1), 1
            ),
            "avg_output_tokens": round(
                sum(r.output_tokens for r in model_results) / max(len(model_results), 1), 1
            ),
            "avg_cases": round(
                sum(r.case_count for r in model_results) / max(len(model_results), 1), 1
            ),
            "avg_raises": round(
                sum(r.raises_count for r in model_results) / max(len(model_results), 1), 1
            ),
            "avg_snippets": round(
                sum(r.snippet_count for r in model_results) / max(len(model_results), 1), 1
            ),
        }

    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "per_model": per_model,
                "per_scenario": [r.to_dict() for r in results],
            },
            indent=2,
        )
    )


# ─────────────────────────────────────────────────────────────────────
# Spec stats helpers
# ─────────────────────────────────────────────────────────────────────


def _extract_spec_stats(yaml_spec: str) -> tuple[int, int, list[str]]:
    """Returns (case_count, raises_count, evaluator_types)."""
    try:
        data = yaml.safe_load(yaml_spec)
        if not isinstance(data, dict):
            return 0, 0, []
        eval_block = next(iter(data.values()))
        if not isinstance(eval_block, dict):
            return 0, 0, []

        dataset = eval_block.get("dataset", [])
        cases = dataset if isinstance(dataset, list) else []
        case_count = len(cases)
        raises_count = sum(
            1
            for c in cases
            if isinstance(c, dict) and ("raises" in c.get("case", {}) or "raises" in c)
        )

        eval_types: set[str] = set()
        for c in cases:
            case_data = c.get("case", c) if isinstance(c, dict) else {}
            for key in ("expected", "raises", "type", "assertion", "contains", "pattern"):
                if key in case_data:
                    eval_types.add(key)
        global_evals = eval_block.get("evals", {})
        if isinstance(global_evals, dict):
            for ev in global_evals.values():
                if isinstance(ev, dict):
                    for key in ("Expected", "Raises", "Type", "Assertion", "Pattern"):
                        if key in ev:
                            eval_types.add(key.lower())

        return case_count, raises_count, sorted(eval_types)
    except Exception:
        return 0, 0, []


# ─────────────────────────────────────────────────────────────────────
# Core runner
# ─────────────────────────────────────────────────────────────────────


async def run_scenario(scenario: Scenario, spec_model: str, explore_model: str) -> BenchmarkResult:
    cslug = _combo_slug(spec_model, explore_model)
    br = BenchmarkResult(
        scenario_name=scenario.name,
        spec_model=spec_model,
        exploration_model=explore_model,
        model_slug=cslug,
    )
    t0 = time.perf_counter()

    try:
        func = Function(
            name=scenario.name,
            code=scenario.code,
            description=scenario.description,
        )
        _ = func.impl  # verify reference impl compiles

        gen = CodeModeGenerator(spec_model=spec_model, exploration_model=explore_model)
        run_id = f"bench_{scenario.name}_{uuid.uuid4().hex[:8]}"

        t0 = time.perf_counter()
        result: CodeModeResult = await gen.generate(
            func,
            run_id=run_id,
            run_evals=True,
            max_refinement_rounds=2,
            min_coverage=1.0,
            inject_durations=False,
        )
        elapsed = time.perf_counter() - t0

        # Re-run for a clean summary
        try:
            summary = (
                RunEvals.from_source(result.yaml_spec)
                .with_functions({scenario.name: func.impl})
                .ignore_duration()
                .run()
            )
            coverage = summary.coverage
            success = summary.all_passed
        except Exception as e:
            coverage = 0.0
            success = False
            br.error = f"Eval run error: {e}"

        case_count, raises_count, eval_types = _extract_spec_stats(result.yaml_spec)
        error_snippet_count = sum(1 for r in result.exploration_results if not r.success)

        br.success = success
        br.coverage = coverage
        br.total_time_s = elapsed
        br.case_count = case_count
        br.raises_count = raises_count
        br.snippet_count = len(result.exploration_results)
        br.error_snippet_count = error_snippet_count
        br.refinement_rounds = result.refinement_rounds
        (
            br.cost_usd,
            br.input_tokens,
            br.output_tokens,
            br.request_count,
            br.price_sources,
        ) = _extract_cost_stats(gen, run_id)
        br.evaluator_types = eval_types
        br.yaml_spec = result.yaml_spec
        br.exploration_results = result.exploration_results

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        br.total_time_s = elapsed
        br.error = f"{type(exc).__name__}: {str(exc)[:300]}"
        print(f"    💥 {br.error}")
        traceback.print_exc()

    return br


# ─────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────


def _print_comparison_to(
    console, results: list[BenchmarkResult], model_pairs: list[tuple[str, str]]
) -> None:
    try:
        from rich.table import Table
    except ImportError:
        return

    console.print("\n[bold cyan]═══ CodeMode Model Comparison Benchmark ═══[/]\n")

    # Legend Table
    legend = Table(title="Model Configurations", show_lines=True)
    legend.add_column("Configuration", style="bold")
    legend.add_column("Spec Model", style="blue")
    legend.add_column("Exploration Model", style="green")

    for i, (s_mod, e_mod) in enumerate(model_pairs, 1):
        legend.add_row(f"Case {i}", _model_short(s_mod), _model_short(e_mod))

    console.print(legend)
    console.print()

    # Per-scenario table
    table = Table(title="Per-Scenario Results", show_lines=True)
    table.add_column("Scenario", style="bold")
    table.add_column("Difficulty", style="dim")
    table.add_column("Config", style="cyan")
    table.add_column("Coverage", justify="right")
    table.add_column("Cases", justify="right")
    table.add_column("Raises", justify="right")
    table.add_column("Snippets", justify="right")
    table.add_column("Err Snips", justify="right")
    table.add_column("Refines", justify="right")
    table.add_column("Time (s)", justify="right")
    table.add_column("Cost ($)", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Status")

    scenario_names = list(dict.fromkeys(r.scenario_name for r in results))
    scenario_map = {s.name: s for s in SCENARIOS}

    for sname in scenario_names:
        for i, (s_mod, e_mod) in enumerate(model_pairs, 1):
            slug = _combo_slug(s_mod, e_mod)
            r = next(
                (x for x in results if x.scenario_name == sname and x.model_slug == slug), None
            )
            if not r:
                continue
            diff = scenario_map.get(sname, Scenario("", "", "", "")).difficulty
            cov = f"{r.coverage * 100:.0f}%"
            short_model = f"Case {i}"
            if r.error and not r.success:
                status = f"[red]💥 {r.error[:40]}[/]"
            elif r.success:
                status = "[green]✅ PASS[/]"
            else:
                status = "[red]❌ FAIL[/]"
            table.add_row(
                sname,
                diff,
                short_model,
                cov,
                str(r.case_count),
                str(r.raises_count),
                str(r.snippet_count),
                str(r.error_snippet_count),
                str(r.refinement_rounds),
                f"{r.total_time_s:.1f}",
                f"{r.cost_usd:.5f}",
                f"{r.input_tokens}/{r.output_tokens}",
                status,
            )

    console.print(table)

    # Aggregate per-model
    agg = Table(title="Aggregate by Model", show_lines=True)
    agg.add_column("Metric", style="bold")
    for i in range(1, len(model_pairs) + 1):
        agg.add_column(f"Case {i}", justify="right")
    if len(model_pairs) == 2:
        agg.add_column("Delta", justify="right", style="cyan")

    slugs = [_combo_slug(s_mod, e_mod) for s_mod, e_mod in model_pairs]

    def _model_results(slug: str) -> list[BenchmarkResult]:
        return [r for r in results if r.model_slug == slug]

    def _avg(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    metrics = [
        ("Functions", lambda rs: f"{len(rs)}", lambda a, b: f"{len(a) - len(b):+d}"),
        ("Pass Rate", lambda rs: f"{sum(1 for r in rs if r.success)}/{len(rs)}", None),
        (
            "Avg Coverage",
            lambda rs: f"{_avg([r.coverage for r in rs]) * 100:.1f}%",
            lambda a,
            b: f"{(_avg([r.coverage for r in a]) - _avg([r.coverage for r in b])) * 100:+.1f}pp",
        ),
        (
            "Avg Time (s)",
            lambda rs: f"{_avg([r.total_time_s for r in rs]):.1f}",
            lambda a,
            b: f"{_avg([r.total_time_s for r in a]) - _avg([r.total_time_s for r in b]):+.1f}",
        ),
        (
            "Avg Cases",
            lambda rs: f"{_avg([float(r.case_count) for r in rs]):.1f}",
            lambda a,
            b: f"{_avg([float(r.case_count) for r in a]) - _avg([float(r.case_count) for r in b]):+.1f}",
        ),
        (
            "Avg Snippets",
            lambda rs: f"{_avg([float(r.snippet_count) for r in rs]):.1f}",
            lambda a,
            b: f"{_avg([float(r.snippet_count) for r in a]) - _avg([float(r.snippet_count) for r in b]):+.1f}",
        ),
        (
            "Avg Raises Cases",
            lambda rs: f"{_avg([float(r.raises_count) for r in rs]):.1f}",
            lambda a,
            b: f"{_avg([float(r.raises_count) for r in a]) - _avg([float(r.raises_count) for r in b]):+.1f}",
        ),
        (
            "Avg Input Tokens",
            lambda rs: f"{_avg([float(r.input_tokens) for r in rs]):.0f}",
            lambda a,
            b: f"{_avg([float(r.input_tokens) for r in a]) - _avg([float(r.input_tokens) for r in b]):+.0f}",
        ),
        (
            "Avg Output Tokens",
            lambda rs: f"{_avg([float(r.output_tokens) for r in rs]):.0f}",
            lambda a,
            b: f"{_avg([float(r.output_tokens) for r in a]) - _avg([float(r.output_tokens) for r in b]):+.0f}",
        ),
        (
            "Total Cost ($)",
            lambda rs: f"{sum(r.cost_usd for r in rs):.5f}",
            lambda a, b: f"{sum(r.cost_usd for r in a) - sum(r.cost_usd for r in b):+.5f}",
        ),
        (
            "Cost Per Function ($)",
            lambda rs: f"{(sum(r.cost_usd for r in rs) / max(len(rs), 1)):.5f}",
            lambda a,
            b: f"{(sum(r.cost_usd for r in a) / max(len(a), 1)) - (sum(r.cost_usd for r in b) / max(len(b), 1)):+.5f}",
        ),
    ]

    all_model_results = [_model_results(s) for s in slugs]
    for label, fmt, delta_fn in metrics:
        row = [label] + [fmt(mr) for mr in all_model_results]
        if len(model_pairs) == 2 and delta_fn:
            row.append(delta_fn(all_model_results[0], all_model_results[1]))
        elif len(model_pairs) == 2:
            row.append("—")
        agg.add_row(*row)

    console.print(agg)


def print_comparison(results: list[BenchmarkResult], model_pairs: list[tuple[str, str]]) -> None:
    try:
        from rich.console import Console

        console = Console()
        _print_comparison_to(console, results, model_pairs)
    except ImportError:
        for r in results:
            status = "PASS" if r.success else f"FAIL ({r.error or 'low coverage'})"
            print(
                f"  {r.scenario_name:15s} [{r.model_slug:30s}] "
                f"cov={r.coverage * 100:.0f}% cases={r.case_count} raises={r.raises_count} "
                f"snips={r.snippet_count} cost=${r.cost_usd:.5f} tok={r.input_tokens}/{r.output_tokens} {status}"
            )


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────


async def _async_main(
    scenarios: list[Scenario], model_pairs: list[tuple[str, str]], run_dir: Path
) -> None:
    all_results: list[BenchmarkResult] = []

    for scenario in scenarios:
        print(f"\n{'=' * 60}")
        print(f"  [{scenario.difficulty.upper()}] {scenario.name}")
        print(f"{'=' * 60}")

        for i, (spec_model, explore_model) in enumerate(model_pairs, 1):
            print(f"\n  🤖 config {i}")
            br = await run_scenario(scenario, spec_model, explore_model)

            status = "✅ PASS" if br.success else "❌ FAIL"
            print(
                f"     {status}  cov={br.coverage * 100:.0f}%  cases={br.case_count}  "
                f"raises={br.raises_count}  snips={br.snippet_count}({br.error_snippet_count} err)  "
                f"refines={br.refinement_rounds}  cost=${br.cost_usd:.5f}  tok={br.input_tokens}/{br.output_tokens}  {br.total_time_s:.1f}s"
            )
            if br.error:
                print(f"     ⚠️  {br.error[:120]}")

            all_results.append(br)
            _record_result(run_dir, br)

    print(f"\n\n{'=' * 60}")
    print_comparison(all_results, model_pairs)
    _record_comparison(run_dir, all_results, model_pairs)
    print(f"\n  Artifacts saved to: {run_dir}")


def replay_benchmark(run_dir: Path) -> None:
    if not run_dir.exists():
        print(f"Error: {run_dir} does not exist.")
        return

    meta_json = run_dir / "meta.json"
    if not meta_json.exists():
        print(f"Error: {run_dir} is missing meta.json.")
        return

    meta = json.loads(meta_json.read_text())
    models_data = meta.get("models", {})
    model_pairs = _normalize_models_to_pairs(models_data)

    results = []
    for result_file in run_dir.glob("*/*/result.json"):
        model_slug = result_file.parent.name
        scenario = result_file.parent.parent.name
        data = json.loads(result_file.read_text())

        cov_val = data.get("coverage", 0.0)
        if isinstance(cov_val, str):
            cov_val = float(cov_val.replace("%", "")) / 100.0

        br = BenchmarkResult(
            scenario_name=data.get("scenario", scenario),
            spec_model=data.get("spec_model") or data.get("model", ""),
            exploration_model=data.get("exploration_model") or data.get("model", ""),
            model_slug=data.get("model_slug", model_slug),
            success=data.get("success", False),
            coverage=cov_val,
            total_time_s=float(data.get("time_s", 0.0)),
            case_count=int(data.get("cases", 0)),
            raises_count=int(data.get("raises_cases", 0)),
            snippet_count=int(data.get("snippets", 0)),
            error_snippet_count=int(data.get("error_snippets", 0)),
            refinement_rounds=int(data.get("refinements", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            request_count=int(data.get("requests", 0)),
            price_sources=[str(x) for x in data.get("price_sources", []) if isinstance(x, str)],
            function_count=int(data.get("function_count", 1) or 1),
            evaluator_types=data.get("evaluator_types", []),
            error=data.get("error"),
        )
        results.append(br)

    # Scenarios might be loaded in unpredictable order from glob
    # Re-sort results based on SCENARIOS array definition
    ordered_results = []
    for scen in SCENARIOS:
        ordered_results.extend([r for r in results if r.scenario_name == scen.name])

    print_comparison(ordered_results, model_pairs)


def select_and_replay(base_dir: Path) -> None:
    if not base_dir.exists() or not base_dir.is_dir():
        print(f"Error: {base_dir} is not a valid directory.")
        return

    run_dirs = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and (d / "meta.json").exists()], reverse=True
    )
    if not run_dirs:
        print(f"No benchmark runs found in {base_dir}.")
        return

    try:
        from rich.console import Console
        from rich.prompt import IntPrompt
        from rich.table import Table

        console = Console()
        all_pairs: list[list[tuple[str, str]]] = []
        max_cases = 0
        for d in run_dirs:
            meta = json.loads((d / "meta.json").read_text())
            pairs = _normalize_models_to_pairs(meta.get("models", {}))
            all_pairs.append(pairs)
            max_cases = max(max_cases, len(pairs))

        table = Table(title="Available Benchmark Runs", show_lines=True)
        table.add_column("ID", justify="right", style="cyan")
        table.add_column("Run Directory", style="bold")
        table.add_column("Date", style="dim")
        for i in range(1, max_cases + 1):
            table.add_column(f"Case {i}", style="blue")

        for i, d in enumerate(run_dirs, 1):
            meta = json.loads((d / "meta.json").read_text())
            date_str = meta.get("iso", d.name.replace("run_", ""))
            if "T" in date_str:
                date_str = date_str.split("T")[0] + " " + date_str.split("T")[1][:5]
            row = [str(i), d.name, date_str]
            pairs = all_pairs[i - 1]
            for case_index in range(max_cases):
                if case_index < len(pairs):
                    spec, exploration = pairs[case_index]
                    row.append(
                        f"Spec: {_model_short(spec)}\nExploration: {_model_short(exploration)}"
                    )
                else:
                    row.append("Spec: -\nExploration: -")
            table.add_row(*row)

        console.print(table)
        choice = IntPrompt.ask(
            "Select a run to replay", choices=[str(i) for i in range(1, len(run_dirs) + 1)]
        )
        selected_run = run_dirs[int(choice) - 1]
    except ImportError:
        print("Available Benchmark Runs:")
        all_pairs_fallback: list[list[tuple[str, str]]] = []
        max_cases = 0
        for d in run_dirs:
            meta = json.loads((d / "meta.json").read_text())
            pairs = _normalize_models_to_pairs(meta.get("models", {}))
            all_pairs_fallback.append(pairs)
            max_cases = max(max_cases, len(pairs))

        header = ["ID", "Run Directory", "Date"]
        for i in range(1, max_cases + 1):
            header.append(f"Case {i}")
        print("  " + " | ".join(header))

        for i, d in enumerate(run_dirs, 1):
            meta = json.loads((d / "meta.json").read_text())
            date_str = meta.get("iso", d.name.replace("run_", ""))
            if "T" in date_str:
                date_str = date_str.split("T")[0] + " " + date_str.split("T")[1][:5]
            row = [f"[{i}]", d.name, date_str]
            pairs = all_pairs_fallback[i - 1]
            for case_index in range(max_cases):
                if case_index < len(pairs):
                    spec, exploration = pairs[case_index]
                    row.append(
                        f"Spec: {_model_short(spec)}; Exploration: {_model_short(exploration)}"
                    )
                else:
                    row.append("Spec: -; Exploration: -")
            print("  " + " | ".join(row))
        while True:
            try:
                choice_str = input(f"Select a run to replay (1-{len(run_dirs)}): ")
                choice = int(choice_str)
                if 1 <= choice <= len(run_dirs):
                    selected_run = run_dirs[choice - 1]
                    break
                else:
                    print("Invalid choice.")
            except ValueError:
                pass

    print(f"\nReplaying {selected_run.name}...\n")
    replay_benchmark(selected_run)


def get_models(arg_list: list[str] | None, env_var: str, default_list: list[str]) -> list[str]:
    if arg_list:
        return arg_list
    env_val = os.getenv(env_var)
    if env_val:
        return [m.strip() for m in env_val.split(",") if m.strip()]
    return default_list


def _print_model_config(model_pairs: list[tuple[str, str]]) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        legend = Table(title="Model Configurations", show_lines=True)
        legend.add_column("Configuration", style="bold")
        legend.add_column("Spec Model", style="blue")
        legend.add_column("Exploration Model", style="green")
        for i, (s_mod, e_mod) in enumerate(model_pairs, 1):
            legend.add_row(f"Case {i}", _model_short(s_mod), _model_short(e_mod))
        console.print(legend)
        console.print()
    except ImportError:
        print("Model Configurations:")
        for i, (s, e) in enumerate(model_pairs, 1):
            print(f"  Case {i}: spec={_model_short(s)}, exploration={_model_short(e)}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeMode model comparison benchmark")
    parser.add_argument(
        "--spec-models",
        nargs="+",
        help="Spec models (space-separated)",
    )
    parser.add_argument(
        "--explore-models",
        nargs="+",
        help="Explore models (space-separated)",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="Run only these scenarios by name",
    )
    parser.add_argument(
        "--replay",
        type=str,
        help="Replay a specific benchmark run directory",
    )
    parser.add_argument(
        "--replay-dir",
        type=str,
        help="List available runs in this directory and select one to replay",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show current model configurations in a table and exit",
    )
    parser.add_argument(
        "--id",
        type=str,
        help="Custom ID for the benchmark run directory",
    )
    args = parser.parse_args()

    if args.replay:
        replay_benchmark(Path(args.replay))
        return

    if args.replay_dir:
        select_and_replay(Path(args.replay_dir))
        return

    spec_models = get_models(args.spec_models, "BENCHMARK_SPEC_MODELS", DEFAULT_SPEC_MODELS)
    explore_models = get_models(
        args.explore_models, "BENCHMARK_EXPLORATION_MODELS", DEFAULT_EXPLORE_MODELS
    )

    if len(spec_models) != len(explore_models):
        print(
            f"Error: Number of spec models ({len(spec_models)}) must match explore models ({len(explore_models)})."
        )
        sys.exit(1)

    model_pairs = list(zip(spec_models, explore_models, strict=False))

    if args.show_config:
        _print_model_config(model_pairs)
        return

    scenarios = SCENARIOS
    if args.only:
        scenarios = [s for s in SCENARIOS if s.name in args.only]
        if not scenarios:
            print(f"No scenarios matched: {args.only}")
            print(f"Available: {[s.name for s in SCENARIOS]}")
            sys.exit(1)

    _print_model_config(model_pairs)
    print(f"Scenarios  : {[s.name for s in scenarios]}")

    run_dir = _init_run_dir(model_pairs, [s.name for s in scenarios], args.id)
    print(f"Recording to: {run_dir}\n")

    asyncio.run(_async_main(scenarios, model_pairs, run_dir))


if __name__ == "__main__":
    main()
