"""Append reproducible native geometric measurements to a saved Python run."""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .benchmark_parallel import record_key, save_results
from .experiment import derived_seed
from .sequences import insertion_order

NATIVE = "geometric-target-local-repair-native"


def run_native_comparison(
    baseline: Path,
    output: Path,
    *,
    sizes: list[int] | None = None,
    timeout: float = 360,
    memory_mib: int = 768,
) -> dict:
    original = json.loads((baseline / "results.json").read_text())
    sizes = original["metadata"]["sizes"] if sizes is None else sizes
    if (
        not sizes
        or sizes != sorted(set(sizes))
        or min(sizes) < 2
        or max(sizes) >= 2**32
        or not 0 < timeout < float("inf")
        or memory_mib < 128
    ):
        raise ValueError("Use increasing sizes >=2, positive timeout and >=128 MiB")
    output = output.resolve()
    settings = dict(sizes=sizes, timeout_seconds=timeout, memory_mib=memory_mib)
    baseline_hash = hashlib.sha256((baseline / "results.json").read_bytes()).hexdigest()
    if output.exists():
        metadata = json.loads((output / "config.json").read_text())
        if (
            metadata["native_settings"] != settings
            or metadata["baseline_sha256"] != baseline_hash
        ):
            raise ValueError("Resume requires identical baseline and settings")
    else:
        output.mkdir(parents=True)
        shutil.copytree(baseline / "source", output / "source")
        native_source = Path(__file__).resolve().parents[1] / "native"
        shutil.copytree(native_source, output / "source/native")
        # Archive the runner and renderer actually used for this extension too.
        for name in ("benchmark_native.py", "benchmark_comparison_report.py"):
            shutil.copyfile(Path(__file__).with_name(name), output / "source" / name)
        compiler = subprocess.run(
            ["c++", "--version"], capture_output=True, text=True, check=True
        )
        metadata = {
            **original["metadata"],
            "strategies": [*original["metadata"]["strategies"], NATIVE],
            "sizes": sorted(set(original["metadata"]["sizes"]) | set(sizes)),
            "native_settings": settings,
            "native_started_at": datetime.now(timezone.utc).isoformat(),
            "baseline_sha256": baseline_hash,
            "compiler": compiler.stdout.splitlines()[0],
            "native_build": "CMake Release; C++20; sequential isolated workers; exact node reserve",
            "native_sampling": "Original input generator and order seeds; original 64-bit rotation seed values, consumed by SplitMix64 rather than Python MT. Streams are not paired.",
            "native_timing": "Insertion and aggregate counters only; input generation/parsing, node reservation, startup and final validation excluded. No Python timing comparison is available in the baseline.",
            "native_source_sha256": {
                str(path.relative_to(output / "source")): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in sorted((output / "source/native").rglob("*"))
                if path.is_file()
            },
        }
        # The old shared-validator stop applies only to the original Python run.
        metadata["python_stop_reason"] = metadata.pop("global_stop_reason", None)
        metadata["catalog"] = {
            **metadata["catalog"],
            NATIVE: dict(
                name="C++ geometric repair",
                note="20-byte indexed node payload; buffered SplitMix64 bits; no rotation trace allocation.",
            ),
        }
        records = {record_key(row): row for row in original["trials"]}
        (output / "trials.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in records.values())
        )
        save_results(output, metadata, records)
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
    # Use the exact input generator from the archived Python experiment.
    expected = original["metadata"]["source_sha256"]["balance_trees/sequences.py"]
    if (
        hashlib.sha256(
            Path(__file__).with_name("sequences.py").read_bytes()
        ).hexdigest()
        != expected
    ):
        raise ValueError("Input generator differs from baseline source snapshot")
    started = perf_counter()
    for order in metadata["orders"]:
        stopped = False
        for n in sizes:
            count = metadata["small_trials"] if n <= metadata["repeat_through"] else 1
            input_path = output / "input.txt"
            prepared = False
            try:
                for trial in range(count):
                    request = dict(
                        strategy=NATIVE,
                        order=order,
                        n=n,
                        trial=trial,
                        seed=derived_seed(
                            metadata["seed"], "rotation", n, order, trial
                        ),
                        order_seed=derived_seed(metadata["seed"], "order", n),
                        memory_mib=memory_mib,
                    )
                    key = record_key(request)
                    if key in records:
                        stopped |= records[key]["status"] != "complete"
                        continue
                    row = {**request, "status": "not_run", "metrics": {}}
                    if not stopped:
                        if not prepared:
                            values = insertion_order(order, n, request["order_seed"])
                            digest = hashlib.sha256()
                            with input_path.open("wb") as handle:
                                for offset in range(0, n, 8192):
                                    chunk = (
                                        " ".join(
                                            map(str, values[offset : offset + 8192])
                                        )
                                        + "\n"
                                    ).encode()
                                    handle.write(chunk)
                                    digest.update(chunk)
                            del values
                            prepared = True
                        row["input_sha256"] = digest.hexdigest()
                        try:
                            with input_path.open() as handle:
                                process = subprocess.run(
                                    [
                                        str(build / "native-benchmark"),
                                        str(request["seed"]),
                                        str(n),
                                        str(memory_mib),
                                    ],
                                    stdin=handle,
                                    capture_output=True,
                                    text=True,
                                    timeout=timeout,
                                )
                            if process.returncode == 0:
                                row.update(
                                    status="complete",
                                    metrics=json.loads(process.stdout),
                                )
                            else:
                                row.update(
                                    status="memory_limit"
                                    if "memory_limit" in process.stderr
                                    else "error",
                                    detail=process.stderr[-2000:],
                                )
                        except subprocess.TimeoutExpired:
                            row.update(
                                status="timeout", detail=f"Exceeded {timeout:g} s"
                            )
                        stopped = row["status"] != "complete"
                    records[key] = row
                    with (output / "trials.jsonl").open("a") as handle:
                        handle.write(json.dumps(row) + "\n")
                    save_results(output, metadata, records)
                    print(
                        f"{row['status']}: C++ {order} n={n:,} trial={trial}"
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
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+")
    parser.add_argument("--timeout", type=float, default=360)
    parser.add_argument("--memory-mib", type=int, default=768)
    args = parser.parse_args()
    run_native_comparison(
        args.baseline,
        args.output,
        sizes=args.sizes,
        timeout=args.timeout,
        memory_mib=args.memory_mib,
    )


if __name__ == "__main__":
    main()
