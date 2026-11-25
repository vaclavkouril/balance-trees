# Benchmark methodology

Generate fresh runs in a new directory under `benchmarks/results/`; raw working
results and native builds are ignored by Git. Reports explicitly requested for
publication are copied into the visualizer's static assets with their graphs,
data, and measured sources. This includes the target-strategy comparison, C++
probability comparison, and full BST insertion/mixed-update reports. See
[the runner guide](../benchmarks/README.md) for reproduction and report commands.

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

## Python insertion measurement boundaries

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

These generic reports are local experiment artifacts unless explicitly bundled
for publication.
`balance_trees.benchmark_merge` combines compatible batches with disjoint sizes
without rerunning trials. Machine, interpreter, seeds and settings must match.
See [the runner guide](../benchmarks/README.md) for memory-capped and analysis tools.

## Full BST mixed-update measurements

`balance_trees.benchmark_updates` benchmarks the C++ `geometric-full-bst` policy
with `p = 3/4`. The five fixed workloads are random churn, ascending churn,
descending churn, shrink/regrow, and read-heavy churn. Their exact key sequences
and the reproduction commands are in
[the workload guide](../benchmarks/README.md#mixed-workloads).

Each trial preloads `n` keys. Four workloads measure `n` deletions and `n` public
insertions. Read-heavy churn adds `8n` lookups, half successful, making its mix
80% lookups, 10% deletions, and 10% insertions. Timing per public operation divides
by `2n` or `10n` respectively. Comparing those averages does not directly compare
deletion speed, because the read-heavy denominator includes its cheaper lookups.

The tree's random seed and the operation-order seed are separately derived by
SHA-256. Repeated tree seeds at one workload/size use an identical operation
stream. That stream depends on the workload seed and operation index, not on
the resulting tree. A specified SplitMix64 generator and rejection-sampled
Fisher–Yates shuffle make it independent of the C++ standard library's shuffle
implementation. An FNV-1a64 fingerprint covers the preload and measured
operations; it identifies matching streams but is not a cryptographic checksum.
Source files are recorded separately with SHA-256 hashes.

The worker reserves capacity for the maximum live size before preloading.
It prepares operation chunks of at most 65,536 entries, then times their
execution. The measured loop includes searches, insertion and deletion,
random sampling, aggregate instrumentation, and checking each operation's
expected result and rotation budget. A successful deletion that leaves keys
present includes both complete refreshes, including their searches, raw removals,
and randomized reinsertions. The direct minimum-to-root move at a sweep wrap is
also included and counted separately from ordinary rotations. A deletion that
empties the tree performs no refreshes.

Process startup, operation generation, capacity reservation, preloading, checkpoint
validation, and rendering are excluded from the update timer. The worker records
preload insertion time separately. `elapsed_seconds` is the sum of measured wall
intervals; `cpu_seconds` is process CPU time over the same intervals. The runner
executes isolated subprocesses concurrently, so wall measurements include
scheduling delays and both timing measures can reflect shared-cache and
memory-bandwidth contention. They describe this concurrent execution, not
isolated latency or a speedup against another implementation. The insertion
suite also supports parallel workers; its historical wall timings should be
read with the recorded concurrency settings.

Checkpoint validation checks the exact live set using a bitmap, then checks
strict BST order, parent links, reachability, and absence of cycles. Equal size,
membership, and strict ordering together establish exact set equality. Churn
checkpoints occur after preload and near each quarter of the replacement rounds.
Shrink/regrow also records power-of-two live sizes on both sides of the empty
stage. The final tree's height and mean depth use edges from root depth zero.
An empty checkpoint has height `-1` and mean depth zero; the report draws that
height at zero. The sampled maximum height includes the preloaded tree and all
checkpoints, but does not measure the largest height after every individual
operation. Lines joining checkpoint observations are visual guides.

Insertion and deletion rotation means divide by their corresponding public
operation counts. Internal reinsertion rotations are charged to deletion.
Overall rotation and random-bit means divide by all measured public operations.
The two/four rotation limits are checked on every insertion/deletion, independent
of checkpoint placement. `minimum_moves` counts actual direct minimum moves,
so a wrap whose minimum is already the root adds zero to that counter.

Peak RSS is Linux `VmHWM` for the worker and includes input permutations,
reference-set and validation storage, and process overhead. Reserved node-array
bytes are reported separately. A 768 MiB `RLIMIT_AS` cap limits each entire
worker's address space, not just its tree. The wall deadline covers the entire
worker, including preparation and validation. A memory failure or timeout stops
that workload's remaining trials and larger sizes; their statuses remain
explicit and are not plotted as zeros. The launcher snapshots the measured
source, builds Release mode from it, and checkpoints each result for resumption.

For the configured 2026-11-24 run, both suites use starting sizes 1,024, 16,384,
262,144, 1,048,576, 4,194,304, and 16,777,216. There are three tree seeds through
65,536 keys and one above that threshold. The insertion suite schedules 210
trials across three strategies and seven insertion orders; the mixed suite
schedules 50 trials across five workloads. Two workers from each suite run
concurrently, for up to four workers in total, each with a 768 MiB cap and
1,800-second deadline. Counts describe the schedule; the downloaded records
state which trials completed.

The mixed report bundles `results.json`, `trials.csv`, `summary.csv`,
`checkpoints.csv`, and `source.zip`, alongside standalone SVG charts and the
explained proof PDF. Group means and error bars use sample standard deviations
across repeated tree seeds; the existing insertion comparison uses standard
errors. A single large-size trial has no uncertainty estimate. Source snapshots
and exact seeds allow reproduction, while finite measurements remain separate
from the mathematical height guarantee.
