"""Geometric targets with exact Bernoulli(3/4) trials."""

from dataclasses import dataclass

from ..random_bits import RandomBits
from .base import RebalanceContext
from .target_repair import repair_at_target_depth


def maximum_target_depth(node_count: int) -> int:
    """Return ceil(log base 4/3 of node_count) using exact integers."""
    if node_count < 1:
        raise ValueError("node_count must include at least the inserted node")
    numerator = denominator = 1
    depth = 0
    while numerator < node_count * denominator:
        numerator *= 4
        denominator *= 3
        depth += 1
    return depth


def sample_target_depth(node_count: int, bits: RandomBits) -> int:
    target = maximum_target_depth(node_count)
    while target > 0:
        # Read both bits even when the first is one: each trial costs two bits.
        first, second = bits.bit(), bits.bit()
        if first == 0 and second == 0:
            break
        target -= 1
    return target


@dataclass(slots=True)
class GeometricThreeQuarters:
    """Local repair using p=3/4; at most two rotations per insertion."""

    inserted_count: int = 0

    def rebalance(self, context: RebalanceContext) -> None:
        self.inserted_count += 1
        target = sample_target_depth(self.inserted_count, context.bits)
        repair_at_target_depth(context, target)
