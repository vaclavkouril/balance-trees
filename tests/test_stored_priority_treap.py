import unittest

from balance_trees.flavors import TreeFlavor
from balance_trees.measurement import run_trial
from balance_trees.sequences import insertion_order
from balance_trees.showcase import build_trace
from balance_trees.strategies.stored_priority_treap import StoredPriorityTreap

ORDERS = ("random", "increasing", "converging")


class StoredPriorityTreapTests(unittest.TestCase):
    def test_benchmark_treap_matches_existing_showcase(self):
        for order in ORDERS:
            for seed in (0, 42, 2026):
                with self.subTest(order=order, seed=seed):
                    values = insertion_order(order, 24, 17)
                    trace = build_trace(values, "treap", seed)
                    final = trace["frames"][-1]["stats"]
                    result = run_trial(values, StoredPriorityTreap(seed), seed)
                    self.assertEqual(result.metrics.height, final["height"])
                    self.assertEqual(result.metrics.mean_depth, final["mean_depth"])
                    self.assertEqual(
                        result.metrics.mean_rotations * len(values), final["rotations"]
                    )
                    self.assertEqual(result.metrics.mean_random_bits, 32)

    def test_empty_duplicates_lookup_and_tied_priorities(self):
        class EqualPriorities:
            def getrandbits(self, count):
                return 7

        strategy = StoredPriorityTreap(0)
        strategy.random = EqualPriorities()
        flavor = TreeFlavor(strategy)
        self.assertEqual(flavor.tree.depths(), {})
        self.assertFalse(flavor.tree.contains(2))
        for key in (3, 2, 1):
            flavor.insert(key)
            flavor.tree.depths()
        before = flavor.tree.depths()
        self.assertEqual(flavor.tree.root.key, 1)
        duplicate = flavor.insert(2)
        self.assertFalse(duplicate.inserted)
        self.assertEqual(duplicate.rotations, 0)
        self.assertEqual(duplicate.random_bits, 0)
        self.assertEqual(flavor.tree.depths(), before)
        self.assertTrue(flavor.tree.contains(2))
