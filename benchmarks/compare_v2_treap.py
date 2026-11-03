"""Reuse archived v2 trials and fill a parallel, shape-only treap comparison.

Run from the repository root with PYTHONPATH=src python3 benchmarks/compare_v2_treap.py.
Only the standard library is required. Re-running resumes completed trials.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from random import Random
from time import perf_counter

from balance_trees.benchmark import summarize, write_csv
from balance_trees.experiment import derived_seed
from balance_trees.measurement import run_trial
from balance_trees.sequences import insertion_order
from balance_trees.strategies import create_strategy

ORDERS = ("random", "increasing", "converging")
STRATEGIES = ("random-level-v2", "treap")
METRICS = ("mean_depth", "height", "mean_rotations")


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


def identity(row):
    return tuple(
        row[k] for k in ("strategy", "order", "n", "trial", "seed", "order_seed")
    )


def measure(request):
    values = insertion_order(request["order"], request["n"], request["order_seed"])
    strategy = (
        StoredPriorityTreap(request["seed"])
        if request["strategy"] == "treap"
        else create_strategy(request["strategy"])
    )
    result = run_trial(values, strategy, request["seed"])
    if request["strategy"] == "treap":
        # run_trial checks BST links, ordering, cycles and complete key set.
        # Independently check the heap through the final BST's parent mapping:
        # sorted keys and priorities define the unique Cartesian tree, whose
        # depths must agree with the measured tree.
        stack = []
        left, right = {}, {}
        for key in range(1, request["n"] + 1):
            last = None
            while stack and (strategy.priorities[key], key) < (
                strategy.priorities[stack[-1]],
                stack[-1],
            ):
                last = stack.pop()
            if stack:
                right[stack[-1]] = key
            if last is not None:
                left[key] = last
            stack.append(key)
        pending = [(stack[0], 0)]
        while pending:
            key, depth = pending.pop()
            assert result.depths[key] == depth, "treap heap invariant violated"
            for child in (left.get(key), right.get(key)):
                if child is not None:
                    pending.append((child, depth + 1))
    return {
        **request,
        "status": "complete",
        "source": "new parallel run",
        "metrics": asdict(result.metrics),
    }


def render(summaries, output):
    colors = dict(zip(ORDERS, ("#2563eb", "#d97706", "#059669")))
    labels = ("Mean node depth · edges", "Final height · edges", "Rotations / key")
    sizes = sorted({r["n"] for r in summaries})
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="540" viewBox="0 0 1440 540">',
        '<rect width="1440" height="540" fill="white"/>',
        "<style>text{font:13px sans-serif;fill:#334155}.grid{stroke:#e2e8f0}</style>",
        '<text x="35" y="30" style="font-size:23px;font-weight:bold">Random level v2 vs stored-priority treap</text>',
        '<text x="35" y="55">All archived key counts · root depth 0 · solid: v2 · dashed: treap · color: insertion order</text>',
    ]
    for index, (metric, label) in enumerate(zip(METRICS, labels)):
        left, top, width, height = 65 + index * 475, 112, 385, 300
        ymax = max(r[metric] + (r.get(metric + "_se") or 0) for r in summaries) * 1.12

        def x(n):
            return left + width * math.log(n / sizes[0]) / math.log(
                sizes[-1] / sizes[0]
            )

        def y(v):
            return top + height * (1 - v / ymax)

        parts.append(
            f'<text x="{left}" y="90" style="font-size:18px;font-weight:bold">{label}</text>'
        )
        for tick in range(6):
            value = ymax * tick / 5
            yy = y(value)
            parts.append(
                f'<path class="grid" d="M{left},{yy}h{width}"/><text x="{left - 8}" y="{yy + 4}" text-anchor="end">{value:.2f}</text>'
            )
        for n in (1000, 10000, 100000, 1000000, sizes[-1]):
            xx = x(n)
            label_n = f"{n / 1e6:.2g}M" if n >= 1e6 else f"{n / 1000:g}k"
            parts.append(
                f'<path class="grid" d="M{xx},{top}v{height}"/><text x="{xx}" y="435" text-anchor="middle">{label_n}</text>'
            )
        for order in ORDERS:
            for strategy in STRATEGIES:
                rows = sorted(
                    (
                        r
                        for r in summaries
                        if r["order"] == order and r["strategy"] == strategy
                    ),
                    key=lambda r: r["n"],
                )
                points = " ".join(f"{x(r['n']):.2f},{y(r[metric]):.2f}" for r in rows)
                dash = ' stroke-dasharray="7 4"' if strategy == "treap" else ""
                parts.append(
                    f'<polyline points="{points}" fill="none" stroke="{colors[order]}" stroke-width="2"{dash}/>'
                )
                for row in rows:
                    xx, yy = x(row["n"]), y(row[metric])
                    se = row.get(metric + "_se")
                    if se is not None:
                        parts.append(
                            f'<path d="M{xx},{y(row[metric] - se)}V{y(row[metric] + se)}" stroke="{colors[order]}"/>'
                        )
                    parts.append(
                        f'<circle cx="{xx}" cy="{yy}" r="2.5" fill="{colors[order]}"><title>{strategy}, {order}, n={row["n"]}: {row[metric]:.6g}; trials={row["completed_trials"]}</title></circle>'
                    )
        parts.append(
            f'<text x="{left + width / 2}" y="460" text-anchor="middle">Keys (log scale)</text>'
        )
    for i, order in enumerate(ORDERS):
        parts.append(
            f'<text x="{35 + i * 190}" y="500" style="fill:{colors[order]};font-weight:bold">● {order}</text>'
        )
    parts.append(
        '<text x="35" y="526">3 paired trials at 1k / 16k / 128k; 1 elsewhere. Whiskers: ±1 SE when available. Depth = mean over final nodes; height = maximum depth.</text></svg>'
    )
    (output / "comparison.svg").write_text("\n".join(parts))
    (output / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>v2 vs treap</title><style>body{margin:24px;font:16px sans-serif}img{width:100%;height:auto}</style><h1>Random level v2 vs treap</h1><img src="comparison.svg" alt="Three comparison charts"><p>All three input families and both strategies share each metric panel. Hover points in the SVG for measurements. Archived v2 trials are reused; other trials ran in parallel. Timings are deliberately excluded.</p><p><a href="summary.csv">Summary CSV</a> · <a href="trials.csv">Raw trials</a> · <a href="config.json">Provenance and configuration</a></p>'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/v2-treap"))
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    configs = [
        Path("benchmarks/random-level-scale-recheck/config.json"),
        Path("src/balance_trees/showcase/site/dist/random-level-results/config.json"),
    ]
    sizes = sorted({n for p in configs for n in json.loads(p.read_text())["sizes"]})
    archive = Path("benchmarks/random-level-v2/trials.csv")
    records = {}
    with archive.open() as handle:
        for row in csv.DictReader(handle):
            if row["order"] not in ORDERS or row["status"] != "complete":
                continue
            request = {k: int(row[k]) for k in ("n", "trial", "seed", "order_seed")}
            record = {
                **request,
                "strategy": row["strategy"],
                "order": row["order"],
                "status": "complete",
                "source": str(archive),
                "metrics": {k: float(row[k]) for k in METRICS},
            }
            records[identity(record)] = record
    checkpoint = args.output / "trials.jsonl"
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            row = json.loads(line)
            records[identity(row)] = row
    requests = []
    for n in sizes:
        for order in ORDERS:
            for strategy in STRATEGIES:
                for trial in range(3 if n in (1000, 16000, 128000) else 1):
                    request = dict(
                        strategy=strategy,
                        order=order,
                        n=n,
                        trial=trial,
                        seed=derived_seed(2026, "rotation", n, order, trial),
                        order_seed=derived_seed(2026, "order", n),
                    )
                    if identity(request) not in records:
                        requests.append(request)
    print(
        f"{len(sizes)} sizes; {len(records)} reused trials; {len(requests)} missing; {args.workers} workers",
        flush=True,
    )
    config = dict(
        sizes=sizes,
        orders=ORDERS,
        strategies=STRATEGIES,
        seed=2026,
        workers=args.workers,
        python=sys.version,
        platform=platform.platform(),
        archive=str(archive),
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        size_sources=[str(p) for p in configs],
        trials="3 paired trials at archived v2 sizes, 1 elsewhere",
        metrics="Final mean node depth, final maximum depth, primitive rotations per inserted key; depths count edges",
        execution="Parallel processes; operation and shape metrics only; no timing comparisons",
        treap="Showcase Python min-heap policy: Random(seed).getrandbits(32), ties ordered by key; priorities stored externally",
        validation="BST order, parent pointers, acyclicity, complete key set; treap depths independently checked against Cartesian tree",
    )
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    with (
        checkpoint.open("a") as handle,
        ProcessPoolExecutor(max_workers=args.workers) as pool,
    ):
        # Largest jobs first keeps all workers busy at the end of the sweep.
        futures = {
            pool.submit(measure, r): r for r in sorted(requests, key=lambda r: -r["n"])
        }
        for i, future in enumerate(as_completed(futures), 1):
            record = future.result()
            records[identity(record)] = record
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            print(
                f"{i}/{len(requests)} {record['strategy']} {record['order']} n={record['n']} complete",
                flush=True,
            )
    rows = sorted(records.values(), key=identity)
    # Compare only the three requested metrics, shared by archived and fresh rows.
    shape_rows = [{**r, "metrics": {k: r["metrics"][k] for k in METRICS}} for r in rows]
    summaries = summarize(shape_rows)
    write_csv(args.output / "summary.csv", summaries)
    write_csv(
        args.output / "trials.csv",
        [
            {**{k: v for k, v in r.items() if k != "metrics"}, **r["metrics"]}
            for r in rows
        ],
    )
    config["wall_seconds"] = perf_counter() - started
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    (args.output / "results.json").write_text(
        json.dumps(dict(metadata=config, summaries=summaries, trials=rows), indent=2)
        + "\n"
    )
    render(summaries, args.output)
    print(
        f"Done: {len(rows)} trials in {config['wall_seconds']:.1f}s; {args.output}/comparison.svg",
        flush=True,
    )


if __name__ == "__main__":
    main()
