import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from balance_trees.benchmark_comparison_report import generate_report
from balance_trees.benchmark_parallel import comparison_strategy, run_comparison
from balance_trees.measurement import run_trial
from balance_trees.sequences import ORDERS, insertion_order


class ParallelBenchmarkTests(unittest.TestCase):
    def test_alternate_geometric_matches_the_main_implementation(self):
        for order in ORDERS:
            values = insertion_order(order, 64, 17)
            original = run_trial(
                values, comparison_strategy("geometric-target-local-repair", 2026), 2026
            )
            alternate = run_trial(
                values,
                comparison_strategy("geometric-target-local-repair-alternate", 2026),
                2026,
            )
            self.assertEqual(asdict(original.metrics), asdict(alternate.metrics))
            self.assertEqual(original.depths, alternate.depths)

    def test_parallel_trials_validate_pair_and_resume_without_repeating_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            settings = dict(
                sizes=[8, 16],
                workers=2,
                timeout=20,
                memory_mib=256,
                small_trials=2,
                repeat_through=8,
                seed=2026,
                strategies=("geometric-target-local-repair", "treap"),
                orders=("random", "converging"),
            )
            results = run_comparison(output, **settings)
            self.assertEqual(len(results["trials"]), 12)
            self.assertTrue(
                all(row["status"] == "complete" for row in results["trials"])
            )
            for row in results["trials"]:
                if row["strategy"] == "treap":
                    self.assertEqual(row["metrics"]["mean_random_bits"], 32)
                else:
                    self.assertLessEqual(row["metrics"]["max_rotations"], 2)
                partner = next(
                    other
                    for other in results["trials"]
                    if other["strategy"] != row["strategy"]
                    and all(other[key] == row[key] for key in ("n", "order", "trial"))
                )
                self.assertEqual(row["seed"], partner["seed"])
                self.assertEqual(row["order_seed"], partner["order_seed"])
            for summary in results["summaries"]:
                heights = [
                    r["metrics"]["height"]
                    for r in results["trials"]
                    if all(r[k] == summary[k] for k in ("strategy", "order", "n"))
                ]
                self.assertEqual(summary["maximum_height"], max(heights))
            with patch(
                "balance_trees.benchmark_parallel.execute_trial",
                side_effect=AssertionError("rerun"),
            ):
                resumed = run_comparison(output, **settings)
            self.assertEqual(results["trials"], resumed["trials"])
            self.assertEqual(
                json.loads((output / "results.json").read_text())["trials"],
                results["trials"],
            )
            report = generate_report(output)
            self.assertIn("Mean random bits / key", report.read_text())
            self.assertIn("Maximum final height", report.read_text())
            self.assertEqual(len(list((report.parent / "figures").glob("*.svg"))), 8)
            for figure in (report.parent / "figures").glob("*.svg"):
                ElementTree.parse(figure)
            ElementTree.parse(report.parent / "all-sequences.svg")

    def test_resource_failure_stops_only_its_strategy_workload(self):
        def fail(request, source, timeout):
            return {
                **request,
                "status": "timeout",
                "metrics": {},
                "detail": "test deadline",
            }

        with tempfile.TemporaryDirectory() as temporary:
            with patch(
                "balance_trees.benchmark_parallel.execute_trial", side_effect=fail
            ) as execute:
                results = run_comparison(
                    Path(temporary) / "run",
                    sizes=[8, 16, 32],
                    workers=2,
                    timeout=1,
                    memory_mib=256,
                    small_trials=2,
                    repeat_through=32,
                    seed=2026,
                    strategies=("treap",),
                    orders=("random",),
                )
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(
                [r["status"] for r in results["trials"]], ["timeout"] + ["not_run"] * 5
            )
