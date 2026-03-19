## Flash vs Opus 4.6 — Spec Quality Analysis

### Numerical Table

| Scenario | Model | Cases | Raises | Snippets | Pass | Time |
|---|---|---|---|---|---|---|
| flatten | **Opus** | **30** | **7** | 26 | ✅ | 36.7s |
| flatten | Flash | 27 | 9 | 20 | ❌ 95% | 28.2s |
| parse_cron | **Opus** | **55** | **19** | **44** | ✅ | 179.7s |
| parse_cron | Flash | 27 | 13 | 29 | ✅ | 77.3s |
| levenshtein | **Opus** | **42** | **9** | 33 | ✅ | 92.1s |
| levenshtein | Flash | 23 | 3 | 20 | ✅ | 10.9s |

**Aggregate:** Opus avg 42.3 case / Flash avg 25.7 case (+64%). Raises: 11.7 vs 8.3 (+41%).

---

### Scenario-by-Scenario Analysis

**flatten — Flash FAILED (95% coverage)**

There is a serious structural issue in Flash's spec: duplicate cases. It wrote `null_input_error`, `int_input_error`, `string_input_error`, and `dict_input_error` **twice** — once with `*_error` prefixes and once with `verified_error_*` prefixes. On top of that, it added a `verified_error_tuple` case where the comment clearly says "we cannot pass tuples in YAML" and then bypasses the check with `assertion: "True"`. That fake case is likely part of why coverage is stuck at 95%. Opus has no such issue — every case is meaningful and unique.

What stands out in Opus flatten: `nested_empty_lists` (correctly collapsing nested empty lists), `dicts_kept_as_is`, `list_with_none_elements`, `list_with_booleans` — strong cross-type correctness coverage. Flash includes similar ideas, but with less diversity and duplicate noise.

**parse_cron — the biggest gap is here**

Opus has 55 cases, Flash has 27. Beyond raw count, quality is very different. Opus highlights:

- Separate **wildcard count tests** per field: `wildcard_minute_count`, `wildcard_hour_count`, etc. Each field is isolated. Flash only tested all fields together with `* * * * *`.
- `step_large_gives_single_value`: `*/60 0 1 1 0` -> returns only `[0]`. Flash misses this edge case.
- `step_1_equals_wildcard`: `*/1` should match `*`. Tests semantic equivalence.
- `complex_mixed_expression`: `0,30 9-17 1,15 */3 1-5` — mixed syntax across multiple fields in one realistic cron expression.
- `typical_work_schedule`: `*/5 9-17 * * 1-5` — a real production pattern.
- In raises, Opus includes both lower and upper bound failures (`month_zero`, `day_of_month_zero`, `day_of_week_7`, `day_of_month_32`). Flash mostly covered upper bounds.

One area where Flash is better: `malformed_step` (like `*/` with missing step) — Opus misses it.

**levenshtein — the most dramatic difference**

Opus has 42 cases, Flash has 23. More importantly, **Opus uses much stronger evaluators:**

```yaml
# Present in Opus:
IdentityProperty: (input[0] == input[1]) == (output == 0)
UpperBound:       output <= max(len(input[0]), len(input[1]))
LowerBound:       output >= abs(len(input[0]) - len(input[1]))
```

Flash has the same global invariants, so they are equal on that point. But Opus goes much further in case depth:

- `unicode_accent`: `café` vs `cafe` -> 1. Flash has no unicode case.
- `symmetry_check_forward/reverse`: proves `levenshtein(a,b) == levenshtein(b,a)` with **two separate cases**.
- `triangle_inequality` is tested with three cases: ab, bc, ac.
- `transposition_is_two`: `ab` -> `ba` = 2 (verifies Levenshtein counts transposition as two edits).
- `long_identical_prefix`: `abcdefgh` vs `abcdefXY` = 2 — only the tail differs.

Flash's raises coverage for levenshtein is weak: only 3 cases. Opus has 9 (none, integer, list, boolean, no_arg, one_arg, etc.), covering a wider range of invalid input shapes.

---

### Evaluator Quality Comparison

| Dimension | Opus | Flash |
|---|---|---|
| Global invariant usage | ✅ Rich (all scenarios) | ✅ Present but lighter |
| Assertion vs expected balance per case | Balanced | More `expected`-heavy |
| Mathematical property testing | ✅ (symmetry, triangle inequality) | ❌ |
| Duplicate/fake cases | ❌ None | ⚠️ Present in flatten |
| Regex match usage | ✅ (error message validation) | ✅ |

---

### Conclusion

This time the gap is not **20-25%**; it is significantly larger: ~65% in case count and ~41% in raises coverage. But the key difference is **conceptual depth** of the spec — Opus tests mathematical properties (symmetry, triangle inequality, identity), while Flash mostly verifies output correctness. These are fundamentally different testing philosophies.

On speed-vs-quality tradeoff: for parse_cron, Opus is 179s vs Flash 77s (2.3x slower, ~2x more cases). For levenshtein, Opus is 92s vs Flash 11s (8x slower, 1.8x more cases). Even considering cost, Flash is still defensible, but if you want a truly reliable test suite, Opus is in a different league.