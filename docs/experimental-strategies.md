# Experimental v2.1, v3 and v4 policies

These policies are available through `TreeFlavor.create`, the Python benchmark
CLI and both browser visualizer engines. They are insertion-only experiments.
No logarithmic-depth guarantee is established for any of them.

- `random-level-v2-1`: use `j.bit_length()` fresh bits for insertion ordinal
  `j`, starting at one. When the width grows, remap the previous extrema to
  `2 * lowest + 1` and `2 * highest`, then use v2's target bands and local
  repair. Coincident extrema temporarily leave an empty interior; integer
  rolls fall below the lower endpoint or above the upper endpoint. Rolls
  from this growing domain are not iid, so v2's expected-rotation proof does
  not transfer to v2.1.
- `random-level-v3`: track a fresh 64-bit priority but use no record override.
  Each non-root insertion stays a leaf with probability 1/10. Otherwise, for
  initial depth `d` and previous node count `n`, sample target depth `k` from
  `0..d-1` with weights `(d / (2 * ln(n)^2))^(d-k)` and promote the leaf
  `d-k` times. Depth one always reaches the root when the gate permits it.
  Float weights are scaled to avoid overflow; conditional probabilities are
  rounded to 53-bit rational coins. Sampling can take O(d) work and memory.
- `random-level-v4`: use v2 when `d < ln(n)`, and v3 otherwise. Equality and
  the empty-tree insertion use v3. Both branches share the same count and
  priority extrema and update state once per successful insertion.

Duplicate keys consume no bits, change no policy state and perform no rotations.
Python and browser PRNGs differ. Regression tests also feed identical bit streams
to both implementations to verify agreement through width changes and hybrid
dispatch. Browser numerical sampling uses the same rounding-to-even convention
as Python; floating-point libraries may differ at extreme rounding boundaries.

## Run small reproducible experiments

Run commands from the repository root with Python 3.11+; all output directories
below must be new. Raw local experiments under `benchmarks/results/` are ignored.

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark \
  --strategies random-level-v2-1 random-level-v3 random-level-v4 \
  --sizes 1000 4000 --trials 3 --seed 2026 --timeout 30 \
  --output benchmarks/results/experimental-policies
PYTHONPATH=src python3 -m balance_trees.benchmark_report \
  --input benchmarks/results/experimental-policies \
  --output benchmarks/results/experimental-policies/site

# Detailed single-run trace: pre-balancing depth, rolling mean, sampled height.
PYTHONPATH=src python3 -m balance_trees.insertion_depth_trace \
  --strategy random-level-v2-1 --size 1000 --sample-count 21 \
  --output benchmarks/results/insertion-trace

# Average pre-balancing insertion depth over whole runs at each final size.
PYTHONPATH=src python3 -m balance_trees.insertion_depth_compare \
  --sizes 1000 4000 --trials 3 \
  --output benchmarks/results/insertion-compare

# Average depth at each insertion index across independent input/rotation seeds.
PYTHONPATH=src python3 -m balance_trees.insertion_depth_by_time \
  --size 1000 --runs 3 --output-dir benchmarks/results/insertion-by-time

# Maximum over batches of seed-averaged measurements, not an adversarial bound.
PYTHONPATH=src python3 -m balance_trees.worst_case \
  --min-size 1000 --max-size 4000 --size-count 3 --runs 2 --seeds-per-run 3 \
  --output benchmarks/results/worst-batches

# Larger v3 sweep, sizes 2^1 through 2^17 across all seven input families.
PYTHONPATH=src python3 benchmarks/run_v3_report.py \
  --trials 3 --output benchmarks/results/v3-large
# Rebuild its charts without rerunning measurements.
PYTHONPATH=src python3 benchmarks/run_v3_report.py \
  --report-only --output benchmarks/results/v3-large
```

Depth means count edges from the root. Pre-balancing insertion depth differs
from final mean node depth and final tree height. The worst-batch tool records
the size and first seed of every batch; different metrics may attain their
maximum in different batches. Its plot uses mean rotations per inserted key.
Reference curves are numeric guides and provide no empirical or theoretical
upper bound. Rotation charts in the standard report use a linear vertical
scale and a `log2(log2(n))` reference; other metrics retain their logarithmic
vertical scale and `log2(n)` guide. Existing recorded reports remain preserved.
