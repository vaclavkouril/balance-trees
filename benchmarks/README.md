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

The geometric repair proof has an exact, small-state adversarial exploration:

```sh
PYTHONPATH=src python3 benchmarks/proof_triage.py --size 8
```

It enumerates target outcomes with rational probabilities and maximizes expected
final height over adaptive insertion gaps. The result is finite evidence, not an
asymptotic bound or a substitute for a proof.

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
Height, mean-depth and random-bit graphs include a dashed gray `c·log₂(n)`
guide. Each chart uses the largest endpoint value/log₂(n) ratio across its
implementations, with a minimum coefficient of 1. The legend prints that
coefficient; this is descriptive scaling, not a proven bound.

The current report is published with the visualizer. Refresh it from the saved
measurements, without rerunning benchmarks:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_comparison_report \
  --input benchmarks/results/target-strategies-20261105 \
  --output src/balance_trees/showcase/site/dist/benchmarks \
  --visualizer-href ../index.html
```

Only this requested web report and its supporting downloads are bundled. Raw
working directories remain ignored; the source ZIP contains the implementations
measured in that run, independently of later visualizer changes.

## Complete C++ geometric comparison

Run both the original fair-coin strategy and the new exact `p=3/4` strategy
without a Python benchmark baseline:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_native \
  --output benchmarks/results/geometric-native-20261112
PYTHONPATH=src python3 -m balance_trees.benchmark_comparison_report \
  --input benchmarks/results/geometric-native-20261112 \
  --proof-href geometric-biased-repair.pdf
cp docs/proofs/geometric-biased-repair.pdf \
  benchmarks/results/geometric-native-20261112/report/geometric-biased-repair.pdf
```

The default suite schedules **252 trials**: two strategies, all seven paper
input families, three seeds at 1,024 / 4,096 / 16,384 / 65,536 keys, and one
seed at 262,144 / 1,048,576 / 2,097,152 / 4,194,304 / 8,388,608 /
16,777,216 keys. Trials run sequentially with a 768 MiB address-space cap and
360-second wall deadline. A resource failure stops only that strategy/input
pair; later cases are recorded as `not_run`.

Use `--strategies`, `--orders`, or `--sizes` to select a subset. The two strategy
identifiers are `geometric-target-local-repair-native` and
`geometric-three-quarters-native`. Matching seed values and byte-identical
inputs are recorded with SHA-256 checksums, but the strategies consume different
numbers of bits. Source snapshots, compiler version, machine information, and
all trial statuses are saved in the output directory. Repeating the same command
resumes without repeating completed trials. Generated results stay under the
ignored `benchmarks/results/` directory. Open `report/index.html` for charts,
timings, downloadable measurements and sources, and the linked probability PDF.

The requested report is also bundled with GitHub Pages under
`benchmarks/geometric-native/`. Refresh it from the saved measurements:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_comparison_report \
  --input benchmarks/results/geometric-native-20261112 \
  --output src/balance_trees/showcase/site/dist/benchmarks/geometric-native \
  --visualizer-href ../../index.html \
  --proof-href ../../geometric-biased-repair.pdf
```

Only the requested report and its supporting downloads are tracked; the raw
working directory and native build remain ignored.

## Native extension of the comparison

Append C++ geometric repair to the saved five-strategy run without changing
any original measurements:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_native \
  --baseline benchmarks/results/target-strategies-20261105 \
  --output benchmarks/results/target-strategies-native-v2-20261105
PYTHONPATH=src python3 -m balance_trees.benchmark_comparison_report \
  --input benchmarks/results/target-strategies-native-v2-20261105 \
  --output src/balance_trees/showcase/site/dist/benchmarks \
  --visualizer-href ../index.html
```

The native runner snapshots and builds C++20 in Release mode, reuses the original
seven input generators and seed derivation, and checkpoints/resumes every trial.
It uses the full configured size schedule, three seeds through 65,536 keys, one
above, a 768 MiB native address-space cap, and a 360-second wall deadline. A failed
input family stops only its larger native cases. Each completed tree validates
its structure and exact keys. Different PRNGs mean native and Python histories
are not paired, despite matching seed values.

The report includes a sixth overlay curve, a native implementation appendix,
native insertion times and memory, 28 native-only SVGs and
`native-all-sequences.svg`, alongside the 28 combined figures and overview.
Native insertion timing excludes parsing, startup, reservation and validation;
there is no comparable Python timing in the original experiment. Native RSS uses
Linux `/proc/self/status` VmHWM to exclude the launcher's pre-exec RSS history.
Node storage is separately reported as reserved array bytes, excluding inputs,
allocator/process overhead and validation. All sources and raw records are
downloadable from the report. The `v2` run uses the corrected RSS measurement;
the interrupted first native working directory is not used in the report.
