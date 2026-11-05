# Lean proof: geometric target repair

This project uses Lean 4.35.0 and pins mathlib 4.35.0 in `lake-manifest.json`.
The current proofs use Lean's standard library; mathlib is pinned for subsequent
probabilistic work. With [elan](https://github.com/leanprover/elan) installed,
run from this directory:

```sh
MATHLIB_NO_CACHE_ON_UPDATE=1 lake build
python3 audit_axioms.py
```

The committed manifest locks transitive dependency revisions. The environment
variable skips downloading mathlib's precompiled cache, which these proofs do
not use. The proof CI runs separately from the website deployment.

## Checked claims

* `local_repair_result` applies the actual rotation instructions to each of the
  four valid local path shapes and checks the exact resulting tree.
  `local_repair_at_most_two_rotations` bounds the length of those traces.
* `runRotations_inorder` shows that the modeled rotations preserve the full
  inorder traversal. `local_repair_anywhere_preserves_bst` lifts this to any
  path of an immutable search tree. `insertAtLeaf_inorder_length` verifies the
  length change for insertion at an empty path, and `insertAtLeaf_key_count`
  establishes the exact key multiplicity change.
* `recursiveWalk_exact` and `recursiveWalk_matches_counter` connect a
  recursive model of ancestor visits with the arithmetic visit counter. They
  do not prove that Python's parent walk refines this model.
* `sampler_exact_expected_bits_scaled` enumerates all Boolean streams of length
  `L`, runs a model of the capped leading-one sampler, and proves their total
  bit cost plus 2 equals `2^(L+1)`. Uniform streams therefore give expected
  cost `2 - 2 / 2^L` for `L >= 1`. `sampler_cost_from_move` relates
  this cost model to the capped number of leading ones used by the target.
* `target_streams_partition` and `target_stream_lengths` split the complete
  fixed-length streams by prefixes `0`, `10`, and `11`. The accompanying
  target theorems prove that, for `k >= 2`, they yield targets `k`, `k - 1`,
  and at most `k - 2` respectively, with relative counts 1/2, 1/4, and 1/4.

`audit_axioms.py` audits each listed result and rejects `sorryAx` and any
axiom except Lean's standard `propext`, `Quot.sound`, and `Classical.choice`.
The current audited proofs use only `propext` and `Quot.sound`; some need no
axioms. There are no custom axioms or admitted proofs.

## Boundaries of the formalization

The model does not yet formalize ordered insertion, duplicate-key handling,
parent pointers, selecting the ancestor in a larger tree, or refinement from Python.
The complete target distribution, expected walk time, all-node expected depth,
adaptive inputs, and long-run tree behavior are not Lean theorems here.
The adaptive counterexample in the mathematical proof, including its failure
of logarithmic expected depth and constant expected repair, is not formalized.
The accompanying mathematical proof and status table explain the corresponding
proved and open claims. In particular, this project does not establish every
requested efficiency property.
