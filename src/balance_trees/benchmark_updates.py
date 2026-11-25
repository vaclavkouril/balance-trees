"""Run reproducible C++ insert/delete/search workloads in isolated parallel workers."""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .benchmark_support import (
    build_native_worker,
    compiler_version,
    machine_metadata,
    write_json,
)
from .experiment import derived_seed

WORKLOADS = (
    "random-churn",
    "ascending-churn",
    "descending-churn",
    "grow-shrink",
    "read-heavy",
)
DEFAULT_SIZES = [2**power for power in (10, 14, 18, 20, 22, 24)]


def record_key(row: dict) -> tuple:
    return row["workload"], row["n"], row["trial"]


def source_hashes(source: Path) -> dict:
    return {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }


def execute_trial(executable: Path, request: dict, timeout: float) -> dict:
    row = {**request, "status": "error", "metrics": {}}
    try:
        process = subprocess.run(
            [
                str(executable),
                str(request["seed"]),
                str(request["n"]),
                str(request["memory_mib"]),
                request["workload"],
                str(request["order_seed"]),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if process.returncode:
            row.update(
                status="memory_limit" if process.returncode == 2 else "error",
                detail=process.stderr[-4000:] or f"Worker exited {process.returncode}",
            )
            return row
        metrics = json.loads(process.stdout)
        # Python's JSON decoder accepts NaN/Infinity; measured output must not.
        json.dumps(metrics, allow_nan=False)
        for key in ("workload", "n", "seed", "order_seed"):
            if metrics[key] != request[key]:
                raise ValueError(f"Worker returned the wrong {key}")
        operations = request["n"] * (10 if request["workload"] == "read-heavy" else 2)
        checkpoints = metrics["checkpoints"]
        if metrics["operations"] != operations or not checkpoints:
            raise ValueError("Worker returned incomplete operation/checkpoint counts")
        for key in ("elapsed_seconds", "peak_rss_mib"):
            if not math.isfinite(metrics[key]) or metrics[key] <= 0:
                raise ValueError(f"Worker returned invalid {key}")
        if metrics["cpu_seconds"] < 0:
            raise ValueError("Worker returned invalid cpu_seconds")
        if metrics["max_insert_rotations"] > 2 or metrics["max_delete_rotations"] > 4:
            raise ValueError("Worker exceeded the deterministic rotation budget")
        n = request["n"]
        searches = 8 * n if request["workload"] == "read-heavy" else 0
        expected_counts = dict(
            insert_attempts=n,
            inserted=n,
            delete_attempts=n,
            erased=n,
            search_attempts=searches,
            found=searches // 2,
            final_nodes=n,
        )
        if any(metrics[key] != value for key, value in expected_counts.items()):
            raise ValueError("Worker returned incorrect operation outcomes")
        positions = [point["completed_ops"] for point in checkpoints]
        if (
            positions != sorted(set(positions))
            or positions[0] != 0
            or positions[-1] != operations
            or checkpoints[0]["n"] != n
            or checkpoints[-1]["n"] != n
        ):
            raise ValueError("Worker returned invalid checkpoint boundaries")
        for point in checkpoints:
            size, height, depth = point["n"], point["height"], point["mean_depth"]
            if not 0 <= size <= n or (
                (size == 0 and (height != -1 or depth != 0))
                or (size > 0 and not 0 <= depth <= height < size)
            ):
                raise ValueError("Worker returned invalid checkpoint depths")
        row.update(status="complete", metrics=metrics)
    except subprocess.TimeoutExpired:
        row.update(
            status="timeout", detail=f"Worker exceeded {timeout:g} s wall deadline"
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        row.update(status="error", detail=str(error))
    return row


def save_results(output: Path, metadata: dict, records: dict) -> dict:
    results = {"metadata": metadata, "trials": sorted(records.values(), key=record_key)}
    write_json(output / "config.json", metadata)
    write_json(output / "results.json", results)
    return results


def prepare_run(output: Path, settings: dict) -> dict:
    source = output / "source"
    if output.exists():
        metadata = json.loads((output / "config.json").read_text())
        if metadata["settings"] != settings:
            raise ValueError("Resume requires identical settings")
        if metadata["source_sha256"] != source_hashes(source):
            raise ValueError(
                "The measured source snapshot changed; use a fresh directory"
            )
        return metadata
    output.mkdir(parents=True)
    repository = Path(__file__).resolve().parents[2]
    shutil.copytree(repository / "src/native", source / "src/native")
    shutil.copytree(
        Path(__file__).parent,
        source / "src/balance_trees",
        ignore=shutil.ignore_patterns("__pycache__", "site"),
    )
    shutil.copytree(
        repository / "tests",
        source / "tests",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copyfile(repository / "pyproject.toml", source / "pyproject.toml")
    (source / "REPRODUCE.txt").write_text(
        "Measured source snapshot. From this directory:\n"
        "cmake -S src/native -B build/native -DCMAKE_BUILD_TYPE=Release\n"
        "cmake --build build/native -j2\n"
        "ctest --test-dir build/native --output-on-failure\n"
        "build/native/native-update-benchmark SEED N MEMORY_MIB WORKLOAD ORDER_SEED\n"
        "Use each row's parameters from trials.jsonl/results.json in the report.\n"
        "The Python runner also regenerates a full suite into a fresh directory:\n"
        "PYTHONPATH=src python3 -m balance_trees.benchmark_updates --help\n"
    )
    metadata = {
        "schema_version": 1,
        "settings": settings,
        **settings,
        "strategy": "geometric-full-bst",
        "probability": "3/4",
        "started_at": datetime.now(timezone.utc).isoformat(),
        **machine_metadata(),
        "cpu_affinity_count": len(os.sched_getaffinity(0)),
        "compiler": compiler_version(),
        "build": "CMake Release (-O3 -DNDEBUG), C++20; pre-reserved compact node arrays",
        "source_sha256": source_hashes(source),
        "execution": (
            "Parallel isolated C++ subprocesses on a shared host; other benchmark suites "
            "may run concurrently. Wall times include scheduling and contention; process "
            "CPU times exclude descheduling but still reflect the shared machine. "
            "Neither is a single-core latency or comparative speedup claim."
        ),
        "sampling": (
            "Workloads are fixed independently of the tree RNG. SHA-256 derives separate "
            "workload and rotation seeds. Each workload/size shares its operation seed "
            "across repeated tree seeds. Buffered SplitMix64 supplies tree random bits; "
            "Fisher-Yates with rejection sampling produces workload permutations. "
            "Operation fingerprints identify identical streams (FNV-1a64, not cryptographic)."
        ),
        "timing": (
            "Timed chunked loops include public operations, both refreshes in each successful "
            "nonempty deletion, and aggregate counters. Process startup, workload generation, "
            "reservation, preload, checkpoint validation and report rendering are excluded. "
            "Preload time is recorded separately."
        ),
        "validation": (
            "All completed trials check exact live key membership against a workload bitmap, "
            "BST order, parent pointers, reachability and size at checkpoints. Every operation "
            "checks its expected outcome and the insert/delete rotation budget. "
            "Heights are observed only at checkpoints, not after every operation."
        ),
        "limits": (
            "Per-worker RLIMIT_AS and wall deadline include preload and validation. "
            "Failure stops only that workload's remaining trials and larger sizes; "
            "those remain explicit not_run records. Raw results are checkpointed and resumable. "
            "Peak RSS includes workload/checkpoint storage, and is not tree-only memory."
        ),
        "sessions": [],
    }
    write_json(output / "config.json", metadata)
    return metadata


def build_worker(output: Path) -> Path:
    build = output / "build"
    executable = build / "native-update-benchmark"
    if executable.is_file():
        return executable
    return build_native_worker(
        output / "source/src/native", build, "native-update-benchmark"
    )


def run_updates(
    output: Path,
    *,
    sizes: list[int] | None = None,
    workloads: tuple[str, ...] = WORKLOADS,
    workers: int = 4,
    memory_mib: int = 768,
    timeout: float = 1800,
    small_trials: int = 3,
    repeat_through: int = 65536,
    seed: int = 2026,
) -> dict:
    sizes = list(DEFAULT_SIZES) if sizes is None else sizes
    if (
        not sizes
        or any(type(n) is not int or not 2 <= n < 2**32 for n in sizes)
        or sizes != sorted(set(sizes))
        or not workloads
        or len(set(workloads)) != len(workloads)
        or any(name not in WORKLOADS for name in workloads)
        or workers < 1
        or memory_mib < 128
        or not 0 < timeout < float("inf")
        or small_trials < 1
        or repeat_through < 0
    ):
        raise ValueError(
            "Use increasing sizes >=2, known workloads, and positive resource limits"
        )
    settings = dict(
        sizes=sizes,
        workloads=list(workloads),
        workers=workers,
        memory_mib=memory_mib,
        timeout_seconds=timeout,
        small_trials=small_trials,
        repeat_through=repeat_through,
        seed=seed,
    )
    output = output.resolve()
    metadata = prepare_run(output, settings)
    journal = output / "trials.jsonl"
    records = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            row = json.loads(line)
            identity = record_key(row)
            if identity in records:
                raise ValueError("Duplicate trial in checkpoint journal")
            records[identity] = row
    pending = {}
    stopped = {}
    requested_identities = set()
    for workload in workloads:
        queue = deque()
        for n in sizes:
            for trial in range(small_trials if n <= repeat_through else 1):
                request = dict(
                    workload=workload,
                    n=n,
                    trial=trial,
                    seed=derived_seed(seed, "update-rotation", n, workload, trial),
                    order_seed=derived_seed(seed, "update-order", n, workload),
                    memory_mib=memory_mib,
                )
                identity = record_key(request)
                requested_identities.add(identity)
                if identity in records:
                    row = records[identity]
                    if any(row[key] != value for key, value in request.items()):
                        raise ValueError(
                            "Checkpoint trial disagrees with the requested seeds"
                        )
                    if row["status"] != "complete":
                        stopped[workload] = row.get("detail", row["status"])
                else:
                    queue.append(request)
        pending[workload] = queue
    if records.keys() - requested_identities:
        raise ValueError("Checkpoint journal contains an unrequested trial")
    expected = sum(len(queue) for queue in pending.values()) + len(records)
    if not any(pending.values()):
        return save_results(output, metadata, records)
    executable = build_worker(output)
    started = perf_counter()
    session = dict(started_at=datetime.now(timezone.utc).isoformat(), workers=workers)
    metadata["sessions"].append(session)

    def record(row: dict) -> None:
        records[record_key(row)] = row
        with journal.open("a") as handle:
            handle.write(json.dumps(row, allow_nan=False) + "\n")
        save_results(output, metadata, records)
        print(
            f"[{len(records)}/{expected}] {row['workload']} n={row['n']:,} "
            f"trial={row['trial']} {row['status']} ({perf_counter() - started:.1f}s)",
            flush=True,
        )

    # A lane handles one workload in size order. This keeps failures from causing
    # avoidable larger runs while independent lanes fill the subprocess pool.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        active = {}
        busy = set()
        while active or any(pending.values()):
            for workload, queue in pending.items():
                if workload in stopped:
                    while queue:
                        record(
                            {
                                **queue.popleft(),
                                "status": "not_run",
                                "metrics": {},
                                "detail": "Earlier workload failure: "
                                + stopped[workload],
                            }
                        )
                if queue and workload not in busy and len(active) < workers:
                    request = queue.popleft()
                    future = executor.submit(
                        execute_trial, executable, request, timeout
                    )
                    active[future] = workload
                    busy.add(workload)
            if not active:
                continue
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                workload = active.pop(future)
                busy.remove(workload)
                row = future.result()
                record(row)
                if row["status"] != "complete":
                    stopped[workload] = row.get("detail", row["status"])
    session.update(
        finished_at=datetime.now(timezone.utc).isoformat(),
        wall_seconds=perf_counter() - started,
    )
    metadata["finished_at"] = session["finished_at"]
    metadata["wall_seconds"] = sum(
        item.get("wall_seconds", 0) for item in metadata["sessions"]
    )
    return save_results(output, metadata, records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=DEFAULT_SIZES)
    parser.add_argument("--workloads", nargs="+", choices=WORKLOADS, default=WORKLOADS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--memory-mib", type=int, default=768)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--small-trials", type=int, default=3)
    parser.add_argument("--repeat-through", type=int, default=65536)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    try:
        results = run_updates(
            args.output,
            sizes=args.sizes,
            workloads=tuple(args.workloads),
            workers=args.workers,
            memory_mib=args.memory_mib,
            timeout=args.timeout,
            small_trials=args.small_trials,
            repeat_through=args.repeat_through,
            seed=args.seed,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    complete = sum(row["status"] == "complete" for row in results["trials"])
    print(
        f"Complete trials: {complete}/{len(results['trials'])}. Results: {args.output / 'results.json'}"
    )


if __name__ == "__main__":
    main()
