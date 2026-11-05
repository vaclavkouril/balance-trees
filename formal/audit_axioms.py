"""Reject unapproved axioms in the public, kernel-checked results."""

import re
import subprocess
import sys
from pathlib import Path

THEOREMS = (
    "rotateRight_inorder",
    "rotateLeft_inorder",
    "applyRotation_inorder",
    "runRotations_inorder",
    "local_repair_result",
    "local_repair_preserves_order",
    "local_repair_at_most_two_rotations",
    "repair_visits_exact",
    "total_bit_cost_exact",
    "sampledMove_bounded",
    "sampler_cost_from_move",
    "bitStrings_length",
    "sum_map_one",
    "sum_map_succ",
    "sampler_cost_sum",
    "sampler_exact_expected_bits_scaled",
    "applyAt_inorder",
    "local_repair_anywhere_preserves_order",
    "local_repair_anywhere_preserves_bst",
    "insertAtLeaf_inorder_length",
    "insertAtLeaf_key_count",
    "recursiveWalk_exact",
    "recursiveWalk_matches_counter",
    "sampled_target_false",
    "sampled_target_true_false",
    "sampled_target_true_true",
    "target_streams_partition",
    "target_stream_lengths",
    "top_stream_target",
    "second_stream_target",
    "lower_stream_target",
)
ALLOWED_AXIOMS = {"propext", "Quot.sound", "Classical.choice"}


def main() -> None:
    project = Path(__file__).resolve().parent
    commands = "import PathRepair\nimport TargetDistribution\n" + "".join(
        f"#print axioms GeometricRepair.{theorem}\n" for theorem in THEOREMS
    )
    result = subprocess.run(
        ["lake", "env", "lean", "--stdin"],
        cwd=project,
        input=commands,
        text=True,
        capture_output=True,
        check=True,
    )
    lines = result.stdout.splitlines()
    if len(lines) != len(THEOREMS):
        raise SystemExit(f"Unexpected Lean output: {result.stdout!r} {result.stderr!r}")
    for name, line in zip(THEOREMS, lines, strict=True):
        prefix = f"'GeometricRepair.{name}' "
        if not line.startswith(prefix):
            raise SystemExit(f"Unexpected audit result: {line}")
        detail = line.removeprefix(prefix)
        if detail == "does not depend on any axioms":
            axioms = set()
        else:
            match = re.fullmatch(r"depends on axioms: \[(.*)\]", detail)
            if match is None:
                raise SystemExit(f"Unrecognized audit result: {line}")
            axioms = set(match.group(1).split(", "))
        rejected = axioms - ALLOWED_AXIOMS
        if rejected:
            raise SystemExit(f"{name}: unapproved axioms {sorted(rejected)}")
        print(line)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stdout or "")
        sys.stderr.write(error.stderr or "")
        raise SystemExit(error.returncode) from error
