import importlib.util
import unittest
from fractions import Fraction
from pathlib import Path

from balance_trees.flavors import TreeFlavor
from balance_trees.strategies.geometric_target_local_repair import (
    GeometricTargetLocalRepair,
    sample_target_depth,
)
from balance_trees.tree import BST

SPEC = importlib.util.spec_from_file_location(
    "proof_triage", Path(__file__).resolve().parents[1] / "benchmarks/proof_triage.py"
)
proof_triage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof_triage)


class ProofTriageTests(unittest.TestCase):
    @staticmethod
    def depth_and_branch_depth(shape, key):
        node = shape
        depth = 0
        while node[0] != key:
            node = node[1] if key < node[0] else node[2]
            depth += 1
        node = shape
        branch_depth = 0
        while node[0] < key:
            node = node[2]
            branch_depth += 1
        return depth, branch_depth

    def test_target_prefixes_have_exact_total_probability(self):
        for count in range(1, 20):
            prefixes = list(proof_triage.target_prefixes(count))
            self.assertEqual(sum(probability for _, probability in prefixes), 1)
            self.assertTrue(all(probability > 0 for _, probability in prefixes))

    def test_increasing_depth_and_visit_bound_in_all_reachable_small_states(self):
        states = {None}
        for count in range(1, 8):
            k = (count - 1).bit_length()
            next_states = set()
            for shape in states:
                outcomes = proof_triage.transitions(shape, count - 1, count)
                expected_visits = sum(
                    probability * visits for (_, _, visits), probability in outcomes
                )
                self.assertLessEqual(expected_visits, 1 - Fraction(1, 2**k))
                for (new_shape, depth, _), _ in outcomes:
                    self.assertLessEqual(depth, k + 1)
                    cursor = new_shape
                    spine_depth = -1
                    while cursor is not None:
                        spine_depth += 1
                        cursor = cursor[2]
                    self.assertLessEqual(spine_depth, k)
                    next_states.add(new_shape)
            states = next_states

    def test_adaptive_search_at_seven_nodes_is_exact(self):
        self.assertEqual(
            proof_triage.optimal_expected_height(None, 0, 7), Fraction(32933, 8192)
        )
        increasing = Fraction(proof_triage.increasing_statistics(7)["expected_height"])
        self.assertLess(increasing, Fraction(32933, 8192))

    def test_monotone_node_potential_has_claimed_conditional_drift(self):
        states = {None}
        for count in range(1, 8):
            next_states = set()
            for shape in states:
                outcomes = proof_triage.transitions(shape, count - 1, count)
                for key in range(count - 1):
                    depth, branch_depth = self.depth_and_branch_depth(shape, key)
                    expected_change = sum(
                        probability
                        * (
                            sum(self.depth_and_branch_depth(new_shape, key))
                            - depth
                            - branch_depth
                        )
                        for (new_shape, _, _), probability in outcomes
                    )
                    upper_bound = Fraction(1, count) if branch_depth == 0 else 0
                    self.assertLessEqual(expected_change, upper_bound)
                next_states.update(new_shape for (new_shape, _, _), _ in outcomes)
            states = next_states

    def test_adaptive_attack_and_probe_transitions_for_every_target(self):
        for has_left_subtree in (False, True):
            tree = BST()
            for key in range(1, 17):
                tree.insert(key)
            if has_left_subtree:
                tree.insert(Fraction(11, 2))
            shape = proof_triage.pack_tree(tree.root)
            count = 17 + has_left_subtree
            k = (count - 1).bit_length()
            previous_depth = tree.depths()[16]
            for prefix, _ in proof_triage.target_prefixes(count):
                target = sample_target_depth(count, proof_triage.FixedBits(prefix))
                for is_probe in (False, True):
                    copy = BST()
                    copy.root = proof_triage.unpack_tree(shape)
                    key = (
                        proof_triage.adaptive_probe_key(copy)
                        if is_probe
                        else proof_triage.adaptive_attack_key(copy, k)
                    )
                    stats = TreeFlavor(
                        GeometricTargetLocalRepair(inserted_count=count - 1),
                        tree=copy,
                        bits=proof_triage.FixedBits(prefix),
                    ).insert(key)
                    change = copy.depths()[16] - previous_depth
                    expected = (
                        -1
                        if is_probe
                        else (1 if target == k else 0 if target == k - 1 else -1)
                    )
                    self.assertEqual(change, expected)
                    if is_probe:
                        self.assertGreaterEqual(stats.visits, previous_depth - k)


if __name__ == "__main__":
    unittest.main()
