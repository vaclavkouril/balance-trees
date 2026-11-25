# Experimental balance trees

Binary search tree experiments in Python 3.11+, browser JavaScript, and C++20.
Python and JavaScript support insertion only; the native C++ implementation also
supports the full insertion/deletion algorithm from Chapter 6. Nodes contain
keys and structural pointers; policy state and measurement counters live outside
the tree.

## Strategies

- `geometric-full-bst` (C++ only): Chapter 6 with exact probability 3/4,
  successor-based deletion, two ordered refreshes per successful nonempty
  deletion, and a direct minimum-to-root move at each sweep boundary. Uses at
  most two rotations per insertion and four per deletion. See
  [the expanded explanation](docs/proofs/full-bst-explained.pdf) and
  [native usage](docs/native.md#full-bst-insertion-deletion-and-search).
- `random-level`: sample a vertex uniformly from the smallest perfect tree
  containing the current node count. Promote the inserted leaf to that depth
  only if it is deeper.
- `geometric-three-quarters`: geometric target sampling with exact probability
  3/4 and at most two local rotations. For insertion orders fixed independently
  of the random choices, the supplied proof establishes expected logarithmic
  height and logarithmic height with high probability. Both the Python and C++
  strategy factories accept this identifier. The maximum target is
  `ceil(log_{4/3}(n))`, computed exactly; each trial consumes two fair bits.
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

For `geometric-three-quarters`, the [probability paper (PDF)](docs/proofs/geometric-biased-repair.pdf)
and [LaTeX source](docs/proofs/geometric-biased-repair.tex) prove logarithmic height
for every fixed insertion order, and constant expected structural repair for
increasing inputs and uniform random permutations. The paper compares all seven
of Brodal's criteria, explicitly qualifying global size information and the cost
of computing the maximum target.

The separate [fair-coin paper](docs/proofs/geometric-repair.pdf) analyzes
`geometric-target-local-repair`: it proves monotone expected-depth bounds and
an adaptive counterexample; its arbitrary fixed-order depth question remains open.
[Proof instructions and status](docs/proofs/README.md) distinguish the two
strategies and explain the GitHub PDF builds and formal coverage.

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

The local visualizer remains at `http://127.0.0.1:8000`. Its **Mixed insert/delete
benchmarks** link opens the [full BST report](src/balance_trees/showcase/site/dist/benchmarks/full-bst/index.html),
with five update workloads, height traces, CPU and wall timings, rotation counts,
memory, downloadable measurements, and the explained proof. After a Pages
deployment, the
[online mixed-operation report](https://vaclavkouril.github.io/balance-trees/benchmarks/full-bst/)
serves the same bundle. The
[full BST insertion comparison](src/balance_trees/showcase/site/dist/benchmarks/full-bst-insertion/index.html)
covers all seven insertion families and the three native geometric policies.
Both suites reach 16,777,216 keys and record concurrency, seeds and measured sources.
The [previous probability comparison](src/balance_trees/showcase/site/dist/benchmarks/geometric-native/index.html)
and [earlier comparison](src/balance_trees/showcase/site/dist/benchmarks/index.html)
remain available. All four reports are included in the static web build.
Insertion traces mark comparisons, up/down
movement and the original inserted node. See [the visualizer guide](docs/showcase.md).

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
- `src/native/`: alternate C++20 implementation with compact indexed nodes,
  geometric repair, full BST deletion, and an extensible strategy factory; see
  [native build and parity testing](docs/native.md).
- `src/balance_trees/showcase/`: local trace API and browser visualizer.
- `tests/`: correctness, sampling, invariants, CLI and browser checks.
- `benchmarks/`: reproducible runners, separate from correctness tests.
- `docs/`: algorithms, development and execution guides.

See [adding a strategy](docs/adding-a-strategy.md) and
[static build instructions](docs/github-pages.md) for extension and hosting.
