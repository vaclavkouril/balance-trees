"""Exact small-state checks for geometric target repair.

Run ``PYTHONPATH=src python3 benchmarks/proof_triage.py --size 7``.
The result maximizes expected final height over adaptive gap choices.  It is
finite evidence, not an asymptotic bound; all branching weights are exact.
"""

import argparse
import json
from collections import defaultdict
from fractions import Fraction
from functools import cache

from balance_trees.flavors import TreeFlavor
from balance_trees.strategies.geometric_target_local_repair import (
    GeometricTargetLocalRepair,
)
from balance_trees.tree import BST, Node


class FixedBits:
    """Supply a sampler prefix that selects one target."""

    def __init__(self, prefix):
        self.prefix = iter(prefix)
        self.count = 0

    def bit(self):
        self.count += 1
        return next(self.prefix)


def unpack_tree(shape, parent=None):
    if shape is None:
        return None
    key, left, right = shape
    node = Node(key, parent=parent)
    node.left = unpack_tree(left, node)
    node.right = unpack_tree(right, node)
    return node


def pack_tree(node):
    if node is None:
        return None
    return (node.key, pack_tree(node.left), pack_tree(node.right))


def shift_keys(shape, gap):
    if shape is None:
        return None
    key, left, right = shape
    return (key + (key >= gap), shift_keys(left, gap), shift_keys(right, gap))


def height(shape):
    if shape is None:
        return -1
    return 1 + max(height(shape[1]), height(shape[2]))


def adaptive_attack_key(tree, target_depth):
    """Choose the minimum gap in the left subtree of a right-spine node.

    Keys must support rational arithmetic and the right spine must reach the
    selected depth. The fresh key is below the current maximum.
    """
    node = tree.root
    lower_bound = None
    for _ in range(target_depth):
        if node is None:
            raise ValueError("right spine does not reach the target")
        lower_bound = node.key
        node = node.right
    if node is None:
        raise ValueError("right spine does not reach the target")
    upper_bound = node.key
    node = node.left
    while node is not None:
        upper_bound = node.key
        node = node.left
    if lower_bound is None:
        return Fraction(upper_bound) - 1
    return (Fraction(lower_bound) + Fraction(upper_bound)) / 2


def adaptive_probe_key(tree):
    """Choose the gap immediately below the current maximum via its left subtree."""
    node = tree.root
    if node is None:
        raise ValueError("cannot probe an empty tree")
    lower_bound = None
    while node.right is not None:
        lower_bound = node.key
        node = node.right
    maximum = node.key
    node = node.left
    while node is not None:
        lower_bound = node.key
        node = node.right
    if lower_bound is None:
        return Fraction(maximum) - 1
    return (Fraction(lower_bound) + Fraction(maximum)) / 2


def target_prefixes(node_count):
    """Give a representative prefix and exact probability for each target."""
    k = (node_count - 1).bit_length()
    for ones in range(k):
        yield (1,) * ones + (0,), Fraction(1, 2 ** (ones + 1))
    # For target zero, both possible final coin outcomes are equivalent;
    # use the zero representative and combine their probabilities.
    yield (1,) * k + (0,), Fraction(1, 2**k)


@cache
def transitions(shape, gap, node_count):
    """Apply the production implementation after choosing a ranked gap."""
    outcomes = defaultdict(Fraction)
    for prefix, probability in target_prefixes(node_count):
        tree = BST()
        tree.root = unpack_tree(shift_keys(shape, gap))
        flavor = TreeFlavor(
            GeometricTargetLocalRepair(inserted_count=node_count - 1),
            tree=tree,
            bits=FixedBits(prefix),
        )
        stats = flavor.insert(gap)
        tree.depths()
        outcomes[(pack_tree(tree.root), stats.insertion_depth, stats.visits)] += (
            probability
        )
    assert sum(outcomes.values()) == 1
    return tuple((outcome, probability) for outcome, probability in outcomes.items())


@cache
def optimal_expected_height(shape, node_count, final_size):
    if node_count == final_size:
        return Fraction(height(shape))
    candidates = []
    for gap in range(node_count + 1):
        expected = sum(
            probability * optimal_expected_height(new_shape, node_count + 1, final_size)
            for (new_shape, _, _), probability in transitions(
                shape, gap, node_count + 1
            )
        )
        candidates.append(expected)
    return max(candidates)


def increasing_statistics(size):
    states = {None: Fraction(1)}
    last_visits = Fraction(0)
    max_insertion_depth = 0
    for count in range(1, size + 1):
        next_states = defaultdict(Fraction)
        last_visits = Fraction(0)
        for shape, shape_probability in states.items():
            for (new_shape, depth, visits), probability in transitions(
                shape, count - 1, count
            ):
                weight = shape_probability * probability
                next_states[new_shape] += weight
                last_visits += weight * visits
                max_insertion_depth = max(max_insertion_depth, depth)
        states = next_states
    return {
        "states": len(states),
        "expected_height": str(
            sum(weight * height(shape) for shape, weight in states.items())
        ),
        "expected_last_visits": str(last_visits),
        "maximum_insertion_depth_seen": max_insertion_depth,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=7)
    args = parser.parse_args()
    if not 1 <= args.size <= 8:
        parser.error("size must be between 1 and 8; state space grows rapidly")
    result = {
        "size": args.size,
        "adaptive_max_expected_final_height": str(
            optimal_expected_height(None, 0, args.size)
        ),
        "increasing": increasing_statistics(args.size),
        "interpretation": "exact finite-state values; no asymptotic inference",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
