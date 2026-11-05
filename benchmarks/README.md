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
