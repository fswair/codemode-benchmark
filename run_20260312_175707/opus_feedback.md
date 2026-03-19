## Flash — Old (1 round) vs New (2 rounds)

| Metric | Old (single-shot) | New (feedback-guided) | Delta |
|---|---|---|---|
| **Pass Rate** | **2/3** (flatten FAIL) | **3/3** | +1 scenario recovered |
| **Avg Coverage** | 98.3% | **100%** | +1.7pp |
| **Total Refinements** | 4 (flatten 3, parse_cron 1) | **0** | dropped to zero |
| **Avg Cases** | 25.7 | **45.3** | **+76%** |
| **Avg Raises** | 8.3 | **11.3** | +36% |
| **Avg Snippets** | 23.0 | **40.0** | +74% |
| **Avg Time** | 38.8s | 57.0s | +18.2s (cost of round 2) |

### Per-scenario comparison

| Scenario | Old | New |
|---|---|---|
| **flatten** | **FAIL** (95%, 3 refines, 27 cases) | **PASS** (100%, 0 refines, 49 cases) |
| **parse_cron** | PASS (100%, 1 refine, 27 cases) | PASS (100%, **0 refines**, **45 cases**) |
| **levenshtein** | PASS (100%, 0 refines, 23 cases) | PASS (100%, 0 refines, **42 cases**) |

### Key highlights

1. **flatten now passes.** In the old pipeline, Flash still could not pass flatten after 3 refinement rounds (stuck at 95%). In the new pipeline, it reaches **100% with zero refinements**.

2. **Refinement disappeared entirely.** Across 3 scenarios, total refinements are 0. The old pipeline had 4 refinements. This shows that Round 2 dramatically improved the quality of evidence passed into spec generation.

3. **Case count nearly doubled.** 25.7 -> 45.3. The additional snippets from Round 2 provide richer evidence to the spec agent, which then generates more and more diverse test cases.

4. **The time increase is reasonable.** +18.2s (extra LLM call + execution in round 2). But the old pipeline also spent time in 4 refinement rounds, so net overhead is still low when considering full pipeline time.

5. **Flash now approaches Opus's old scores.** Opus single-shot was producing 42.3 average cases; Flash reached 45.3 with 2 rounds. Feedback-guided exploration closed much of the weaker model's quality gap.

ChatGPT was right: **this was the highest-ROI change in the pipeline.**