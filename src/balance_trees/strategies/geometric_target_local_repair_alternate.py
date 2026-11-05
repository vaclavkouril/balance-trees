"""Random-level v2.1.3: geometric target levels with local repair."""

from dataclasses import dataclass

from .base import RebalanceContext
from .paper import ZigZag

LOCALREPAIR = ZigZag()


@dataclass(slots=True)
class RandomLevelV213:
    """Sample a geometric target depth and perform at most two rotations."""

    inserted_count: int = 0

    def rebalance(self, context: RebalanceContext) -> None:
        # Vertex count including the newly inserted vertex.
        n = self.inserted_count + 1
        self.inserted_count = n

        # Your modified geometric target sampling.
        maximum = (n - 1).bit_length() + 1
        move = 0

        while move < maximum and context.bits.bit():
            move += 1

        target = max(0, maximum - move - 1)
        depth = context.stats.insertion_depth
        context.stats.priority = move

        # The vertex is already at or above the target.
        if depth <= target:
            return

        node = context.inserted

        # Only one level below the target: one rotation suffices.
        if depth == target + 1:
            context.promote(node, distance=0)
            return

        # Select a vertex two levels below the target.
        distance = depth - target - 2
        for _ in range(distance):
            context.visit(node)
            node = node.parent

        context.visit(node)

        # Straight path: promote the parent once.
        # Bent path: promote the selected vertex twice.
        LOCALREPAIR.apply(context, node, distance)
