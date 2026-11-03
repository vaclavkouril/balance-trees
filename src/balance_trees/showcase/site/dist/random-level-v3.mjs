// Match Python's round-to-even for the 53-bit conditional coin numerator.
function roundEven(value) {
  const lower = Math.floor(value), fraction = value - lower;
  return fraction === 0.5 ? lower + (lower % 2) : Math.round(value);
}

export function randomLevelV3(c, state = { count: 0, lowest: null, highest: null }) {
  return function* (node, depth) {
    let priority = 0n;
    for (let bit = 0; bit < 64; bit++) priority = (priority << 1n) | BigInt(c.bit());
    const previousCount = state.count;
    state.count++;
    if (state.lowest === null || priority < state.lowest) state.lowest = priority;
    if (state.highest === null || priority > state.highest) state.highest = priority;
    let target = depth;
    if (depth > 0 && (yield* c.choose(node, 9, 10, 'promote-leaf'))) {
      target = 0;
      if (depth > 1) {
        const logRatio = Math.log(depth) - Math.log(2)
          - 2 * Math.log(Math.log(previousCount));
        const peak = logRatio >= 0 ? depth : 1;
        const weights = new Float64Array(depth);
        const suffix = new Float64Array(depth + 1);
        for (let level = 0; level < depth; level++) {
          weights[level] = Math.exp((depth - level - peak) * logRatio);
        }
        for (let i = depth - 1; i >= 0; i--) suffix[i] = weights[i] + suffix[i + 1];
        target = depth - 1;
        const scale = 2 ** 53;
        for (let i = 0; i < depth - 1; i++) {
          const numerator = Math.min(scale, Math.max(0, roundEven(weights[i] / suffix[i] * scale)));
          if (yield* c.choose(node, numerator, scale, 'choose-final-level')) {
            target = i;
            break;
          }
        }
      }
    }
    yield* c.event('target', `Target depth ${target}`,
      `Rolled ${priority}; extrema remain tracked but do not override sampling. Non-root insertions use a fixed 90% promotion gate. Final depth ${target}; ${depth - target} rotations.`, node);
    for (let current = depth; current > target; current--) yield* c.promote(node);
  };
}
