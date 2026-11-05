# Random level and geometric target local repair

Depths count edges, with the root at zero. Both new strategies maintain only a
successful-insertion count outside the nodes. The count `n` includes the new leaf;
duplicates consume no bits, perform no rotations and change no policy state.

## Random level: promote the inserted vertex

Select `random-level`, implemented by `RandomLevel` in `strategies/random_level.py`.
The reference is the smallest perfect tree that can contain `n` vertices, with
`L = n.bit_length()` levels and `2**L - 1` vertices. Draw an `L`-bit integer,
reject zero, and use `label.bit_length() - 1` as the target depth. For the
single-vertex tree, return zero without consuming bits.

Each reference vertex is equally likely, so depth `t` has probability
`2**t / (2**L - 1)`. This is exact perfect-tree level sampling; no previous
priority interval influences the target. For insertion depth `d`:

- If `d <= target`, keep the new leaf where it is.
- Otherwise promote **that inserted vertex** exactly `d - target` times.

This can require more than two rotations. Rejection sampling has no fixed
worst-case bit limit. No logarithmic-height or constant-rotation bound is claimed.

## Geometric target sampling with local repair

Select `geometric-target-local-repair`, implemented by
`GeometricTargetLocalRepair`. This follows the supplied LaTeX pseudocode:

1. Set `L = ceil(log2(n)) + 1`, computed exactly as `(n - 1).bit_length() + 1`.
2. Starting at `move = 0`, count leading one bits until a zero or `L` bits.
3. Set `target = max(0, L - move - 1)`.
4. If `d <= target`, return; if `d = target + 1`, promote the leaf once.
5. Otherwise walk to the ancestor at depth `target + 2`. For a straight
   left-left or right-right path, promote its parent once; for a bend,
   promote that ancestor twice.

There are at most two rotations on **every** insertion, with no record exception.
The inserted vertex need not reach the target; an ancestor subtree is repaired.
Ancestor walking can take O(d) steps. The sampler consumes at most `L` bits,
including a bit for the root insertion, as prescribed by the pseudocode.
Its depth distribution differs from uniform perfect-tree vertex sampling:
the last two possible `move` values both map to root depth zero.

## Descriptive name for the earlier v2 policy

`IntervalTargetLocalRepair` replaces the class name `RandomLevelV2`, with the
old import kept as an alias. The CLI identifier is
`interval-target-local-repair`, matching
`strategies/interval_target_local_repair.py`. The earlier CLI name has been
removed; Python imports of `RandomLevelV2` remain compatible. Its fresh
64-bit roll is mapped through the previous observed priority interval. Ordinary
insertions use the same local repair, but strict record minima can promote the
leaf all the way to the root. Those exceptions distinguish it from the new
LaTeX strategy's unconditional two-rotation limit.

The original leaf-promotion policy is still exposed as `TreapPriority` and is
selected with `interval-target-promotion`. Earlier experiments used the identifier `random-level` for that policy.
Saved benchmark datasets have since been removed.

For Interval-target local repair, the expected rotation bound under iid uniform
priority rolls from an empty tree is below three: with `k` previous insertions,
a strict record minimum has probability at most `1/(k+1)` and costs at most `k`
rotations; all other insertions cost at most two. Thus
`E[R] <= 2 + k/(k+1) < 3`. Finite-priority ties only reduce the chance of a strict
record. This is an expectation over the entire random history, not a guarantee
for each preexisting tree. It does not imply logarithmic depth or constant
ancestor-walk cost, and does not transfer to the growing-domain v2.1 sampler.

## Run

```sh
PYTHONPATH=src python3 -m balance_trees.demo --strategy random-level --keys 1 8 2 7 3 6 4 5 --seed 2026
PYTHONPATH=src python3 -m balance_trees.demo --strategy geometric-target-local-repair --keys 1 8 2 7 3 6 4 5 --seed 2026
PYTHONPATH=src python3 -m balance_trees.benchmark \
  --strategies random-level geometric-target-local-repair interval-target-local-repair \
  --orders random increasing converging --sizes 1000 4000 --trials 3 \
  --output benchmarks/results/perfect-tree-comparison
```

Both new policies run in Python, detailed browser traces and large browser
workers. Fixed-bit tests check identical Python/browser decisions, exact target
sampling, power-of-two boundaries, straight and bent repairs, duplicates and
structural invariants across all seven input families.
