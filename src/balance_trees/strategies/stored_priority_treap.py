"""Stored-priority treap reference with the visualizer's priority semantics."""

from random import Random


class StoredPriorityTreap:
    """The showcase Python treap policy without animation snapshots.

    Preserve its 32-bit priorities and key-based tie breaker exactly.
    """

    def __init__(self, seed):
        self.random = Random(seed)
        self.priorities = {}

    def rebalance(self, context):
        node = context.inserted
        priority = self.random.getrandbits(32)
        self.priorities[node.key] = priority
        context.bits.count += 32
        while node.parent is not None:
            if not context.compare_priority(
                node, priority, self.priorities[node.parent.key]
            ):
                break
            context.promote(node, 0)
