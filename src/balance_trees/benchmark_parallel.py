"""Run an adaptive, checkpointed comparison in parallel isolated processes."""

import argparse
import hashlib
import heapq
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
from array import array
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .benchmark import summarize, write_csv
from .experiment import derived_seed
from .measurement import run_trial
from .sequences import ORDERS, insertion_order
from .strategies import create_strategy, strategy_factory
from .strategies.geometric_target_local_repair_alternate import RandomLevelV213
from .strategies.stored_priority_treap import StoredPriorityTreap

COMPARISON_STRATEGIES = (
    "geometric-target-local-repair",
    "geometric-target-local-repair-alternate",
    "interval-target-local-repair",
    "random-level",
    "treap",
)


def comparison_strategy(name: str, seed: int):
    if name == "treap":
        return StoredPriorityTreap(seed)
    if name == "geometric-target-local-repair-alternate":
        return RandomLevelV213()
    return create_strategy(name)


def worker(request: dict) -> dict:
    memory_limit = request["memory_mib"] * 1024**2
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    values = insertion_order(request["order"], request["n"], request["order_seed"])
    policy = comparison_strategy(request["strategy"], request["seed"])
    result = run_trial(values, policy, request["seed"])
    if request["strategy"] == "treap":
        # Independently check the treap distribution's defining Cartesian tree.
        # The ordinary trial already validates BST links, ordering and key set.
        ancestor_stack = []
        left_children = array("i", [0]) * (request["n"] + 1)
        right_children = array("i", [0]) * (request["n"] + 1)
        for key in range(1, request["n"] + 1):
            last = None
            while ancestor_stack and (policy.priorities[key], key) < (
                policy.priorities[ancestor_stack[-1]],
                ancestor_stack[-1],
            ):
                last = ancestor_stack.pop()
            if ancestor_stack:
                right_children[ancestor_stack[-1]] = key
            if last is not None:
                left_children[key] = last
            ancestor_stack.append(key)
        pending = [(ancestor_stack[0], 0)]
        while pending:
            key, depth = pending.pop()
            if result.depths[key] != depth:
                raise AssertionError("stored-priority treap heap invariant violated")
            for child in (left_children[key], right_children[key]):
                if child:
                    pending.append((child, depth + 1))
    return {
        **asdict(result.metrics),
        "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }


def execute_trial(request: dict, source: Path, timeout: float) -> dict:
    row = {**request, "status": "error", "metrics": {}}
    try:
        process = subprocess.run(
            [sys.executable, "-m", "balance_trees.benchmark_parallel", "--worker"],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(source)},
        )
        if process.returncode == 0:
            row.update(status="complete", metrics=json.loads(process.stdout))
        else:
            detail = process.stderr[-2000:]
            row.update(
                status="memory_limit" if "MemoryError" in detail else "error",
                detail=detail or f"Worker exited {process.returncode}",
            )
    except subprocess.TimeoutExpired:
        row.update(status="timeout", detail=f"Exceeded {timeout:g} s wall deadline")
    return row


def record_key(row: dict) -> tuple:
    return tuple(row[key] for key in ("strategy", "order", "n", "trial"))


def summaries_with_maximum_height(records: list[dict]) -> list[dict]:
    summaries = summarize(records)
    for summary in summaries:
        completed = [
            row
            for row in records
            if (row["strategy"], row["order"], row["n"])
            == (summary["strategy"], summary["order"], summary["n"])
            and row["status"] == "complete"
        ]
        if completed:
            summary["maximum_height"] = max(
                row["metrics"]["height"] for row in completed
            )
    return summaries


def save_results(output: Path, metadata: dict, records: dict) -> dict:
    rows = sorted(records.values(), key=record_key)
    results = dict(
        metadata=metadata, summaries=summaries_with_maximum_height(rows), trials=rows
    )
    (output / "config.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    write_csv(output / "summary.csv", results["summaries"])
    write_csv(
        output / "trials.csv",
        [
            {
                **{key: value for key, value in row.items() if key != "metrics"},
                **row["metrics"],
            }
            for row in rows
        ],
    )
    return results


def run_comparison(
    output: Path,
    *,
    sizes: list[int],
    workers: int,
    timeout: float,
    memory_mib: int,
    small_trials: int,
    repeat_through: int,
    seed: int,
    strategies=COMPARISON_STRATEGIES,
    orders=ORDERS,
) -> dict:
    if (
        not sizes
        or min(sizes) < 2
        or sorted(set(sizes)) != sizes
        or workers < 1
        or small_trials < 1
        or memory_mib < 128
        or not 0 < timeout < float("inf")
        or not strategies
        or not orders
    ):
        raise ValueError("Use increasing unique sizes >=2 and positive resource limits")
    output = output.resolve()
    source = output / "source"
    existing_config = output / "config.json"
    settings = dict(
        sizes=sizes,
        workers=workers,
        timeout_seconds=timeout,
        memory_mib=memory_mib,
        small_trials=small_trials,
        repeat_through=repeat_through,
        seed=seed,
        strategies=list(strategies),
        orders=list(orders),
    )
    if existing_config.exists():
        metadata = json.loads(existing_config.read_text())
        if any(metadata[key] != value for key, value in settings.items()):
            raise ValueError("Resume requires the original settings")
    else:
        output.mkdir(parents=True, exist_ok=False)
        shutil.copytree(
            Path(__file__).parent,
            source / "balance_trees",
            ignore=shutil.ignore_patterns("__pycache__", "site"),
        )
        hashes = {
            str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source.rglob("*.py"))
        }
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            platform.machine(),
        )
        metadata = dict(
            **settings,
            started_at=datetime.now(timezone.utc).isoformat(),
            python=sys.version,
            platform=platform.platform(),
            cpu=cpu,
            logical_cpus=os.cpu_count(),
            source_sha256=hashes,
            execution="Parallel isolated Python subprocesses; no relative timing claims.",
            sampling="Fixed input per size; paired SHA-256-derived rotation seeds. SE conditional on that input.",
            metrics="Mean rotations/key, final mean node depth, maximum final height across completed trials, mean logical random bits/key. Root depth is zero.",
            limits="Per-process address-space cap includes inputs, insertion and final validation. Deadline is wall time under parallel load. Stop larger sizes for a strategy/workload after a resource failure.",
            validation="Every complete tree passes BST ordering, parent links, cycles and full key-set checks; stored treap also matches an independent Cartesian tree.",
            catalog={
                **{
                    name: strategy_factory.catalog()[name]
                    for name in strategies
                    if name in strategy_factory.catalog()
                },
                "treap": dict(
                    name="Stored-priority treap",
                    note="Existing Python reference: independent 32-bit priorities, key tie breaker, stored external priority map.",
                ),
                "geometric-target-local-repair-alternate": dict(
                    name="Geometric local repair · alternate",
                    note="Unmodified alternate implementation RandomLevelV213; records move count in stats.priority.",
                ),
            },
        )
        existing_config.write_text(json.dumps(metadata, indent=2) + "\n")
    checkpoint = output / "trials.jsonl"
    records = {}
    if checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            row = json.loads(line)
            records[record_key(row)] = row
    queue, serial = [], 0

    def schedule(strategy, order, size_index, trial_index=0):
        nonlocal serial
        stopped_by = None
        for index in range(size_index, len(sizes)):
            n = sizes[index]
            trial_count = small_trials if n <= repeat_through else 1
            for trial in range(trial_index if index == size_index else 0, trial_count):
                request = dict(
                    strategy=strategy,
                    order=order,
                    n=n,
                    trial=trial,
                    order_seed=derived_seed(seed, "order", n),
                    seed=derived_seed(seed, "rotation", n, order, trial),
                    memory_mib=memory_mib,
                )
                key = record_key(request)
                if key in records:
                    if records[key]["status"] not in ("complete", "not_run"):
                        stopped_by = f"{records[key]['status']} at n={n}"
                    continue
                if stopped_by:
                    row = {
                        **request,
                        "status": "not_run",
                        "metrics": {},
                        "detail": f"Larger/repeated trial skipped after {stopped_by}",
                    }
                    records[key] = row
                    checkpoint_handle.write(json.dumps(row) + "\n")
                    checkpoint_handle.flush()
                else:
                    serial += 1
                    heapq.heappush(queue, (n, trial, serial, request, index))
                    return

    invocation_started = perf_counter()
    with (
        checkpoint.open("a") as checkpoint_handle,
        ThreadPoolExecutor(max_workers=workers) as pool,
    ):
        for strategy in strategies:
            for order in orders:
                schedule(strategy, order, 0)
        running = {}
        while queue or running:
            while queue and len(running) < workers:
                _, _, _, request, index = heapq.heappop(queue)
                future = pool.submit(execute_trial, request, source, timeout)
                running[future] = (request, index)
            finished, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                request, index = running.pop(future)
                row = future.result()
                records[record_key(row)] = row
                checkpoint_handle.write(json.dumps(row) + "\n")
                checkpoint_handle.flush()
                print(
                    f"{row['status']}: {request['strategy']} {request['order']} n={request['n']:,} trial={request['trial']}",
                    flush=True,
                )
                # Rewalk this group: completed indices are reused and failures
                # censor all larger trials without launching further processes.
                schedule(request["strategy"], request["order"], 0)
                save_results(output, metadata, records)
    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    metadata["active_wall_seconds"] = (
        metadata.get("active_wall_seconds", 0) + perf_counter() - invocation_started
    )
    return save_results(output, metadata, records)


def main():
    if sys.argv[1:] == ["--worker"]:
        print(json.dumps(worker(json.load(sys.stdin))))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[2**power for power in (10, 12, 14, 16, 18, 20, 21, 22, 23, 24)],
    )
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--timeout", type=float, default=360)
    parser.add_argument("--memory-mib", type=int, default=768)
    parser.add_argument("--small-trials", type=int, default=3)
    parser.add_argument("--repeat-through", type=int, default=65536)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    results = run_comparison(
        args.output,
        sizes=args.sizes,
        workers=args.workers,
        timeout=args.timeout,
        memory_mib=args.memory_mib,
        small_trials=args.small_trials,
        repeat_through=args.repeat_through,
        seed=args.seed,
    )
    complete = sum(row["status"] == "complete" for row in results["trials"])
    print(f"Saved {complete} completed trials to {args.output}")


if __name__ == "__main__":
    main()
