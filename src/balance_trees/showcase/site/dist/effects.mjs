// Insertion-local history. Key intervals describe every moving subtree without
// traversing it, so recording a rotation also works for million-node previews.
export class InsertionEffects {
  constructor() { this.begin(); }
  begin() { this.inserted = null; this.compared = new Set(); this.rose = []; this.fell = []; }
  compare(...keys) { for (const key of keys) if (key !== null) this.compared.add(key); }
  rotation(node, parent, { left, right, key }) {
    const extreme = (start, child) => {
      let next;
      while ((next = child(start)) !== null) start = next;
      return key(start);
    };
    if (left(parent) === node) {
      this.rose.push([extreme(node, left), key(node)]);
      this.fell.push([key(parent), extreme(parent, right)]);
    } else {
      this.rose.push([key(node), extreme(node, right)]);
      this.fell.push([extreme(parent, left), key(parent)]);
    }
  }
  snapshot(nodes) {
    const keys = nodes.map(node => node.key).sort((a, b) => a - b);
    const inside = ranges => keys.filter(key => ranges.some(([low, high]) => low <= key && key <= high));
    return { inserted: this.inserted, compared: keys.filter(key => this.compared.has(key)), rose: inside(this.rose), fell: inside(this.fell) };
  }
}

export const ROLE_LABELS = { inserted: 'Inserted this operation', compared: 'Compared this insertion', rose: 'Moved up this insertion', fell: 'Moved down this insertion' };
export const ROLE_SYMBOLS = { inserted: '★', compared: 'C', rose: '↑', fell: '↓' };

export function nodeRoles(frame) {
  // Older imported traces still expose the current operation's participants.
  const effects = frame.effects ?? {
    inserted: frame.kind === 'insert' ? frame.key : null,
    compared: ['compare', 'priority'].includes(frame.kind) ? [frame.focus, frame.demoted].filter(key => key != null) : [],
    rose: ['prepare', 'rotate'].includes(frame.kind) ? [frame.promoted] : [],
    fell: ['prepare', 'rotate'].includes(frame.kind) ? [frame.demoted] : [],
  };
  const sets = Object.fromEntries(['compared', 'rose', 'fell'].map(role => [role, new Set(effects[role])]));
  return new Map(frame.nodes.map(node => [node.key, Object.keys(ROLE_LABELS).filter(role => role === 'inserted' ? effects.inserted === node.key : sets[role].has(node.key))]));
}
