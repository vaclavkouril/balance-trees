import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = (
    "random-churn",
    "ascending-churn",
    "descending-churn",
    "grow-shrink",
    "read-heavy",
)
MASK = (1 << 64) - 1


class OrderRandom:
    def __init__(self, seed):
        self.state = seed

    def word(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK
        return value ^ (value >> 31)

    def bounded(self, bound):
        threshold = (1 << 64) % bound
        while True:
            value = self.word()
            if value >= threshold:
                return value % bound

    def shuffle(self, values):
        for count in range(len(values), 1, -1):
            index = self.bounded(count)
            values[count - 1], values[index] = values[index], values[count - 1]


def reference_workload(workload, size, order_seed):
    """Independently generate and check the exact fixed operation stream."""
    rng = OrderRandom(order_seed)
    permutation = list(range(size))
    random_order = workload not in ("ascending-churn", "descending-churn")
    if random_order:
        rng.shuffle(permutation)
    preload = (
        list(reversed(range(size)))
        if workload == "descending-churn"
        else permutation.copy()
    )
    if random_order:
        rng.shuffle(permutation)
    operations = []
    if workload == "grow-shrink":
        operations.extend((1, key) for key in permutation)
        operations.extend((0, size + key) for key in permutation)
    else:
        for index in range(size):
            if workload == "read-heavy":
                for query in range(8):
                    rank = rng.bounded(size)
                    if query % 2:
                        operations.append((3, 2 * size + rank))
                    else:
                        key = size + rank if rank < index else permutation[rank]
                        operations.append((2, key))
            if workload == "descending-churn":
                old_key, new_key = size - 1 - index, -1 - index
            else:
                old_key, new_key = permutation[index], size + index
            operations.extend(((1, old_key), (0, new_key)))
    expected = set(preload)
    for kind, key in operations:
        if kind == 0:
            assert key not in expected
            expected.add(key)
        elif kind == 1:
            expected.remove(key)
        else:
            assert (key in expected) == (kind == 2)
    assert expected == (
        set(range(-size, 0))
        if workload == "descending-churn"
        else set(range(size, 2 * size))
    )
    fingerprint = 14695981039346656037
    for kind, key in [(0, key) for key in preload] + operations:
        for byte in bytes([kind]) + (key & MASK).to_bytes(8, "little"):
            fingerprint = ((fingerprint ^ byte) * 1099511628211) & MASK
    return f"{fingerprint:016x}"


@unittest.skipUnless(shutil.which("c++"), "C++20 compiler required")
class NativeUpdateBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.executable = Path(cls.directory.name) / "native-update-benchmark"
        subprocess.run(
            [
                "c++",
                "-std=c++20",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-I",
                str(ROOT / "src/native/include"),
                str(ROOT / "src/native/tree.cpp"),
                str(ROOT / "src/native/benchmark_updates.cpp"),
                "-o",
                str(cls.executable),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_worker(self, workload, size=17, seed=2026, order_seed=7331):
        result = subprocess.run(
            [
                str(self.executable),
                str(seed),
                str(size),
                "256",
                workload,
                str(order_seed),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.loads(result.stdout)

    def test_all_workloads_have_exact_inputs_and_operation_counts(self):
        for workload in WORKLOADS:
            for size in (1, 2, 17):
                with self.subTest(workload=workload, size=size):
                    result = self.run_worker(workload, size)
                    self.assertEqual(
                        result["operation_fingerprint"],
                        reference_workload(workload, size, 7331),
                    )
                    operations = size * (10 if workload == "read-heavy" else 2)
                    self.assertEqual(result["operations"], operations)
                    self.assertEqual(result["insert_attempts"], size)
                    self.assertEqual(result["inserted"], size)
                    self.assertEqual(result["delete_attempts"], size)
                    self.assertEqual(result["erased"], size)
                    self.assertEqual(result["final_nodes"], size)
                    self.assertEqual(result["node_storage_bytes"], 20 * size)
                    self.assertEqual(
                        result["search_attempts"],
                        size * 8 if workload == "read-heavy" else 0,
                    )
                    self.assertEqual(
                        result["found"], size * 4 if workload == "read-heavy" else 0
                    )
                    expected_refreshes = (
                        2 * (size - 1)
                        if workload == "grow-shrink" or size == 1
                        else 2 * size
                    )
                    self.assertEqual(result["refreshes"], expected_refreshes)
                    self.assertLessEqual(result["max_insert_rotations"], 2)
                    self.assertLessEqual(result["max_delete_rotations"], 4)
                    self.assertEqual(
                        result["rotations"],
                        result["insert_rotations"] + result["delete_rotations"],
                    )
                    self.assertAlmostEqual(
                        result["mean_rotations"], result["rotations"] / operations
                    )
                    self.assertAlmostEqual(
                        result["mean_insert_rotations"],
                        result["insert_rotations"] / size,
                    )
                    self.assertAlmostEqual(
                        result["mean_delete_rotations"],
                        result["delete_rotations"] / size,
                    )
                    self.assertGreater(result["elapsed_seconds"], 0)
                    self.assertGreaterEqual(result["cpu_seconds"], 0)
                    self.assertGreater(result["preload_seconds"], 0)
                    self.assertGreaterEqual(
                        result["worker_seconds"],
                        result["preload_seconds"] + result["elapsed_seconds"],
                    )
                    self.assertGreater(result["peak_rss_mib"], 0)
                    points = result["checkpoints"]
                    self.assertEqual(points[0]["completed_ops"], 0)
                    self.assertEqual(points[-1]["completed_ops"], operations)
                    self.assertEqual(points[-1]["height"], result["height"])
                    self.assertEqual(points[-1]["mean_depth"], result["mean_depth"])
                    self.assertEqual(
                        result["sampled_max_height"], max(p["height"] for p in points)
                    )

    def test_shrink_checkpoints_cover_empty_singleton_and_power_of_two_sizes(self):
        result = self.run_worker("grow-shrink", 17)
        points = result["checkpoints"]
        self.assertEqual(
            [(point["completed_ops"], point["n"]) for point in points],
            [
                (0, 17),
                (1, 16),
                (9, 8),
                (13, 4),
                (15, 2),
                (16, 1),
                (17, 0),
                (18, 1),
                (19, 2),
                (21, 4),
                (25, 8),
                (33, 16),
                (34, 17),
            ],
        )
        empty = next(point for point in points if not point["n"])
        self.assertEqual(empty["height"], -1)
        self.assertEqual(empty["mean_depth"], 0)
        self.assertTrue(
            all(point["height"] == 0 for point in points if point["n"] == 1)
        )

    def test_seed_controls_shape_without_changing_the_fixed_workload(self):
        timing = {
            "elapsed_seconds",
            "cpu_seconds",
            "preload_seconds",
            "worker_seconds",
            "peak_rss_mib",
        }
        first = self.run_worker("random-churn", 128, seed=1)
        again = self.run_worker("random-churn", 128, seed=1)
        second = self.run_worker("random-churn", 128, seed=2)
        other_order = self.run_worker("random-churn", 128, seed=1, order_seed=8)
        self.assertEqual(
            {key: value for key, value in first.items() if key not in timing},
            {key: value for key, value in again.items() if key not in timing},
        )
        self.assertEqual(
            first["operation_fingerprint"], second["operation_fingerprint"]
        )
        self.assertNotEqual(first["random_bits"], second["random_bits"])
        self.assertNotEqual(
            first["operation_fingerprint"], other_order["operation_fingerprint"]
        )

    def test_chunk_boundaries_preserve_lookup_expectations(self):
        # Each quarter exceeds the 65,536-operation preparation buffer.
        result = self.run_worker("read-heavy", 30001)
        self.assertEqual(result["operations"], 300010)
        self.assertEqual(result["found"], 120004)
        self.assertEqual(
            result["operation_fingerprint"],
            reference_workload("read-heavy", 30001, 7331),
        )

    def test_invalid_arguments_and_memory_exhaustion_are_explicit(self):
        for arguments in (
            [],
            ["1", "0", "64", "random-churn", "2"],
            ["-1", "2", "64", "random-churn", "2"],
            ["1", "2garbage", "64", "random-churn", "2"],
            ["1", "2", "0", "random-churn", "2"],
            ["1", "2", "64", "unknown", "2"],
            ["1", "2", "64", "random-churn", str(1 << 64)],
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [str(self.executable), *arguments],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)
        result = subprocess.run(
            [str(self.executable), "1", str(1 << 24), "32", "random-churn", "2"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("memory_limit", result.stderr)


if __name__ == "__main__":
    unittest.main()
