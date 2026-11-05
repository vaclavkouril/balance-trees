# Benchmark tools

Generate measurements under ignored `results/` directories; results are not
tracked in source control. Use a new directory for each experiment. Keep
correctness tests in `tests/`.

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark --help
PYTHONPATH=src python3 -m balance_trees.experiment --help
```

See [methodology](../docs/benchmarks.md) for seeds, timing boundaries, validation
and output formats. The [experimental policy guide](../docs/experimental-strategies.md)
covers insertion-depth tools, worst seed-averaged batches and the larger
`run_v3_report.py` sweep.

For the Linux memory-capped interval-promotion runner:

```sh
PYTHONPATH=src python3 benchmarks/random_level_scale.py \
  --min-power 10 --max-power 16 --memory-mib 1024 --timeout 360 \
  --output benchmarks/results/interval-promotion-scale
```

This runner selects `interval-target-promotion`, validates every completed tree,
and records peak child memory. Use the general benchmark CLI to select the new
`random-level` perfect-tree sampler or `geometric-target-local-repair`.
The stored-priority treap reference is retained in
`src/balance_trees/strategies/stored_priority_treap.py`.

## Parallel target-strategy comparison

The adaptive Linux runner compares both geometric implementations, interval
repair, random-level leaf promotion and stored-priority treap across all seven
input families. It defaults to four isolated processes, a 768 MiB address-space
cap per process, and a 360-second deadline per trial. It samples increasing sizes
from 1,024 through 16,777,216 keys, stopping each strategy/input pair after its
first resource failure. Three paired seeds are used through 65,536 keys, one
above that size. Resource failures and unattempted larger cases remain explicit.

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_parallel \
  --output benchmarks/results/target-comparison --workers 4 \
  --memory-mib 768 --timeout 360
PYTHONPATH=src python3 -m balance_trees.benchmark_comparison_report \
  --input benchmarks/results/target-comparison
```

Repeating the runner command resumes completed trials from `trials.jsonl` and
requires matching settings. A source snapshot and SHA-256 checksums preserve
the worker implementations used for measurement. The report at
`report/index.html` includes all four requested metrics, the largest common
completed size, individual size limits, CSV/JSON downloads, 28 standalone SVG
charts, and `all-sequences.svg`. Maximum final height is the greatest final depth
observed across a group's completed seeds. Means have one-standard-error whiskers
when repeated trials exist; a single large trial has no uncertainty estimate.
Parallel runs compare shape and operation counts, without timing comparisons.
