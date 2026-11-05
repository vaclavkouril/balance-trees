# Benchmark methodology

Saved measurements and old report sites have been removed. Generate fresh runs
in a new directory under `benchmarks/results/`; generated output is ignored by
Git and is not bundled with the visualizer or static build.

## Run

Python 3.11+ and the standard library are sufficient. From the repository root:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark \
  --strategies random-level geometric-target-local-repair interval-target-local-repair \
  --orders random increasing converging --sizes 1000 4000 --trials 3 \
  --seed 2026 --timeout 30 --output benchmarks/results/my-run
```

Use `--help` to inspect supported strategies and input families. The seven
families are random, increasing, decreasing, converging, pairs, bitonic and runs.
Algorithm details are in [perfect-tree targets](perfect-tree-targets.md).
`interval-target-local-repair` selects Interval-target local repair; `interval-target-promotion`
selects the earlier interval-based promotion policy.

## Measurement boundaries

- Each timed trial runs in an isolated subprocess, sequentially, with a separate
  32-key warmup. Instrumented timings include search, balancing and counters;
  input generation, startup, final validation and rendering are excluded.
- Every completed trial checks ordering, parent links, absence of cycles and
  the complete key set. Depth counts edges from root depth zero; height is
  maximum final depth. Mean insertion depth is measured before balancing.
- Rotations count primitive promotions. Visits count rebalance inspections;
  scans count explicit structural recount work; logical bits count sampled
  fair bits. None of these counters is a bare algorithm timing.
- Deadlines cover subprocess startup, input preparation, warmup, insertion and
  validation. Timeout/error groups have explicit statuses; remaining trials
  in a stopped group are recorded as not run. Missing results are not zeros.
- A fixed input permutation is shared across strategies and trial indices at
  each size. Rotation seeds use deterministic SHA-256 derivation. Standard
  errors measure seed variation conditional on that input. A single trial
  provides no uncertainty estimate.
- Results are finite measurements, not balance proofs or asymptotic guarantees.
  Parallel shape/operation experiments should not be used for timing comparisons.

## Generated outputs

`config.json` records the machine, interpreter, seeds and method. `trials.jsonl`
is an append-only checkpoint; `trials.csv` records every status and measurement.
`summary.csv` holds group means and standard errors; `results.json` combines
metadata, trials and summaries.

The optional generic exporter can render fresh data locally:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_report \
  --input benchmarks/results/my-run --output benchmarks/results/my-run/report
```

These generated reports are experiment artifacts, not published website pages.
`balance_trees.benchmark_merge` combines compatible batches with disjoint sizes
without rerunning trials. Machine, interpreter, seeds and settings must match.
See [the runner guide](../benchmarks/README.md) for memory-capped and analysis tools.
