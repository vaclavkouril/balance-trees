import json
import tempfile
import unittest
from pathlib import Path

from balance_trees.benchmark_support import write_json


class BenchmarkCheckpointTests(unittest.TestCase):
    def test_invalid_checkpoint_preserves_the_previous_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            original = {"trials": [{"status": "complete"}]}
            write_json(path, original)
            for invalid in (float("nan"), float("inf"), object()):
                with self.subTest(value=invalid):
                    with self.assertRaises((TypeError, ValueError)):
                        write_json(path, {"measurement": invalid})
                    self.assertEqual(json.loads(path.read_text()), original)
                    self.assertEqual(list(path.parent.iterdir()), [path])
            replacement = {"trials": []}
            write_json(path, replacement)
            self.assertEqual(json.loads(path.read_text()), replacement)
