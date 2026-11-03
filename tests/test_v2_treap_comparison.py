import importlib.util
import unittest
from pathlib import Path

from balance_trees.flavors import TreeFlavor
from balance_trees.measurement import run_trial
from balance_trees.sequences import insertion_order
from balance_trees.showcase import build_trace

SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks/compare_v2_treap.py"
SPEC = importlib.util.spec_from_file_location("comparison", SCRIPT)
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


class TreapComparisonTests(unittest.TestCase):
    def test_benchmark_treap_matches_existing_showcase(self):
        for order in comparison.ORDERS:
            for seed in (0, 42, 2026):
                with self.subTest(order=order, seed=seed):
                    values = insertion_order(order, 24, 17)
                    trace = build_trace(values, "treap", seed)
                    final = trace["frames"][-1]["stats"]
                    result = run_trial(
                        values, comparison.StoredPriorityTreap(seed), seed
                    )
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

        strategy = comparison.StoredPriorityTreap(0)
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

    def test_worker_validates_both_strategies_for_each_workload(self):
        for strategy in comparison.STRATEGIES:
            for order in comparison.ORDERS:
                row = comparison.measure(
                    dict(
                        strategy=strategy,
                        order=order,
                        n=32,
                        trial=0,
                        seed=2026,
                        order_seed=17,
                    )
                )
                self.assertEqual(row["status"], "complete")
                self.assertLess(row["metrics"]["height"], 32)
