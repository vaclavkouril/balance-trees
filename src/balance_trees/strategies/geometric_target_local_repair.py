"""Geometric target sampling and local repair, following the supplied algorithm."""

from dataclasses import dataclass

from ..random_bits import RandomBits
from .base import RebalanceContext
from .target_repair import repair_at_target_depth


def sample_target_depth(node_count: int, bits: RandomBits) -> int:
    """Return max(0, L - move - 1), where L = ceil(log2(n)) + 1.

    Count leading ones until a zero or L bits have been drawn. Integer
    arithmetic handles n=1 and powers of two without logarithm rounding.
    The last two possible move counts both map to root depth zero.
    """
    if node_count < 1:
        raise ValueError("node_count must include at least the inserted node")
    level_count = (node_count - 1).bit_length() + 1
    move = 0
    while move < level_count:
        if bits.bit() == 0:
            break
        move += 1
    return max(0, level_count - move - 1)


@dataclass(slots=True)
class GeometricTargetLocalRepair:
    """Perform at most two rotations per successful insertion.

    Sample against a perfect-tree reference, using n including the new leaf.
    Leave a leaf at or above the target unchanged; otherwise repair the path
    at that depth. No priority rolls, extrema or record promotions are used.
    Ancestor traversal can take O(d); no logarithmic-height claim is made.
    """

    inserted_count: int = 0

    def rebalance(self, context: RebalanceContext) -> None:
        self.inserted_count += 1
        target_depth = sample_target_depth(self.inserted_count, context.bits)
        repair_at_target_depth(context, target_depth)
