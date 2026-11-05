#include "balance_trees/tree.hpp"

#include <iostream>
#include <stdexcept>

using namespace balance_trees;

void check(bool condition) {
    if (!condition) throw std::runtime_error("native test failed");
}

template<class Function>
void rejects(Function function) {
    try { function(); } catch (const std::exception&) { return; }
    throw std::runtime_error("expected an exception");
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
            check(stats.inserted && stats.rotations <= 2 && stats.random_bits >= 1);
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
    std::cout << "Native tree tests passed\n";
}
