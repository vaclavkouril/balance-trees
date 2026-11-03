"""Publish the recorded random-level-v2 / treap comparison in the showcase."""

import argparse
import json
import shutil
from pathlib import Path

from .benchmark_report import esc, number

FILENAME = "v2-treap.html"
ASSETS = "v2-treap-results"
LINK = '<a href="./v2-treap.html">V2 vs treap · comparison</a>'
DOWNLOADS = (
    "comparison.svg",
    "summary.csv",
    "trials.csv",
    "results.json",
    "config.json",
)


def generate_report(source: Path, output: Path) -> Path:
    results = json.loads((source / "results.json").read_text())
    summaries, trials = results["summaries"], results["trials"]
    if not trials or any(row["status"] != "complete" for row in trials):
        raise ValueError("The comparison requires completed trials.")
    metadata = results["metadata"]
    sizes = metadata["sizes"]
    largest = max(sizes)
    reused = sum(row["source"] != "new parallel run" for row in trials)
    lookup = {(r["strategy"], r["order"], r["n"]): r for r in summaries}
    largest_rows = []
    for order in metadata["orders"]:
        cells = [f"<td>{esc(order.capitalize())}</td>"]
        for metric in ("mean_depth", "height", "mean_rotations"):
            for strategy in ("random-level-v2", "treap"):
                cells.append(
                    f"<td>{number(lookup[strategy, order, largest][metric])}</td>"
                )
        largest_rows.append("<tr>" + "".join(cells) + "</tr>")
    all_rows = []
    for row in sorted(summaries, key=lambda r: (r["order"], r["n"], r["strategy"])):
        cells = [
            esc(row["strategy"]),
            esc(row["order"]),
            f"{row['n']:,}",
            str(row["completed_trials"]),
        ]
        for metric in ("mean_depth", "height", "mean_rotations"):
            value = number(row[metric])
            if row.get(metric + "_se") is not None:
                value += " ± " + number(row[metric + "_se"])
            cells.append(value)
        all_rows.append(
            "<tr>" + "".join(f"<td>{value}</td>" for value in cells) + "</tr>"
        )
    downloads = "".join(
        f'<a href="./{ASSETS}/{name}" download>{esc(name)}</a>' for name in DOWNLOADS
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Random level v2 and stored-priority treap measurements across random, increasing and converging inputs, up to two million keys.">
<title>Random level v2 vs treap · Rotation Lab</title><link rel="stylesheet" href="./report.css"></head>
<body><main><nav aria-label="Lab pages"><a href="./index.html">← Tree preview</a><a href="#downloads">Downloads</a></nav>
<header><span class="eyebrow">Rotation Lab / recorded comparison</span><h1>Random level v2 vs treap</h1>
<p class="lede">Both strategies on random, increasing and converging inputs. Compare final mean node depth, final height and rotations per inserted key across every archived key count.</p></header>
<div class="stats"><div class="stat"><strong>{len(sizes)}</strong><span>sequence sizes</span></div><div class="stat"><strong>{largest:,}</strong><span>largest key count</span></div><div class="stat"><strong>{len(trials)}</strong><span>completed trials</span></div><div class="stat"><strong>{reused}</strong><span>archived v2 trials reused</span></div></div>
<section aria-labelledby="comparison-title"><h2 id="comparison-title">Three metrics, all six series</h2>
<p>Color identifies the input order; solid lines show v2 and dashed lines show treap. Key counts use a logarithmic scale. Depth and height count edges from a root at depth zero.</p>
<figure class="chart"><img src="./{ASSETS}/comparison.svg" alt="Three panels overlay random level v2 and treap for random, increasing and converging inputs: final mean node depth, final height and rotations per key."><a href="./{ASSETS}/comparison.svg" download>Download combined SVG</a></figure>
<p class="status-note">Mean depth averages node depths in the final tree. Final height is the maximum node depth. Three paired trials at 1,000, 16,000 and 128,000 keys; one paired trial at other sizes. Whiskers show ±1 standard error where available.</p></section>
<section><h2>At {largest:,} keys</h2><p>V2 uses fewer rotations on random and converging input. Its converging tree finishes substantially taller. These largest-size measurements use one trial per strategy and input.</p>
<div class="table-wrap"><table><thead><tr><th rowspan="2" scope="col">Input</th><th colspan="2" scope="colgroup">Mean depth</th><th colspan="2" scope="colgroup">Final height</th><th colspan="2" scope="colgroup">Rotations / key</th></tr><tr><th>V2</th><th>Treap</th><th>V2</th><th>Treap</th><th>V2</th><th>Treap</th></tr></thead><tbody>{"".join(largest_rows)}</tbody></table></div></section>
<section><h2>Method and interpretation</h2><ul>
<li>All {len(sizes)} existing key counts, from {min(sizes):,} to {largest:,}, for the three named insertion families. Inputs and rotation seeds are paired using the existing benchmark's seed derivation.</li>
<li>{reused} matching archived v2 trials are reused. The {len(trials) - reused} missing trials ran in four worker processes. This report compares tree shape and operation counts; it makes no elapsed-time comparison.</li>
<li>Treap uses the existing Python visualizer's stored 32-bit random priorities, a min-heap and key-based tie breaking. It is a separate reference from the hash-priority strategy.</li>
<li>Every fresh tree passed ordering, parent-pointer, cycle and complete-key-set checks. Treap depths also matched an independently reconstructed Cartesian tree.</li>
<li>One trial gives no uncertainty estimate. Three-trial standard errors describe variation over balancing seeds conditional on the fixed input. These finite measurements do not prove a balance or complexity guarantee.</li>
</ul><p>V2 chooses a repair level from a fresh 64-bit roll and the previous priority interval. Ordinary insertions repair a local path with at most two rotations; a strict new minimum promotes the inserted leaf to the root. The policy has no established logarithmic-depth guarantee.</p></section>
<details class="panel"><summary>All {len(summaries)} measurement groups</summary><div class="table-wrap"><table><thead><tr><th>Strategy</th><th>Input</th><th>Keys</th><th>Trials</th><th>Mean depth ± SE</th><th>Final height ± SE</th><th>Rotations / key ± SE</th></tr></thead><tbody>{"".join(all_rows)}</tbody></table></div></details>
<section id="downloads"><h2>Recorded data and graph</h2><div class="downloads">{downloads}</div><p class="meta">Raw trials include seeds and record provenance. Configuration includes the source archive checksum and execution method.</p></section>
</main></body></html>"""
    assets = output / ASSETS
    assets.mkdir(parents=True, exist_ok=True)
    for name in DOWNLOADS:
        shutil.copyfile(source / name, assets / name)
    destination = output / FILENAME
    destination.write_text(page, encoding="utf-8")
    preview = output / "index.html"
    if preview.exists():
        preview_html = preview.read_text(encoding="utf-8")
        if 'href="./v2-treap.html"' not in preview_html:
            preview.write_text(
                preview_html.replace("</nav>", LINK + "</nav>", 1), encoding="utf-8"
            )
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("benchmarks/v2-treap"))
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).parent / "showcase/site/dist"
    )
    args = parser.parse_args()
    print(generate_report(args.input, args.output))


if __name__ == "__main__":
    main()
