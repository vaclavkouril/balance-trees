"""Tests for the proven 3/4 geometric target distribution and repair."""

import unittest

from helpers import FixedBits
from test_geometric_proof_conformance import (
    immutable_tree,
    ordered_trees,
    pointer_tree,
    reference_transition,
)

from balance_trees import TreeFlavor
from balance_trees.strategies.geometric_three_quarters import (
    GeometricThreeQuarters,
    maximum_target_depth,
    sample_target_depth,
)


class ThreeQuartersTests(unittest.TestCase):
    def test_exact_depth_boundaries(self):
        with self.assertRaises(ValueError):
            maximum_target_depth(0)
        numerator = denominator = 1
        for depth in range(1, 100):
            numerator *= 4
            denominator *= 3
            boundary = numerator // denominator
            if boundary * 3 ** (depth - 1) > 4 ** (depth - 1):
                self.assertEqual(maximum_target_depth(boundary), depth)
            result = maximum_target_depth(boundary + 1)
            self.assertGreater(result, depth)
            self.assertGreaterEqual(4**result, (boundary + 1) * 3**result)
            self.assertLess(4 ** (result - 1), (boundary + 1) * 3 ** (result - 1))

    def test_sampling_bit_patterns_and_cap(self):
        self.assertEqual(sample_target_depth(1, FixedBits([])), 0)
        for success in ([0, 1], [1, 0], [1, 1]):
            bits = FixedBits([*success, 0, 0])
            self.assertEqual(sample_target_depth(2, bits), 2)
            self.assertEqual(bits.count, 4)
        bits = FixedBits([1, 1] * 3)
        self.assertEqual(sample_target_depth(2, bits), 0)
        self.assertEqual(bits.count, 6)

    def test_all_small_trees_gaps_and_targets(self):
        for size in range(1, 7):
            level = maximum_target_depth(size)
            for original in ordered_trees(tuple(range(0, 2 * (size - 1), 2))):
                for gap in range(size):
                    key = 2 * gap - 1
                    for target in range(level + 1):
                        moves = level - target
                        tape = [1, 1] * moves + ([0, 0] if target else [])
                        flavor = TreeFlavor(
                            GeometricThreeQuarters(inserted_count=size - 1),
                            tree=pointer_tree(original),
                            bits=FixedBits(tape),
                        )
                        expected, depth, rotations, visits = reference_transition(
                            original, key, target
                        )
                        stats = flavor.insert(key)
                        self.assertEqual(
                            (
                                immutable_tree(flavor.tree.root),
                                stats.insertion_depth,
                                stats.rotations,
                                stats.visits,
                            ),
                            (expected, depth, rotations, visits),
                        )
                        self.assertEqual(len(flavor.tree.depths()), size)


if __name__ == "__main__":
    unittest.main()
