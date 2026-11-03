import csv
import math
import runpy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from balance_trees.flavors import TreeFlavor
from balance_trees.insertion_depth_by_time import (
    measure_insertion_depth_by_time,
    write_results,
)
from balance_trees.insertion_depth_compare import build_svg as compare_svg
from balance_trees.insertion_depth_compare import measure_size
from balance_trees.insertion_depth_trace import (
    build_svg,
    rolling_mean,
    trace_insertions,
)
from balance_trees.sequences import insertion_order
from balance_trees.worst_case import linear_sizes, rotations_svg, worst_case


class AnalysisToolTests(unittest.TestCase):
    def test_time_resolved_depth_matches_independent_runs_and_accepts_one_key(self):
        expected = [0] * 16
        for seed in (17, 18):
            tree = TreeFlavor.create("random-level-v2-1", seed=seed)
            for i, key in enumerate(insertion_order("random", 16, seed)):
                expected[i] += tree.insert(key).insertion_depth / 2
        self.assertEqual(measure_insertion_depth_by_time(16, 2, seed=17), expected)
        with tempfile.TemporaryDirectory() as temporary:
            csv_path, svg_path = (
                Path(temporary) / "depth.csv",
                Path(temporary) / "depth.svg",
            )
            write_results(measure_insertion_depth_by_time(1, 2), csv_path, svg_path)
            ElementTree.parse(svg_path)
            with csv_path.open() as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)

    def test_trace_height_uses_actual_sample_insertion_indices(self):
        records, samples = trace_insertions(
            strategy="none",
            order="increasing",
            size=9,
            seed=17,
            window=2,
            sample_count=3,
        )
        depths = [r["depth"] for r in records]
        svg = build_svg(
            depths,
            rolling_mean(depths, 2),
            samples,
            strategy="none",
            order="increasing",
            seed=17,
            window=2,
        )
        root = ElementTree.fromstring(svg)
        height = next(p for p in root.iter() if p.attrib.get("stroke") == "#dc2626")
        self.assertIn("L1028.00,", height.attrib["d"])
        self.assertEqual(samples[-1]["insertion"], 9)

    def test_worst_rotation_metric_and_seed_provenance_render_at_one_size(self):
        averages, worst = worst_case(
            strategy="none",
            order="increasing",
            size=8,
            runs=2,
            seed=17,
            seeds_per_run=2,
        )
        self.assertEqual(worst["worst_mean_rotations"], 0)
        self.assertEqual(worst["worst_height"], 7)
        self.assertEqual([r["seed"] for r in averages], [17, 19])
        self.assertTrue(all(r["size"] == 8 for r in averages))
        ElementTree.fromstring(
            rotations_svg([worst], strategy="none", order="increasing")
        )
        self.assertEqual(linear_sizes(8, 8, 2), [8])

    def test_size_comparison_renders_one_size_and_v3_report_handles_one_trial(self):
        row = measure_size(strategy="random-level-v2-1", size=8, trials=1, seed=17)
        self.assertEqual(row["two_ln_n"], 2 * math.log(8))
        ElementTree.fromstring(compare_svg([row], strategy="random-level-v2-1"))
        script = Path(__file__).resolve().parents[1] / "benchmarks/run_v3_report.py"
        chart = runpy.run_path(str(script))["chart"]
        svg = chart(
            [dict(n=8, status="complete", height=4, height_se=None)],
            "height",
            "Height",
            True,
        )
        ElementTree.fromstring(svg)
