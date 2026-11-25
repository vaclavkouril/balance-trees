# Benchmark tools

Generate measurements under ignored `results/` directories. Use a new directory
for each experiment. Raw working runs and builds are not tracked; explicitly
requested web reports and their supporting downloads are retained with the
visualizer. Keep correctness tests in `tests/`.

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
16,777,216 keys. By default, trials run sequentially with a 768 MiB address-space
cap and 360-second wall deadline. Set `--workers` to run independent native
trials concurrently; equal order/size cases share one prepared input file. A
resource failure stops only that strategy/input pair; later cases are recorded
as `not_run`.

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

<a id="full-bst-preparation"></a>

## Full BST insertion and mixed operations

The C++ `geometric-full-bst` policy implements
[the explained Chapter 6](../docs/proofs/full-bst-explained.pdf), including deletion
and its two ordered refreshes. Its insertion path is identical to
`geometric-three-quarters` for equal input and random bits. The insertion suite
compares all three native strategies across all seven input families; the mixed
suite exercises the full BST's deletion schedule and searches.

The following two commands reproduce the configured 2026-11-24 experiment.
Run them in separate terminals to use two workers per suite, four in total.
Use new output directory names for a new experiment; repeating an existing
command resumes that run and requires identical settings.

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_native \
  --strategies geometric-target-local-repair-native geometric-three-quarters-native geometric-full-bst-native \
  --sizes 1024 16384 262144 1048576 4194304 16777216 \
  --small-trials 3 --repeat-through 65536 --seed 2026 \
  --workers 2 --memory-mib 768 --timeout 1800 \
  --output benchmarks/results/full-bst-insertion-20261124
```

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_updates \
  --sizes 1024 16384 262144 1048576 4194304 16777216 \
  --small-trials 3 --repeat-through 65536 --seed 2026 \
  --workers 2 --memory-mib 768 --timeout 1800 \
  --output benchmarks/results/full-bst-updates-20261124
```

The configured schedules contain **210 insertion trials** and **50 mixed trials**.
At 1,024 and 16,384 keys there are three tree seeds; each larger size has one.
The largest starting set is 16,777,216 keys. Each mixed trial measures `2n`
public operations, except `read-heavy`, which measures `10n`. Preloading adds
another `n` insertions outside the update timer. Failed or skipped trials remain
explicit in the records; scheduled counts are not claims that every trial
completed.

The retained 2026-11-24 run completed all 260 trials successfully: 469,023,744
measured insertions and 402,020,352 measured mixed operations. Every workload
reached the largest configured size. Preload insertions are additional and are
excluded from those totals.

Four workers each capped at 768 MiB can together reserve about 3 GiB of address
space, in addition to launchers, input preparation, and other programs. Reduce
`--workers` if the machine lacks spare memory. The wall deadline covers startup,
generation, preload, execution, and validation, not only the measured loop.
Parallel wall times include scheduling delays. Process CPU times exclude those
delays but can still reflect cache and memory contention, so neither series is
an isolated latency measurement or evidence of a speedup between policies.

### Mixed workloads

All trials begin with keys `0, …, n - 1`. Random preloads and deletion orders use
seeded permutations. A replacement round deletes its selected key before
inserting a fresh key, temporarily leaving `n - 1` live keys.

| Name | Preload and measured operations |
| --- | --- |
| `random-churn` | Preload in shuffled order. Independently shuffle the original keys for deletion; round `i` deletes the next original key and inserts `n + i`. Fresh keys arrive in increasing order. |
| `ascending-churn` | Preload in increasing order; round `i` deletes `i` and inserts `n + i`. |
| `descending-churn` | Preload in decreasing order; round `i` deletes `n - 1 - i` and inserts `-1 - i`. This reverses the key direction relative to the increasing refresh sweep. |
| `grow-shrink` | Preload in shuffled order. Delete all original keys in a second shuffled order, reaching empty; then insert `n + key` in that same second order, returning to `n` live keys. |
| `read-heavy` | Use the random-churn replacements. Before each replacement, perform four lookups drawn uniformly from the current live set and four drawn uniformly from the absent range `2n, …, 3n - 1`, alternating hits and misses. |

The workload seed is separate from the tree's seed. All repeated tree seeds
for one workload/size share exactly the same operation stream, chosen without
observing the tree. SHA-256 seed derivation, the source snapshot, and a recorded
operation fingerprint make the sequence reproducible.

Operations are prepared in chunks of at most 65,536 before each timed loop.
Timing includes public methods, aggregate counters, and both complete refreshes
after each successful deletion that leaves a nonempty tree. Generation,
reservation, preload, and validation are excluded; preload time is recorded
separately. Checkpoints verify exact live membership against a bitmap plus BST
ordering, parent links, reachability, and size. Every operation checks its
expected outcome and rotation limit. Height is sampled at checkpoints; the
reported sampled maximum is not the maximum over every update. See
[the full measurement boundaries](../docs/benchmarks.md#full-bst-mixed-update-measurements).

### Build the web reports

Render saved results without rerunning trials. Use fresh output directories for
new reports; the mixed-report renderer refuses to overwrite an existing one.

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_comparison_report \
  --input benchmarks/results/full-bst-insertion-20261124 \
  --output src/balance_trees/showcase/site/dist/benchmarks/full-bst-insertion \
  --visualizer-href ../../index.html \
  --proof-href ../full-bst/full-bst-explained.pdf
PYTHONPATH=src python3 -m balance_trees.benchmark_updates_report \
  --results benchmarks/results/full-bst-updates-20261124 \
  --output src/balance_trees/showcase/site/dist/benchmarks/full-bst \
  --proof docs/proofs/full-bst-explained.pdf \
  --insertion-href ../full-bst-insertion/index.html \
  --visualizer-href ../../index.html
```

The report entry points are `benchmarks/full-bst/index.html` and
`benchmarks/full-bst-insertion/index.html` in the static website. The mixed report
includes workload filters, portable SVG graphs, all trial statuses, per-trial
and summary CSV files, checkpoint CSV, raw JSON, the measured source ZIP, and the
explained algorithm PDF. Its means and error bars use sample standard deviations
across repeated tree seeds; the insertion report uses standard errors. A single
large trial provides no uncertainty estimate. See
[the Pages build instructions](../docs/github-pages.md) to preview and publish
the bundled reports. Working runs and build directories remain ignored.

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
