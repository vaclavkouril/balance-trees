"""Strategy factories: add a name here to include a flavor in the CLI."""

from fractions import Fraction

from .base import NoRebalance, RebalanceContext, Strategy
from .fixed import ConstantWalk, InverseDepthWalk
from .geometric_target_local_repair import GeometricTargetLocalRepair
from .geometric_three_quarters import GeometricThreeQuarters
from .halving import HalvingWalk
from .hashed import HashPriority
from .interval_target_local_repair import IntervalTargetLocalRepair
from .lottery import RecountRoot, WindowRoot
from .paper import GeometricStop, Zig, ZigZag
from .random_level import RandomLevel, TreapPriority
from .random_level_v2 import RandomLevelV2
from .random_level_v2_1 import RandomLevelV21
from .random_level_v3 import RandomLevelV3
from .random_level_v4 import RandomLevelV4
from .registry import StrategyFactory, StrategySpec

strategy_factory = StrategyFactory()
for identifier, spec in {
    "halving": StrategySpec(
        HalvingWalk,
        "Halving walk",
        "Full upward walk",
        "Try 1/2, 1/4, 1/8… and continue to the root after either outcome. Expected fewer than one rotation per insertion; ancestor work can be linear.",
    ),
    "constant-half": StrategySpec(
        ConstantWalk,
        "Constant ½",
        "Full upward walk",
        "Rotate with probability 1/2 at every visited ancestor, continuing to the root. Both visits and rotations can grow with depth.",
    ),
    "inverse-depth": StrategySpec(
        InverseDepthWalk,
        "Inverse depth",
        "Depth-informed rule",
        "Freeze initial insertion depth h and use 1/h at every decision. Sorted inputs produce a chain despite at most one expected rotation.",
    ),
    "none": StrategySpec(
        NoRebalance,
        "Plain BST",
        "No rebalancing",
        "Ordinary leaf insertion. Ordered inputs can produce linear height and quadratic insertion work.",
    ),
    "paper-zig": StrategySpec(
        GeometricStop,
        "Paper · Zig",
        "Geometric stop",
        "Continue upward with probability 1/2; otherwise promote the cursor once and stop.",
    ),
    "paper-zigzag": StrategySpec(
        lambda: GeometricStop(Fraction(3, 4), ZigZag()),
        "Paper · ZigZag",
        "Geometric stop",
        "Continue with probability 3/4. On stopping, a straight path promotes the parent once, a bent path promotes the cursor twice.",
    ),
    "recount-root": StrategySpec(
        RecountRoot,
        "Recount root lottery",
        "Exact distribution",
        "Exact random-BST shape distribution from empty, using transient full-tree counting. Linear scan work per insertion; quadratic total scans.",
    ),
    "window-root": StrategySpec(
        WindowRoot,
        "Window root lottery",
        "Bounded local heuristic",
        "Root lotteries within 64 actual node inspections by default. Never uses an incomplete count; no general logarithmic-depth guarantee.",
    ),
    "hash-priority": StrategySpec(
        HashPriority,
        "Recomputed priority",
        "Keyed hash heuristic",
        "Recompute SplitMix64 key/seed priorities for treap-style comparisons. No priority table or fresh insertion bits; finite hashes are not independent priorities.",
    ),
    "random-level": StrategySpec(
        RandomLevel,
        "Random level · perfect-tree target",
        "Sampled leaf destination",
        "Sample a vertex uniformly from the smallest perfect tree containing n nodes, including the new leaf. Promote the inserted leaf to that depth if deeper; otherwise leave it unchanged. No priority extrema or height guarantee.",
    ),
    "interval-target-promotion": StrategySpec(
        TreapPriority,
        "Interval-target leaf promotion (original random level)",
        "Priority-free depth heuristic",
        "Roll 64 fair bits and choose a depth from the previous observed priority interval. New minima reach the root; new maxima stay leaves. Stores only a count and two extrema; no balance guarantee.",
    ),
    "interval-target-local-repair": StrategySpec(
        IntervalTargetLocalRepair,
        "Interval-target local repair",
        "Local repair at sampled level",
        "Choose a repair level using the original 64-bit interval bands. Ordinary insertions perform at most two local rotations; strict new minima promote the leaf to the root. Expected fewer than three rotations per insertion from empty under iid uniform rolls. Ancestor walks can be long; no logarithmic-depth guarantee.",
    ),
    "geometric-target-local-repair": StrategySpec(
        GeometricTargetLocalRepair,
        "Geometric target local repair",
        "Perfect-tree reference, at most two rotations",
        "Sample target depth with capped leading fair bits and L=ceil(log2(n))+1, including the new leaf. Stay at or above the target; otherwise repair a straight or bent ancestor path with at most two rotations. No record exceptions or height guarantee.",
    ),
    "geometric-three-quarters": StrategySpec(
        GeometricThreeQuarters,
        "Geometric target · 3/4",
        "Logarithmic height for fixed insertion sequences",
        "Sample a target from ceil(log base 4/3 of n) using independent Bernoulli(3/4) trials, then repair locally with at most two rotations.",
    ),
    "random-level-v2-1": StrategySpec(
        RandomLevelV21,
        "Random level v2.1",
        "Local repair, log-width priorities",
        "For insertion ordinal j starting at 1, use j.bit_length() fresh bits, then apply v2 target selection and local repair with remapped extrema. Strict new minima reach the root. The sampled priority range widens over time; v2's iid rotation bound does not transfer. No logarithmic-depth guarantee.",
    ),
    "random-level-v3": StrategySpec(
        RandomLevelV3,
        "Random level v3",
        "Sampled final level",
        "Keep v2 priority tracking, sample a final level from a depth-aware distribution, and promote the inserted leaf v1-style to that level. Every non-root insertion stays with probability 1/10; otherwise sample target k in 0..d-1 with weight (d / (2 ln(n)^2))^(d-k). No record-minimum override or balance guarantee.",
    ),
    "random-level-v4": StrategySpec(
        RandomLevelV4,
        "Random level v4",
        "Depth-switched v2/v3 hybrid",
        "Use v2 local repair when insertion depth d < ln(n), otherwise current v3 with a fixed 10% no-rotation gate, epsilon=1 and targets including the root. n counts previous insertions; equality and the empty tree use v3. Both branches share count and priority extrema. No balance guarantee.",
    ),
}.items():
    strategy_factory.register(identifier, spec)

# Backwards-compatible iterable of callable descriptors.
STRATEGIES = strategy_factory.specs
create_strategy = strategy_factory.create

__all__ = [
    "STRATEGIES",
    "ConstantWalk",
    "GeometricStop",
    "GeometricTargetLocalRepair",
    "GeometricThreeQuarters",
    "HalvingWalk",
    "HashPriority",
    "IntervalTargetLocalRepair",
    "InverseDepthWalk",
    "NoRebalance",
    "RandomLevel",
    "RandomLevelV2",
    "RandomLevelV3",
    "RandomLevelV4",
    "RandomLevelV21",
    "RebalanceContext",
    "RecountRoot",
    "Strategy",
    "StrategyFactory",
    "StrategySpec",
    "TreapPriority",
    "WindowRoot",
    "Zig",
    "ZigZag",
    "create_strategy",
    "strategy_factory",
]
