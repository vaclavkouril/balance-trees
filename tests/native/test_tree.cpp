#include "balance_trees/tree.hpp"

#include <algorithm>
#include <iostream>
#include <numeric>
#include <random>
#include <set>
#include <source_location>
#include <stdexcept>

using namespace balance_trees;

void check(bool condition, std::source_location location = std::source_location::current()) {
    if (!condition)
        throw std::runtime_error("native test failed at line " + std::to_string(location.line()));
}

template<class Function>
void rejects(Function function) {
    try { function(); } catch (const std::exception&) { return; }
    throw std::runtime_error("expected an exception");
}

void check_keys(const BST& tree, const std::set<Key>& expected) {
    check(tree.size() == expected.size());
    check(tree.depths().size() == expected.size()); // Ordering, links, reachability.
    std::set<Key> actual;
    for (std::size_t index = 0; index < tree.size(); ++index)
        actual.insert(tree.key(static_cast<Index>(index)));
    check(actual == expected);
    for (auto key : expected) check(tree.contains(key));
}

void test_raw_deletion_and_refresh() {
    // All insertion permutations through six keys exercise slot relocation
    // when the last slot is a root, parent, child, successor, or unrelated node.
    for (Key count = 1; count <= 6; ++count) {
        std::vector<Key> order(static_cast<std::size_t>(count));
        std::iota(order.begin(), order.end(), 0);
        const std::set<Key> all_keys(order.begin(), order.end());
        do {
            for (auto removed_key : order) {
                BST tree;
                for (auto key : order) tree.insert(key);
                auto expected = all_keys;
                expected.erase(removed_key);
                tree.erase(tree.find(removed_key));
                check_keys(tree, expected);
                check(!tree.contains(removed_key));
                tree.insert(removed_key);
                check_keys(tree, all_keys);

                const auto bytes = tree.storage_bytes();
                const auto insertion = tree.reinsert(tree.find(removed_key));
                check(insertion.inserted && tree.key(insertion.node) == removed_key);
                check(tree.depths()[insertion.node] == insertion.depth);
                check(tree.storage_bytes() == bytes);
                check_keys(tree, all_keys);
            }
        } while (std::next_permutation(order.begin(), order.end()));
    }

    BST right_only;
    for (auto key : {10, 30, 20, 25, 40}) right_only.insert(key);
    right_only.erase(right_only.root());
    // Successor replacement is required even with no left child.
    check(right_only.key(right_only.root()) == 20);
    check_keys(right_only, {20, 25, 30, 40});

    BST reset;
    check(!reset.move_minimum_to_root());
    for (auto key : {20, 10, 15, 12, 30}) reset.insert(key);
    const auto before = reset.depths();
    const auto minimum = reset.minimum(reset.root());
    check(reset.move_minimum_to_root());
    check(reset.root() == minimum && reset.left(minimum) == null);
    const auto after = reset.depths();
    for (std::size_t i = 0; i < before.size(); ++i)
        if (i != minimum) check(after[i] <= before[i] + 1);
    check_keys(reset, {10, 12, 15, 20, 30});
    check(!reset.move_minimum_to_root());
    check(reset.successor(14) == reset.find(15)); // Absent cursor value.
    check(reset.successor(30) == null);

    BST deep_minimum;
    for (Key key = 10000; key > 0; --key) deep_minimum.insert(key);
    check(deep_minimum.move_minimum_to_root());
    check(deep_minimum.key(deep_minimum.root()) == 1);
    check(deep_minimum.depths().size() == 10000);
    deep_minimum.reinsert(deep_minimum.root());
    deep_minimum.erase(deep_minimum.find(1));
    check(!deep_minimum.contains(1) && deep_minimum.depths().size() == 9999);
}

void test_full_bst_examples(const StrategyFactory& factory) {
    TreeFlavor full(factory.create("geometric-full-bst"), RandomBits(std::string(1024, '0')), true);
    check(!full.erase(20).erased && !full.cursor());
    for (auto key : {20, 10, 30}) full.insert(key);
    const auto first = full.erase(20);
    check(first.erased && first.refreshes == 2 && first.minimum_moves == 0);
    check(first.random_bits == 4 && first.rotations == 0);
    check(first.refreshed_keys == std::vector<Key>({10, 30}));
    check(full.cursor() == 30 && full.tree().key(full.tree().root()) == 10);
    check_keys(full.tree(), {10, 30});
    full.insert(5);
    full.insert(25);
    const auto wrapped = full.erase(30);
    check(wrapped.refreshed_keys == std::vector<Key>({5, 10}));
    check(wrapped.minimum_moves == 1 && full.cursor() == 10);
    check_keys(full.tree(), {5, 10, 25});
    const auto absent = full.erase(30);
    check(!absent.erased && absent.random_bits == 0 && absent.refreshes == 0);
    check(full.cursor() == 10);

    const auto lowest = std::numeric_limits<Key>::min();
    const auto highest = std::numeric_limits<Key>::max();
    TreeFlavor extremes(factory.create("geometric-full-bst"), RandomBits("00"), true);
    extremes.insert(lowest);
    extremes.insert(highest);
    const auto singleton = extremes.erase(highest);
    check(singleton.refreshed_keys == std::vector<Key>({lowest, lowest}));
    check(singleton.random_bits == 0 && singleton.rotations == 0);
    check(extremes.cursor() == lowest); // A real key, not the -infinity marker.
    check_keys(extremes.tree(), {lowest});
    const auto empty = extremes.erase(lowest);
    check(empty.erased && empty.refreshes == 0 && empty.random_bits == 0);
    check(!extremes.cursor() && extremes.tree().root() == null);
    extremes.insert(highest); // A new first singleton requires no bits.
    check(!extremes.cursor());
    check_keys(extremes.tree(), {highest});

    for (auto policy : {"none", "geometric-three-quarters", "geometric-target-local-repair"}) {
        TreeFlavor unsupported(factory.create(policy));
        unsupported.insert(1);
        rejects([&] { unsupported.erase(1); });
        check_keys(unsupported.tree(), {1});
    }
}

void test_sampling_after_shrink(const StrategyFactory& factory) {
    TreeFlavor full(factory.create("geometric-full-bst"), RandomBits(std::string(100000, '1')));
    for (Key key = 0; key < 128; ++key) {
        const auto stats = full.insert(key);
        check(stats.random_bits == 2 * maximum_three_quarters_target_depth(key + 1));
    }
    for (Key key = 127; key >= 1; --key) {
        const auto stats = full.erase(key);
        check(stats.random_bits == 4 * maximum_three_quarters_target_depth(key));
        check(stats.refreshes == 2 && stats.rotations <= 4);
        check(stats.refreshed_keys.empty() && stats.rotation_distances.empty());
        full.tree().depths();
    }
    const auto next = full.insert(200);
    check(next.random_bits == 6); // ell_2 = 3, regardless of earlier insertions.
    check_keys(full.tree(), {0, 200});
}

void test_mixed_operations(const StrategyFactory& factory) {
    for (unsigned seed = 0; seed < 8; ++seed) {
        // The operation generator is independent of the tree's random stream.
        std::mt19937_64 operations(seed + 2026);
        TreeFlavor full(factory.create("geometric-full-bst"), RandomBits(seed), true);
        full.reserve(256);
        const auto bytes = full.tree().storage_bytes();
        std::set<Key> expected;
        std::optional<Key> cursor;
        for (unsigned step = 0; step < 2000; ++step) {
            const Key key = static_cast<Key>(operations() % 201) - 100;
            const auto action = operations() % 10;
            if (action < 4) {
                const auto inserted = expected.insert(key).second;
                const auto stats = full.insert(key);
                check(stats.inserted == inserted && stats.rotations <= 2);
                if (!inserted) check(stats.random_bits == 0 && stats.rotations == 0);
            } else if (action < 8) {
                const bool erased = expected.erase(key) != 0;
                std::vector<Key> refreshed;
                if (erased && expected.empty()) cursor.reset();
                else if (erased) {
                    for (unsigned visit = 0; visit < 2; ++visit) {
                        auto next = cursor ? expected.upper_bound(*cursor) : expected.begin();
                        if (next == expected.end()) next = expected.begin();
                        cursor = *next;
                        refreshed.push_back(*cursor);
                    }
                }
                const auto stats = full.erase(key);
                check(stats.erased == erased && stats.rotations <= 4 && stats.minimum_moves <= 2);
                check(stats.refreshed_keys == refreshed && stats.refreshes == refreshed.size());
                check(stats.rotation_distances.size() == stats.rotations);
                if (!erased) check(stats.random_bits == 0 && stats.rotations == 0);
            } else check(full.tree().contains(key) == expected.contains(key));
            check(full.cursor() == cursor);
            check(full.tree().storage_bytes() == bytes);
            check_keys(full.tree(), expected);
        }
    }
}

int main() {
    StrategyFactory factory;
    rejects([&] { factory.create("missing"); });
    rejects([&] { factory.register_strategy("none", [] { return std::make_unique<NoRebalance>(); }); });
    rejects([&] { factory.register_strategy("", {}); });
    factory.register_strategy("custom", [] { return std::make_unique<NoRebalance>(); });
    check(factory.create("custom") != nullptr);
    rejects([] { TreeFlavor invalid(nullptr); });
    rejects([] { RandomBits invalid("02"); });
    RandomBits empty("");
    rejects([&] { empty.bit(); });
    rejects([&] { sample_target_depth(0, empty); });

    rejects([&] { maximum_three_quarters_target_depth(0); });
    RandomBits root_bits("");
    check(sample_three_quarters_target_depth(1, root_bits) == 0);
    check(maximum_three_quarters_target_depth(2) == 3);
    check(maximum_three_quarters_target_depth(3) == 4);
    check(maximum_three_quarters_target_depth(UINT32_MAX) == 78);
    for (auto tape : {"01", "10", "11"}) {
        RandomBits bits(std::string(tape) + "00");
        check(sample_three_quarters_target_depth(2, bits) == 2);
        check(bits.count() == 4);
    }
    RandomBits root_sample("111111");
    check(sample_three_quarters_target_depth(2, root_sample) == 0);
    check(root_sample.count() == 6);

    // SplitMix64's seed-zero first word, including buffer refill and bit order.
    RandomBits seeded(0);
    std::uint64_t word = 0;
    for (unsigned bit = 0; bit < 64; ++bit) word |= std::uint64_t(seeded.bit()) << bit;
    check(word == UINT64_C(0xe220a8397b1dcdaf));
    check(seeded.count() == 64);
    RandomBits scripted(std::string(64, '1') + "0");
    for (unsigned bit = 0; bit < 64; ++bit) check(scripted.bit() == 1);
    check(scripted.bit() == 0);
    rejects([&] { scripted.bit(); });

    BST plain;
    check(plain.depths().empty());
    check(!plain.contains(0));
    plain.reserve(3);
    check(plain.storage_bytes() == 60);
    plain.insert(std::numeric_limits<Key>::min());
    plain.insert(std::numeric_limits<Key>::max());
    plain.insert(0);
    check(!plain.insert(0).inserted);
    plain.rotate_up(2);
    plain.rotate_up(2);
    check(plain.root() == 2);
    check(plain.depths().size() == 3);
    rejects([&] { plain.rotate_up(2); });
    rejects([&] { plain.reserve(std::uint64_t(null) + 1); });

    // Each policy is freshly constructed; all mutation invariants are checked.
    for (unsigned seed = 0; seed < 8; ++seed) {
        TreeFlavor tree(factory.create("geometric-target-local-repair"), RandomBits(seed));
        check(tree.tree().depths().empty());
        for (Key key = 0; key < 1000; ++key) {
            auto stats = tree.insert(seed % 2 ? -key : key);
            check(stats.inserted && stats.rotations <= 2 && (key == 0 || stats.random_bits >= 1));
            check(stats.rotation_distances.empty());
            check(tree.tree().depths().size() == std::size_t(key + 1));
        }
        auto duplicate = tree.insert(0);
        check(!duplicate.inserted && duplicate.random_bits == 0 && duplicate.rotations == 0);
        check(tree.tree().contains(0) && !tree.tree().contains(1001));
    }
    TreeFlavor chain(factory.create("none"));
    for (Key key = 0; key < 10000; ++key) chain.insert(key);
    check(chain.tree().depths().back() == 9999); // Iterative even on linear height.
    test_raw_deletion_and_refresh();
    test_full_bst_examples(factory);
    test_sampling_after_shrink(factory);
    test_mixed_operations(factory);
    std::cout << "Native tree tests passed\n";
}
