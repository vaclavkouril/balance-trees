import json
import tempfile
import unittest
from pathlib import Path

from balance_trees.showcase.server import STATIC
from balance_trees.treap_comparison_report import DOWNLOADS, generate_report


class TreapComparisonReportTests(unittest.TestCase):
    def test_report_preserves_measurements_and_links_existing_pages_once(self):
        source = Path(__file__).resolve().parents[1] / "benchmarks/v2-treap"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "index.html").write_text(
                '<nav><a href="./results.html">Results</a></nav>'
            )
            marker = output / "results.html"
            marker.write_text("preserved report without navigation")
            generate_report(source, output)
            page = generate_report(source, output).read_text()
            self.assertEqual(
                (output / "index.html").read_text().count('href="./v2-treap.html"'), 1
            )
            self.assertEqual(marker.read_text(), "preserved report without navigation")
            self.assertIn("156", page)
            self.assertIn("2,097,152", page)
            for filename in DOWNLOADS:
                self.assertEqual(
                    (output / "v2-treap-results" / filename).read_bytes(),
                    (source / filename).read_bytes(),
                )
            for row in json.loads((source / "results.json").read_text())["summaries"]:
                self.assertIn(row["strategy"], page)

    def test_published_downloads_match_the_benchmark_artifacts(self):
        source = Path(__file__).resolve().parents[1] / "benchmarks/v2-treap"
        for filename in DOWNLOADS:
            self.assertEqual(
                (STATIC / "v2-treap-results" / filename).read_bytes(),
                (source / filename).read_bytes(),
            )
