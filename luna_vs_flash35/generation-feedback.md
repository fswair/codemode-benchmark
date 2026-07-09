# Generation Feedback: Luna vs Gemini 3.5 Flash

## Scope and method

This review reads both models' `spec.yml` and `exploration.txt` artifacts for
`group_by`, `flatten`, and `parse_cron`. It assesses contract coverage,
correctness of expected outcomes, useful discoveries, and whether exploration
was translated into a maintainable evaluation spec. The benchmark result is
supporting evidence, not the sole quality measure.

## Overall judgment

Luna produced the stronger overall set of specifications. Its three specs pass
their generated cases and it is notably more reliable when Python runtime
semantics become non-obvious. Gemini 3.5 Flash explores more aggressively and
is strongest on `flatten`, but its `group_by` spec contains seven incorrect
expected outputs. This is a material quality failure: several tests describe a
different function from the reference implementation.

| Scenario | Better generation | Why |
| --- | --- | --- |
| `group_by` | Luna | Correctly turns Python key-equality observations into expectations; Flash does not. |
| `flatten` | Gemini 3.5 Flash, narrowly | Better depth coverage and a meaningful no-nested-list invariant. |
| `parse_cron` | Luna | Covers the documented grammar and error contract without making accidental parser permissiveness a large part of the public contract. |

## `group_by`

### Luna: best result in the benchmark

Luna's 45 cases all pass. Its strongest case is the deliberately mixed
`False`/`0` input: the spec expects one dictionary bucket containing both
records, matching Python's equality and hash behavior. It also correctly covers
missing keys and explicit `None` in the same bucket, preserves input order, and
checks invalid item/value paths with the observed exception types.

The exploration was useful rather than merely broad. It explicitly investigated
the `False`/zero collision, object identity preservation, integer and `None`
field names, and unhashable grouping values. Most importantly, the generated
expected values retained those findings correctly.

The main limitation is scope discipline: several cases test undocumented
implementation behavior such as integer field names, non-list iterables, and
exact interpreter exceptions. These are valid regression probes for this exact
implementation, but should be separated from the public behavioral contract.
`GroupValuesAreLists` is also a weak invariant because it mostly restates the
shape already implied by the expected outputs.

### Gemini 3.5 Flash: good exploration, incorrect translation

Flash's exploration found the right issue: it includes snippets for float/int
and bool/int key equality. The generated spec then drops the first record from
each collided bucket. For example, its expected output for `[0, False]` keeps
only `False`, while the reference output correctly keeps both records under the
same key.

The same error occurs in seven generated cases:

- `falsy_keys_distinct_groups`: `0` and `False`
- `float_and_int_value_equality`: `1` and `1.0`
- `boolean_true_and_int_1_group`: `True` and `1`
- `boolean_true_false_and_ints`: `True`/`1` and `False`/`0`
- `negative_numeric_keys`: `-1` and `-1.0`
- `zero_modes_intertwined`: `0.0`, `-0.0`, and `0`
- `heterogeneous_number_shapes`: `10` and `10.0`

That explains the benchmark's `82.9%` coverage result. Flash did add one good
identity assertion and explored insertion order, but the incorrect collision
expectations outweigh those strengths. The key improvement is to execute every
candidate oracle case after exploration and retain the observed output, instead
of inferring output from a verbal description of Python equality.

## `flatten`

### Gemini 3.5 Flash: best case design

Flash's 47 passing cases are the best single spec in the comparison. It tests
ordinary nesting, empty branches, heterogeneous leaves, a 50-level nest, and
wide inputs. Its global `NoNestedListsLeft` assertion is a useful independent
property: it can catch a partially flattened result even where a particular
exact-output example is absent. The exploration also probes recursion cycles,
non-list top-level inputs, and sequence-like leaves that must remain atomic.

Its `FastEnough: 0.05` duration evaluator is not well justified. The benchmark
reruns specs with durations ignored, so this threshold was not validated and
could create flaky evaluation on slower hardware. It should be removed or
calibrated from repeated measurements.

### Luna: correct, clean, and slightly less discriminating

Luna's 44 cases all pass and provide sound coverage of deep nesting, empty
lists, scalar leaves, and the exact top-level `TypeError` messages. Its
exploration noticed a cyclic list leads to recursion failure but did not add a
non-terminating/costly case to the dataset, which is a good judgment call.

The weakness is the global `PreservesFlattenedLength` assertion:
`isinstance(output, list)` duplicates `ReturnType` rather than validating a
distinct property. Replacing it with Flash's no-nested-list invariant would
make Luna's otherwise solid spec more discriminating.

## `parse_cron`

### Luna: better contract alignment

Luna's 44 passing cases cover all documented forms: wildcards, lists, ranges,
wildcard steps, bounded range steps, single-start steps, duplicate values,
whitespace handling, and field-specific bounds. The error cases are focused and
include field counts, non-positive steps, malformed tokens, invalid ranges, and
invalid types. `ExpectedFields` and `SortedIntegerLists` are meaningful global
properties.

A particularly useful discovery is that a descending *stepped* range such as
`10-5/2` produces an empty list rather than raising; that behavior is explicitly
captured. Since it is not part of the stated cron grammar, it should be labeled
as implementation behavior, not treated as a general cron compatibility claim.

### Gemini 3.5 Flash: broad but overfits parser permissiveness

Flash's 60 passing cases have excellent breadth. It independently checks sorted
and unique output lists, overlapping ranges, duplicate comma values, mixed
syntax, each field's ordinary bounds, and malformed separators. Those are strong
regression tests.

However, much of the extra breadth tests Python `int()` permissiveness rather
than the documented cron language: unary-plus values, unary-plus ranges and
steps, negative-zero spellings, and descending stepped ranges treated as valid
empty fields. These inputs may be accepted by this implementation, but making
them expected public behavior locks in accidental parser behavior and obscures
the core specification. Flash would improve by keeping these as exploratory
observations or clearly marking them as implementation-compatibility cases.

## Recommended synthesis

Use Luna's `group_by` and `parse_cron` specs as the base. Import Flash's
`flatten` depth cases and `NoNestedListsLeft` assertion, but omit its unverified
duration threshold. For `group_by`, retain Luna's collision cases and reject all
Flash collision expectations that omit the first equivalent record. For
`parse_cron`, retain Flash's overlap/duplicate and per-field error coverage,
while moving unary-plus and other undocumented accepted forms to a separately
labeled compatibility suite.
