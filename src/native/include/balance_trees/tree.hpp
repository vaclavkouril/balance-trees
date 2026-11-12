#pragma once

#include <cstdint>
#include <functional>
#include <limits>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace balance_trees {

using Key = std::int64_t;
using Index = std::uint32_t;
inline constexpr Index null = std::numeric_limits<Index>::max();

// SplitMix64 words are consumed least significant bit first, without discards.
// Scripted streams use the same packed buffer, for cross-language conformance.
class RandomBits {
public:
    explicit RandomBits(std::uint64_t seed = 0) : state_(seed) {}
    explicit RandomBits(std::string_view tape);
    unsigned bit();
    std::uint64_t count() const { return count_; }

private:
    std::uint64_t state_ = 0, buffer_ = 0, count_ = 0;
    unsigned remaining_ = 0;
    bool scripted_ = false;
    std::size_t tape_size_ = 0;
    std::vector<std::uint64_t> tape_;
};

struct InsertResult {
    Index node;
    bool inserted;
    std::uint32_t depth;
};

// Structure of arrays avoids the padding of an int64 key + three uint32 links.
// No priorities, heights, sizes, or random state are stored per node.
class BST {
public:
    void reserve(std::size_t count);
    InsertResult insert(Key key);
    bool contains(Key key) const;
    void rotate_up(Index node);
    std::vector<std::uint32_t> depths() const;
    Index root() const { return root_; }
    std::size_t size() const { return keys_.size(); }
    Key key(Index node) const { return keys_.at(node); }
    Index left(Index node) const { return left_.at(node); }
    Index right(Index node) const { return right_.at(node); }
    Index parent(Index node) const { return parent_.at(node); }
    std::size_t storage_bytes() const;

private:
    Index root_ = null;
    std::vector<Key> keys_;
    std::vector<Index> left_, right_, parent_;
};

struct InsertionStats {
    bool inserted;
    std::uint32_t insertion_depth;
    std::uint64_t visits = 0, random_bits = 0;
    std::uint64_t rotations = 0;
    // Optional tracing keeps allocations out of the default insertion path.
    std::vector<std::uint32_t> rotation_distances;
};

struct RebalanceContext {
    BST& tree;
    Index inserted;
    RandomBits& bits;
    InsertionStats& stats;
    bool trace;
    void promote(Index node, std::uint32_t distance);
};

class Strategy {
public:
    virtual ~Strategy() = default;
    virtual void rebalance(RebalanceContext& context) = 0;
};

class GeometricTargetLocalRepair final : public Strategy {
public:
    void rebalance(RebalanceContext& context) override;
private:
    std::uint32_t inserted_count_ = 0;
};

class GeometricThreeQuarters final : public Strategy {
public:
    void rebalance(RebalanceContext& context) override;
private:
    std::uint32_t inserted_count_ = 0;
};

std::uint32_t maximum_three_quarters_target_depth(std::uint32_t node_count);
std::uint32_t sample_three_quarters_target_depth(std::uint32_t node_count, RandomBits& bits);

class NoRebalance final : public Strategy {
public:
    void rebalance(RebalanceContext&) override {}
};

std::uint32_t sample_target_depth(std::uint32_t node_count, RandomBits& bits);

class StrategyFactory {
public:
    using Creator = std::function<std::unique_ptr<Strategy>()>;
    StrategyFactory();
    void register_strategy(std::string name, Creator creator);
    std::unique_ptr<Strategy> create(const std::string& name) const;
private:
    std::unordered_map<std::string, Creator> creators_;
};

class TreeFlavor {
public:
    explicit TreeFlavor(std::unique_ptr<Strategy> strategy,
                        RandomBits bits = RandomBits{}, bool trace = false);
    InsertionStats insert(Key key);
    void reserve(std::size_t count) { tree_.reserve(count); }
    const BST& tree() const { return tree_; }
private:
    BST tree_;
    std::unique_ptr<Strategy> strategy_;
    RandomBits bits_;
    bool trace_;
};

} // namespace balance_trees
