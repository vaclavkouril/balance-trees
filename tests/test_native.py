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
from test_geometric_proof_conformance import reference_transition

from balance_trees import TreeFlavor
from balance_trees.strategies import GeometricThreeQuarters
from balance_trees.strategies.geometric_target_local_repair import (
    GeometricTargetLocalRepair,
)

ROOT = Path(__file__).resolve().parents[1]
NULL = 2**32 - 1


def remove_minimum(tree):
    left, key, right = tree
    if left is None:
        return right, key
    remaining, minimum = remove_minimum(left)
    return (remaining, key, right), minimum


def remove_key(tree, key):
    left, stored, right = tree
    if key < stored:
        return remove_key(left, key), stored, right
    if key > stored:
        return left, stored, remove_key(right, key)
    if right is None:
        return left
    remaining, successor = remove_minimum(right)
    return left, successor, remaining


class FullBSTReference:
    """Chapter 6 on immutable tuples, independent of native node indices."""

    def __init__(self, tape):
        self.tree = None
        self.keys = set()
        self.cursor = None
        self.bits = iter(map(int, tape))
        self.bit_count = 0

    def raw_insert(self, key):
        self.keys.add(key)
        # Exact arithmetic, independent of the native threshold table.
        target, left, right = 0, len(self.keys), 1
        while left > right:
            target += 1
            left *= 3
            right *= 4
        while target > 0:
            first, second = next(self.bits), next(self.bits)
            self.bit_count += 2
            if first == second == 0:
                break
            target -= 1
        self.tree, depth, rotations, visits = reference_transition(
            self.tree, key, target
        )
        return depth, rotations, visits

    def step(self, operation, key):
        before = self.bit_count
        if operation == "contains":
            return {"found": key in self.keys}
        if operation == "insert":
            inserted = key not in self.keys
            stats = {"inserted": inserted}
            if inserted:
                depth, rotations, visits = self.raw_insert(key)
                stats.update(insertion_depth=depth, visits=visits)
        else:
            erased = key in self.keys
            rotations = visits = minimum_moves = 0
            refreshed = []
            if erased:
                self.tree = remove_key(self.tree, key)
                self.keys.remove(key)
                if not self.keys:
                    self.cursor = None
                else:
                    for _ in range(2):
                        larger = [
                            value
                            for value in self.keys
                            if self.cursor is None or value > self.cursor
                        ]
                        chosen = min(larger) if larger else min(self.keys)
                        if not larger:
                            minimum_moves += self.tree[1] != chosen
                            remaining, minimum = remove_minimum(self.tree)
                            self.tree = (None, minimum, remaining)
                        self.tree = remove_key(self.tree, chosen)
                        self.keys.remove(chosen)
                        _, added_rotations, added_visits = self.raw_insert(chosen)
                        rotations += added_rotations
                        visits += added_visits
                        refreshed.append(chosen)
                        self.cursor = chosen
            stats = dict(
                erased=erased,
                rotations=rotations,
                visits=visits,
                minimum_moves=minimum_moves,
                refreshes=len(refreshed),
                refreshed_keys=refreshed,
            )
        stats["random_bits"] = self.bit_count - before
        return stats


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
            {
                "geometric-target-local-repair": GeometricTargetLocalRepair,
                "geometric-three-quarters": GeometricThreeQuarters,
                "geometric-full-bst": GeometricThreeQuarters,
                "none": lambda: None,
            }[strategy](),
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
                    self.compare(keys, tape * 4, strategy="geometric-three-quarters")
                    self.compare(keys, tape * 4, strategy="geometric-full-bst")
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

    def test_full_bst_matches_immutable_chapter_six_reference(self):
        generator = random.Random(20261124)
        examples = [
            ("insert", 20),
            ("insert", 10),
            ("insert", 30),
            ("delete", 20),
            ("insert", 5),
            ("insert", 25),
            ("delete", 30),
            ("delete", 10),
            ("contains", 25),
            ("delete", 5),
            ("delete", 25),
            ("delete", 25),
            ("insert", -(2**63)),
            ("insert", 2**63 - 1),
            ("delete", 2**63 - 1),
            ("insert", -(2**63)),
            ("delete", -(2**63)),
        ]
        sequences = [examples]
        sequences.append(
            [("insert", key) for key in range(100)]
            + [("delete", key) for key in range(100)]
            + [("insert", key) for key in range(10)]
        )
        for _ in range(4):
            sequences.append(
                [
                    (
                        generator.choice(("insert", "delete", "contains")),
                        generator.randrange(-30, 31),
                    )
                    for _ in range(500)
                ]
            )
        tapes = [
            "0" * 60000,
            "1" * 60000,
            "".join(str(generator.randrange(2)) for _ in range(60000)),
        ]
        for sequence in sequences:
            for tape in tapes:
                with self.subTest(operations=len(sequence), bits=tape[:12]):
                    result = subprocess.run(
                        [
                            str(self.executable),
                            "--strategy",
                            "geometric-full-bst",
                            "--updates",
                            "--trace",
                            "--bits",
                            tape,
                        ],
                        input="\n".join(
                            f"{operation} {key}" for operation, key in sequence
                        ),
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    rows = [json.loads(line) for line in result.stdout.splitlines()]
                    self.assertEqual(len(rows), len(sequence))
                    reference = FullBSTReference(tape)
                    for (operation, key), row in zip(sequence, rows, strict=True):
                        expected = reference.step(operation, key)
                        for name, value in expected.items():
                            self.assertEqual(row[name], value, (operation, key, name))
                        self.assertEqual(row["cursor"], reference.cursor)

                        def shape(index):
                            if index == NULL:
                                return None
                            value, left, right, _ = row["nodes"][index]
                            return shape(left), value, shape(right)

                        self.assertEqual(shape(row["root"]), reference.tree)
                        self.assertEqual(len(row["nodes"]), len(reference.keys))

    def test_full_bst_update_summary_and_errors(self):
        command = [
            str(self.executable),
            "--strategy",
            "geometric-full-bst",
            "--updates",
        ]
        result = subprocess.run(
            command,
            input="insert 1 insert 2 insert 2 contains 2 delete 1 delete 3 contains 1 delete 2",
            capture_output=True,
            text=True,
            check=True,
        )
        summary = json.loads(result.stdout)
        for name, expected in dict(
            operations=8,
            insert_attempts=3,
            inserted=2,
            delete_attempts=3,
            erased=2,
            search_attempts=2,
            found=1,
            nodes=0,
            height=0,
            refreshes=2,
        ).items():
            self.assertEqual(summary[name], expected)
        for arguments, data in (
            (command, "insert"),
            (command, "remove 2"),
            (command, "delete invalid"),
            (command, f"insert {2**63}"),
            ([*command, "--bits", "0000"], "insert 1 insert 2 insert 3 delete 1"),
            ([str(self.executable), "--updates"], "insert 1 delete 1"),
        ):
            failed = subprocess.run(
                arguments, input=data, capture_output=True, text=True
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("balance-tree:", failed.stderr)


if __name__ == "__main__":
    unittest.main()
