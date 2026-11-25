#pragma once

#include <cstdint>
#include <functional>
#include <limits>
#include <memory>
#include <optional>
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
    Index find(Key key, std::uint64_t* visits = nullptr) const;
    Index minimum(Index subtree, std::uint64_t* visits = nullptr) const;
    Index successor(Key key, std::uint64_t* visits = nullptr) const;
    // Raw deletion compacts storage; indices must be reacquired afterward.
    void erase(Index node, std::uint64_t* visits = nullptr);
    // Remove and reattach the same key, reusing the detached node's slot.
    // The caller must apply the insertion repair to the returned node.
    InsertResult reinsert(Index node, std::uint64_t* visits = nullptr);
    bool move_minimum_to_root(std::uint64_t* visits = nullptr);
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
    struct InsertionPosition {
        Index existing, parent;
        std::uint32_t depth;
    };
    InsertionPosition insertion_position(Key key) const;
    void attach_leaf(Index node, Index parent);
    Index detach(Index node, std::uint64_t* visits);
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

struct DeletionStats {
    bool erased = false;
    // Search/minimum/successor/reinsertion walks, separate from repair visits.
    std::uint64_t search_visits = 0, visits = 0, random_bits = 0, rotations = 0;
    std::uint32_t refreshes = 0, minimum_moves = 0;
    // Populated only when tracing is enabled.
    std::vector<Key> refreshed_keys;
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
    virtual bool supports_deletion() const { return false; }
};

class GeometricTargetLocalRepair final : public Strategy {
public:
    void rebalance(RebalanceContext& context) override;
};

class GeometricThreeQuarters : public Strategy {
public:
    void rebalance(RebalanceContext& context) override;
};

// Chapter 6 with p = 3/4: the same insertion repair plus deletion sweeps.
class GeometricFullBST final : public GeometricThreeQuarters {
public:
    bool supports_deletion() const override { return true; }
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
    DeletionStats erase(Key key);
    void reserve(std::size_t count) { tree_.reserve(count); }
    const BST& tree() const { return tree_; }
    std::optional<Key> cursor() const { return cursor_; }
private:
    InsertionStats repair(InsertResult result);
    void refresh_next(DeletionStats& stats);
    BST tree_;
    std::unique_ptr<Strategy> strategy_;
    RandomBits bits_;
    bool trace_;
    // nullopt represents the formal -infinity, including for INT64_MIN keys.
    std::optional<Key> cursor_;
};

} // namespace balance_trees
