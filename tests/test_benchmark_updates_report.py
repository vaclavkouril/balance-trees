import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from balance_trees.benchmark_updates_report import (
    METRICS,
    checkpoint_svg,
    generate_report,
    scaling_svg,
    summarize,
)


def completed_trial(workload, size, trial=0, wall_us=1):
    operations = size * 2
    return dict(
        workload=workload,
        n=size,
        trial=trial,
        seed=2026 + trial,
        order_seed=500 + trial,
        status="complete",
        metrics=dict(
            operations=operations,
            elapsed_seconds=wall_us * operations / 1e6,
            cpu_seconds=operations / 2e6,
            final_nodes=size,
            height=5,
            mean_depth=3.2,
            sampled_max_height=7,
            mean_insert_rotations=0.4,
            mean_delete_rotations=0.8,
            max_insert_rotations=2,
            max_delete_rotations=4,
            peak_rss_mib=10.0,
            checkpoints=[
                dict(completed_ops=0, n=size, height=5, mean_depth=3.2),
                dict(completed_ops=size, n=0, height=-1, mean_depth=0),
                dict(completed_ops=operations, n=size, height=5, mean_depth=3.2),
            ],
        ),
    )


def sample_results():
    return dict(
        metadata=dict(
            sizes=[8, 16, 32],
            workloads=["random-churn", "grow-shrink"],
            workers=2,
            cpu="Example CPU <script>bad()</script>",
            compiler="Example C++20",
        ),
        trials=[
            completed_trial("random-churn", 8, wall_us=1),
            completed_trial("random-churn", 8, trial=1, wall_us=3),
            dict(
                workload="random-churn",
                n=16,
                trial=0,
                seed=2026,
                order_seed=500,
                status="timeout",
                error="Worker exceeded <10 seconds>",
            ),
            completed_trial("random-churn", 32, wall_us=4),
            completed_trial("grow-shrink", 32, wall_us=2),
        ],
    )


class MixedUpdateReportTests(unittest.TestCase):
    def test_summaries_use_complete_trials_and_sample_standard_deviation(self):
        rows = summarize(sample_results())
        self.assertEqual(len(rows), 3)
        small = next(row for row in rows if row["n"] == 8)
        self.assertEqual(small["completed_trials"], 2)
        self.assertEqual(small["wall_us_per_operation"], 2)
        self.assertAlmostEqual(small["wall_us_per_operation_sd"], math.sqrt(2))
        self.assertAlmostEqual(small["height_ratio"], 5 / math.log2(9))
        self.assertEqual(small["maximum_final_height"], 5)
        self.assertEqual(small["sampled_max_height"], 7)
        self.assertTrue(
            all(
                row["wall_us_per_operation_sd"] is None
                for row in rows
                if row["n"] == 32
            )
        )
        self.assertFalse(any(row["n"] == 16 for row in rows))

    def test_failed_group_leaves_a_gap_in_scaling_curve(self):
        results = sample_results()
        svg = ElementTree.fromstring(
            scaling_svg(results, summarize(results), "wall_us_per_operation")
        )
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        series = svg.find("svg:g[@data-series='random-churn']", namespace)
        self.assertEqual(len(series.findall("svg:circle", namespace)), 2)
        # There must be no segment joining the complete 8- and 32-key points.
        self.assertFalse(
            any(
                "L" in path.attrib["d"]
                for path in series.findall("svg:path", namespace)
            )
        )
        self.assertIn("Failed groups leave gaps", "".join(svg.itertext()))

    def test_checkpoint_trace_retains_the_empty_tree_and_seed(self):
        trial = completed_trial("grow-shrink", 32, trial=4)
        svg = ElementTree.fromstring(checkpoint_svg(trial))
        text = "".join(svg.itertext())
        self.assertIn("Seed 2030", text)
        self.assertIn("0 live keys; height -1", text)
        self.assertIn("not after every operation", text)
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        self.assertEqual(len(svg.findall("svg:polyline", namespace)), 2)

    def test_report_preserves_raw_data_and_exports_source_and_portable_figures(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, output = base / "run", base / "report"
            source.mkdir()
            (source / "source").mkdir()
            (source / "source" / "worker.cpp").write_text("// measured worker\n")
            results = sample_results()
            (source / "results.json").write_text(json.dumps(results))
            (source / "config.json").write_text('{"seed":2026}')
            proof = base / "proof.pdf"
            proof.write_bytes(b"%PDF-fixture")
            page = generate_report(source, output, proof_path=proof)
            text = page.read_text()
            self.assertIn("4</strong><span>completed trials", text)
            self.assertIn("not isolated throughput rankings", text)
            self.assertIn("Sampled max H", text)
            self.assertIn("Worker exceeded &lt;10 seconds&gt;", text)
            self.assertIn("Example CPU &lt;script&gt;bad()&lt;/script&gt;", text)
            self.assertNotIn("<script>bad()", text)
            self.assertEqual(json.loads((output / "results.json").read_text()), results)
            self.assertEqual(
                (output / "full-bst-explained.pdf").read_bytes(), proof.read_bytes()
            )
            with ZipFile(output / "source.zip") as archive:
                self.assertEqual(
                    archive.read("source/worker.cpp"), b"// measured worker\n"
                )
                self.assertIn("config.json", archive.namelist())
                self.assertIn("render_report.py", archive.namelist())
            figures = list((output / "figures").glob("*.svg"))
            self.assertEqual(len(figures), len(METRICS) + 2)
            for path in figures:
                ElementTree.parse(path)
                self.assertIn(f'href="./figures/{path.name}"', text)
            with (output / "trials.csv").open() as stream:
                trials = list(csv.DictReader(stream))
            failed = next(row for row in trials if row["status"] == "timeout")
            self.assertEqual(failed["wall_us_per_operation"], "")
            with (output / "checkpoints.csv").open() as stream:
                checkpoints = list(csv.DictReader(stream))
            self.assertEqual(len(checkpoints), 12)
            empty = next(row for row in checkpoints if row["live_keys"] == "0")
            self.assertEqual(empty["height"], "-1")
            self.assertIn("Exact checkpoint measurements", text)
            with (output / "summary.csv").open() as stream:
                summaries = list(csv.DictReader(stream))
            self.assertEqual(len(summaries), 3)
            self.assertFalse(any(row["n"] == "16" for row in summaries))
            with self.assertRaises(FileExistsError):
                generate_report(source, output)

    def test_all_failed_report_does_not_claim_rotation_checks_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "run"
            source.mkdir()
            results = sample_results()
            results["trials"] = [results["trials"][2]]
            (source / "results.json").write_text(json.dumps(results))
            text = generate_report(source, base / "report").read_text()
            self.assertIn("No trial completed", text)
            self.assertNotIn("Every completed trial stayed", text)

    def test_invalid_complete_measurement_fails_before_creating_report(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "run"
            source.mkdir()
            results = sample_results()
            results["trials"][0]["metrics"]["cpu_seconds"] = -1
            (source / "results.json").write_text(json.dumps(results))
            with self.assertRaisesRegex(ValueError, "cpu_us_per_operation"):
                generate_report(source, base / "report")
            self.assertFalse((base / "report").exists())

    def test_recorded_execution_and_failure_detail_are_displayed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "run"
            source.mkdir()
            results = sample_results()
            results["metadata"]["execution"] = (
                "Two mixed workers and two insertion workers."
            )
            results["trials"][2]["detail"] = "Detailed timeout reason."
            (source / "results.json").write_text(json.dumps(results))
            text = generate_report(source, base / "report").read_text()
            self.assertIn("Detailed timeout reason.", text)
            self.assertIn("Two mixed workers and two insertion workers.", text)


if __name__ == "__main__":
    unittest.main()
