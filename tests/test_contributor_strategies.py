import unittest

from balance_trees.flavors import TreeFlavor
from balance_trees.random_bits import RandomBits
from balance_trees.sequences import ORDERS, insertion_order
from balance_trees.strategies import create_strategy


class ContributorStrategyTests(unittest.TestCase):
    def test_new_policies_preserve_invariants_and_duplicates_in_every_order(self):
        for name in ("random-level-v2-1", "random-level-v3", "random-level-v4"):
            for order in ORDERS:
                for seed in (0, 2026):
                    with self.subTest(strategy=name, order=order, seed=seed):
                        flavor = TreeFlavor.create(name, seed=seed)
                        self.assertEqual(flavor.tree.depths(), {})
                        for key in insertion_order(order, 48, seed):
                            flavor.insert(key)
                            flavor.tree.depths()
                        self.assertTrue(flavor.tree.contains(24))
                        self.assertFalse(flavor.tree.contains(49))
                        before = flavor.tree.depths()
                        count = flavor.strategy.inserted_count
                        duplicate = flavor.insert(24)
                        self.assertFalse(duplicate.inserted)
                        self.assertEqual(duplicate.random_bits, 0)
                        self.assertEqual(duplicate.rotations, 0)
                        self.assertEqual(flavor.strategy.inserted_count, count)
                        self.assertEqual(flavor.tree.depths(), before)

    def test_v21_bit_width_and_extrema_mapping_at_each_growth(self):
        flavor = TreeFlavor.create("random-level-v2-1", seed=17)
        source = RandomBits(17)
        lowest = highest = None
        old_width = 0
        for ordinal in range(1, 65):
            width = ordinal.bit_length()
            if width > old_width:
                if lowest is not None:
                    lowest = 2 * lowest + 1
                    highest *= 2
                old_width = width
            priority = 0
            for _ in range(width):
                priority = priority * 2 + source.bit()
            lowest = priority if lowest is None else min(lowest, priority)
            highest = priority if highest is None else max(highest, priority)
            stats = flavor.insert(ordinal)
            self.assertEqual(stats.random_bits, width)
            self.assertEqual(flavor.strategy.lowest_priority, lowest)
            self.assertEqual(flavor.strategy.highest_priority, highest)
        self.assertIsNot(
            create_strategy("random-level-v3"), create_strategy("random-level-v3")
        )
