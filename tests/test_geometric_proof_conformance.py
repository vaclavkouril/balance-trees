"""Check the proof's immutable transition against the pointer implementation."""

import functools
import unittest

from helpers import FixedBits

from balance_trees import BST, TreeFlavor
from balance_trees.strategies.geometric_target_local_repair import (
    GeometricTargetLocalRepair,
)
from balance_trees.tree import Node


@functools.lru_cache(maxsize=None)
def ordered_trees(keys):
    if not keys:
        return (None,)
    return tuple(
        (left, key, right)
        for index, key in enumerate(keys)
        for left in ordered_trees(keys[:index])
        for right in ordered_trees(keys[index + 1 :])
    )


def insert(tree, key):
    if tree is None:
        return (None, key, None), ()
    left, value, right = tree
    if key < value:
        new_left, path = insert(left, key)
        return (new_left, value, right), (0, *path)
    if key > value:
        new_right, path = insert(right, key)
        return (left, value, new_right), (1, *path)
    raise ValueError("The conformance cases insert distinct keys")


def rotate_at(tree, path, side):
    """Promote one child of the node reached by path in an immutable tree."""
    left, key, right = tree
    if path:
        if path[0] == 0:
            return rotate_at(left, path[1:], side), key, right
        return left, key, rotate_at(right, path[1:], side)
    if side == 0:
        outer, child, middle = left
        return outer, child, (middle, key, right)
    middle, child, outer = right
    return (left, key, middle), child, outer


def reference_transition(tree, key, target):
    tree, path = insert(tree, key)
    depth = len(path)
    if depth <= target:
        return tree, depth, 0, 0
    if depth == target + 1:
        return rotate_at(tree, path[:-1], path[-1]), depth, 1, 0
    if path[target] == path[target + 1]:
        tree = rotate_at(tree, path[:target], path[target])
        rotations = 1
    else:
        tree = rotate_at(tree, path[: target + 1], path[target + 1])
        tree = rotate_at(tree, path[:target], path[target])
        rotations = 2
    return tree, depth, rotations, depth - target - 1


def pointer_tree(tree):
    result = BST()

    def build(subtree, parent):
        if subtree is None:
            return None
        left, key, right = subtree
        node = Node(key, parent=parent)
        node.left = build(left, node)
        node.right = build(right, node)
        return node

    result.root = build(tree, None)
    return result


def immutable_tree(node):
    if node is None:
        return None
    return immutable_tree(node.left), node.key, immutable_tree(node.right)


class GeometricProofConformanceTests(unittest.TestCase):
    def test_all_small_trees_gaps_and_target_levels_match_reference(self):
        # Independent immutable rotations check the precise sampled repair,
        # including both bent orientations and all shallow/no-op cases.
        for size in range(1, 8):
            keys = tuple(2 * index for index in range(size - 1))
            level = (size - 1).bit_length()
            for original in ordered_trees(keys):
                for gap in range(size):
                    key = 2 * gap - 1
                    for move in range(level + 1):
                        target = level - move
                        expected, depth, rotations, visits = reference_transition(
                            original, key, target
                        )
                        bits = FixedBits([1] * move + [0])
                        flavor = TreeFlavor(
                            GeometricTargetLocalRepair(inserted_count=size - 1),
                            tree=pointer_tree(original),
                            bits=bits,
                        )
                        stats = flavor.insert(key)
                        actual = immutable_tree(flavor.tree.root)
                        self.assertEqual(
                            (
                                actual,
                                stats.insertion_depth,
                                stats.rotations,
                                stats.visits,
                            ),
                            (expected, depth, rotations, visits),
                            (size, original, key, target),
                        )
                        self.assertEqual(stats.random_bits, move + 1)
                        self.assertEqual(len(flavor.tree.depths()), size)

    def test_reachable_chain_has_unbounded_conditional_repair_cost(self):
        # Selecting target zero for every increasing insertion makes the new
        # maximum the root. This history has positive probability under fair bits.
        for count in (4, 8, 16, 64):
            history = [
                bit
                for size in range(1, count + 1)
                for bit in [1] * ((size - 1).bit_length() + 1)
            ]
            flavor = TreeFlavor(
                GeometricTargetLocalRepair(), bits=FixedBits([*history, 0])
            )
            for key in range(1, count + 1):
                flavor.insert(key)
                self.assertEqual(flavor.tree.root.key, key)
            self.assertEqual(flavor.tree.depths()[1], count - 1)
            stats = flavor.insert(0)
            level = count.bit_length()  # ceil(log₂(count + 1))
            self.assertEqual(stats.insertion_depth, count)
            self.assertEqual(stats.visits, max(0, count - level - 1))


if __name__ == "__main__":
    unittest.main()
