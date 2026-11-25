// Isolated Linux worker for fixed, reproducible mixed-operation workloads.
// Generation, allocation, preload and exact checkpoint validation are not part
// of measured update time. No operation depends on the randomized tree shape.
#include "balance_trees/tree.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string_view>
#include <sys/resource.h>

using namespace balance_trees;

namespace {

using Clock = std::chrono::steady_clock;

std::uint64_t parse_unsigned(std::string_view text) {
    std::uint64_t result = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), result);
    if (error != std::errc{} || end != text.data() + text.size())
        throw std::invalid_argument("expected an unsigned decimal integer");
    return result;
}

// Explicit SplitMix64 plus rejection sampling makes permutations reproducible
// across standard-library implementations. This is separate from tree randomness.
struct OrderRandom {
    std::uint64_t state;
    std::uint64_t word() {
        auto value = (state += 0x9e3779b97f4a7c15ULL);
        value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
        value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
        return value ^ (value >> 31);
    }
    std::uint64_t bounded(std::uint64_t bound) {
        const auto threshold = -bound % bound;
        for (;;) {
            const auto value = word();
            if (value >= threshold) return value % bound;
        }
    }
    void shuffle(std::vector<std::uint32_t>& values) {
        for (std::size_t count = values.size(); count > 1; --count)
            std::swap(values[count - 1], values[bounded(count)]);
    }
};

enum class Kind : unsigned char { insert = 0, erase = 1, hit = 2, miss = 3 };
struct Operation { Key key; Kind kind; };

// A compact exact reference set; it is updated outside measured execution.
// Strict BST ordering plus membership and equal cardinality prove set equality.
struct ExpectedSet {
    std::vector<bool> present;
    Key offset;
    std::uint64_t size = 0;
    ExpectedSet(std::uint64_t count, bool descending)
        : present(2 * count, false), offset(descending ? count : 0) {}
    std::size_t index(Key key) const {
        const auto value = key + offset;
        if (value < 0 || static_cast<std::uint64_t>(value) >= present.size())
            throw std::logic_error("workload key is outside the reference set range");
        return static_cast<std::size_t>(value);
    }
    void insert(Key key) {
        const auto slot = index(key);
        if (present[slot]) throw std::logic_error("workload contains a duplicate insertion");
        present[slot] = true;
        ++size;
    }
    void erase(Key key) {
        const auto slot = index(key);
        if (!present[slot]) throw std::logic_error("workload removes an absent key");
        present[slot] = false;
        --size;
    }
};

struct Checkpoint {
    std::uint64_t completed_ops, nodes;
    std::int64_t height;
    double mean_depth;
};

Checkpoint validate(const BST& tree, const ExpectedSet& expected, std::uint64_t completed) {
    if (tree.size() != expected.size) throw std::logic_error("incorrect number of stored keys");
    const auto depths = tree.depths();  // ordering, parent links, cycles and reachability
    std::uint64_t depth_sum = 0;
    std::int64_t height = -1;
    for (std::size_t slot = 0; slot < tree.size(); ++slot) {
        if (!expected.present[expected.index(tree.key(static_cast<Index>(slot)))])
            throw std::logic_error("tree contains a key absent from the reference set");
        depth_sum += depths[slot];
        height = std::max(height, static_cast<std::int64_t>(depths[slot]));
    }
    return {completed, tree.size(), height, tree.size() ? double(depth_sum) / tree.size() : 0.0};
}

struct Counters {
    std::uint64_t insert_attempts = 0, inserted = 0, delete_attempts = 0, erased = 0;
    std::uint64_t search_attempts = 0, found = 0, insertion_depth = 0;
    std::uint64_t insert_rotations = 0, delete_rotations = 0;
    std::uint64_t max_insert_rotations = 0, max_delete_rotations = 0;
    std::uint64_t bits = 0, max_bits = 0, visits = 0, search_visits = 0;
    std::uint64_t refreshes = 0, minimum_moves = 0;

    void execute(TreeFlavor& tree, const Operation& operation) {
        if (operation.kind == Kind::insert) {
            const auto stats = tree.insert(operation.key);
            if (!stats.inserted) throw std::logic_error("expected insertion failed");
            if (stats.rotations > 2) throw std::logic_error("insertion rotation bound exceeded");
            ++insert_attempts;
            ++inserted;
            insertion_depth += stats.insertion_depth;
            insert_rotations += stats.rotations;
            max_insert_rotations = std::max(max_insert_rotations, stats.rotations);
            bits += stats.random_bits;
            max_bits = std::max(max_bits, stats.random_bits);
            visits += stats.visits;
            search_visits += stats.insertion_depth;
        } else if (operation.kind == Kind::erase) {
            const auto stats = tree.erase(operation.key);
            if (!stats.erased) throw std::logic_error("expected deletion failed");
            if (stats.rotations > 4) throw std::logic_error("deletion rotation bound exceeded");
            ++delete_attempts;
            ++erased;
            delete_rotations += stats.rotations;
            max_delete_rotations = std::max(max_delete_rotations, stats.rotations);
            bits += stats.random_bits;
            max_bits = std::max(max_bits, stats.random_bits);
            visits += stats.visits;
            search_visits += stats.search_visits;
            refreshes += stats.refreshes;
            minimum_moves += stats.minimum_moves;
        } else {
            const auto node = tree.tree().find(operation.key, &search_visits);
            const bool result = node != null;
            if (result != (operation.kind == Kind::hit))
                throw std::logic_error("lookup disagrees with the workload's expected result");
            ++search_attempts;
            found += result;
        }
    }
};

void fingerprint_operation(std::uint64_t& hash, const Operation& operation) {
    hash = (hash ^ static_cast<unsigned char>(operation.kind)) * 1099511628211ULL;
    auto key = static_cast<std::uint64_t>(operation.key);
    for (unsigned byte = 0; byte < 8; ++byte) {
        hash = (hash ^ (key & 255)) * 1099511628211ULL;
        key >>= 8;
    }
}

std::vector<std::uint64_t> checkpoint_positions(std::uint64_t n, bool grow_shrink, bool read_heavy) {
    const auto operations = n * (read_heavy ? 10 : 2);
    std::vector<std::uint64_t> result{0, operations};
    if (grow_shrink) {
        result.push_back(n);  // empty tree between the two phases
        for (std::uint64_t size = 1; size < n; size *= 2) {
            result.push_back(n - size);
            result.push_back(n + size);
        }
    } else {
        const auto round_size = read_heavy ? 10 : 2;
        for (unsigned quarter = 1; quarter < 4; ++quarter)
            result.push_back(((n * quarter + 3) / 4) * round_size);
    }
    std::sort(result.begin(), result.end());
    result.erase(std::unique(result.begin(), result.end()), result.end());
    return result;
}

std::uint64_t peak_rss_kib() {
    // VmHWM belongs to this executable, unlike ru_maxrss inherited across exec.
    std::ifstream status("/proc/self/status");
    std::string field, ignored;
    while (status >> field) {
        if (field == "VmHWM:") {
            std::uint64_t value = 0;
            status >> value;
            if (value) return value;
            break;
        }
        std::getline(status, ignored);
    }
    throw std::runtime_error("cannot measure VmHWM");
}

double seconds_since(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

} // namespace

int main(int argc, char** argv) {
    const auto worker_start = Clock::now();
    try {
        if (argc != 6)
            throw std::invalid_argument("usage: native-update-benchmark SEED N MEMORY_MIB WORKLOAD ORDER_SEED");
        const auto seed = parse_unsigned(argv[1]);
        const auto n = parse_unsigned(argv[2]);
        const auto memory_mib = parse_unsigned(argv[3]);
        const std::string workload = argv[4];
        const auto order_seed = parse_unsigned(argv[5]);
        if (n == 0 || n > null) throw std::invalid_argument("unsupported node count");
        if (memory_mib == 0 || memory_mib > std::numeric_limits<rlim_t>::max() / (1024 * 1024))
            throw std::invalid_argument("unsupported memory limit");
        const bool ascending = workload == "ascending-churn";
        const bool descending = workload == "descending-churn";
        const bool grow_shrink = workload == "grow-shrink";
        const bool read_heavy = workload == "read-heavy";
        if (!ascending && !descending && !grow_shrink && !read_heavy && workload != "random-churn")
            throw std::invalid_argument("unknown mixed-operation workload");
        const auto memory = static_cast<rlim_t>(memory_mib * 1024 * 1024);
        const rlimit limit{memory, memory};
        if (setrlimit(RLIMIT_AS, &limit) != 0) throw std::runtime_error("cannot set address-space cap");

        OrderRandom order_random{order_seed};
        std::vector<std::uint32_t> permutation(n);
        std::iota(permutation.begin(), permutation.end(), 0U);
        if (!ascending && !descending) order_random.shuffle(permutation);
        ExpectedSet expected(n, descending);
        TreeFlavor tree(StrategyFactory{}.create("geometric-full-bst"), RandomBits(seed));
        tree.reserve(n);
        std::uint64_t fingerprint = 14695981039346656037ULL;
        // Prepare the reference and the preload fingerprint before its timer.
        for (std::uint64_t i = 0; i < n; ++i) {
            const Key key = descending ? n - 1 - i : permutation[i];
            expected.insert(key);
            fingerprint_operation(fingerprint, {key, Kind::insert});
        }
        const auto preload_start = Clock::now();
        for (std::uint64_t i = 0; i < n; ++i) {
            const Key key = descending ? n - 1 - i : permutation[i];
            const auto stats = tree.insert(key);
            if (!stats.inserted || stats.rotations > 2)
                throw std::logic_error("invalid preload insertion");
        }
        const double preload_seconds = seconds_since(preload_start);
        if (!ascending && !descending) order_random.shuffle(permutation);

        const auto positions = checkpoint_positions(n, grow_shrink, read_heavy);
        std::vector<Checkpoint> checkpoints;
        checkpoints.reserve(positions.size());
        checkpoints.push_back(validate(tree.tree(), expected, 0));
        std::int64_t sampled_max_height = checkpoints.back().height;
        std::vector<Operation> chunk;
        constexpr std::uint64_t chunk_size = 65536;
        chunk.reserve(chunk_size);
        Counters counters;
        double elapsed_seconds = 0.0, cpu_seconds = 0.0;
        std::uint64_t completed = 0;
        for (std::size_t checkpoint_index = 1; checkpoint_index < positions.size(); ++checkpoint_index) {
            const auto boundary = positions[checkpoint_index];
            while (completed < boundary) {
                chunk.clear();
                const auto chunk_end = std::min(boundary, completed + chunk_size);
                for (auto index = completed; index < chunk_end; ++index) {
                    Operation operation{};
                    if (grow_shrink) {
                        operation = index < n
                            ? Operation{permutation[index], Kind::erase}
                            : Operation{static_cast<Key>(n + permutation[index - n]), Kind::insert};
                    } else {
                        const auto round = index / (read_heavy ? 10 : 2);
                        const auto part = index % (read_heavy ? 10 : 2);
                        if (read_heavy && part < 8) {
                            const auto rank = order_random.bounded(n);
                            const bool hit = part % 2 == 0;
                            const Key key = !hit ? 2 * n + rank
                                : rank < round ? n + rank : permutation[rank];
                            operation = {key, hit ? Kind::hit : Kind::miss};
                        } else if (part % 2 == 0) {
                            const Key key = descending ? n - 1 - round : permutation[round];
                            operation = {key, Kind::erase};
                        } else {
                            const Key key = descending ? -1 - static_cast<Key>(round) : n + round;
                            operation = {key, Kind::insert};
                        }
                    }
                    if (operation.kind == Kind::insert) expected.insert(operation.key);
                    if (operation.kind == Kind::erase) expected.erase(operation.key);
                    fingerprint_operation(fingerprint, operation);
                    chunk.push_back(operation);
                }
                const auto start = Clock::now();
                const auto cpu_start = std::clock();
                for (const auto& operation : chunk) counters.execute(tree, operation);
                const auto cpu_end = std::clock();
                elapsed_seconds += seconds_since(start);
                if (cpu_start == std::clock_t(-1) || cpu_end == std::clock_t(-1))
                    throw std::runtime_error("cannot measure process CPU time");
                cpu_seconds += double(cpu_end - cpu_start) / CLOCKS_PER_SEC;
                completed = chunk_end;
            }
            checkpoints.push_back(validate(tree.tree(), expected, completed));
            sampled_max_height = std::max(sampled_max_height, checkpoints.back().height);
        }
        const auto& final = checkpoints.back();
        const auto rotations = counters.insert_rotations + counters.delete_rotations;
        const double count = completed;
        const double inserts = counters.insert_attempts, deletes = counters.delete_attempts;
        std::cout << std::setprecision(17)
                  << "{\"schema_version\":1,\"workload\":\"" << workload << "\",\"n\":" << n
                  << ",\"seed\":" << seed << ",\"order_seed\":" << order_seed
                  << ",\"preload_order\":\"" << (ascending ? "ascending" : descending ? "descending" : "random")
                  << "\",\"operation_fingerprint\":\"" << std::hex << std::setw(16) << std::setfill('0')
                  << fingerprint << std::dec << "\",\"operations\":" << completed
                  << ",\"insert_attempts\":" << counters.insert_attempts << ",\"inserted\":" << counters.inserted
                  << ",\"delete_attempts\":" << counters.delete_attempts << ",\"erased\":" << counters.erased
                  << ",\"search_attempts\":" << counters.search_attempts << ",\"found\":" << counters.found
                  << ",\"final_nodes\":" << final.nodes << ",\"height\":" << final.height
                  << ",\"mean_depth\":" << final.mean_depth << ",\"sampled_max_height\":" << sampled_max_height
                  << ",\"mean_insertion_depth\":" << counters.insertion_depth / inserts
                  << ",\"rotations\":" << rotations << ",\"mean_rotations\":" << rotations / count
                  << ",\"max_rotations\":" << std::max(counters.max_insert_rotations, counters.max_delete_rotations)
                  << ",\"insert_rotations\":" << counters.insert_rotations
                  << ",\"mean_insert_rotations\":" << counters.insert_rotations / inserts
                  << ",\"max_insert_rotations\":" << counters.max_insert_rotations
                  << ",\"delete_rotations\":" << counters.delete_rotations
                  << ",\"mean_delete_rotations\":" << counters.delete_rotations / deletes
                  << ",\"max_delete_rotations\":" << counters.max_delete_rotations
                  << ",\"random_bits\":" << counters.bits << ",\"mean_random_bits\":" << counters.bits / count
                  << ",\"max_random_bits\":" << counters.max_bits
                  << ",\"visits\":" << counters.visits << ",\"search_visits\":" << counters.search_visits
                  << ",\"refreshes\":" << counters.refreshes << ",\"minimum_moves\":" << counters.minimum_moves
                  << ",\"elapsed_seconds\":" << elapsed_seconds << ",\"cpu_seconds\":" << cpu_seconds
                  << ",\"preload_seconds\":" << preload_seconds << ",\"worker_seconds\":" << seconds_since(worker_start)
                  << ",\"node_storage_bytes\":" << tree.tree().storage_bytes()
                  << ",\"peak_rss_mib\":" << peak_rss_kib() / 1024.0 << ",\"checkpoints\":[";
        for (std::size_t index = 0; index < checkpoints.size(); ++index) {
            const auto& point = checkpoints[index];
            if (index) std::cout << ',';
            std::cout << "{\"completed_ops\":" << point.completed_ops << ",\"n\":" << point.nodes
                      << ",\"height\":" << point.height << ",\"mean_depth\":" << point.mean_depth << '}';
        }
        std::cout << "]}\n";
    } catch (const std::bad_alloc&) {
        std::cerr << "memory_limit: allocation failed\n";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
