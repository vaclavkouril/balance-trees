#include "balance_trees/tree.hpp"

#include <algorithm>
#include <bit>
#include <stdexcept>
#include <utility>

namespace balance_trees {

RandomBits::RandomBits(std::string_view tape) : scripted_(true), tape_size_(tape.size()) {
    tape_.resize((tape.size() + 63) / 64);
    for (std::size_t i = 0; i < tape.size(); ++i) {
        if (tape[i] != '0' && tape[i] != '1') {
            throw std::invalid_argument("bit tape must contain only 0 and 1");
        }
        tape_[i / 64] |= std::uint64_t(tape[i] - '0') << (i % 64);
    }
}

unsigned RandomBits::bit() {
    if (scripted_ && count_ >= tape_size_) {
        throw std::out_of_range("bit tape exhausted");
    }
    if (remaining_ == 0) {
        if (scripted_) {
            buffer_ = tape_[count_ / 64];
        } else {
            // SplitMix64: fixed-width unsigned arithmetic defines wraparound.
            state_ += UINT64_C(0x9e3779b97f4a7c15);
            auto word = state_;
            word = (word ^ (word >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
            word = (word ^ (word >> 27)) * UINT64_C(0x94d049bb133111eb);
            buffer_ = word ^ (word >> 31);
        }
        remaining_ = 64;
    }
    unsigned result = buffer_ & 1;
    buffer_ >>= 1;
    --remaining_;
    ++count_;
    return result;
}

void BST::reserve(std::size_t count) {
    if (count > null) throw std::length_error("32-bit node index limit exceeded");
    keys_.reserve(count);
    left_.reserve(count);
    right_.reserve(count);
    parent_.reserve(count);
}

InsertResult BST::insert(Key key_value) {
    Index ancestor = null, current = root_;
    std::uint32_t depth = 0;
    while (current != null) {
        if (key_value == keys_[current]) return {current, false, depth};
        ancestor = current;
        current = key_value < keys_[current] ? left_[current] : right_[current];
        ++depth;
    }
    if (size() == null) throw std::length_error("32-bit node index limit exceeded");
    // Reserve all arrays before changing their lengths, including on allocation
    // failure. Geometric growth avoids quadratic allocation without reserve().
    const auto capacity = std::min({keys_.capacity(), left_.capacity(),
                                    right_.capacity(), parent_.capacity()});
    if (size() == capacity) {
        reserve(std::min<std::size_t>(null, std::max<std::size_t>(8, size() * 2)));
    }
    const auto node = static_cast<Index>(size());
    keys_.push_back(key_value);
    left_.push_back(null);
    right_.push_back(null);
    parent_.push_back(ancestor);
    if (ancestor == null) root_ = node;
    else if (key_value < keys_[ancestor]) left_[ancestor] = node;
    else right_[ancestor] = node;
    return {node, true, depth};
}

bool BST::contains(Key key_value) const {
    auto current = root_;
    while (current != null) {
        if (key_value == keys_[current]) return true;
        current = key_value < keys_[current] ? left_[current] : right_[current];
    }
    return false;
}

void BST::rotate_up(Index node) {
    const auto ancestor = parent_.at(node);
    if (ancestor == null) throw std::invalid_argument("cannot rotate root");
    const auto grandparent = parent_[ancestor];
    if (grandparent != null && left_[grandparent] != ancestor && right_[grandparent] != ancestor)
        throw std::logic_error("inconsistent grandparent link");
    if (left_[ancestor] == node) {
        left_[ancestor] = right_[node];
        if (right_[node] != null) parent_[right_[node]] = ancestor;
        right_[node] = ancestor;
    } else if (right_[ancestor] == node) {
        right_[ancestor] = left_[node];
        if (left_[node] != null) parent_[left_[node]] = ancestor;
        left_[node] = ancestor;
    } else {
        throw std::logic_error("inconsistent parent link");
    }
    parent_[node] = grandparent;
    parent_[ancestor] = node;
    if (grandparent == null) root_ = node;
    else if (left_[grandparent] == ancestor) left_[grandparent] = node;
    else right_[grandparent] = node;
}

std::vector<std::uint32_t> BST::depths() const {
    struct Entry { Index node, parent, lower, upper; std::uint32_t depth; };
    std::vector<Entry> stack{{root_, null, null, null, 0}};
    std::vector<std::uint32_t> result(size());
    std::vector<bool> seen(size());
    std::size_t visited = 0;
    while (!stack.empty()) {
        auto entry = stack.back();
        stack.pop_back();
        auto node = entry.node;
        if (node == null) continue;
        if (node >= size() || seen[node]) throw std::logic_error("cycle or invalid child");
        seen[node] = true;
        ++visited;
        if (parent_[node] != entry.parent) throw std::logic_error("inconsistent parent link");
        if ((entry.lower != null && keys_[node] <= keys_[entry.lower]) ||
            (entry.upper != null && keys_[node] >= keys_[entry.upper]))
            throw std::logic_error("BST ordering violated");
        result[node] = entry.depth;
        stack.push_back({right_[node], node, node, entry.upper, entry.depth + 1});
        stack.push_back({left_[node], node, entry.lower, node, entry.depth + 1});
    }
    if (visited != size()) throw std::logic_error("unreachable node");
    return result;
}

std::size_t BST::storage_bytes() const {
    return keys_.capacity() * sizeof(Key) +
        (left_.capacity() + right_.capacity() + parent_.capacity()) * sizeof(Index);
}

void RebalanceContext::promote(Index node, std::uint32_t distance) {
    if (trace) stats.rotation_distances.push_back(distance);
    tree.rotate_up(node);
    ++stats.rotations;
}

std::uint32_t sample_target_depth(std::uint32_t node_count, RandomBits& bits) {
    if (node_count == 0) throw std::invalid_argument("node count must be positive");
    const auto levels = static_cast<unsigned>(std::bit_width(node_count - 1)) + 1;
    unsigned move = 0;
    while (move < levels && bits.bit() != 0) ++move;
    return move >= levels - 1 ? 0 : levels - move - 1;
}

void GeometricTargetLocalRepair::rebalance(RebalanceContext& context) {
    const auto target = sample_target_depth(++inserted_count_, context.bits);
    const auto depth = context.stats.insertion_depth;
    if (depth <= target) return;
    if (depth == target + 1) {
        context.promote(context.inserted, 0);
        return;
    }
    auto cursor = context.inserted;
    const auto distance = depth - target - 2;
    for (std::uint32_t step = 0; step < distance; ++step) {
        ++context.stats.visits;
        cursor = context.tree.parent(cursor);
    }
    ++context.stats.visits;
    const auto ancestor = context.tree.parent(cursor);
    const auto grandparent = context.tree.parent(ancestor);
    const bool straight = (context.tree.left(ancestor) == cursor) ==
                          (context.tree.left(grandparent) == ancestor);
    // Straight paths promote the parent once, unlike ordinary splay zig-zig.
    if (straight) context.promote(ancestor, distance + 1);
    else {
        context.promote(cursor, distance);
        context.promote(cursor, distance);
    }
}

StrategyFactory::StrategyFactory() {
    register_strategy("geometric-target-local-repair", [] {
        return std::make_unique<GeometricTargetLocalRepair>();
    });
    register_strategy("none", [] { return std::make_unique<NoRebalance>(); });
}

void StrategyFactory::register_strategy(std::string name, Creator creator) {
    if (name.empty() || !creator || creators_.contains(name))
        throw std::invalid_argument("empty or duplicate strategy registration");
    creators_.emplace(std::move(name), std::move(creator));
}

std::unique_ptr<Strategy> StrategyFactory::create(const std::string& name) const {
    const auto found = creators_.find(name);
    if (found == creators_.end()) throw std::invalid_argument("unknown strategy: " + name);
    auto strategy = found->second();
    if (!strategy) throw std::invalid_argument("strategy creator returned null");
    return strategy;
}

TreeFlavor::TreeFlavor(std::unique_ptr<Strategy> strategy, RandomBits bits, bool trace)
    : strategy_(std::move(strategy)), bits_(std::move(bits)), trace_(trace) {
    if (!strategy_) throw std::invalid_argument("strategy must not be null");
}

InsertionStats TreeFlavor::insert(Key key_value) {
    auto result = tree_.insert(key_value);
    InsertionStats stats{result.inserted, result.depth, 0, 0, 0, {}};
    if (result.inserted) {
        const auto before = bits_.count();
        RebalanceContext context{tree_, result.node, bits_, stats, trace_};
        strategy_->rebalance(context);
        stats.random_bits = bits_.count() - before;
    }
    return stats;
}

} // namespace balance_trees
