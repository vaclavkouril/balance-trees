"""Bounded exact checks of the biased paper's lemmas, not substitutes for proof."""

import unittest
from collections import defaultdict
from fractions import Fraction
from itertools import permutations

from test_geometric_proof_conformance import ordered_trees, reference_transition

from balance_trees.strategies.geometric_three_quarters import maximum_target_depth

SUCCESS_PROBABILITY = Fraction(3, 4)


def external_search_path(tree, query):
    path = []
    while tree is not None:
        left, key, right = tree
        if query == key:
            raise ValueError("The query must belong to an external gap")
        goes_right = query > key
        path.append(int(goes_right))
        tree = right if goes_right else left
    return tuple(path)


def small_insertion_cases():
    for previous_count in range(7):
        keys = tuple(4 * index for index in range(previous_count))
        for original in ordered_trees(keys):
            for gap in range(previous_count + 1):
                key = 4 * gap - 2
                for target in range(maximum_target_depth(previous_count + 1) + 1):
                    repaired, depth, _, _ = reference_transition(original, key, target)
                    yield original, repaired, gap, target, depth, previous_count


def target_probabilities(node_count):
    level = maximum_target_depth(node_count)
    return {
        target: (
            SUCCESS_PROBABILITY**level
            if target == 0
            else (1 - SUCCESS_PROBABILITY) * SUCCESS_PROBABILITY ** (level - target)
        )
        for target in range(level + 1)
    }


def advance_tree_distribution(states, key, node_count):
    updated = defaultdict(Fraction)
    for original, mass in states.items():
        for target, probability in target_probabilities(node_count).items():
            repaired, _, _, _ = reference_transition(original, key, target)
            updated[repaired] += mass * probability
    return dict(updated)


def right_spine_length(tree):
    length = 0
    while tree is not None:
        length += 1
        tree = tree[2]
    return length


class BiasedProofConformanceTests(unittest.TestCase):
    def test_different_gap_external_depth_changes_for_all_small_shapes(self):
        observed_changes = set()
        for original, repaired, gap, target, _, count in small_insertion_cases():
            insertion_path = external_search_path(original, 4 * gap - 2)
            for query_gap in range(count + 1):
                if query_gap == gap:
                    continue
                query = 4 * query_gap - 1
                query_path = external_search_path(original, query)
                divergence = next(
                    index
                    for index, (insertion_side, query_side) in enumerate(
                        zip(insertion_path, query_path, strict=False)
                    )
                    if insertion_side != query_side
                )
                expected = (
                    1 if target == divergence else -1 if target <= divergence - 2 else 0
                )
                actual = len(external_search_path(repaired, query)) - len(query_path)
                self.assertEqual(actual, expected, (original, gap, query_gap, target))
                observed_changes.add(actual)
        self.assertEqual(observed_changes, {-1, 0, 1})

    def test_same_gap_external_depth_bounds_for_all_small_shapes(self):
        deep_cases = 0
        for original, repaired, gap, target, depth, _ in small_insertion_cases():
            # Both new gaps must obey the lemma, whichever contains the fixed query.
            for query in (4 * gap - 3, 4 * gap - 1):
                self.assertEqual(len(external_search_path(original, query)), depth)
                new_depth = len(external_search_path(repaired, query))
                self.assertLessEqual(new_depth, depth + 1)
                # This stronger local statement implies the paper's claim for
                # D >= ell_n + 2 simultaneously for every target <= ell_n.
                if depth >= target + 2:
                    self.assertEqual(new_depth, depth, (original, gap, query, target))
                    deep_cases += 1
        self.assertGreater(deep_cases, 0)

    def test_target_masses_and_cumulative_probabilities_are_exact(self):
        for node_count in range(1, 33):
            probabilities = target_probabilities(node_count)
            level = maximum_target_depth(node_count)
            self.assertEqual(sum(probabilities.values()), 1)
            self.assertLessEqual(probabilities[0], Fraction(1, node_count))
            for target in range(level + 1):
                self.assertEqual(
                    sum(probabilities[depth] for depth in range(target + 1)),
                    SUCCESS_PROBABILITY ** (level - target),
                )

    def test_three_key_random_permutation_balanced_probability(self):
        balanced_probability = Fraction()
        for sequence in permutations(range(3)):
            states = {None: Fraction(1)}
            for node_count, key in enumerate(sequence, 1):
                states = advance_tree_distribution(states, key, node_count)
            self.assertEqual(sum(states.values()), 1)
            balanced_probability += (
                sum(probability for tree, probability in states.items() if tree[1] == 1)
                / 6
            )
        self.assertEqual(balanced_probability, Fraction(337, 768))
        # An ordinary random BST/treap is balanced with probability 1/3.
        self.assertNotEqual(balanced_probability, Fraction(1, 3))

    def test_increasing_right_spine_distribution_matches_recurrence(self):
        states = {None: Fraction(1)}
        spine_probabilities = {0: Fraction(1)}
        for node_count in range(1, 8):
            states = advance_tree_distribution(states, node_count, node_count)
            level = maximum_target_depth(node_count)
            predicted = defaultdict(Fraction)
            for length, mass in spine_probabilities.items():
                # R_n = R_{n-1} + 1{T_n >= R_{n-1}}, with R counting nodes.
                growth_probability = (
                    Fraction(1)
                    if length == 0
                    else 1 - SUCCESS_PROBABILITY ** max(level - length + 1, 0)
                )
                predicted[length] += mass * (1 - growth_probability)
                predicted[length + 1] += mass * growth_probability
            observed = defaultdict(Fraction)
            for tree, mass in states.items():
                observed[right_spine_length(tree)] += mass
            spine_probabilities = {
                length: probability
                for length, probability in predicted.items()
                if probability
            }
            self.assertEqual(dict(observed), spine_probabilities)
            self.assertEqual(sum(observed.values()), 1)
            self.assertLessEqual(max(observed), level + 1)


if __name__ == "__main__":
    unittest.main()
