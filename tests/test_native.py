"""Compare native geometric repair with Python using identical logical bits."""

import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import FixedBits

from balance_trees import TreeFlavor
from balance_trees.strategies.geometric_target_local_repair import (
    GeometricTargetLocalRepair,
)

ROOT = Path(__file__).resolve().parents[1]
NULL = 2**32 - 1


class NativeConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which(os.environ.get("CXX", "c++"))
        if compiler is None:
            raise unittest.SkipTest("C++20 compiler required for native conformance")
        cls.directory = tempfile.TemporaryDirectory(prefix="balance-trees-native-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.executable = Path(cls.directory.name) / "balance-tree"
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-I",
                str(ROOT / "src/native/include"),
                str(ROOT / "src/native/tree.cpp"),
                str(ROOT / "src/native/main.cpp"),
                "-o",
                str(cls.executable),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def compare(self, keys, tape, strategy="geometric-target-local-repair"):
        result = subprocess.run(
            [str(self.executable), "--strategy", strategy, "--bits", tape, "--trace"],
            input=" ".join(map(str, keys)),
            capture_output=True,
            text=True,
            check=True,
        )
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(rows), len(keys))
        flavor = TreeFlavor(
            GeometricTargetLocalRepair() if strategy != "none" else None,
            bits=FixedBits(list(map(int, tape))),
        )
        nodes = []
        indices = {None: NULL}
        for key, actual in zip(keys, rows, strict=True):
            stats = flavor.insert(key)
            if stats.inserted:
                node = flavor.tree.root
                while node.key != key:
                    node = node.left if key < node.key else node.right
                indices[node] = len(nodes)
                nodes.append(node)
            expected = {
                "inserted": stats.inserted,
                "insertion_depth": stats.insertion_depth,
                "visits": stats.visits,
                "random_bits": stats.random_bits,
                "rotation_distances": stats.rotation_distances,
                "root": indices[flavor.tree.root],
                "nodes": [
                    [
                        node.key,
                        indices[node.left],
                        indices[node.right],
                        indices[node.parent],
                    ]
                    for node in nodes
                ],
            }
            self.assertEqual(actual, expected)
            flavor.tree.depths()

    def test_shapes_statistics_and_duplicates_match_python(self):
        generator = random.Random(2026)
        sequences = [
            [],
            [0, 0, -(2**63), 2**63 - 1, 0],
            list(range(128)),
            list(range(128, -1, -1)),
            [value for pair in zip(range(64), range(128, 64, -1)) for value in pair],
            [generator.randrange(-100, 100) for _ in range(250)],
        ]
        for keys in sequences:
            for tape in (
                "0" * 4096,
                "1" * 4096,
                "10" * 2048,
                "".join(str(generator.randrange(2)) for _ in range(4096)),
            ):
                with self.subTest(keys=keys[:5], tape=tape[:12]):
                    self.compare(keys, tape)
            self.compare(keys, "", strategy="none")

    def test_invalid_inputs_fail_explicitly(self):
        for arguments, data in (
            (["--strategy", "unknown"], ""),
            (["--bits", "2"], ""),
            (["--bits", ""], "1"),
            (["--seed", "-1"], ""),
            ([], str(2**63)),
            ([], "1 invalid"),
        ):
            result = subprocess.run(
                [str(self.executable), *arguments],
                input=data,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("balance-tree:", result.stderr)


if __name__ == "__main__":
    unittest.main()
