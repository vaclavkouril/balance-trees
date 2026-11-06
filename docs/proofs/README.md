# Geometric repair: proof and triage

The [mathematical paper (PDF)](geometric-repair.pdf) and its
[LaTeX source](geometric-repair.tex) give the model, proofs,
counterexample, limitations, and primary references. It analyzes the existing
geometric target and local ancestor repair, not Brodal's different geometric
stopping rules. The formal model and its exact coverage are documented in the
Lean project under [`formal/`](../../formal/).

## Results and their scope

| Property | Status |
| --- | --- |
| Ordered keys, tree shape, and no per-node balancing metadata | Proved for every bit stream; the implementation stores a global insertion count and an external PRNG. |
| Rotations | At most two per successful insertion, deterministically. |
| Randomness | Fewer than two independent fair bits in expectation; an entropy-optimal sampler for the same target law is analyzed separately. |
| Repair work | Exactly characterized by the excess insertion depth. An adaptive adversary causes linear unconditional expected repair work on an infinite subsequence. |
| Increasing and decreasing inputs | Every node has logarithmic expected depth; conditional expected ancestor visits per insertion are less than one. |
| Arbitrary adaptive input | Both logarithmic expected node depth and constant expected repair time are disproved. The worst-case expected depth is Θ(n), as are expected visits along the constructed probe subsequence. |
| Arbitrary fixed input | Logarithmic expected node depth and unconditional constant expected repair time remain unresolved. |
| Optimality | A logarithmic lower bound on the maximum expected node depth applies to every BST; the monotone upper bound matches it asymptotically. |

The probability results assume independent fair bits. Python's seeded PRNG is a
deterministic implementation and is not a proof of independent randomness. The
conditional repair-time counterexample has positive but potentially small
probability; by itself it does not disprove an unconditional expectation
bound. The separate adaptive construction does establish unconditional linear
lower bounds over dense rational keys; see the paper for finite-horizon integer
embedding and the distinction from a fixed nonadaptive sequence.

## Comparing an adaptive treap input

The usual [treap analysis](https://faculty.washington.edu/aragon/pubs/rst89.pdf)
does not automatically extend to keys chosen from the observed tree. For a
simple insertion-only example with independent continuous priorities, insert
`0` and then `1`. If `0` is the root, insert `2`; otherwise insert `-1`.
The resulting three-node treap is always a chain: the current root has better
priority than the other old node, and the new key is an extreme. A treap on
three fixed keys instead has a chain with probability 2/3. The attacker uses
only the current tree shape to select the last key.

This proves that adaptive observation can change the treap distribution. It
does not prove a superlogarithmic expected-depth lower bound for insertion-only
treaps, nor does the geometric-repair counterexample establish such a bound.

## Reproduce the checks

From the repository root, compile the paper without placing build artifacts in
the source tree:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=/tmp/geometric-repair-paper docs/proofs/geometric-repair.tex
```

After updating the paper, copy the final PDF to both `docs/proofs/` and
`src/balance_trees/showcase/site/dist/`. The Pages tests check that the two
copies match so the website cannot silently publish an older proof.

The bounded independent transition check covers all ordered BST shapes with up
to six existing keys, each insertion gap, and every possible sampled target.
The adversarial explorer uses exact rational probabilities and the production
policy; its `--size 8` limit is a finite-state calculation, not an asymptotic
result.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_geometric_proof_conformance.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_proof_triage.py' -v
PYTHONPATH=src python3 benchmarks/proof_triage.py --size 8
```

Follow the formal project's instructions to build and audit Lean theorems.
Tests compare specified behavior with the Python pointer implementation on
bounded inputs; they do not constitute a proof of Python execution semantics.

## Review and proof quality

The investigation used independent tracks for deterministic and stochastic
proofs, adaptive counterexamples, Lean checking, and a separate review of the
counterexample's rotation cases and probability argument. The mathematical
paper was also compiled and checked for LaTeX warnings. Each result in the
paper is either proved with its assumptions or explicitly marked open; the Lean
README identifies which results have actually been machine-checked.

The following scores are an assessment of exposition, not correctness or
completeness. On a five-point scale, **5** is exceptionally clear or concise,
**3** is usable but requires substantial navigation, and **1** is difficult to
follow or needlessly long.

| Artifact | Readability | Compactness | Assessment |
| --- | ---: | ---: | --- |
| Mathematical paper | 4/5 | 4/5 | Seven pages, with explicit proofs and a separately stated adaptive construction; basic probability knowledge is assumed. |
| Lean development | 4/5 | 4/5 | Small named lemmas and a checked axiom audit make the formalized portions navigable; it covers only the subset listed in its README. |

The Lean score is not a claim that the adaptive counterexample, global depth
theory, or Python interpreter has been formally verified.
