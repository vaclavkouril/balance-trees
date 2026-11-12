import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from balance_trees.benchmark_comparison_report import generate_report
from balance_trees.benchmark_native import (
    BIASED_NATIVE,
    NATIVE,
    execute_native_trial,
    run_native_comparison,
)
from balance_trees.benchmark_parallel import run_comparison


@unittest.skipUnless(
    shutil.which("c++") and shutil.which("cmake"), "C++20 and CMake required"
)
class NativeBenchmarkTests(unittest.TestCase):
    def test_standalone_run_compares_both_strategies_and_reuses_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "native"
            options = dict(
                sizes=[8, 32],
                orders=("random", "increasing"),
                small_trials=2,
                repeat_through=8,
                timeout=20,
                memory_mib=256,
            )
            results = run_native_comparison(None, output, **options)
            self.assertEqual(results["metadata"]["strategies"], [NATIVE, BIASED_NATIVE])
            self.assertEqual(len(results["trials"]), 12)
            inputs = {}
            for row in results["trials"]:
                self.assertEqual(row["status"], "complete")
                self.assertLessEqual(row["metrics"]["max_rotations"], 2)
                self.assertEqual(row["metrics"]["node_storage_bytes"], 20 * row["n"])
                case = row["order"], row["n"], row["trial"]
                if case in inputs:
                    self.assertEqual(inputs[case], (row["seed"], row["input_sha256"]))
                inputs[case] = row["seed"], row["input_sha256"]
            for size in (8, 32):
                bits = {
                    row["strategy"]: row["metrics"]["mean_random_bits"]
                    for row in results["trials"]
                    if row["n"] == size
                    and row["order"] == "increasing"
                    and row["trial"] == 0
                }
                self.assertGreater(bits[BIASED_NATIVE], bits[NATIVE])
            before = (output / "trials.jsonl").read_bytes()
            resumed = run_native_comparison(None, output, **options)
            self.assertEqual(results["trials"], resumed["trials"])
            self.assertEqual(before, (output / "trials.jsonl").read_bytes())
            with self.assertRaisesRegex(ValueError, "identical baseline and settings"):
                run_native_comparison(None, output, **options, seed=123)
            self.assertFalse((output / "input.txt").exists())

    def test_failure_stops_only_its_strategy_and_remains_censored_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "native"
            options = dict(
                sizes=[8, 16],
                orders=("increasing",),
                small_trials=2,
                repeat_through=16,
                timeout=20,
                memory_mib=256,
            )

            def fail_old_strategy(executable, input_path, request, timeout):
                if request["strategy"] == NATIVE:
                    return {
                        **request,
                        "status": "memory_limit",
                        "metrics": {},
                        "detail": "injected resource limit",
                    }
                return execute_native_trial(executable, input_path, request, timeout)

            with patch(
                "balance_trees.benchmark_native.execute_native_trial",
                side_effect=fail_old_strategy,
            ):
                results = run_native_comparison(None, output, **options)
            old = [row for row in results["trials"] if row["strategy"] == NATIVE]
            new = [row for row in results["trials"] if row["strategy"] == BIASED_NATIVE]
            self.assertEqual(
                [row["status"] for row in old],
                ["memory_limit", "not_run", "not_run", "not_run"],
            )
            self.assertTrue(all(row["status"] == "complete" for row in new))
            with patch("balance_trees.benchmark_native.execute_native_trial") as worker:
                resumed = run_native_comparison(None, output, **options)
            worker.assert_not_called()
            self.assertEqual(results["trials"], resumed["trials"])

    def test_native_run_preserves_baseline_validates_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline"
            output = Path(directory) / "native"
            original = run_comparison(
                baseline,
                sizes=[8, 16],
                workers=1,
                timeout=20,
                memory_mib=256,
                small_trials=2,
                repeat_through=8,
                seed=2026,
                strategies=("geometric-target-local-repair", "treap"),
                orders=("random", "increasing"),
            )
            original_bytes = (baseline / "results.json").read_bytes()
            results = run_native_comparison(
                baseline, output, timeout=20, memory_mib=256
            )
            self.assertEqual((baseline / "results.json").read_bytes(), original_bytes)
            old = [row for row in results["trials"] if row["strategy"] != NATIVE]
            self.assertEqual(
                old,
                sorted(
                    original["trials"],
                    key=lambda row: (
                        row["strategy"],
                        row["order"],
                        row["n"],
                        row["trial"],
                    ),
                ),
            )
            native = [row for row in results["trials"] if row["strategy"] == NATIVE]
            self.assertEqual(len(native), 6)
            for row in native:
                self.assertEqual(row["status"], "complete")
                metrics = row["metrics"]
                self.assertEqual(metrics["node_storage_bytes"], row["n"] * 20)
                self.assertLessEqual(metrics["max_rotations"], 2)
                self.assertGreater(metrics["elapsed_seconds"], 0)
                self.assertGreater(metrics["peak_rss_mib"], 0)
                self.assertLessEqual(metrics["mean_random_bits"], 4)
                self.assertEqual(len(row["input_sha256"]), 64)
            resumed = run_native_comparison(
                baseline, output, timeout=20, memory_mib=256
            )
            self.assertEqual(results["trials"], resumed["trials"])
            report = generate_report(output)
            text = report.read_text()
            self.assertIn("C++ geometric repair · native benchmark extension", text)
            self.assertIn("not paired random streams", text)
            self.assertIn("20 bytes", text)
            figures = list((report.parent / "figures").glob("*.svg"))
            self.assertEqual(len(figures), 16)
            for path in [
                *figures,
                report.parent / "all-sequences.svg",
                report.parent / "native-all-sequences.svg",
            ]:
                ElementTree.parse(path)
            with ZipFile(report.parent / "source.zip") as archive:
                self.assertIn("native/benchmark.cpp", archive.namelist())
                self.assertIn(
                    "native/include/balance_trees/tree.hpp", archive.namelist()
                )
                self.assertIn("report_renderer.py", archive.namelist())
            config = json.loads((report.parent / "config.json").read_text())
            self.assertIn("SplitMix64", config["native_sampling"])
