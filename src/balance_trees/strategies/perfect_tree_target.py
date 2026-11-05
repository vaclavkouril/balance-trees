"""Sample the depth of a uniformly chosen vertex in a perfect reference tree."""

from ..random_bits import RandomBits


def sample_perfect_tree_depth(node_count: int, bits: RandomBits) -> int:
    """Use the smallest perfect tree that can contain node_count vertices.

    With L levels there are 2**L - 1 vertices. A uniform label from 1 through
    that count lies at depth label.bit_length() - 1 in breadth-first order.
    Reject zero so depth probabilities are exactly 1:2:4:... rather than a
    truncated geometric approximation. The single-node tree needs no bits.
    """
    if node_count < 1:
        raise ValueError("node_count must include at least the inserted node")
    if node_count == 1:
        return 0
    level_count = node_count.bit_length()
    while True:
        label = 0
        for _ in range(level_count):
            label = (label << 1) | bits.bit()
        if label:
            return label.bit_length() - 1
