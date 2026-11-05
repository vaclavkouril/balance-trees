# Experimental balance trees

Insertion-only binary search tree experiments in Python 3.11+ and browser
JavaScript. Nodes contain keys and structural pointers; policy state and
measurement counters live outside the tree. Deletion is not implemented.

## Strategies

- `random-level`: sample a vertex uniformly from the smallest perfect tree
  containing the current node count. Promote the inserted leaf to that depth
  only if it is deeper.
- `geometric-target-local-repair`: capped geometric target sampling followed
  by the supplied straight/bent ancestor repair, with at most two rotations.
- `interval-target-local-repair`: **Interval-target local repair**, implemented by
  `IntervalTargetLocalRepair` (`RandomLevelV2` remains a compatibility alias).
- `interval-target-promotion`: the original interval-based leaf promotion.
- Other references include halving and constant-probability walks, inverse-depth,
  paper Zig/ZigZag, recount/window root lotteries, hash priorities, and
  experimental v2.1/v3/v4 policies.

See [perfect-tree target algorithms](docs/perfect-tree-targets.md),
[experimental policies](docs/experimental-strategies.md), and
[priority-free strategies](docs/priority-free-strategies.md). The stopping-rule
references are inspired by [Brodal's paper](https://arxiv.org/abs/2404.08287).

For the geometric repair rule, the [mathematical proof](docs/proofs/geometric-repair.tex)
establishes constant rotations and expected random bits, and logarithmic expected
node depth for monotone insertion sequences. It also gives an adaptive sequence
with linear expected depth and repair work, while general bounds for fixed
sequences remain unresolved. [Proof instructions and status](docs/proofs/README.md)
describe the key-domain assumptions, formal model, and checks.

## Run and test

Run from the repository root. Python execution and tests use the standard
library; browser model tests require Node.js 24+. Ruff is optional development
tooling.

```sh
PYTHONPATH=src python3 -m balance_trees.demo --strategy random-level --keys 1 8 2 7 3 6 4 5 --seed 2026
PYTHONPATH=src python3 -m balance_trees.showcase --port 8000
PYTHONPATH=src python3 -m unittest discover -s tests -v
node tests/test_showcase_browser.mjs
node tests/test_large_showcase.mjs
```

The local visualizer remains at `http://127.0.0.1:8000`. Its **Benchmark results**
link opens the [current five-strategy comparison](src/balance_trees/showcase/site/dist/benchmarks/index.html),
also included in the static web build. Insertion traces mark comparisons,
up/down movement and the original inserted node. See [the visualizer guide](docs/showcase.md).

Optional editable installation and formatting:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ruff check src tests benchmarks
.venv/bin/ruff format src tests benchmarks
```

## Fresh experiments

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark \
  --strategies random-level geometric-target-local-repair interval-target-local-repair \
  --orders random increasing converging --sizes 1000 4000 --trials 3 \
  --output benchmarks/results/my-run
```

Use a new output directory for each run. Generated data is ignored by Git.
See [benchmark methodology](docs/benchmarks.md) and
[benchmark tools](benchmarks/README.md).

## Layout

- `src/balance_trees/`: BST, rotations, strategies, measurements, CLI tools.
- `src/balance_trees/showcase/`: local trace API and browser visualizer.
- `tests/`: correctness, sampling, invariants, CLI and browser checks.
- `benchmarks/`: reproducible runners, separate from correctness tests.
- `docs/`: algorithms, development and execution guides.

See [adding a strategy](docs/adding-a-strategy.md) and
[static build instructions](docs/github-pages.md) for extension and hosting.
