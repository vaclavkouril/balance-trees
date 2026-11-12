// Generated from the Python strategy factory by showcase.build.
export const FLAVORS = {
  "treap": {
    "name": "Treap",
    "tag": "Priority heap",
    "note": "A BST by key and min-heap by stored random priority. This browser reference retains per-node priorities."
  },
  "halving": {
    "name": "Halving walk",
    "tag": "Full upward walk",
    "note": "Try 1/2, 1/4, 1/8… and continue to the root after either outcome. Expected fewer than one rotation per insertion; ancestor work can be linear."
  },
  "constant-half": {
    "name": "Constant ½",
    "tag": "Full upward walk",
    "note": "Rotate with probability 1/2 at every visited ancestor, continuing to the root. Both visits and rotations can grow with depth."
  },
  "inverse-depth": {
    "name": "Inverse depth",
    "tag": "Depth-informed rule",
    "note": "Freeze initial insertion depth h and use 1/h at every decision. Sorted inputs produce a chain despite at most one expected rotation."
  },
  "none": {
    "name": "Plain BST",
    "tag": "No rebalancing",
    "note": "Ordinary leaf insertion. Ordered inputs can produce linear height and quadratic insertion work."
  },
  "paper-zig": {
    "name": "Paper · Zig",
    "tag": "Geometric stop",
    "note": "Continue upward with probability 1/2; otherwise promote the cursor once and stop."
  },
  "paper-zigzag": {
    "name": "Paper · ZigZag",
    "tag": "Geometric stop",
    "note": "Continue with probability 3/4. On stopping, a straight path promotes the parent once, a bent path promotes the cursor twice."
  },
  "recount-root": {
    "name": "Recount root lottery",
    "tag": "Exact distribution",
    "note": "Exact random-BST shape distribution from empty, using transient full-tree counting. Linear scan work per insertion; quadratic total scans."
  },
  "window-root": {
    "name": "Window root lottery",
    "tag": "Bounded local heuristic",
    "note": "Root lotteries within 64 actual node inspections by default. Never uses an incomplete count; no general logarithmic-depth guarantee."
  },
  "hash-priority": {
    "name": "Recomputed priority",
    "tag": "Keyed hash heuristic",
    "note": "Recompute SplitMix64 key/seed priorities for treap-style comparisons. No priority table or fresh insertion bits; finite hashes are not independent priorities."
  },
  "random-level": {
    "name": "Random level · perfect-tree target",
    "tag": "Sampled leaf destination",
    "note": "Sample a vertex uniformly from the smallest perfect tree containing n nodes, including the new leaf. Promote the inserted leaf to that depth if deeper; otherwise leave it unchanged. No priority extrema or height guarantee."
  },
  "interval-target-promotion": {
    "name": "Interval-target leaf promotion (original random level)",
    "tag": "Priority-free depth heuristic",
    "note": "Roll 64 fair bits and choose a depth from the previous observed priority interval. New minima reach the root; new maxima stay leaves. Stores only a count and two extrema; no balance guarantee."
  },
  "interval-target-local-repair": {
    "name": "Interval-target local repair",
    "tag": "Local repair at sampled level",
    "note": "Choose a repair level using the original 64-bit interval bands. Ordinary insertions perform at most two local rotations; strict new minima promote the leaf to the root. Expected fewer than three rotations per insertion from empty under iid uniform rolls. Ancestor walks can be long; no logarithmic-depth guarantee."
  },
  "geometric-target-local-repair": {
    "name": "Geometric target local repair",
    "tag": "Perfect-tree reference, at most two rotations",
    "note": "Sample target depth with capped leading fair bits and L=ceil(log2(n))+1, including the new leaf. Stay at or above the target; otherwise repair a straight or bent ancestor path with at most two rotations. No record exceptions or height guarantee."
  },
  "geometric-three-quarters": {
    "name": "Geometric target · 3/4",
    "tag": "Logarithmic height for fixed insertion sequences",
    "note": "Sample a target from ceil(log base 4/3 of n) using independent Bernoulli(3/4) trials, then repair locally with at most two rotations."
  },
  "random-level-v2-1": {
    "name": "Random level v2.1",
    "tag": "Local repair, log-width priorities",
    "note": "For insertion ordinal j starting at 1, use j.bit_length() fresh bits, then apply v2 target selection and local repair with remapped extrema. Strict new minima reach the root. The sampled priority range widens over time; v2's iid rotation bound does not transfer. No logarithmic-depth guarantee."
  },
  "random-level-v3": {
    "name": "Random level v3",
    "tag": "Sampled final level",
    "note": "Keep v2 priority tracking, sample a final level from a depth-aware distribution, and promote the inserted leaf v1-style to that level. Every non-root insertion stays with probability 1/10; otherwise sample target k in 0..d-1 with weight (d / (2 ln(n)^2))^(d-k). No record-minimum override or balance guarantee."
  },
  "random-level-v4": {
    "name": "Random level v4",
    "tag": "Depth-switched v2/v3 hybrid",
    "note": "Use v2 local repair when insertion depth d < ln(n), otherwise current v3 with a fixed 10% no-rotation gate, epsilon=1 and targets including the root. n counts previous insertions; equality and the empty tree use v3. Both branches share count and priority extrema. No balance guarantee."
  }
};
