import itertools
import unittest
from collections import Counter

from helpers import FixedBits

from balance_trees import BST, IntervalTargetLocalRepair, RandomLevelV2, TreeFlavor
from balance_trees.sequences import ORDERS, insertion_order
from balance_trees.strategies.geometric_target_local_repair import sample_target_depth
from balance_trees.strategies.perfect_tree_target import sample_perfect_tree_depth


class PerfectTreeStrategyTests(unittest.TestCase):
    def test_v2_descriptive_name_preserves_the_original_class(self):
        self.assertIs(RandomLevelV2, IntervalTargetLocalRepair)
        self.assertIs(
            type(TreeFlavor.create("interval-target-local-repair").strategy),
            IntervalTargetLocalRepair,
        )

    def test_uniform_perfect_tree_vertex_depths_have_exact_level_weights(self):
        depths = Counter()
        for label in range(1, 8):
            bits = FixedBits(int(bit) for bit in f"{label:03b}")
            depths[sample_perfect_tree_depth(7, bits)] += 1
            self.assertEqual(bits.count, 3)
        self.assertEqual(depths, {0: 1, 1: 2, 2: 4})
        bits = FixedBits([0, 0, 0, 1, 0, 1])
        self.assertEqual(sample_perfect_tree_depth(7, bits), 2)
        self.assertEqual(bits.count, 6)
        self.assertEqual(sample_perfect_tree_depth(1, FixedBits([])), 0)
        for size, width in ((2, 2), (3, 2), (4, 3), (7, 3), (8, 4)):
            bits = FixedBits([1] * width)
            self.assertEqual(sample_perfect_tree_depth(size, bits), width - 1)

    def test_geometric_sampler_matches_pseudocode_at_power_boundaries(self):
        for size in (1, 2, 3, 4, 5, 7, 8, 9):
            levels = (size - 1).bit_length() + 1
            for values in itertools.product((0, 1), repeat=levels):
                move = next((i for i, bit in enumerate(values) if bit == 0), levels)
                bits = FixedBits(values)
                self.assertEqual(
                    sample_target_depth(size, bits), max(0, levels - move - 1)
                )
                self.assertEqual(bits.count, min(move + 1, levels))

    def test_leaf_promotion_reaches_target_and_can_exceed_two_rotations(self):
        tree = BST()
        for key in range(7):
            tree.insert(key)
        policy = TreeFlavor.create("random-level").strategy
        policy.inserted_count = 7
        flavor = TreeFlavor(policy, tree=tree, bits=FixedBits([0, 0, 0, 1]))
        stats = flavor.insert(7)
        self.assertEqual(stats.insertion_depth, 7)
        self.assertEqual(stats.rotations, 7)
        self.assertEqual(tree.depths()[7], 0)

    def test_leaves_above_or_at_the_target_remain_in_place(self):
        for strategy in ("random-level", "geometric-target-local-repair"):
            for keys, key, insertion_depth in (([0, -1, -2], 1, 1), ([0, 1, -1], 2, 2)):
                tree = BST()
                for existing in keys:
                    tree.insert(existing)
                policy = TreeFlavor.create(strategy).strategy
                policy.inserted_count = 3
                bits = FixedBits([1, 1, 1] if strategy == "random-level" else [0])
                flavor = TreeFlavor(policy, tree=tree, bits=bits)
                stats = flavor.insert(key)
                self.assertEqual(stats.insertion_depth, insertion_depth)
                self.assertEqual(stats.rotations, 0)
                self.assertEqual(tree.depths()[key], insertion_depth)

    def test_geometric_repairs_straight_and_bent_paths_at_the_root(self):
        for keys, key, expected_root, rotations in (
            ([0, 1, 2, 3, 4, 5, 6], 7, 1, 1),
            ([0, 6, 1, 5, 2, 4, 3], 7, 6, 1),
            ([0, 6, 1, 5, 2, 4, 3], -1, -1, 1),
            ([0, 6, 1, 5, 2, 4], 3, 1, 2),
        ):
            with self.subTest(keys=keys, key=key):
                tree = BST()
                for existing in keys:
                    tree.insert(existing)
                policy = TreeFlavor.create("geometric-target-local-repair").strategy
                policy.inserted_count = len(keys)
                flavor = TreeFlavor(policy, tree=tree, bits=FixedBits([1] * 4))
                stats = flavor.insert(key)
                self.assertEqual(stats.rotations, rotations)
                self.assertEqual(tree.root.key, expected_root)
                tree.depths()

    def test_empty_duplicates_lookup_and_invariants_across_all_workloads(self):
        for strategy in ("random-level", "geometric-target-local-repair"):
            for order in ORDERS:
                for seed in (0, 2026):
                    flavor = TreeFlavor.create(strategy, seed=seed)
                    self.assertEqual(flavor.tree.depths(), {})
                    for key in insertion_order(order, 64, seed):
                        stats = flavor.insert(key)
                        flavor.tree.depths()
                        if strategy == "geometric-target-local-repair":
                            self.assertLessEqual(stats.rotations, 2)
                    before = flavor.tree.depths()
                    duplicate = flavor.insert(32)
                    self.assertFalse(duplicate.inserted)
                    self.assertEqual(duplicate.random_bits, 0)
                    self.assertEqual(duplicate.rotations, 0)
                    self.assertEqual(flavor.strategy.inserted_count, 64)
                    self.assertEqual(flavor.tree.depths(), before)
                    self.assertTrue(flavor.tree.contains(32))
                    self.assertFalse(flavor.tree.contains(65))

    def test_samplers_reject_empty_reference_trees(self):
        for sampler in (sample_target_depth, sample_perfect_tree_depth):
            with self.assertRaises(ValueError):
                sampler(0, FixedBits([]))
