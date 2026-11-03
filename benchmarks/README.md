# Benchmarks

Run `PYTHONPATH=src python3 -m balance_trees.benchmark --help` from the repository
root. Raw run directories under `results/` are ignored to protect source history
from local experiments. Each run requires a new directory.

The completed machine measurements, all statuses, CSV/JSON downloads and SVG
graphs shipped with the website are in
`src/balance_trees/showcase/site/dist/results/`.

See [methodology and reproduction](../docs/benchmarks.md). Correctness tests are
separate in `tests/`; a small subprocess test checks the benchmark/report pipeline.

The [experimental policy guide](../docs/experimental-strategies.md) describes
v2.1, v3, v4, the insertion-depth tools, worst seed-averaged batches and the
larger `benchmarks/run_v3_report.py` sweep, with small reproduction commands.

## Random level v2 against treap

Open [the combined comparison](v2-treap/index.html) or the standalone
[three-panel SVG](v2-treap/comparison.svg). Each panel overlays both strategies
for random, increasing and converging insertion orders. Metrics are final mean
node depth, final maximum depth (height), and primitive rotations per key.
Depths count edges, starting at zero; mean depth is not height averaged over
the insertion history.

The sweep uses the union of all 20 archived benchmark sizes, from 1,000 to
2,097,152 keys. It reuses the 27 matching archived v2 trials and runs the 129
missing trials in four processes. There are three paired trials at 1,000,
16,000 and 128,000 keys, and one paired trial at each other size. Seeds and
permutations use the existing benchmark's deterministic derivation. The treap
uses the existing Python showcase's stored 32-bit priorities and key tie breaker;
it is distinct from the `hash-priority` strategy.

```sh
PYTHONPATH=src python3 benchmarks/compare_v2_treap.py --workers 4
PYTHONPATH=src python3 -m balance_trees.treap_comparison_report
PYTHONPATH=src python3 -m unittest discover -s tests -p test_v2_treap_comparison.py -v
```

The runner resumes its append-only checkpoint. `v2-treap/` retains raw trials,
summaries, seed/machine configuration and the source archive's SHA-256 checksum.
Every fresh trial validates ordering, parent pointers, cycles and the full key
set; treap depths also match an independently reconstructed Cartesian tree.
Small regression tests verify exact agreement with the existing showcase treap.
Parallel execution is used for shape and operation counts; elapsed-time
comparisons are excluded. Whiskers show one standard error where three trials
exist. A single trial supplies no estimate of uncertainty.

The separate showcase page is `/v2-treap.html`, linked from the visualizer and
all existing reports. Its SVG and CSV/JSON downloads live in
`src/balance_trees/showcase/site/dist/v2-treap-results/` and enter the normal
static build. Regenerate the page from the saved results using the report
command above; no benchmark rerun is needed.

`random-level-v2/` retains the separate policy's 63-trial validation, group
summaries and comparisons against paired trials from the original dataset.
See [the policy, bound and reproduction instructions](../docs/random-level-v2.md).

For a larger, memory-capped random-level test on Linux:

```sh
PYTHONPATH=src python3 benchmarks/random_level_scale.py \
  --min-power 10 --max-power 21 --memory-mib 1024 --timeout 360 \
  --output benchmarks/results/my-random-level-scale
```

This tests every power of two from 1,024 through 2,097,152 keys, including
exactly 2^16, across all seven workloads. Each isolated trial validates the final
BST ordering, parent pointers, absence of cycles, and complete key set. The
default is one trial per group with seed 2026 and a 360-second deadline; use
`--trials 5` for repeated measurements or raise `--max-power` to explore further.
The 1 GiB address-space cap applies to input generation, insertion, and validation.
Memory exhaustion is recorded as an error; incomplete trials make the runner
exit unsuccessfully. `memory.json` records the effective cap and largest child
process's peak resident memory, including validation.

The checked-in [powers-of-two sweep](random-level-scale/results.json),
[summary CSV](random-level-scale/summary.csv), and
[memory measurement](random-level-scale/memory.json) preserve this larger test
separately from the existing five-trial website measurements. One trial provides
no standard error and does not establish a balance or complexity guarantee.

The recorded sweep completed all 77 trials in 649 seconds. Peak child resident
memory was 311,812,096 bytes (297.4 MiB), including validation. At 2^20 keys,
final heights ranged from 46 to 94 edges across the seven workloads.

The [repeat sweep](random-level-scale-recheck/results.json) reruns the original
sizes and extends every workload to 2^21 (2,097,152 keys), using the explicit
insertion-depth cap. Regenerate its website graphs with:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_report \
  --input benchmarks/random-level-scale-recheck \
  --output src/balance_trees/showcase/site/dist --random-level-scale
```

Open `/random-level-scale.html` on the local showcase server. The dedicated
page and `random-level-scale-results/` downloads preserve the earlier reports.

The repeat sweep completed all 84 trials in 1,277 seconds. Peak child resident
memory was 597,504,000 bytes (569.8 MiB), below the 1 GiB address-space cap.
All 77 repeated trials matched every original non-timing metric exactly;
[validation.json](random-level-scale-recheck/validation.json) records the
comparison and baseline checksum. The seven new 2^21 trials passed final
invariant checks, with heights ranging from 54 to 110 edges.
