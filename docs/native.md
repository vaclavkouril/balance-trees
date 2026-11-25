# Native C++ implementation

`src/native/` is an alternate, standalone C++20 source folder. It implements the
Python insertion pipeline, BST rotations, `geometric-target-local-repair`,
`geometric-three-quarters`, and Chapter 6's `geometric-full-bst` with deletion.
The `none` baseline is also available. C++ provides fixed-width storage and a
strategy factory without adding dependencies. It is not yet wired into the
browser visualizer. The native insertion benchmark compares the geometric
strategies across all seven input families, or extends a saved Python comparison.
A separate mixed-operation runner measures the full BST's insertions, deletions,
and searches; see
[benchmark commands](../benchmarks/README.md#full-bst-insertion-and-mixed-operations).

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
for performance measurements. Without deletions, node indices follow successful insertion order;
`4294967295` represents a missing link. `--bits 110010...` supplies an explicit
bit stream, overriding the seed, for deterministic comparisons.

## Behavior and storage

The original `geometric-target-local-repair` samples `L = bit_width(n - 1) + 1`,
counts leading ones through the first zero or L bits, and chooses
`max(0, L - move - 1)`. The new `geometric-three-quarters` starts at the exact
integer depth `ceil(log_(4/3)(n))`, then decreases it with probability 3/4 until
a trial fails or the target reaches zero. Sampling happens even when the leaf
needs no repair. Duplicate insertions consume no bits and do not
change the size. Sampling uses the current size after insertion, including
reinsertions after a deletion. Straight paths promote the parent once; bent paths
promote the selected cursor twice. These are the same rules, visits, and rotation
distances as Python, including the one-edge repair case.

Keys use signed 64-bit integers, rather than Python's arbitrary-size integers.
Three 32-bit indices replace three native pointers. Separate contiguous arrays
avoid structure padding and use **20 bytes per node of array payload**. The tree
allows at most `2^32 - 1` distinct keys, reserving one index value for null.
Capacity grows geometrically unless reserved in advance and is retained after
deletions. Growth can copy O(n) array elements at a capacity boundary; reserve
the maximum live size before measuring individual update latency.
`storage_bytes` reports
actual array capacity, excluding vector objects, allocator overhead, strategy,
random state, and temporary validation memory. Calling `reserve(n)` before an
experiment avoids growth allocations. Indices remain valid across growth, but
public deletion may relocate the last live slot to keep the arrays compact.
Reacquire indices by key after deletion; no node addresses are exposed.
There is no per-node balancing metadata.

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
speedup claim is made for the collection of experimental strategies.

## Full BST: insertion, deletion, and search

`geometric-full-bst` implements the algorithm in
[the explained Chapter 6](proofs/full-bst-explained.pdf), using its exact
`p = 3/4` choice. Its insertion behavior matches `geometric-three-quarters` for
identical input and random bits. Deletion first removes the requested key using
the successor whenever a right subtree exists, including for a node with only
a right child. If any keys remain, it refreshes two surviving keys in increasing
cursor order. Each refresh removes and reinserts the selected key with fresh
sampling trials. At a wrap, it moves the minimum directly to the root before
refreshing it.

The cursor stores the last refreshed **key value**, even if that key is later
deleted. An empty optional value represents the formal lower endpoint, so
`INT64_MIN` remains a valid stored key. Only a public deletion that empties the
tree resets the cursor. Refreshing a singleton visits that same key twice,
consumes no random bits, and preserves the cursor between visits. Missing-key
deletions and duplicate insertions consume no random bits or refreshes.

Read an operation stream with `--updates`:

```sh
build/native/balance-tree --strategy geometric-full-bst --updates --seed 2026 --trace <<'EOF'
insert 20
insert 10
insert 30
delete 20
insert 5
insert 25
delete 30
contains 25
EOF
```

Use `--bits` for a scripted stream as in insertion mode. With `--trace`, each
operation reports the cursor and validated topology. Deletions also report
`erased`, `refreshes`, the selected `refreshed_keys`, actual `minimum_moves`,
rotations, random bits, and walk counts. A sweep boundary whose minimum is
already the root needs no physical move and contributes zero to `minimum_moves`.
Without `--trace`, the CLI reports aggregate counts and final height.
`input_and_update_seconds` includes input parsing. Use the dedicated
`native-update-benchmark` worker below for mixed-workload measurements.

The same operations are available directly in C++:

```cpp
using namespace balance_trees;
TreeFlavor tree(StrategyFactory{}.create("geometric-full-bst"), RandomBits(2026));
tree.reserve(100000);
InsertionStats insertion = tree.insert(20);
tree.insert(10);
DeletionStats deletion = tree.erase(20);
bool present = tree.tree().contains(10);
tree.tree().depths(); // Structural validation; keep outside benchmark timing.
```

`DeletionStats::visits` counts repair ancestor visits, like insertion statistics.
Its separate `search_visits` counts deletion, minimum, successor, and reinsertion
search walks. Trace vectors remain empty unless tracing was enabled in the
constructor. There are at most two rotations per insertion and four per deletion.
The direct minimum move is counted separately and uses constant link updates.
Refreshes reuse the detached node slot without allocating; public deletion's
storage compaction updates only the relocated node's parent and children.

The other strategies remain insertion-only: calling `TreeFlavor::erase` on them
fails before changing the tree. The insertion benchmark runner accepts
`geometric-full-bst-native` explicitly and measures only its insertion path.
Its default comparison remains the original two strategies. Use
`balance_trees.benchmark_updates` to measure the deletion schedule; see
[the benchmark commands](../benchmarks/README.md#full-bst-insertion-and-mixed-operations).

Native tests check all insertion permutations through six keys for raw deletion
and reinsertion, deep minimum moves, absent cursor keys, singleton/empty trees,
extreme keys, and sampling after shrinkage. Mixed operations are checked against
`std::set`; Python conformance tests independently compare complete keyed tree
shapes against immutable implementations of Chapter 6's operations under identical
scripted bits. These are correctness checks, not a verification of the height
theorem. The theorem assumes operations fixed independently of the random bits.

## Mixed-operation benchmark worker

The Release build includes a Linux worker with this argument order:

```sh
build/native/native-update-benchmark 2026 1048576 768 random-churn 7331
```

The arguments are the tree's random seed, starting live size, address-space cap
in MiB, workload name, and operation-order seed. The worker emits one JSON record.
The Python runner builds a source snapshot, derives and records both seeds,
limits concurrent workers, enforces wall deadlines, and saves resumable results:

```sh
PYTHONPATH=src python3 -m balance_trees.benchmark_updates \
  --output benchmarks/results/my-mixed-run --workers 4 \
  --sizes 1024 16384 262144 1048576 4194304 16777216 \
  --memory-mib 768 --timeout 1800 --seed 2026
```

Every trial reserves space for `n` keys and preloads a tree of that size.
`random-churn`, `ascending-churn`, and `descending-churn` perform `n` pairs of
one deletion followed by one insertion, so the live size alternates between
`n - 1` and `n`. `grow-shrink` deletes all `n` keys, then inserts a new set of
`n` keys. `read-heavy` performs eight lookups, one deletion, and one insertion
per round, giving 80% lookups, 10% deletions, and 10% insertions. Half its
lookups succeed. The exact key orders are listed in
[the workload table](../benchmarks/README.md#mixed-workloads).

The worker prepares at most 65,536 operations at a time before starting that
chunk's timer. Timed loops include search, public updates, deletion's internal
refreshes, random sampling, outcome checks, and aggregate counters. A deletion
that leaves a nonempty tree pays for both complete refreshes; a deletion that
empties it performs none. Generation, reservation, preload, and checkpoint
validation are excluded. `preload_seconds` reports the initial insertion loop
separately. `elapsed_seconds` sums measured wall intervals, `cpu_seconds` sums
process CPU time over those intervals, and `worker_seconds` also includes
preparation and validation. Process CPU time excludes descheduling, but still
reflects contention for shared caches and memory when trials run concurrently.

At checkpoints, `BST::depths()` verifies strict key ordering, parent links,
reachability, and absence of cycles. A compact reference bitmap checks exact
membership and the live size. Every measured operation must have its expected
outcome, and every insertion/deletion must respect its two/four-rotation limit.
Checkpoints include the preloaded tree, quarter-round boundaries for churn,
and power-of-two live sizes while shrinking and regrowing, including empty and
singleton trees. `sampled_max_height` is the maximum **at these checkpoints**;
it is not the maximum after every individual update. This worker represents an
empty tree's height as `-1`, unlike the interactive CLI's zero convention.

Insertion and deletion rotation means use their respective public operation
counts. Refresh reinsertions belong to deletion's counters. Overall means divide
by all measured public operations, including lookups in `read-heavy`.
`minimum_moves` counts actual direct minimum-to-root moves, separately from
rotations. Peak RSS includes the worker, input permutation, reference bitmap,
and validation storage; `node_storage_bytes` counts only reserved node arrays.
The address-space cap applies to the whole worker and is not a tree-memory limit.

The operation stream is fixed independently of tree randomness. The order
generator uses an explicitly defined SplitMix64/Fisher–Yates implementation with
rejection sampling. `operation_fingerprint` is an FNV-1a64 checksum of the preload
and measured operation stream, useful for matching runs rather than cryptographic
integrity. The runner records SHA-256 hashes of its measured source snapshot.
`tests/test_benchmark_updates_worker.py` independently regenerates the operations,
checks fingerprints and outcomes, and covers empty-tree checkpoints, chunk
boundaries, seed independence, malformed inputs, and memory-limit failures.

## Add a strategy

Implement `Strategy::rebalance(RebalanceContext&)` and register a creator with
`StrategyFactory::register_strategy(name, creator)`. Each call to `create(name)`
must return a fresh strategy instance. The factory rejects empty or duplicate
registrations, unknown names, and null creators/results. Compose the created
strategy with `TreeFlavor`; its private tree starts empty and rebalances only
successful insertions. Strategies use context `promote()` to rotate and record
measurements. This keeps BST storage independent of policy selection.

Like the Python pipeline, updates are not transactional if a strategy throws
(for example, when a scripted bit tape runs out). Such errors terminate the CLI;
do not continue using that flavor after a failed rebalance. This includes a
deletion whose refresh runs out of scripted bits.

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
