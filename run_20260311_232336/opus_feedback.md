## Opus 4.6 vs Flash — Detailed Analysis

### 1. Headline Numbers

| Metric | Opus 4.6 | Flash | Delta |
|---|---|---|---|
| Pass Rate | **3/3** | 2/3 | Opus wins |
| Avg Coverage | **100%** | 98.3% | +1.7pp |
| Total Refinements | **0** | 4 | Opus: zero-shot perfection |
| Avg Cases | **42.3** | 25.7 | +65% |
| Avg Raises Cases | **11.7** | 8.3 | +41% |
| Avg Time | 102.8s | **38.8s** | Flash is 2.65x faster |

Most striking finding: **Opus reached 100% coverage on all 3 scenarios with zero refinements.** Flash spent 3 refinements on flatten and still stayed at 95% (FAIL).

---

### 2. Per-Scenario Deep Dive

#### flatten (Flash's weakest scenario)

**Opus**: 30 cases, 7 raises, 0 refinements, 100% — clean pass on first try.
**Flash**: 27 cases, 9 raises, 3 refinements, 95% — **FAIL**.

Quality differences:

| Dimension | Opus | Flash |
|---|---|---|
| Global evaluators | 4 (`ReturnType`, `ResultIsFlat`, `PreservesOrder`, `NonNegativeLength`) | 2 (`IsList`, `NoNestedLists`) |
| Case diversity | strings_not_recursed, dicts_kept_as_is, list_with_none_elements, list_with_booleans, floats_nested, triple_nested | Similar coverage but less variety |
| Error case quality | Clean, non-redundant 7 raises | **Serious issues** (below) |

There are **3 critical problems** in Flash's spec:

1. **Wrong assertion**: `other_containers_as_atoms` expects `output == [[1, 2], {'a': 1}]`, which implies flatten should not flatten anything. Correct expected value should be `[1, 2, {'a': 1}]`. **Semantic error.**

2. **Repeated error cases**: `null_input_error` and `verified_error_none` are the same test. Same for `int_input_error` and `verified_error_int`. In total there are **5 duplicate error cases**.

3. **Fake error case**: `verified_error_tuple` -> `input: null, assertion: "True", raises: TypeError` — meaningless filler.

#### levenshtein

**Opus**: 42 cases, 9 raises, 0 refinements, 100%, 92.1s
**Flash**: 23 cases, 3 raises, 0 refinements, 100%, 10.9s

Both pass, but quality gap is substantial:

| Dimension | Opus | Flash |
|---|---|---|
| Global evaluators | 5 (ReturnType, NonNeg, Upper, Lower, Identity) | 5 (same - equal here) |
| **Mathematical property tests** | symmetry_check (forward+reverse), triangle_ineq (3 cases), transposition_is_two | Missing |
| Unicode | `café` vs `cafe` test | Missing |
| Error cases | 9 (none x3, int, list, no_args, one_arg, bool) | 3 (none, int, list) |

Most impressive part of Opus is **mathematical reasoning**:
- **Symmetry**: `levenshtein("kitten","sitting") == levenshtein("sitting","kitten")`, validated with separate cases.
- **Triangle inequality**: `d(a,c) <= d(a,b) + d(b,c)`, tested using 3 related cases.
- **Transposition cost**: `d("ab","ba") == 2`, correctly distinguishing Levenshtein from Damerau-Levenshtein.

Flash does not show this level of conceptual depth.

#### parse_cron (most complex scenario)

**Opus**: 55 cases, 19 raises, 0 refinements, 100%, 179.7s
**Flash**: 27 cases, 13 raises, 1 refinement, 100%, 77.3s

Here the **global evaluator gap is huge**:

| Opus (9 evaluator) | Flash (3 evaluator) |
|---|---|
| ReturnType(dict) | ReturnType(dict) |
| HasAllKeys (set comparison) | KeyCheck (list order) |
| AllValuesAreSortedLists | — |
| AllValuesAreInts | ValueType (list + int combined) |
| MinuteInRange (0-59) | — |
| HourInRange (0-23) | — |
| DayOfMonthInRange (1-31) | — |
| MonthInRange (1-12) | — |
| DayOfWeekInRange (0-6) | — |

Opus adds independent range validation for each field. This is a strong structural guarantee that would matter in mutation testing. Even if a mutant allows minute=60, Opus likely catches it; Flash likely does not.

Opus's spec is also structured with sections: `TYPICAL CASES`, `ALL WILDCARDS`, `BOUNDARY CASES`, `EDGE CASES`, `ERROR CASES` — more readable and reviewable.

---

### 3. Conclusions and Trade-off Analysis

**Real advantages of Opus:**
1. **Zero-shot reliability** - reaches 100% without entering the refinement loop.
2. **Richer global evaluator set** - especially in parse_cron (9 vs 3), making it a stronger bug detector.
3. **Mathematical concept testing** - symmetry, triangle inequality, transposition.
4. **Clean error cases** - no duplicates, no fake placeholders, meaningful `match` patterns.
5. **Semantic correctness** - avoids assertion mistakes like Flash's `other_containers_as_atoms` issue.

**Advantages of Flash:**
- **Speed**: 2.65x faster
- **Cost**: ~100x cheaper (token pricing + lower token usage)
- Finishes levenshtein in 10.9s (Opus: 92.1s)

**Decision point:** Flash is usually adequate for pass/fail outcomes, but spec *quality* is clearly lower. Opus produces something closer to a true regression-grade suite, while Flash is more like a smoke-test baseline. Mutation testing would likely show a dramatic gap.

**Recommendation:** Making Opus the default model is not cost-efficient. But for critical-path functions (payments, auth, parsers), Opus is clearly worth it. A hybrid approach remains strongest: **lite exploration + Opus spec generation**.