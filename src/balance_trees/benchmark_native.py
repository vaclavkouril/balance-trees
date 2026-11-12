"""Run reproducible native geometric benchmarks, optionally extending a Python run."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .benchmark_parallel import record_key, save_results
from .experiment import derived_seed
from .sequences import ORDERS, insertion_order

NATIVE = "geometric-target-local-repair-native"
BIASED_NATIVE = "geometric-three-quarters-native"
NATIVE_STRATEGIES = (NATIVE, BIASED_NATIVE)
DEFAULT_SIZES = [2**power for power in (10, 12, 14, 16, 18, 20, 21, 22, 23, 24)]


def prepare_input(path: Path, order: str, n: int, seed: int) -> str:
    values = insertion_order(order, n, seed)
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for offset in range(0, n, 8192):
            chunk = (" ".join(map(str, values[offset : offset + 8192])) + "\n").encode()
            handle.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


def execute_native_trial(
    executable: Path, input_path: Path, request: dict, timeout: float
) -> dict:
    row = {**request, "status": "error", "metrics": {}}
    try:
        with input_path.open() as handle:
            process = subprocess.run(
                [
                    str(executable),
                    str(request["seed"]),
                    str(request["n"]),
                    str(request["memory_mib"]),
                    request["strategy"].removesuffix("-native"),
                ],
                stdin=handle,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        if process.returncode == 0:
            row.update(status="complete", metrics=json.loads(process.stdout))
        else:
            row.update(
                status="memory_limit" if "memory_limit" in process.stderr else "error",
                detail=process.stderr[-2000:] or f"Worker exited {process.returncode}",
            )
    except subprocess.TimeoutExpired:
        row.update(status="timeout", detail=f"Exceeded {timeout:g} s")
    return row


def run_native_comparison(
    baseline: Path | None,
    output: Path,
    *,
    sizes: list[int] | None = None,
    timeout: float = 360,
    memory_mib: int = 768,
    strategies: tuple[str, ...] | None = None,
    orders: tuple[str, ...] | None = None,
    small_trials: int = 3,
    repeat_through: int = 65536,
    seed: int = 2026,
) -> dict:
    original = json.loads((baseline / "results.json").read_text()) if baseline else None
    if original:
        sizes = original["metadata"]["sizes"] if sizes is None else sizes
        orders = tuple(original["metadata"]["orders"]) if orders is None else orders
        small_trials = original["metadata"]["small_trials"]
        repeat_through = original["metadata"]["repeat_through"]
        seed = original["metadata"]["seed"]
    else:
        sizes = DEFAULT_SIZES if sizes is None else sizes
        orders = ORDERS if orders is None else orders
    strategies = (
        ((NATIVE,) if original else NATIVE_STRATEGIES)
        if strategies is None
        else strategies
    )
    if (
        not sizes
        or sizes != sorted(set(sizes))
        or min(sizes) < 2
        or max(sizes) >= 2**32
        or not 0 < timeout < float("inf")
        or memory_mib < 128
        or not strategies
        or len(set(strategies)) != len(strategies)
        or any(name not in NATIVE_STRATEGIES for name in strategies)
        or not orders
        or len(set(orders)) != len(orders)
        or any(name not in ORDERS for name in orders)
        or small_trials < 1
        or repeat_through < 0
    ):
        raise ValueError(
            "Use increasing sizes >=2, known strategies/orders, positive limits and >=128 MiB"
        )
    if original and set(strategies) & set(original["metadata"]["strategies"]):
        raise ValueError("The baseline already contains a requested native strategy")
    output = output.resolve()
    settings = dict(
        sizes=sizes,
        timeout_seconds=timeout,
        memory_mib=memory_mib,
        strategies=list(strategies),
        orders=list(orders),
        small_trials=small_trials,
        repeat_through=repeat_through,
        seed=seed,
    )
    baseline_hash = (
        hashlib.sha256((baseline / "results.json").read_bytes()).hexdigest()
        if baseline
        else None
    )
    if output.exists():
        metadata = json.loads((output / "config.json").read_text())
        if (
            metadata["native_settings"] != settings
            or metadata["baseline_sha256"] != baseline_hash
        ):
            raise ValueError("Resume requires identical baseline and settings")
    else:
        output.mkdir(parents=True)
        if baseline:
            shutil.copytree(baseline / "source", output / "source")
        else:
            shutil.copytree(
                Path(__file__).parent,
                output / "source/balance_trees",
                ignore=shutil.ignore_patterns("__pycache__", "site"),
            )
        native_source = Path(__file__).resolve().parents[1] / "native"
        shutil.copytree(native_source, output / "source/native")
        for name in ("benchmark_native.py", "benchmark_comparison_report.py"):
            shutil.copyfile(Path(__file__).with_name(name), output / "source" / name)
        compiler = subprocess.run(
            ["c++", "--version"], capture_output=True, text=True, check=True
        )
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            platform.machine(),
        )
        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            **(original["metadata"] if original else settings),
            "strategies": [
                *(original["metadata"]["strategies"] if original else []),
                *strategies,
            ],
            "sizes": sorted(
                set(original["metadata"]["sizes"] if original else []) | set(sizes)
            ),
            "orders": list(
                dict.fromkeys(
                    [*(original["metadata"]["orders"] if original else []), *orders]
                )
            ),
            "native_settings": settings,
            "native_started_at": now,
            "baseline_sha256": baseline_hash,
            "compiler": compiler.stdout.splitlines()[0],
            "native_build": "CMake Release; C++20; sequential isolated workers; exact node reserve",
            "native_sampling": "Fixed input per order/size; SHA-256-derived rotation seeds consumed by buffered SplitMix64. Native strategies share seed values but consume different bit counts; Python MT streams are not paired.",
            "native_timing": "Insertion and aggregate counters only; input generation/parsing, node reservation, startup and final validation excluded. Sequential native workers on the same host; no Python timing comparison.",
            "native_source_sha256": {
                str(path.relative_to(output / "source")): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in sorted((output / "source/native").rglob("*"))
                if path.is_file()
            },
        }
        if not original:
            metadata.update(
                started_at=now,
                workers=1,
                python=sys.version,
                platform=platform.platform(),
                cpu=cpu,
                logical_cpus=os.cpu_count(),
                source_sha256={
                    str(path.relative_to(output / "source")): hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
                    for path in sorted((output / "source").rglob("*.py"))
                },
                execution="Sequential isolated C++ workers; Python generates inputs and orchestrates trials.",
                sampling=metadata["native_sampling"],
                metrics="Mean rotations/key, final mean node depth, maximum final height, logical random bits/key; native insertion seconds, ancestor visits and peak RSS. Root depth is zero.",
                limits="Per-worker address-space cap and wall deadline include insertion and final validation. A failed strategy/order stops its repeated and larger trials; these remain explicit not_run records.",
                validation="Every complete tree passes BST ordering, parent links, cycle detection, and exact input-key checks.",
                catalog={},
            )
        metadata["python_stop_reason"] = metadata.pop("global_stop_reason", None)
        native_catalog = {
            NATIVE: dict(
                name="C++ geometric repair",
                note="Fair-coin targets; 20-byte indexed node payload; buffered SplitMix64 bits.",
            ),
            BIASED_NATIVE: dict(
                name="C++ geometric repair · p=3/4",
                note="Exact Bernoulli(3/4) targets; same 20-byte indexed payload and local repair; at most two rotations.",
            ),
        }
        metadata["catalog"] = {
            **metadata["catalog"],
            **{name: native_catalog[name] for name in strategies},
        }
        records = (
            {record_key(row): row for row in original["trials"]} if original else {}
        )
        (output / "trials.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in records.values())
        )
        save_results(output, metadata, records)
    for module in ("sequences.py", "experiment.py"):
        expected = metadata["source_sha256"][f"balance_trees/{module}"]
        if (
            hashlib.sha256(Path(__file__).with_name(module).read_bytes()).hexdigest()
            != expected
        ):
            raise ValueError(
                "Input generator or seed derivation differs from source snapshot"
            )
    compiler = subprocess.run(
        ["c++", "--version"], capture_output=True, text=True, check=True
    )
    if compiler.stdout.splitlines()[0] != metadata["compiler"]:
        raise ValueError("Compiler differs from the recorded native run")
    for relative, digest in metadata["native_source_sha256"].items():
        if (
            hashlib.sha256((output / "source" / relative).read_bytes()).hexdigest()
            != digest
        ):
            raise ValueError("Archived native source differs from recorded checksum")
    build = output / "build"
    subprocess.run(
        [
            "cmake",
            "-S",
            str(output / "source/native"),
            "-B",
            str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_TESTING=OFF",
        ],
        check=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build), "--target", "native-benchmark", "-j2"],
        check=True,
    )
    records = {}
    for line in (output / "trials.jsonl").read_text().splitlines():
        row = json.loads(line)
        records[record_key(row)] = row
    started = perf_counter()
    for order in orders:
        stopped = {strategy: None for strategy in strategies}
        for n in sizes:
            count = small_trials if n <= repeat_through else 1
            input_path = output / "input.txt"
            input_digest = None
            order_seed = derived_seed(seed, "order", n)
            try:
                for trial in range(count):
                    for strategy in strategies:
                        request = dict(
                            strategy=strategy,
                            order=order,
                            n=n,
                            trial=trial,
                            seed=derived_seed(seed, "rotation", n, order, trial),
                            order_seed=order_seed,
                            memory_mib=memory_mib,
                        )
                        key = record_key(request)
                        if key in records:
                            if records[key]["status"] not in ("complete", "not_run"):
                                stopped[strategy] = f"{records[key]['status']} at n={n}"
                            continue
                        if stopped[strategy]:
                            row = {
                                **request,
                                "status": "not_run",
                                "metrics": {},
                                "detail": f"Skipped after {stopped[strategy]}",
                            }
                        else:
                            if input_digest is None:
                                input_digest = prepare_input(
                                    input_path, order, n, order_seed
                                )
                            row = execute_native_trial(
                                build / "native-benchmark", input_path, request, timeout
                            )
                            row["input_sha256"] = input_digest
                            if row["status"] != "complete":
                                stopped[strategy] = f"{row['status']} at n={n}"
                        records[key] = row
                        with (output / "trials.jsonl").open("a") as handle:
                            handle.write(json.dumps(row) + "\n")
                        save_results(output, metadata, records)
                        print(
                            f"{row['status']}: {strategy} {order} n={n:,} trial={trial}"
                            + (
                                f" insert={row['metrics']['elapsed_seconds']:.3f}s RSS={row['metrics']['peak_rss_mib']:.1f}MiB"
                                if row["status"] == "complete"
                                else ""
                            ),
                            flush=True,
                        )
            finally:
                input_path.unlink(missing_ok=True)
    metadata["native_finished_at"] = datetime.now(timezone.utc).isoformat()
    metadata["native_session_wall_seconds"] = perf_counter() - started
    return save_results(output, metadata, records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Optional saved Python comparison to preserve and extend",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+")
    parser.add_argument("--strategies", nargs="+", choices=NATIVE_STRATEGIES)
    parser.add_argument("--orders", nargs="+", choices=ORDERS)
    parser.add_argument("--small-trials", type=int, default=3)
    parser.add_argument("--repeat-through", type=int, default=65536)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--timeout", type=float, default=360)
    parser.add_argument("--memory-mib", type=int, default=768)
    args = parser.parse_args()
    run_native_comparison(
        args.baseline,
        args.output,
        sizes=args.sizes,
        timeout=args.timeout,
        memory_mib=args.memory_mib,
        strategies=tuple(args.strategies) if args.strategies is not None else None,
        orders=tuple(args.orders) if args.orders is not None else None,
        small_trials=args.small_trials,
        repeat_through=args.repeat_through,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
