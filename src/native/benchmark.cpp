// Linux isolated benchmark worker. Input parsing and validation are not timed.
#include "balance_trees/tree.hpp"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <sys/resource.h>

using namespace balance_trees;

int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::invalid_argument("usage: native-benchmark SEED N MEMORY_MIB");
        const auto seed = std::stoull(argv[1]);
        const auto n = std::stoull(argv[2]);
        const auto memory = std::stoull(argv[3]) * 1024 * 1024;
        if (n == 0 || n > null) throw std::invalid_argument("unsupported node count");
        rlimit limit{memory, memory};
        if (setrlimit(RLIMIT_AS, &limit) != 0) throw std::runtime_error("cannot set address-space cap");
        std::vector<Key> values;
        values.reserve(n);
        Key key;
        while (std::cin >> key) {
            if (values.size() == n) throw std::invalid_argument("too many keys");
            values.push_back(key);
        }
        if (!std::cin.eof() || values.size() != n) throw std::invalid_argument("invalid input keys");
        TreeFlavor tree(StrategyFactory{}.create("geometric-target-local-repair"), RandomBits(seed));
        tree.reserve(n);
        std::uint64_t rotations = 0, bits = 0, visits = 0, insertion_depth = 0;
        std::uint64_t max_rotations = 0, max_bits = 0, max_visits = 0;
        const auto start = std::chrono::steady_clock::now();
        for (auto value : values) {
            const auto stats = tree.insert(value);
            if (!stats.inserted) throw std::invalid_argument("duplicate benchmark key");
            rotations += stats.rotations;
            bits += stats.random_bits;
            visits += stats.visits;
            insertion_depth += stats.insertion_depth;
            max_rotations = std::max(max_rotations, stats.rotations);
            max_bits = std::max(max_bits, stats.random_bits);
            max_visits = std::max(max_visits, stats.visits);
        }
        const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        const auto depths = tree.tree().depths();
        std::uint64_t depth_sum = 0, height = 0;
        for (auto depth : depths) { depth_sum += depth; height = std::max<std::uint64_t>(height, depth); }
        // Compare each stored key with its input slot, as well as BST validation.
        if (tree.tree().size() != values.size()) throw std::logic_error("lost keys");
        for (std::size_t i = 0; i < values.size(); ++i)
            if (tree.tree().key(static_cast<Index>(i)) != values[i]) throw std::logic_error("changed key");
        // VmHWM belongs to this executable's address space. ru_maxrss can retain
        // a larger high-water mark from before exec (the Python launcher).
        std::ifstream status("/proc/self/status");
        std::string field, ignored;
        std::uint64_t peak_rss_kib = 0;
        while (status >> field) {
            if (field == "VmHWM:") { status >> peak_rss_kib; break; }
            std::getline(status, ignored);
        }
        if (peak_rss_kib == 0) throw std::runtime_error("cannot measure VmHWM");
        const double count = n;
        std::cout << std::setprecision(17)
                  << "{\"mean_depth\":" << depth_sum / count << ",\"height\":" << height
                  << ",\"mean_insertion_depth\":" << insertion_depth / count
                  << ",\"mean_rotations\":" << rotations / count << ",\"max_rotations\":" << max_rotations
                  << ",\"mean_visits\":" << visits / count << ",\"max_visits\":" << max_visits
                  << ",\"mean_random_bits\":" << bits / count << ",\"max_random_bits\":" << max_bits
                  << ",\"mean_scanned_nodes\":0,\"max_scanned_nodes\":0"
                  << ",\"elapsed_seconds\":" << seconds << ",\"node_storage_bytes\":" << tree.tree().storage_bytes()
                  << ",\"peak_rss_mib\":" << peak_rss_kib / 1024.0 << "}\n";
    } catch (const std::bad_alloc&) {
        std::cerr << "memory_limit: allocation failed\n";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
