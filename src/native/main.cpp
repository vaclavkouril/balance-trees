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

template<class Value>
void print_array(const std::vector<Value>& values) {
    std::cout << '[';
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << values[i];
    }
    std::cout << ']';
}

void print_insertion(const InsertionStats& stats) {
    std::cout << "\"inserted\":" << (stats.inserted ? "true" : "false")
              << ",\"insertion_depth\":" << stats.insertion_depth
              << ",\"visits\":" << stats.visits
              << ",\"random_bits\":" << stats.random_bits
              << ",\"rotation_distances\":";
    print_array(stats.rotation_distances);
}

void print_topology(const BST& tree) {
    std::cout << ",\"root\":" << tree.root() << ",\"nodes\":[";
    for (std::size_t j = 0; j < tree.size(); ++j) {
        if (j) std::cout << ',';
        const auto node = static_cast<Index>(j);
        std::cout << '[' << tree.key(node) << ',' << tree.left(node)
                  << ',' << tree.right(node) << ',' << tree.parent(node) << ']';
    }
    std::cout << ']';
}

void run_updates(TreeFlavor& flavor, bool trace) {
    std::uint64_t operations = 0, insertions = 0, inserted = 0;
    std::uint64_t deletions = 0, erased = 0, searches = 0, found = 0;
    std::uint64_t rotations = 0, bits = 0, visits = 0, search_visits = 0;
    std::uint64_t refreshes = 0, minimum_moves = 0;
    const auto start = std::chrono::steady_clock::now();
    std::string operation, token;
    while (std::cin >> operation) {
        if (operation != "insert" && operation != "delete" && operation != "contains")
            throw std::invalid_argument("unknown operation: " + operation);
        if (!(std::cin >> token)) throw std::invalid_argument("missing operation key");
        const auto key = parse_integer<Key>(token);
        auto print_prefix = [&] {
            std::cout << "{\"operation\":\"" << operation << "\",\"key\":" << key << ',';
        };
        if (operation == "insert") {
            const auto stats = flavor.insert(key);
            ++insertions;
            inserted += stats.inserted;
            rotations += stats.rotations;
            bits += stats.random_bits;
            visits += stats.visits;
            search_visits += stats.insertion_depth + (stats.inserted ? 0 : 1);
            if (trace) { print_prefix(); print_insertion(stats); }
        } else if (operation == "delete") {
            const auto stats = flavor.erase(key);
            ++deletions;
            erased += stats.erased;
            rotations += stats.rotations;
            bits += stats.random_bits;
            visits += stats.visits;
            search_visits += stats.search_visits;
            refreshes += stats.refreshes;
            minimum_moves += stats.minimum_moves;
            if (trace) {
                print_prefix();
                std::cout << "\"erased\":" << (stats.erased ? "true" : "false")
                          << ",\"search_visits\":" << stats.search_visits
                          << ",\"visits\":" << stats.visits
                          << ",\"random_bits\":" << stats.random_bits
                          << ",\"rotations\":" << stats.rotations
                          << ",\"refreshes\":" << stats.refreshes
                          << ",\"minimum_moves\":" << stats.minimum_moves
                          << ",\"refreshed_keys\":";
                print_array(stats.refreshed_keys);
                std::cout << ",\"rotation_distances\":";
                print_array(stats.rotation_distances);
            }
        } else {
            const auto present = flavor.tree().find(key, &search_visits) != null;
            ++searches;
            found += present;
            if (trace) {
                print_prefix();
                std::cout << "\"found\":" << (present ? "true" : "false");
            }
        }
        ++operations;
        if (trace) {
            flavor.tree().depths();
            std::cout << ",\"cursor\":";
            if (flavor.cursor()) std::cout << *flavor.cursor();
            else std::cout << "null";
            print_topology(flavor.tree());
            std::cout << "}\n";
        }
    }
    if (std::cin.bad()) throw std::runtime_error("failed to read operations");
    const auto seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - start).count();
    const auto depths = flavor.tree().depths();
    std::uint32_t height = 0;
    for (auto depth : depths) height = std::max(height, depth);
    if (!trace) {
        std::cout << "{\"operations\":" << operations
                  << ",\"insert_attempts\":" << insertions << ",\"inserted\":" << inserted
                  << ",\"delete_attempts\":" << deletions << ",\"erased\":" << erased
                  << ",\"search_attempts\":" << searches << ",\"found\":" << found
                  << ",\"nodes\":" << flavor.tree().size() << ",\"height\":" << height
                  << ",\"rotations\":" << rotations << ",\"random_bits\":" << bits
                  << ",\"visits\":" << visits << ",\"search_visits\":" << search_visits
                  << ",\"refreshes\":" << refreshes << ",\"minimum_moves\":" << minimum_moves
                  << ",\"storage_bytes\":" << flavor.tree().storage_bytes()
                  << ",\"input_and_update_seconds\":" << seconds << "}\n";
    }
}

int main(int argc, char** argv) {
    try {
        std::string strategy = "geometric-target-local-repair", tape;
        std::uint64_t seed = 0;
        std::size_t capacity = 0;
        bool trace = false, scripted = false, updates = false;
        for (int i = 1; i < argc; ++i) {
            std::string_view option = argv[i];
            if (option == "--trace") { trace = true; continue; }
            if (option == "--updates") { updates = true; continue; }
            if (option == "--help") {
                std::cout << "balance-tree [--strategy NAME] [--seed N] [--reserve N] "
                             "[--bits 0101...] [--trace] [--updates]\n"
                             "Read signed 64-bit keys from stdin; emit JSON summary.\n"
                             "--trace emits per-operation statistics and indexed topology.\n"
                             "--updates reads insert/delete/contains KEY commands instead.\n"
                             "Deletion requires --strategy geometric-full-bst (p=3/4).\n";
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
        if (updates) { run_updates(flavor, trace); return 0; }
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
            std::cout << '{';
            print_insertion(stats);
            print_topology(flavor.tree());
            std::cout << "}\n";
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
