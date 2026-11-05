# Global Coding Standards

1. **YAGNI**: Build only what is needed.
2. **DRY**: Extract shared patterns after the second duplication, not before.
3. **Fail Fast**: Prefer explicit errors over silent failures.
4. **Simple First**: Write the obvious solution; optimize only when needed.
5. **Delete Aggressively**: Less code means fewer bugs.
6. **Semantic Naming**: Use descriptive, self-documenting names for variables,
   parameters, and API endpoints. Favor comprehension over brevity, for example
   `wait_until_obs_is_saved`.

# Repository Guidelines

- Python 3.11+ sources belong in `src/`, tests in `tests/`, benchmarks in
  `benchmarks/`, and documentation in `docs/`. Browser assets live in
  `src/balance_trees/showcase/site/dist/`. Keep hidden directories for tooling.
- Use Ruff with the configuration in `pyproject.toml`. Keep tree operations and
  invariant checks focused; explain non-obvious balancing rules in comments.
- Add deterministic tests for behavior changes and regressions. Cover empty trees,
  duplicates, insertion, lookup, and structural invariants after mutations.
  Deletion is outside the current insertion-only implementation.
- Keep generated benchmark results out of source control. Use fresh output
  directories, record seeds and methodology, and retain results only when
  requested. Support performance claims with reproducible inputs and explain
  complexity tradeoffs.
- Keep setup and layout in `README.md`; see `docs/benchmarks.md` and
  `benchmarks/README.md` for benchmark commands. Discover files with
  `rg --files --hidden -g '!.git'`.

Run from the repository root (Node.js 24 for browser checks; install Ruff for lint):

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node tests/test_showcase_browser.mjs
node tests/test_large_showcase.mjs
ruff check src tests benchmarks
ruff format src tests benchmarks
PYTHONPATH=src python3 -m balance_trees.showcase --port 8000
PYTHONPATH=src python3 -m balance_trees.showcase.build --output _site
```

The static build requires a fresh output directory. Use concise imperative commit
subjects. PRs should state the problem, resulting behavior, validation commands
and results, and related issues when available.
