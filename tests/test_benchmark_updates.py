import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

from balance_trees.benchmark_updates import WORKLOADS, execute_trial, run_updates
from balance_trees.experiment import derived_seed


def worker_request():
    return dict(
        workload="random-churn", n=8, trial=0, seed=13, order_seed=29, memory_mib=256
    )


def worker_metrics(request):
    n = request["n"]
    return {
        "schema_version": 1,
        **{key: request[key] for key in ("workload", "n", "seed", "order_seed")},
        "preload_order": "random",
        "operation_fingerprint": "0123456789abcdef",
        "operations": 2 * n,
        "insert_attempts": n,
        "inserted": n,
        "delete_attempts": n,
        "erased": n,
        "search_attempts": 0,
        "found": 0,
        "final_nodes": n,
        "height": 4,
        "mean_depth": 2.5,
        "sampled_max_height": 4,
        "mean_insertion_depth": 3,
        "rotations": 20,
        "mean_rotations": 20 / (2 * n),
        "max_rotations": 4,
        "insert_rotations": 8,
        "mean_insert_rotations": 8 / n,
        "max_insert_rotations": 2,
        "delete_rotations": 12,
        "mean_delete_rotations": 12 / n,
        "max_delete_rotations": 4,
        "random_bits": 100,
        "mean_random_bits": 100 / (2 * n),
        "max_random_bits": 16,
        "visits": 40,
        "search_visits": 80,
        "refreshes": 2 * n,
        "minimum_moves": 1,
        "elapsed_seconds": 0.01,
        "cpu_seconds": 0.005,
        "preload_seconds": 0.005,
        "worker_seconds": 0.02,
        "node_storage_bytes": 20 * n,
        "peak_rss_mib": 4.0,
        "checkpoints": [
            dict(completed_ops=completed, n=n, height=4, mean_depth=2.5)
            for completed in (0, 4, 8, 12, 16)
        ],
    }


class UpdateWorkerResponseTests(unittest.TestCase):
    def test_valid_response_retains_measurements_and_uses_requested_parameters(self):
        request = worker_request()
        metrics = worker_metrics(request)
        process = subprocess.CompletedProcess([], 0, json.dumps(metrics), "")
        with patch(
            "balance_trees.benchmark_updates.subprocess.run", return_value=process
        ) as run:
            row = execute_trial(Path("/worker"), request, 2.5)
        self.assertEqual(row, {**request, "status": "complete", "metrics": metrics})
        run.assert_called_once_with(
            ["/worker", "13", "8", "256", "random-churn", "29"],
            capture_output=True,
            text=True,
            timeout=2.5,
        )

    def test_wrong_identity_incomplete_results_and_invalid_numbers_are_errors(self):
        request = worker_request()
        original = worker_metrics(request)
        cases = [
            {**original, key: wrong}
            for key, wrong in (
                ("workload", "grow-shrink"),
                ("n", 9),
                ("seed", 14),
                ("order_seed", 30),
                ("operations", 15),
                ("checkpoints", []),
                ("elapsed_seconds", float("nan")),
                ("cpu_seconds", -1),
                ("peak_rss_mib", float("inf")),
                ("max_insert_rotations", 3),
                ("max_delete_rotations", 5),
                ("sampled_max_height", float("nan")),
                ("final_nodes", 7),
                ("inserted", 7),
                ("erased", 7),
                ("search_attempts", 1),
                ("found", 1),
                ("checkpoints", [{}]),
            )
        ]
        for point, change in (
            (0, {"completed_ops": 1}),
            (-1, {"completed_ops": 15}),
            (-1, {"n": 7}),
            (1, {"completed_ops": 0}),
            (1, {"n": 0, "height": 0, "mean_depth": 0}),
            (1, {"height": 8}),
            (1, {"mean_depth": 5}),
            (1, {"n": -1}),
        ):
            malformed = copy.deepcopy(original)
            malformed["checkpoints"][point].update(change)
            cases.append(malformed)
        missing = dict(original)
        del missing["operations"]
        for index, payload in enumerate([*cases, missing, [], None]):
            with self.subTest(case=index):
                process = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
                with patch(
                    "balance_trees.benchmark_updates.subprocess.run",
                    return_value=process,
                ):
                    row = execute_trial(Path("/worker"), request, 1)
                self.assertEqual(row["status"], "error")
                self.assertEqual(row["metrics"], {})
                self.assertTrue(row["detail"])

    def test_sub_resolution_cpu_time_is_valid(self):
        request = worker_request()
        metrics = {**worker_metrics(request), "cpu_seconds": 0}
        process = subprocess.CompletedProcess([], 0, json.dumps(metrics), "")
        with patch(
            "balance_trees.benchmark_updates.subprocess.run", return_value=process
        ):
            row = execute_trial(Path("/worker"), request, 1)
        self.assertEqual(row["status"], "complete")

    def test_process_failures_and_malformed_json_are_explicit(self):
        request = worker_request()
        cases = (
            (
                subprocess.CompletedProcess([], 2, "", "allocation failed"),
                "memory_limit",
            ),
            (subprocess.CompletedProcess([], 1, "", "invalid workload"), "error"),
            (subprocess.CompletedProcess([], -9, "", ""), "error"),
            (subprocess.CompletedProcess([], 0, "{bad json", ""), "error"),
            (subprocess.TimeoutExpired("worker", 1), "timeout"),
            (FileNotFoundError("worker missing"), "error"),
        )
        for result, status in cases:
            with self.subTest(result=result):
                options = (
                    {"side_effect": result}
                    if isinstance(result, Exception)
                    else {"return_value": result}
                )
                with patch("balance_trees.benchmark_updates.subprocess.run", **options):
                    row = execute_trial(Path("/worker"), request, 1)
                self.assertEqual(row["status"], status)
                self.assertEqual(row["metrics"], {})
                self.assertTrue(row["detail"])


class UpdateRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "run"
        self.options = dict(
            sizes=[8, 16],
            workloads=("random-churn", "ascending-churn"),
            workers=2,
            memory_mib=256,
            timeout=10,
            small_trials=2,
            repeat_through=8,
            seed=2026,
        )
        compiler = patch(
            "balance_trees.benchmark_updates.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "test compiler\n", ""),
        )
        compiler.start()
        self.addCleanup(compiler.stop)
        build = patch(
            "balance_trees.benchmark_updates.build_worker", return_value=Path("/worker")
        )
        self.build = build.start()
        self.addCleanup(build.stop)

    @staticmethod
    def complete(executable, request, timeout):
        return {
            **request,
            "status": "complete",
            "metrics": {"operations": 2 * request["n"]},
        }

    def run_complete(self):
        with patch(
            "balance_trees.benchmark_updates.execute_trial", side_effect=self.complete
        ):
            return run_updates(self.output, **self.options)

    def test_parallel_lanes_do_not_overlap_the_same_workload_and_resume_exactly(self):
        barrier = Barrier(2, timeout=10)
        lock = Lock()
        active = set()
        maximum_active = 0

        def worker(executable, request, timeout):
            nonlocal maximum_active
            workload = request["workload"]
            with lock:
                self.assertNotIn(workload, active)
                active.add(workload)
                maximum_active = max(maximum_active, len(active))
            try:
                barrier.wait()
                return self.complete(executable, request, timeout)
            finally:
                with lock:
                    active.remove(workload)

        with patch("balance_trees.benchmark_updates.execute_trial", side_effect=worker):
            results = run_updates(self.output, **self.options)
        self.assertEqual(maximum_active, 2)
        self.assertEqual(len(results["trials"]), 6)
        for row in results["trials"]:
            self.assertEqual(row["status"], "complete")
            self.assertEqual(
                row["seed"],
                derived_seed(
                    2026, "update-rotation", row["n"], row["workload"], row["trial"]
                ),
            )
            self.assertEqual(
                row["order_seed"],
                derived_seed(2026, "update-order", row["n"], row["workload"]),
            )
        before = (self.output / "trials.jsonl").read_bytes()
        self.build.reset_mock()
        with patch("balance_trees.benchmark_updates.execute_trial") as execute:
            resumed = run_updates(self.output, **self.options)
        execute.assert_not_called()
        self.build.assert_not_called()
        self.assertEqual(results, resumed)
        self.assertEqual(before, (self.output / "trials.jsonl").read_bytes())

    def test_resume_checks_settings_source_snapshot_and_checkpoint_seeds(self):
        self.run_complete()
        for changed in ({"seed": 123}, {"workers": 1}, {"sizes": [8, 32]}):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "identical settings"):
                    run_updates(self.output, **{**self.options, **changed})
        journal = self.output / "trials.jsonl"
        original = journal.read_text()
        rows = [json.loads(line) for line in original.splitlines()]
        rows[0]["seed"] += 1
        journal.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(ValueError, "requested seeds"):
            run_updates(self.output, **self.options)
        journal.write_text(original + original.splitlines()[0] + "\n")
        with self.assertRaisesRegex(ValueError, "Duplicate trial"):
            run_updates(self.output, **self.options)
        unrequested = json.loads(original.splitlines()[0])
        unrequested["trial"] = 99
        journal.write_text(original + json.dumps(unrequested) + "\n")
        with self.assertRaisesRegex(ValueError, "unrequested trial"):
            run_updates(self.output, **self.options)
        journal.write_text(original)
        archived_source = self.output / "source/src/native/tree.cpp"
        archived_source.write_text(
            archived_source.read_text() + "\n// changed snapshot\n"
        )
        with self.assertRaisesRegex(ValueError, "source snapshot changed"):
            run_updates(self.output, **self.options)

    def test_partial_resume_only_runs_missing_trial(self):
        results = self.run_complete()
        journal = self.output / "trials.jsonl"
        lines = journal.read_text().splitlines()
        missing = json.loads(lines.pop())
        journal.write_text("\n".join(lines) + "\n")
        with patch(
            "balance_trees.benchmark_updates.execute_trial", side_effect=self.complete
        ) as execute:
            resumed = run_updates(self.output, **self.options)
        execute.assert_called_once()
        request = execute.call_args.args[1]
        self.assertEqual(request, {key: missing[key] for key in request})
        self.assertEqual(results["trials"], resumed["trials"])
        self.assertEqual(len(resumed["metadata"]["sessions"]), 2)

    def test_failure_censors_only_its_workload_including_after_resume(self):
        def worker(executable, request, timeout):
            if request["workload"] == "random-churn":
                return {
                    **request,
                    "status": "timeout",
                    "metrics": {},
                    "detail": "test deadline",
                }
            return self.complete(executable, request, timeout)

        with patch(
            "balance_trees.benchmark_updates.execute_trial", side_effect=worker
        ) as execute:
            results = run_updates(self.output, **self.options)
        self.assertEqual(execute.call_count, 4)
        failed = [row for row in results["trials"] if row["workload"] == "random-churn"]
        healthy = [
            row for row in results["trials"] if row["workload"] == "ascending-churn"
        ]
        self.assertEqual(
            [row["status"] for row in failed], ["timeout", "not_run", "not_run"]
        )
        self.assertTrue(all(row["status"] == "complete" for row in healthy))
        with patch("balance_trees.benchmark_updates.execute_trial") as execute:
            resumed = run_updates(self.output, **self.options)
        execute.assert_not_called()
        self.assertEqual(results["trials"], resumed["trials"])


@unittest.skipUnless(
    shutil.which("c++") and shutil.which("cmake"), "C++20 and CMake required"
)
class UpdateBenchmarkIntegrationTests(unittest.TestCase):
    def test_all_workloads_validate_reproducible_inputs_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            options = dict(
                sizes=[4, 32],
                workers=2,
                memory_mib=256,
                timeout=30,
                small_trials=2,
                repeat_through=4,
                seed=2026,
            )
            results = run_updates(output, **options)
            self.assertEqual(len(results["trials"]), 3 * len(WORKLOADS))
            inputs = {}
            for row in results["trials"]:
                self.assertEqual(row["status"], "complete", row.get("detail"))
                metrics = row["metrics"]
                n = row["n"]
                self.assertEqual(metrics["final_nodes"], n)
                self.assertEqual(metrics["node_storage_bytes"], 20 * n)
                self.assertEqual(metrics["inserted"], n)
                self.assertEqual(metrics["erased"], n)
                self.assertLessEqual(metrics["max_insert_rotations"], 2)
                self.assertLessEqual(metrics["max_delete_rotations"], 4)
                self.assertGreater(metrics["elapsed_seconds"], 0)
                self.assertGreaterEqual(metrics["cpu_seconds"], 0)
                self.assertEqual(metrics["checkpoints"][0]["completed_ops"], 0)
                self.assertEqual(
                    metrics["checkpoints"][-1]["completed_ops"], metrics["operations"]
                )
                if row["workload"] == "grow-shrink":
                    self.assertEqual(metrics["refreshes"], 2 * (n - 1))
                    empty = [
                        point for point in metrics["checkpoints"] if point["n"] == 0
                    ]
                    self.assertEqual(len(empty), 1)
                    self.assertEqual(empty[0]["height"], -1)
                else:
                    self.assertEqual(metrics["refreshes"], 2 * n)
                if row["workload"] == "read-heavy":
                    self.assertEqual(metrics["operations"], 10 * n)
                    self.assertEqual(metrics["search_attempts"], 8 * n)
                    self.assertEqual(metrics["found"], 4 * n)
                else:
                    self.assertEqual(metrics["operations"], 2 * n)
                    self.assertEqual(metrics["search_attempts"], 0)
                identity = row["workload"], n
                fingerprint = row["order_seed"], metrics["operation_fingerprint"]
                if identity in inputs:
                    self.assertEqual(inputs[identity], fingerprint)
                inputs[identity] = fingerprint
            self.assertIn(
                "src/native/benchmark_updates.cpp", results["metadata"]["source_sha256"]
            )
            self.assertFalse(
                (output / "source/src/balance_trees/showcase/site").exists()
            )
            before = (output / "trials.jsonl").read_bytes()
            with patch("balance_trees.benchmark_updates.execute_trial") as execute:
                resumed = run_updates(output, **options)
            execute.assert_not_called()
            self.assertEqual(results, resumed)
            self.assertEqual(before, (output / "trials.jsonl").read_bytes())
