"""Shared build, environment and checkpoint helpers for benchmark runners."""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def machine_metadata() -> dict:
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        platform.machine(),
    )
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
    }


def compiler_version() -> str:
    compiler = subprocess.run(
        ["c++", "--version"], capture_output=True, text=True, check=True
    )
    return compiler.stdout.splitlines()[0]


def build_native_worker(source: Path, build: Path, target: str) -> Path:
    """Build a Release worker from the frozen source, retaining diagnostics."""
    commands = (
        [
            "cmake",
            "-S",
            str(source),
            "-B",
            str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_TESTING=OFF",
        ],
        ["cmake", "--build", str(build), "--target", target, "-j2"],
    )
    with (build.parent / "build.log").open("w") as log:
        for command in commands:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    return build / target


def write_json(path: Path, value: dict) -> None:
    """Replace a checkpoint only after its complete JSON has been written."""
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)
