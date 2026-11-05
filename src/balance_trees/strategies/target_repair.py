"""Repair a two-edge path at a selected depth without promoting every leaf."""

from .base import RebalanceContext
from .paper import ZigZag

_LOCAL_REPAIR = ZigZag()


def repair_at_target_depth(context: RebalanceContext, target_depth: int) -> None:
    insertion_depth = context.stats.insertion_depth
    if insertion_depth <= target_depth:
        return
    if insertion_depth == target_depth + 1:
        context.promote(context.inserted, distance=0)
        return

    ancestor = context.inserted
    distance = insertion_depth - target_depth - 2
    for _ in range(distance):
        context.visit(ancestor)
        ancestor = ancestor.parent
    context.visit(ancestor)
    # Straight paths promote the parent once; bends promote the cursor twice.
    _LOCAL_REPAIR.apply(context, ancestor, distance)
