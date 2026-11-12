import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from balance_trees.benchmark_comparison_report import METRICS, generate_report


class NativeComparisonReportTests(unittest.TestCase):
    def write_results(self, source, strategies):
        metadata = dict(
            sizes=[8, 16],
            strategies=strategies,
            orders=["increasing", "random"],
            small_trials=1,
            repeat_through=16,
            seed=2026,
            cpu="Test CPU",
            compiler="Test C++20 compiler",
            native_settings=dict(memory_mib=256, timeout_seconds=20),
            native_sampling="SplitMix64 with buffered fair bits.",
            native_timing="Insertion timing excludes validation.",
            catalog={
                "custom-native": dict(name="Custom native strategy"),
            },
        )
        trials, summaries = [], []
        for strategy in strategies:
            for order in metadata["orders"]:
                for size in metadata["sizes"]:
                    trials.append(
                        dict(
                            strategy=strategy,
                            order=order,
                            n=size,
                            trial=0,
                            status="complete",
                            metrics={},
                        )
                    )
                    summaries.append(
                        dict(
                            strategy=strategy,
                            order=order,
                            n=size,
                            status="complete",
                            completed_trials=1,
                            elapsed_seconds=0.001,
                            peak_rss_mib=10,
                            node_storage_bytes=size * 20,
                            **dict.fromkeys(METRICS, 2),
                        )
                    )
        source.mkdir()
        (source / "results.json").write_text(
            json.dumps(dict(metadata=metadata, trials=trials, summaries=summaries))
        )
        (source / "config.json").write_text(json.dumps(metadata))
        for filename in ("summary.csv", "trials.csv", "trials.jsonl"):
            (source / filename).write_text("")
        (source / "source").mkdir()

    def test_standalone_report_compares_both_cpp_strategies_and_links_proof(self):
        strategies = [
            "geometric-target-local-repair-native",
            "geometric-three-quarters-native",
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "run"
            self.write_results(source, strategies)
            report = generate_report(
                source,
                proof_href="../geometric-biased-repair.pdf?download=1&view=1",
                visualizer_href="../index.html",
            )
            text = report.read_text()
            self.assertIn("C++ geometric probability comparison", text)
            self.assertIn("C++ geometric repair · p = 3/4", text)
            self.assertIn("This standalone C++ run has 8 completed trials", text)
            self.assertIn("1</strong><span>C++ worker · 256 MiB", text)
            self.assertIn(
                'href="../geometric-biased-repair.pdf?download=1&amp;view=1"', text
            )
            self.assertNotIn("Python workers", text)
            self.assertNotIn("Mersenne Twister", text)
            self.assertNotIn("Stored treap depths", text)
            ns = {"svg": "http://www.w3.org/2000/svg"}
            for path in (report.parent / "figures").glob("*.svg"):
                svg = ElementTree.parse(path)
                circles = svg.findall("svg:circle", ns)
                self.assertEqual(len(circles), 4)
                self.assertEqual(len({dot.attrib["fill"] for dot in circles}), 2)
                self.assertIn("p = 3/4", "".join(svg.getroot().itertext()))
            ElementTree.parse(report.parent / "native-all-sequences.svg")

    def test_native_suffix_uses_catalog_for_additional_strategy_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "run"
            self.write_results(source, ["custom-native"])
            report = generate_report(source)
            self.assertIn("Custom native strategy", report.read_text())
            self.assertIn("This standalone C++ run", report.read_text())
            svg = (report.parent / "figures/native-random-mean_depth.svg").read_text()
            self.assertIn("Custom native strategy", svg)
            self.assertNotIn("proof (PDF)", report.read_text())
