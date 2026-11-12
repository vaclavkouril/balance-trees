# Native C++ implementation

`src/native/` is an alternate, standalone C++20 source folder. It implements the
Python insertion pipeline, BST rotations, `geometric-target-local-repair`, and
`geometric-three-quarters`. The `none` baseline is also available. C++ provides fixed-width storage and a
strategy factory without adding dependencies. It is not yet wired into the
browser visualizer. A native benchmark runner compares both geometric strategies
across all seven input families, or extends a saved Python comparison; see
[benchmark commands](../benchmarks/README.md#complete-c-geometric-comparison).

## Build and run

From the repository root, using a C++20 compiler and CMake 3.16+:

```sh
cmake -S src/native -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --parallel
ctest --test-dir build/native --output-on-failure
printf '1 8 2 7 3 6 4 5\n' | build/native/balance-tree --seed 2026 --reserve 8
PYTHONPATH=src python3 -m unittest discover -s tests -p test_native.py -v
```

The CLI reads whitespace-separated signed 64-bit keys from standard input. It
emits a JSON summary of attempts, distinct nodes, primitive rotations, logical
random bits, ancestor visits, maximum edge depth, reserved node storage, and
input-plus-insertion elapsed seconds. Empty-tree height is reported as zero.
Malformed keys/options, unknown strategies, and exhausted scripted bits fail
with a nonzero exit status. Validation runs after insertion timing. The elapsed
time includes parsing and is not a standalone algorithm benchmark.

Use `--trace` for per-insertion JSON with the original insertion depth, logical
bit count, visits, rotation distances, and full indexed topology. This also
validates after every operation and costs O(n) per insertion; do not enable it
for performance measurements. Node indices follow successful insertion order;
`4294967295` represents a missing link. `--bits 110010...` supplies an explicit
bit stream, overriding the seed, for deterministic comparisons.

## Behavior and storage

The original `geometric-target-local-repair` samples `L = bit_width(n - 1) + 1`,
counts leading ones through the first zero or L bits, and chooses
`max(0, L - move - 1)`. The new `geometric-three-quarters` starts at the exact
integer depth `ceil(log_(4/3)(n))`, then decreases it with probability 3/4 until
a trial fails or the target reaches zero. Sampling happens even when the leaf
needs no repair. Duplicate insertions consume no bits and do not
advance the strategy's count. Straight paths promote the parent once; bent paths
promote the selected cursor twice. These are the same rules, visits, and rotation
distances as Python, including the one-edge repair case.

Keys use signed 64-bit integers, rather than Python's arbitrary-size integers.
Three 32-bit indices replace three native pointers. Separate contiguous arrays
avoid structure padding and use **20 bytes per node of array payload**. The tree
allows at most `2^32 - 1` distinct keys, reserving one index value for null.
Capacity grows geometrically unless reserved in advance. `storage_bytes` reports
actual array capacity, excluding vector objects, allocator overhead, strategy,
random state, and temporary validation memory. Calling `reserve(n)` before an
experiment avoids growth allocations. Indices remain valid across growth; no
node addresses are exposed. There is no per-node balancing metadata.

The default bit source is SplitMix64, with a 64-bit state and a 64-bit buffer.
It consumes each generated word least significant bit first and reuses every
remaining bit. The original fair-coin target consumes fewer than two logical
bits in expectation; the 3/4 target consumes fewer than eight. These expectations
assume the algorithm's ideal independent-bit model; the PRNG is a reproducible
simulation source, not a cryptographic generator. Scripted
test bits are also packed into 64-bit words. The seed does **not** reproduce
Python's Mersenne Twister stream: compare implementations with identical explicit
bits. `tests/test_native.py` checks complete topology and statistics after each
insertion against Python for ordered, alternating, random, duplicate, and
extreme-key inputs. It builds in a temporary directory and skips only when the
configured `CXX` compiler (default `c++`) is unavailable.

Instrumentation stays outside nodes. Ordinary insertions count rotations without
allocating a rotation trace; pass `true` as the third `TreeFlavor` constructor
argument to retain distances. Tree validation is iterative, including on linear
chains. Lookup and insertion take O(height); repair makes at most two rotations
but may traverse O(height) ancestors. No universal logarithmic-height or measured
speedup claim is made.

## Add a strategy

Implement `Strategy::rebalance(RebalanceContext&)` and register a creator with
`StrategyFactory::register_strategy(name, creator)`. Each call to `create(name)`
must return a fresh strategy instance. The factory rejects empty or duplicate
registrations, unknown names, and null creators/results. Compose the created
strategy with `TreeFlavor`; its private tree starts empty and rebalances only
successful insertions. Strategies use context `promote()` to rotate and record
measurements. This keeps BST storage independent of policy selection.

Like the Python pipeline, insertion is not transactional if a strategy throws
(for example, when a scripted bit tape runs out). Such errors terminate the CLI;
do not continue using that flavor after a failed rebalance.

For memory and runtime experiments, use a Release build, fixed input sequences,
explicit seeds, and `--reserve`; keep inputs and outputs in fresh ignored
`benchmarks/results/` directories. Record compiler, flags, hardware, sequence
generation, and seed. Compare equal workloads and report parsing separately
when making algorithm performance claims.

The `geometric-three-quarters` strategy implements the same local repair with
independent probability 3/4 target decreases. It computes the maximum target
exactly from integer thresholds and consumes two fair bits per trial; no bits
are consumed for the first insertion. Python and native implementations accept
the same strategy identifier and scripted-bit semantics. The logarithmic height
guarantee assumes a fixed insertion sequence independent of the random choices.
