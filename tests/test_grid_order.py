import tempfile
import unittest
from pathlib import Path

from balance_trees.benchmark import run_benchmarks
from balance_trees.sequences import ORDERS, SUPPORTED_ORDERS, insertion_order


class GridOrderTests(unittest.TestCase):
    def test_exact_small_orders(self):
        for n, expected in (
            (1, [0]),
            (4, [0, 2, 1, 3]),
            (9, [0, 3, 6, 1, 4, 7, 2, 5, 8]),
            (16, [0, 4, 8, 12, 1, 5, 9, 13, 2, 6, 10, 14, 3, 7, 11, 15]),
        ):
            with self.subTest(n=n):
                self.assertEqual(insertion_order("grid", n, 2026), expected)

    def test_square_orders_cover_every_key_once_and_ignore_seed(self):
        for b in range(1, 33):
            with self.subTest(b=b):
                n = b * b
                values = insertion_order("grid", n, 2026)
                self.assertEqual(len(values), n)
                self.assertEqual(sorted(values), list(range(n)))
                self.assertEqual(values, insertion_order("grid", n, 0))
                for j in range(b):
                    self.assertEqual(values[j * b : (j + 1) * b], list(range(j, n, b)))

    def test_non_square_sizes_are_rejected(self):
        for n in (2, 3, 5, 8, 10, 15, 17, 1000):
            with self.subTest(n=n):
                with self.assertRaisesRegex(ValueError, "perfect-square"):
                    insertion_order("grid", n, 2026)

    def test_non_positive_sizes_are_rejected(self):
        for n in (0, -1):
            with self.subTest(n=n):
                with self.assertRaisesRegex(ValueError, "positive"):
                    insertion_order("grid", n, 2026)

    def test_grid_is_opt_in_and_paper_defaults_are_unchanged(self):
        self.assertEqual(
            ORDERS,
            ("random", "increasing", "decreasing", "converging", "pairs", "bitonic", "runs"),
        )
        self.assertEqual(SUPPORTED_ORDERS, (*ORDERS, "grid"))

    def test_benchmark_rejects_non_square_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with self.assertRaisesRegex(ValueError, "perfect-square"):
                run_benchmarks(
                    output,
                    sizes=[9, 10],
                    trials=1,
                    seed=2026,
                    strategies=["none"],
                    orders=["grid"],
                    timeout=10,
                )
            self.assertFalse(output.exists())

    def test_grid_benchmark_completes_and_validates_trees(self):
        with tempfile.TemporaryDirectory() as temporary:
            results = run_benchmarks(
                Path(temporary) / "run",
                sizes=[4, 9],
                trials=1,
                seed=2026,
                strategies=["none", "random-level"],
                orders=["grid"],
                timeout=10,
            )
            self.assertEqual(results["metadata"]["orders"], ["grid"])
            self.assertEqual(len(results["trials"]), 4)
            self.assertTrue(all(row["status"] == "complete" for row in results["trials"]))
