"""Random-level v2.1: local repairs with logarithmically wide priorities."""

from dataclasses import dataclass

from .base import RebalanceContext
from .random_level_v2 import RandomLevelV2


@dataclass(slots=True)
class RandomLevelV21(RandomLevelV2):
    """For insertion ordinal j (starting at 1), use j.bit_length() fresh bits.

    When the width grows from b to b + 1 bits, the stored extrema are remapped
    to preserve a gap around the previously observed interval:

    - lowest_priority becomes 2 * lowest_priority + 1
    - highest_priority becomes 2 * highest_priority

    For example, a 4-bit interval [0000, 1111] becomes the 5-bit interval
    [00001, 11110]. Values below the remapped minimum are strict new minima,
    values above the remapped maximum are strict new maxima, and the old
    interval occupies the middle of the new range. The v2 target selection and
    local-repair mechanics are unchanged. When previous extrema coincide,
    the remapped lower endpoint exceeds the upper by one: the old interior
    is empty, and each integer roll is classified as a new minimum or maximum.
    This growing-domain process is not iid; v2's expected-rotation proof does
    not transfer to v2.1.
    """

    priority_bits: int = 0

    def roll_priority(self, context: RebalanceContext) -> int:
        """Sample one priority using a growing logarithmic bit width."""
        bits = max(1, (self.inserted_count + 1).bit_length())
        if bits > self.priority_bits:
            if self.lowest_priority is not None:
                self.lowest_priority = 2 * self.lowest_priority + 1
            if self.highest_priority is not None:
                self.highest_priority = 2 * self.highest_priority
            self.priority_bits = bits
        value = 0
        for _ in range(bits):
            value = (value << 1) | context.bits.bit()
        return value
