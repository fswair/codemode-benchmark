"""Auto-generated conftest for vowel pytest codegen output."""


# --- vowel pytest codegen helpers (start) ---
from __future__ import annotations

import builtins
import importlib
import re
import time
import typing

import pytest
from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter


def _resolve_eval_function(eval_id: str):
    if "." not in eval_id:
        if hasattr(builtins, eval_id):
            return getattr(builtins, eval_id)
        raise ImportError(f"Cannot resolve function '{eval_id}'. Use module.function format.")

    module_name, attr_name = eval_id.rsplit(".", 1)
    module = importlib.import_module(module_name)
    if not hasattr(module, attr_name):
        raise ImportError(f"Module '{module_name}' has no attribute '{attr_name}'")
    return getattr(module, attr_name)


def _invoke_target(fn, case: dict):
    if case.get("inputs") is not None:
        inputs = case["inputs"]
        if isinstance(inputs, dict):
            return fn(**inputs)
        return fn(*inputs)
    return fn(case.get("input"))


def _assertion_input(case: dict):
    if case.get("inputs") is not None:
        return case["inputs"]
    return case.get("input")


def _run_case(fn, case: dict) -> dict:
    t0 = time.perf_counter()
    try:
        output = _invoke_target(fn, case)
        duration_ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": True,
            "output": output,
            "exc_type": None,
            "exc_msg": None,
            "duration_ms": duration_ms,
        }
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": False,
            "output": None,
            "exc_type": type(exc).__name__,
            "exc_msg": str(exc),
            "duration_ms": duration_ms,
        }


def _assert_raises_behavior(result: dict, case: dict):
    expected = case.get("raises")
    optional = bool(case.get("raises_optional"))
    match = case.get("match")

    if expected is None:
        assert result["ok"], f"Unexpected exception: {result['exc_type']}: {result['exc_msg']}"
        return

    expected = str(expected)
    if expected == "any":
        if optional:
            return
        assert not result["ok"], "Expected any exception, but function returned normally"
        return

    if optional and result["ok"]:
        return

    assert not result["ok"], f"Expected {expected}, but function returned normally"
    actual_type = str(result["exc_type"])
    expected_short = expected.split(".")[-1]
    assert actual_type == expected_short, f"Expected {expected_short}, got {actual_type}: {result['exc_msg']}"
    if match:
        message = result.get("exc_msg") or ""
        assert re.search(str(match), message, re.IGNORECASE), (
            f"Exception message does not match pattern {match!r}. Message: {message!r}"
        )


def _check_expected(result: dict, case: dict):
    if case.get("has_expected"):
        assert result["output"] == case.get("expected")


def _check_duration(result: dict, duration_ms: float | None):
    if duration_ms is not None:
        assert result["duration_ms"] <= float(duration_ms)


def _check_pattern(output, pattern: str | None, case_sensitive: bool = True):
    if pattern is None:
        return
    flags = 0 if case_sensitive else re.IGNORECASE
    assert re.search(pattern, str(output), flags), f"Output {output!r} does not match pattern {pattern!r}"


def _check_contains(output, contains):
    if contains is None:
        return
    assert contains in output, f"Output {output!r} does not contain {contains!r}"


def _check_assertion(output, case: dict, assertion: str | None):
    if assertion is None:
        return
    env = {
        "input": _assertion_input(case),
        "output": output,
        "expected": case.get("expected") if case.get("has_expected") else None,
        "duration": None,
        "metadata": {},
    }
    assert bool(eval(assertion, env, env)), f"Assertion failed: {assertion}"


def _check_type(output, type_expr: str | None, strict: bool = False):
    if type_expr is None:
        return
    safe = {
        "Any": typing.Any,
        "None": None,
        "bool": bool,
        "bytes": bytes,
        "dict": dict,
        "float": float,
        "frozenset": frozenset,
        "int": int,
        "list": list,
        "object": object,
        "set": set,
        "str": str,
        "tuple": tuple,
        "typing": typing,
    }
    safe.update({name: getattr(typing, name) for name in dir(typing) if not name.startswith("_")})
    expected = eval(str(type_expr), {"__builtins__": {}}, safe)
    adapter = TypeAdapter(expected)
    try:
        adapter.validate_python(output, strict=bool(strict))
    except (ValidationError, TypeError, ValueError) as exc:
        pytest.fail(f"Output is not of type {type_expr!r}: {exc}")


def _assert_common_case_checks(result: dict, case: dict):
    _check_expected(result, case)
    _check_duration(result, case.get("duration"))
    _check_pattern(result["output"], case.get("pattern"), case_sensitive=bool(case.get("case_sensitive", True)))
    _check_contains(result["output"], case.get("contains"))
    _check_assertion(result["output"], case, case.get("assertion"))
    _check_type(result["output"], case.get("type"), strict=bool(case.get("strict_type")))


def _run_global_type_eval(result: dict, params: dict):
    _check_type(result["output"], params.get("type"), strict=bool(params.get("strict", False)))


def _run_global_assertion_eval(result: dict, case: dict, params: dict):
    _check_assertion(result["output"], case, params.get("assertion"))


def _run_global_duration_eval(result: dict, params: dict):
    duration_s = params.get("duration")
    if duration_s is None:
        return
    assert result["duration_ms"] <= float(duration_s) * 1000.0


def _run_global_contains_input_eval(result: dict, case: dict, params: dict):
    input_value = _assertion_input(case)
    output = result["output"]
    as_strings = bool(params.get("as_strings", False))
    case_sensitive = bool(params.get("case_sensitive", True))
    if as_strings or (isinstance(input_value, str) and isinstance(output, str)):
        lhs = str(input_value)
        rhs = str(output)
        if not case_sensitive:
            lhs = lhs.lower()
            rhs = rhs.lower()
        assert lhs in rhs, f"Output {output!r} does not contain input {input_value!r}"
        return
    assert input_value in output, f"Output {output!r} does not contain input {input_value!r}"


def _run_global_pattern_eval(result: dict, params: dict):
    _check_pattern(
        result["output"],
        params.get("pattern"),
        case_sensitive=bool(params.get("case_sensitive", True)),
    )
# --- vowel pytest codegen helpers (end) ---
