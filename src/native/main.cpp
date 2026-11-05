#include "balance_trees/tree.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <iostream>
#include <stdexcept>

using namespace balance_trees;

template<class Integer>
Integer parse_integer(std::string_view text) {
    Integer result;
    auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), result);
    if (error != std::errc{} || end != text.data() + text.size())
        throw std::invalid_argument("invalid integer: " + std::string(text));
    return result;
}

int main(int argc, char** argv) {
    try {
        std::string strategy = "geometric-target-local-repair", tape;
        std::uint64_t seed = 0;
        std::size_t capacity = 0;
        bool trace = false, scripted = false;
        for (int i = 1; i < argc; ++i) {
            std::string_view option = argv[i];
            if (option == "--trace") { trace = true; continue; }
            if (option == "--help") {
                std::cout << "balance-tree [--strategy NAME] [--seed N] [--reserve N] "
                             "[--bits 0101...] [--trace]\n"
                             "Read signed 64-bit keys from stdin; emit JSON summary.\n"
                             "--trace emits per-insertion statistics and indexed topology.\n";
                return 0;
            }
            if (i + 1 == argc) throw std::invalid_argument("missing option value");
            std::string_view value = argv[++i];
            if (option == "--strategy") strategy = value;
            else if (option == "--seed") seed = parse_integer<std::uint64_t>(value);
            else if (option == "--reserve") capacity = parse_integer<std::size_t>(value);
            else if (option == "--bits") { scripted = true; tape = value; }
            else throw std::invalid_argument("unknown option: " + std::string(option));
        }
        StrategyFactory factory;
        TreeFlavor flavor(factory.create(strategy),
                          scripted ? RandomBits(tape) : RandomBits(seed), trace);
        flavor.reserve(capacity);
        std::uint64_t insertions = 0, rotations = 0, bits = 0, visits = 0;
        std::string token;
        const auto start = std::chrono::steady_clock::now();
        while (std::cin >> token) {
            auto key = parse_integer<Key>(token);
            auto stats = flavor.insert(key);
            ++insertions;
            rotations += stats.rotations;
            bits += stats.random_bits;
            visits += stats.visits;
            if (!trace) continue;
            flavor.tree().depths();
            std::cout << "{\"inserted\":" << (stats.inserted ? "true" : "false")
                      << ",\"insertion_depth\":" << stats.insertion_depth
                      << ",\"visits\":" << stats.visits
                      << ",\"random_bits\":" << stats.random_bits
                      << ",\"rotation_distances\":[";
            for (std::size_t j = 0; j < stats.rotation_distances.size(); ++j) {
                if (j) std::cout << ',';
                std::cout << stats.rotation_distances[j];
            }
            std::cout << "],\"root\":" << flavor.tree().root() << ",\"nodes\":[";
            for (std::size_t j = 0; j < flavor.tree().size(); ++j) {
                if (j) std::cout << ',';
                auto node = static_cast<Index>(j);
                std::cout << '[' << flavor.tree().key(node) << ',' << flavor.tree().left(node)
                          << ',' << flavor.tree().right(node) << ',' << flavor.tree().parent(node) << ']';
            }
            std::cout << "]}\n";
        }
        if (std::cin.bad()) throw std::runtime_error("failed to read keys");
        const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        // Validation is intentionally outside insertion timing.
        const auto depths = flavor.tree().depths();
        std::uint32_t height = 0;
        for (auto depth : depths) height = std::max(height, depth);
        if (!trace) {
            std::cout << "{\"attempts\":" << insertions << ",\"nodes\":" << flavor.tree().size()
                      << ",\"rotations\":" << rotations << ",\"random_bits\":" << bits
                      << ",\"visits\":" << visits << ",\"height\":" << height
                      << ",\"storage_bytes\":" << flavor.tree().storage_bytes()
                      << ",\"input_and_insert_seconds\":" << elapsed << "}\n";
        }
    } catch (const std::exception& error) {
        std::cerr << "balance-tree: " << error.what() << '\n';
        return 1;
    }
}
