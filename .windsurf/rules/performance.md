---
trigger: model_decision
---

Every code change must be profiled and benchmarked:
 
1. **Profiled** — run `cProfile` or `py-spy` on the affected code path and compare before/after.
2. **Benchmarked** — run the relevant `pytest-benchmark` suite (or a manual timing harness) and confirm no regression.
3. **Reported** — include a brief summary of profiling results (function call counts, wall time) in the review.
 
Do not consider a change complete until profiling and benchmarking confirm no performance regression.