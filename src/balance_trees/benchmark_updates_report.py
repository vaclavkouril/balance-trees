"""Build a portable, source-backed report of native mixed-update measurements."""

import argparse
import csv
import html
import json
import math
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

WORKLOADS = {
    "random-churn": (
        "Random churn",
        "Retire original keys in a seeded shuffled order and insert fresh keys "
        "in increasing order. The live set stays close to its starting size.",
    ),
    "ascending-churn": (
        "Ascending churn",
        "Delete the original keys in increasing order and insert increasing fresh "
        "keys. This keeps the live set close to its starting size.",
    ),
    "descending-churn": (
        "Descending churn",
        "Delete the original keys in decreasing order and insert decreasing fresh "
        "keys. This tests the reverse direction of the increasing refresh sweep.",
    ),
    "grow-shrink": (
        "Shrink and regrow",
        "Delete every original key, reaching an empty tree, then insert a new set "
        "of the same size. Extra checkpoints record the small-tree stages.",
    ),
    "read-heavy": (
        "Read-heavy churn",
        "Retire original keys in shuffled order and insert increasing fresh keys. "
        "Add eight lookups per replacement: four successful and four unsuccessful.",
    ),
}
COLORS = ("#176b89", "#b45f22", "#7153a0", "#237957", "#be4263")
# These values are computed for each trial before averaging across seeds.
METRICS = {
    "wall_us_per_operation": ("Wall time per public operation", "µs / operation"),
    "cpu_us_per_operation": ("CPU time per public operation", "µs / operation"),
    "height_ratio": ("Final height relative to live size", "height / log₂(n + 1)"),
    "mean_depth": ("Mean final node depth", "edges from the root"),
    "mean_insert_rotations": (
        "Rotations per public insertion",
        "rotations / insertion",
    ),
    "mean_delete_rotations": ("Rotations per public deletion", "rotations / deletion"),
    "peak_rss_mib": ("Peak resident memory", "MiB / worker process"),
}


def escape(value):
    return html.escape(str(value), quote=True)


def workload_label(workload):
    return WORKLOADS.get(workload, (workload, ""))[0]


def compact_count(value):
    """Use exact base-two units, with the unit convention stated on the page."""
    if value >= 2**20:
        return f"{value / 2**20:g}M"
    if value >= 2**10:
        return f"{value / 2**10:g}k"
    return f"{value:g}"


def measurement_values(trial):
    metrics = trial["metrics"]
    operations = metrics["operations"]
    if operations <= 0 or metrics["final_nodes"] < 0:
        raise ValueError("a complete trial must have operations and a valid final size")
    values = {name: metrics[name] for name in METRICS if name in metrics}
    values.update(
        wall_us_per_operation=metrics["elapsed_seconds"] * 1e6 / operations,
        cpu_us_per_operation=metrics["cpu_seconds"] * 1e6 / operations,
        height_ratio=(
            metrics["height"] / math.log2(metrics["final_nodes"] + 1)
            if metrics["final_nodes"]
            else 0.0
        ),
    )
    for name in METRICS:
        if name not in values or not math.isfinite(values[name]) or values[name] < 0:
            raise ValueError(f"complete trial has an invalid {name} measurement")
    return values


def summarize(results):
    """Missing trials stay missing; never substitute zero for a failed process."""
    groups = defaultdict(list)
    for trial in results["trials"]:
        if trial["status"] == "complete":
            groups[trial["workload"], trial["n"]].append(trial)
    summaries = []
    for (workload, size), trials in sorted(groups.items()):
        values = [measurement_values(trial) for trial in trials]
        row = dict(workload=workload, n=size, completed_trials=len(trials))
        for name in METRICS:
            samples = [value[name] for value in values]
            row[name] = statistics.mean(samples)
            row[name + "_sd"] = statistics.stdev(samples) if len(samples) > 1 else None
        row.update(
            operations_per_trial=trials[0]["metrics"]["operations"],
            final_nodes=trials[0]["metrics"]["final_nodes"],
            maximum_final_height=max(trial["metrics"]["height"] for trial in trials),
            sampled_max_height=max(
                trial["metrics"]["sampled_max_height"] for trial in trials
            ),
            max_insert_rotations=max(
                trial["metrics"]["max_insert_rotations"] for trial in trials
            ),
            max_delete_rotations=max(
                trial["metrics"]["max_delete_rotations"] for trial in trials
            ),
        )
        summaries.append(row)
    return summaries


def _svg_start(identity, title, description, height):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 {height}" '
        f'role="img" aria-labelledby="{identity}-title {identity}-desc">',
        f'<title id="{identity}-title">{escape(title)}</title>',
        f'<desc id="{identity}-desc">{escape(description)}</desc>',
        "<style>text{font:12px system-ui,sans-serif;fill:#314654}"
        ".grid{stroke:#e4e9e9}.muted{fill:#607482}</style>",
        f'<rect width="720" height="{height}" fill="white" rx="12"/>',
        f'<text x="24" y="31" style="font-size:18px;font-weight:650">{escape(title)}</text>',
    ]


def scaling_svg(results, summaries, metric):
    metadata = results["metadata"]
    workloads = metadata["workloads"]
    sizes = sorted(set(metadata["sizes"]))
    rows = {(row["workload"], row["n"]): row for row in summaries}
    title, unit = METRICS[metric]
    upper = max(
        (row[metric] + (row[metric + "_sd"] or 0) for row in summaries),
        default=1,
    )
    ymax = max(upper * 1.12, 0.1)
    left, top, width, height = 74, 77, 618, 234
    canvas_height = 398 + 23 * math.ceil(len(workloads) / 2)

    def x(size):
        if len(sizes) == 1:
            return left + width / 2
        return left + width * math.log2(size / sizes[0]) / math.log2(
            sizes[-1] / sizes[0]
        )

    def y(value):
        return top + height * (1 - value / ymax)

    parts = _svg_start(
        metric,
        title,
        "Horizontal axis: starting live keys, logarithmic scale. "
        f"Vertical axis: {unit}, linear scale. Each point averages completed "
        "trials; whiskers show one sample standard deviation when repeated "
        "seeds exist. Failed groups leave gaps, not zeros.",
        canvas_height,
    )
    parts.append(f'<text class="muted" x="24" y="53">{escape(unit)}</text>')
    for tick in range(6):
        value = ymax * tick / 5
        yy = y(value)
        parts.append(
            f'<path class="grid" d="M{left},{yy:.2f}h{width}"/>'
            f'<text x="{left - 10}" y="{yy + 4:.2f}" text-anchor="end">{value:.3g}</text>'
        )
    for index in sorted({round(i * (len(sizes) - 1) / 5) for i in range(6)}):
        size = sizes[index]
        xx = x(size)
        parts.append(
            f'<path class="grid" d="M{xx:.2f},{top}v{height}"/>'
            f'<text x="{xx:.2f}" y="333" text-anchor="middle">{compact_count(size)}</text>'
        )
    parts.append(
        '<text class="muted" x="74" y="355">Starting live keys '
        "(k = 1,024; M = 1,048,576) · whiskers ±1 SD</text>"
    )
    for index, workload in enumerate(workloads):
        color = COLORS[index % len(COLORS)]
        parts.append(f'<g data-series="{escape(workload)}">')
        previous = None
        for size in sizes:
            row = rows.get((workload, size))
            if row is None:
                previous = None
                continue
            xx, yy = x(size), y(row[metric])
            if previous is not None:
                parts.append(
                    f'<path d="M{previous[0]:.2f},{previous[1]:.2f}L{xx:.2f},{yy:.2f}" '
                    f'stroke="{color}" stroke-width="2.4" fill="none"/>'
                )
            deviation = row[metric + "_sd"]
            if deviation is not None:
                parts.append(
                    f'<path d="M{xx:.2f},{y(max(0, row[metric] - deviation)):.2f}'
                    f'V{y(row[metric] + deviation):.2f}" stroke="{color}"/>'
                )
            parts.append(
                f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="3.5" fill="{color}">'
                f"<title>{escape(workload_label(workload))}: n={size:,}; "
                f"{row[metric]:.6g} {escape(unit)}; {row['completed_trials']} "
                "completed trials</title></circle>"
            )
            previous = xx, yy
        lx, ly = 24 + index % 2 * 345, 388 + index // 2 * 23
        parts.append(
            f'<path d="M{lx},{ly}h21" stroke="{color}" stroke-width="3"/>'
            f'<text x="{lx + 28}" y="{ly + 4}">{escape(workload_label(workload))}</text></g>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def checkpoint_svg(trial):
    workload, size = trial["workload"], trial["n"]
    checkpoints = trial["metrics"]["checkpoints"]
    if not checkpoints:
        raise ValueError("a complete trial needs at least one checkpoint")
    operations = trial["metrics"]["operations"]
    title = f"{workload_label(workload)} · {compact_count(size)} starting keys"
    identity = "trace-" + workload
    parts = _svg_start(
        identity,
        title,
        "One recorded seed at this workload's largest completed size. Upper panel: "
        "live keys on a log2(n+1) scale. Lower panel: tree height at validation "
        "checkpoints, not after every operation. The empty tree has height -1 "
        "and is drawn at zero. Joining segments are guides between observations.",
        462,
    )
    parts.append(
        f'<text class="muted" x="24" y="53">Seed {trial["seed"]} · '
        f"{operations:,} public operations · checkpoint samples</text>"
    )
    left, width = 74, 618

    def x(done):
        return left + width * done / operations

    panels = (
        ("Live keys · log₂(n + 1) scale", 92, lambda point: math.log2(point["n"] + 1)),
        ("Tree height · edges", 270, lambda point: max(0, point["height"])),
    )
    for panel, (label, top, value_of) in enumerate(panels):
        height = 124
        upper = max(1, max(value_of(point) for point in checkpoints)) * 1.07

        def y(value, top=top, upper=upper):
            return top + height * (1 - value / upper)

        parts.append(f'<text x="24" y="{top - 12}">{escape(label)}</text>')
        if panel == 0:
            # Label actual power-of-two key counts instead of fractional counts
            # produced by equally spaced ticks in logarithm space.
            largest_size = max(point["n"] for point in checkpoints)
            power_step = max(1, math.ceil(math.log2(largest_size + 1) / 4))
            key_ticks = [0] + [
                2**power
                for power in range(power_step, largest_size.bit_length(), power_step)
            ]
            ticks = [(math.log2(size + 1), compact_count(size)) for size in key_ticks]
        else:
            ticks = [(upper * tick / 4, f"{upper * tick / 4:.0f}") for tick in range(5)]
        for value, label_value in ticks:
            yy = y(value)
            parts.append(
                f'<path class="grid" d="M{left},{yy:.2f}h{width}"/>'
                f'<text x="{left - 9}" y="{yy + 4:.2f}" text-anchor="end">{label_value}</text>'
            )
        coordinates = " ".join(
            f"{x(point['completed_ops']):.2f},{y(value_of(point)):.2f}"
            for point in checkpoints
        )
        color = "#176b89" if panel == 0 else "#b45f22"
        parts.append(
            f'<polyline points="{coordinates}" stroke="{color}" '
            'stroke-width="2.4" fill="none"/>'
        )
        for point in checkpoints:
            parts.append(
                f'<circle cx="{x(point["completed_ops"]):.2f}" '
                f'cy="{y(value_of(point)):.2f}" r="3" fill="{color}">'
                f"<title>After {point['completed_ops']:,} operations: "
                f"{point['n']:,} live keys; height {point['height']}; "
                f"mean depth {point['mean_depth']:.3f}</title></circle>"
            )
        for tick in range(5):
            xx = x(operations * tick / 4)
            parts.append(
                f'<text x="{xx:.2f}" y="{top + height + 21}" '
                f'text-anchor="middle">{tick * 25}%</text>'
            )
    parts.append(
        '<text class="muted" x="74" y="443">Progress through the measured public '
        "operations · preload excluded</text></svg>"
    )
    return "\n".join(parts)


def _write_csv(path, rows):
    columns = list(dict.fromkeys(column for row in rows for column in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _metric_cell(row, metric):
    value = f"{row[metric]:.3f}"
    deviation = row[metric + "_sd"]
    if deviation is not None:
        value += f" ± {deviation:.3f}"
    return f"<td>{value}</td>"


def _summary_table(rows):
    body = []
    for row in rows:
        body.append(
            f'<tr data-workload="{escape(row["workload"])}">'
            f'<th scope="row">{escape(workload_label(row["workload"]))}</th>'
            f"<td>{row['n']:,}</td><td>{row['completed_trials']}</td>"
            + _metric_cell(row, "wall_us_per_operation")
            + _metric_cell(row, "cpu_us_per_operation")
            + f"<td>{row['maximum_final_height']}</td>"
            + _metric_cell(row, "height_ratio")
            + f"<td>{row['sampled_max_height']}</td>"
            + _metric_cell(row, "mean_insert_rotations")
            + _metric_cell(row, "mean_delete_rotations")
            + f"<td>{row['max_delete_rotations']}</td>"
            + _metric_cell(row, "peak_rss_mib")
            + "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Workload</th><th>Starting keys</th>'
        "<th>Seeds</th><th>Wall µs/op</th><th>CPU µs/op</th><th>Max final H</th>"
        "<th>Mean H/log₂(n+1)</th><th>Sampled max H</th><th>Rotations/insert</th>"
        "<th>Rotations/delete</th><th>Max rotations/delete</th><th>Peak RSS MiB</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )


def _checkpoint_table(trial):
    rows = "".join(
        f"<tr><td>{point['completed_ops']:,}</td><td>{point['n']:,}</td>"
        f"<td>{point['height']}</td><td>{point['mean_depth']:.3f}</td></tr>"
        for point in trial["metrics"]["checkpoints"]
    )
    return (
        '<details><summary>Exact checkpoint measurements</summary><div class="table-wrap">'
        "<table><thead><tr><th>Public operations completed</th><th>Live keys</th>"
        "<th>Height</th><th>Mean depth</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></div></details>"
    )


STYLE = """
:root{color-scheme:light;--ink:#17313d;--muted:#526975;--line:#dce5e5;--accent:#176b89}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f6f5;color:var(--ink);font:16px/1.65 system-ui,sans-serif}
main{max-width:1460px;margin:auto;padding:28px 34px 64px}a{color:var(--accent);text-underline-offset:3px}nav{display:flex;flex-wrap:wrap;gap:8px 22px;font-size:13px}
header{max-width:960px;padding:36px 0 22px}.eyebrow{color:var(--accent);font-weight:700;font-size:12px;letter-spacing:.12em;text-transform:uppercase}
h1{font-size:clamp(36px,5vw,62px);line-height:1.06;letter-spacing:-2px;margin:12px 0 22px}h2{font-size:26px;line-height:1.25;margin:0 0 14px}h3{font-size:18px;margin:0 0 8px}
header p{font-size:18px;color:var(--muted)}section,.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:26px;margin:24px 0}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.stat{background:white;border:1px solid var(--line);border-top:3px solid var(--accent);border-radius:10px;padding:18px 20px}
.stat strong{display:block;font-size:30px;line-height:1.3;letter-spacing:-.5px}.stat span,.note{font-size:13px;color:var(--muted)}.lede{font-size:18px;max-width:1000px}.warning{border-left:4px solid #b45f22;padding:12px 18px;background:#fff8f0}
.charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}figure{margin:0;min-width:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:white}figure svg{display:block;width:100%;height:auto}figcaption{padding:0 20px 16px;font-size:12px;color:var(--muted)}
.table-wrap{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right}thead th{background:#eaf1f2;position:sticky;top:0;z-index:1}th:first-child,td:first-child{text-align:left}tbody th{font-weight:500}tbody tr:nth-child(even){background:#f8faf9}
.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:16px 0}label{font-weight:650}select{font:inherit;padding:8px 14px;border:1px solid #bfcfd1;border-radius:8px;background:white;color:var(--ink)}[hidden]{display:none!important}[data-dimmed=true]{opacity:.13}
.workloads{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.workloads article{padding:18px;border:1px solid var(--line);border-radius:10px}.workloads p{font-size:14px;margin:0;color:var(--muted)}.downloads{display:flex;flex-wrap:wrap;gap:12px}.downloads a{display:block;padding:10px 16px;border:1px solid var(--line);border-radius:8px;background:#f7faf9;text-decoration:none}.downloads a:hover{background:#eaf2f3}
details{margin:16px 0}summary{cursor:pointer;font-weight:650}pre{overflow:auto;font-size:12px;background:#f4f7f7;padding:18px;border-radius:8px;line-height:1.5}li+li{margin-top:8px}.method{columns:2;column-gap:40px}.method li{break-inside:avoid;margin-bottom:12px}.status-list{font-family:ui-monospace,monospace;font-size:12px}
footer{font-size:13px;color:var(--muted);padding-top:8px}@media(max-width:900px){main{padding:20px 16px 40px}.stats{grid-template-columns:repeat(2,1fr)}.charts{grid-template-columns:1fr}.workloads{grid-template-columns:1fr 1fr}.method{columns:1}section,.panel{padding:20px}h1{letter-spacing:-1px}}@media(max-width:520px){.workloads{grid-template-columns:1fr}.stat strong{font-size:24px}}
@media print{body{background:white}main{max-width:none;padding:0}.controls,nav,script{display:none}section{break-inside:avoid;border:0;padding:12px 0}figure{break-inside:avoid}.table-wrap{max-height:none;overflow:visible}table{font-size:8px}th,td{padding:4px}.charts{grid-template-columns:1fr 1fr}.method{columns:1}[data-dimmed=true]{opacity:1}}
"""


def generate_report(
    results_directory,
    output_directory,
    *,
    proof_path=None,
    insertion_href="../full-bst-insertion/index.html",
    visualizer_href="../../index.html",
):
    results_directory, output = Path(results_directory), Path(output_directory)
    results_path = results_directory / "results.json"
    results = json.loads(results_path.read_text())
    metadata, trials = results["metadata"], results["trials"]
    if not metadata["sizes"] or not metadata["workloads"]:
        raise ValueError("the report needs a nonempty size and workload schedule")
    if any(size < 1 for size in metadata["sizes"]):
        raise ValueError("starting sizes must be positive")
    summaries = summarize(results)
    output.mkdir(parents=True, exist_ok=False)
    figures = output / "figures"
    figures.mkdir()
    shutil.copyfile(results_path, output / "results.json")
    if (results_directory / "config.json").exists():
        shutil.copyfile(results_directory / "config.json", output / "config.json")
    _write_csv(output / "summary.csv", summaries)
    flat_trials = []
    for trial in trials:
        flat = {key: value for key, value in trial.items() if key != "metrics"}
        for key, value in trial.get("metrics", {}).items():
            if key != "checkpoints":
                flat[key] = value
        if trial["status"] == "complete":
            flat.update(measurement_values(trial))
        flat_trials.append(flat)
    _write_csv(output / "trials.csv", flat_trials)
    checkpoint_rows = [
        dict(
            workload=trial["workload"],
            starting_keys=trial["n"],
            trial=trial["trial"],
            seed=trial["seed"],
            order_seed=trial["order_seed"],
            completed_ops=point["completed_ops"],
            live_keys=point["n"],
            height=point["height"],
            mean_depth=point["mean_depth"],
        )
        for trial in trials
        if trial["status"] == "complete"
        for point in trial["metrics"]["checkpoints"]
    ]
    _write_csv(output / "checkpoints.csv", checkpoint_rows)
    with ZipFile(output / "source.zip", "w", compression=ZIP_DEFLATED) as archive:
        # Rendering may be refined after measurement; retain its final source
        # separately without altering the hashed benchmark snapshot.
        archive.write(Path(__file__), "render_report.py")
        source = results_directory / "source"
        if source.exists():
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, Path("source") / path.relative_to(source))
        for name in ("config.json", "README.txt", "reproduce.txt"):
            path = results_directory / name
            if path.exists():
                archive.write(path, name)
    proof_link = ""
    if proof_path is not None:
        shutil.copyfile(proof_path, output / "full-bst-explained.pdf")
        proof_link = '<a href="./full-bst-explained.pdf">Explained algorithm &amp; proof (PDF)</a>'

    statuses = Counter(trial["status"] for trial in trials)
    complete = [trial for trial in trials if trial["status"] == "complete"]
    largest = max((trial["n"] for trial in complete), default=0)
    total_operations = sum(trial["metrics"]["operations"] for trial in complete)
    largest_rows, traces = [], []
    for workload in metadata["workloads"]:
        matching = [row for row in summaries if row["workload"] == workload]
        if not matching:
            continue
        largest_rows.append(max(matching, key=lambda row: row["n"]))
        candidates = [trial for trial in complete if trial["workload"] == workload]
        selected = min(candidates, key=lambda trial: (-trial["n"], trial["trial"]))
        svg = checkpoint_svg(selected)
        filename = f"checkpoints-{workload}.svg"
        (figures / filename).write_text(svg)
        traces.append(
            f'<figure data-workload="{escape(workload)}">{svg}<figcaption>'
            "One seed; segments join observations and do not show intervening heights. "
            f'<a href="./figures/{filename}" download>Download SVG</a>'
            f"{_checkpoint_table(selected)}</figcaption></figure>"
        )
    charts = []
    for metric in METRICS:
        svg = scaling_svg(results, summaries, metric)
        filename = metric + ".svg"
        (figures / filename).write_text(svg)
        charts.append(
            f'<figure>{svg}<figcaption><a href="./figures/{filename}" download>'
            "Download SVG</a></figcaption></figure>"
        )

    failures = [trial for trial in trials if trial["status"] != "complete"]
    failure_rows = "".join(
        f'<tr data-workload="{escape(trial["workload"])}">'
        f'<th scope="row">{escape(workload_label(trial["workload"]))}</th>'
        f"<td>{trial['n']:,}</td><td>{trial['trial']}</td>"
        f"<td>{escape(trial['status'])}</td>"
        f"<td>{escape(trial.get('detail', trial.get('error', trial.get('reason', ''))))}</td></tr>"
        for trial in failures
    )
    failure_section = (
        "<section><h2>Incomplete or skipped measurements</h2>"
        "<p>These entries have no plotted measurement. A timeout or memory limit "
        "is a limit of this run and its validation overhead, not a proved algorithmic limit.</p>"
        '<div class="table-wrap"><table><thead><tr><th>Workload</th><th>Starting keys</th>'
        "<th>Trial</th><th>Status</th><th>Recorded reason</th></tr></thead><tbody>"
        + failure_rows
        + "</tbody></table></div></section>"
        if failures
        else ""
    )
    rotation_violations = [
        trial
        for trial in complete
        if trial["metrics"]["max_insert_rotations"] > 2
        or trial["metrics"]["max_delete_rotations"] > 4
    ]
    rotation_note = (
        f'<p class="warning">{len(rotation_violations)} completed trials exceed the '
        "specified rotation limits. Inspect the raw results before using these measurements.</p>"
        if rotation_violations
        else "<p>Every completed trial stayed within two rotations per public insertion "
        "and four per public deletion. The deletion totals include both internal refreshes.</p>"
        if complete
        else '<p class="warning">No trial completed. The report retains the recorded failures.</p>'
    )
    workload_cards = "".join(
        f'<article data-workload="{escape(workload)}"><h3>{escape(workload_label(workload))}</h3>'
        f"<p>{escape(WORKLOADS.get(workload, (workload, 'See recorded configuration.'))[1])}</p></article>"
        for workload in metadata["workloads"]
    )
    options = '<option value="all">All workloads</option>' + "".join(
        f'<option value="{escape(workload)}">{escape(workload_label(workload))}</option>'
        for workload in metadata["workloads"]
    )
    workers = metadata.get("workers", "recorded")
    parallel_note = metadata.get(
        "execution_note",
        metadata.get(
            "execution",
            f"Up to {workers} mixed-workload workers run concurrently. Other benchmark "
            "workers may share the machine; the recorded configuration gives the limits.",
        ),
    )
    cpu = metadata.get(
        "cpu", metadata.get("hardware", "See recorded environment below.")
    )
    compiler = metadata.get("compiler", "See recorded compiler below.")
    environment = f"{escape(cpu)} · {escape(compiler)}"
    downloads = (
        '<a href="./results.json" download>Raw results · JSON</a>'
        '<a href="./trials.csv" download>Individual trials · CSV</a>'
        '<a href="./summary.csv" download>Group means &amp; SD · CSV</a>'
        '<a href="./checkpoints.csv" download>Every checkpoint · CSV</a>'
        '<a href="./source.zip" download>Measured source &amp; configuration · ZIP</a>'
        + proof_link
    )
    notes = (
        "<li>The measured strategy is <code>geometric-full-bst</code>, with "
        "<em>p</em> = 3/4. A successful deletion that leaves keys refreshes two keys in sorted "
        "cursor order. A sweep wrap moves the minimum directly to the root; "
        "this pointer move is counted separately from rotations.</li>"
        "<li>Each trial starts with <em>n</em> live keys. Preloading, capacity "
        "reservation, operation generation and structural validation are outside "
        "the update timer. Internal refreshes, their searches and random trials, "
        "and operation-statistics accumulation are inside it.</li>"
        "<li>The four update-only workloads perform <em>n</em> deletions and "
        "<em>n</em> public insertions: 2<em>n</em> measured operations. Read-heavy "
        "churn adds 8<em>n</em> lookups, giving 10<em>n</em> operations. Its "
        "time-per-operation denominator therefore includes cheaper lookups; "
        "it is not a direct comparison of deletion speed.</li>"
        f"<li>{escape(parallel_note)} Wall time includes scheduling delays. "
        "Process CPU time excludes time waiting for the CPU, but both measurements "
        "can reflect shared memory and cache contention. These are concurrent-run "
        "measurements, not isolated throughput rankings.</li>"
        "<li>For repeated seeds, each chart point is the arithmetic mean and "
        "whiskers are ± one sample standard deviation. The table uses the same "
        "convention. A single seed has no variability estimate. Neither standard "
        "deviations nor these finite samples establish a high-probability theorem.</li>"
        "<li>Root depth is zero. Final mean depth averages all stored nodes. "
        "“Max final H” is the largest final height across the recorded seeds. "
        "“Sampled max H” is the largest height at the validation checkpoints, "
        "including the preloaded tree; it is not the maximum after every update.</li>"
        "<li>The height ratio uses the final live size: H/log₂(n + 1). Each trace "
        "shows live size and height together, including the empty stage during "
        "shrink and regrow. Empty-tree height is -1, drawn at zero in the trace. "
        "Lines between checkpoints are visual guides, not additional observations.</li>"
        "<li>Insert/delete rotation averages divide by the corresponding public "
        "operation counts. Refresh reinsertions are charged to deletion. Peak RSS "
        "covers the entire worker process, including input generation, preload "
        "and validation, so it is larger than node-array storage alone.</li>"
        "<li>Completed trials pass the worker's structural and key-set checks at "
        "the recorded checkpoints. Failed and skipped trials remain in the data "
        "and are never replaced by zeros. The source archive, seeds and recorded "
        "configuration make the workloads reproducible.</li>"
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Reproducible C++ mixed insert, delete and lookup benchmarks for a randomized binary search tree, with downloadable measurements and SVG graphs.">
<title>Full BST · mixed-update benchmarks</title><style>{STYLE}</style></head>
<body><main>
<nav aria-label="Report navigation"><a href="{escape(visualizer_href)}">Rotation Lab</a><a href="{escape(insertion_href)}">Full BST insertion benchmarks</a><a href="../geometric-native/index.html">Earlier C++ probability comparison</a><a href="#method">Method</a><a href="#downloads">Downloads</a></nav>
<header><div class="eyebrow">Rotation Lab / C++ measurements / p = 3/4</div><h1>Full BST:<br>insert, delete, search</h1><p>Mixed operations in the full randomized BST. See the time per operation, the shape of the tree, and its memory use as the live set grows, churns and shrinks.</p></header>
<div class="stats"><div class="stat"><strong>{largest:,}</strong><span>largest completed starting set</span></div><div class="stat"><strong>{total_operations:,}</strong><span>measured public operations</span></div><div class="stat"><strong>{statuses["complete"]:,}</strong><span>completed trials</span></div><div class="stat"><strong>{len(metadata["workloads"])}</strong><span>workload families</span></div></div>
<p class="note">{environment}</p>
<p class="note">Recorded outcomes: {escape(", ".join(f"{name}: {count}" for name, count in sorted(statuses.items())))}. Counts use k = 1,024 and M = 1,048,576; memory uses MiB.</p>
<section><h2>Read the measurements in context</h2>{rotation_note}<p class="note">{escape(parallel_note)} Compare timings within that execution context. The height and rotation observations describe these seeded workloads; the mathematical guarantee is a separate argument{"; see the explained proof in Downloads" if proof_path is not None else ""}.</p>
<div class="controls"><label for="workload-filter">Focus on a workload</label><select id="workload-filter">{options}</select><span class="note">Filters tables and traces; highlights its curves.</span></div><div class="workloads">{workload_cards}</div></section>
<section><h2>Largest completed size in each workload</h2><p class="note">Each row uses that workload's own largest completed size; check the starting-key count before comparing. Means show ± sample SD when repeated seeds exist. Maximum heights and rotation maxima are observed extrema, not means.</p>{_summary_table(largest_rows)}</section>
<section><h2>Scaling across starting sizes</h2><p class="note">Every point is measured. Curves stop or leave gaps where no trial completed. Large sizes with one seed have no error bar. Height is normalized by the final live size; the time charts divide by all public operations in that workload.</p><div class="charts">{"".join(charts)}</div></section>
<section><h2>Follow the tree through an update sequence</h2><p class="note">One recorded seed at each workload's largest completed size. The live-key panel uses a logarithmic scale so the small-tree portion of shrinking remains visible. Heights are sampled at checkpoints, not measured after every operation.</p><div class="charts">{"".join(traces)}</div></section>
{failure_section}
<section><h2>All completed measurement groups</h2><details><summary>Open the full table ({len(summaries)} groups)</summary>{_summary_table(summaries)}</details></section>
<section id="method"><h2>How the experiment was measured</h2><ul class="method">{notes}</ul><details><summary>Exact recorded environment and configuration</summary><pre>{escape(json.dumps(metadata, indent=2, sort_keys=True))}</pre></details></section>
<section id="downloads"><h2>Data, source and explanation</h2><p>Keep the individual trials when making comparisons. CSV summaries include the number of completed seeds and sample standard deviations; raw JSON retains checkpoint traces and all process outcomes.</p><div class="downloads">{downloads}</div></section>
<footer>Generated from recorded benchmark output. All graphs are portable SVGs; this page has no external scripts, fonts or chart-service dependencies.</footer>
</main><script>
document.getElementById('workload-filter').addEventListener('change',event=>{{
 const selected=event.target.value;
 for(const element of document.querySelectorAll('[data-workload]'))element.hidden=selected!=='all'&&element.dataset.workload!==selected;
 for(const element of document.querySelectorAll('[data-series]'))element.dataset.dimmed=String(selected!=='all'&&element.dataset.series!==selected);
}});
</script></body></html>
"""
    destination = output / "index.html"
    destination.write_text(page)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--insertion-href", default="../full-bst-insertion/index.html")
    parser.add_argument("--visualizer-href", default="../../index.html")
    args = parser.parse_args()
    print(
        generate_report(
            args.results,
            args.output,
            proof_path=args.proof,
            insertion_href=args.insertion_href,
            visualizer_href=args.visualizer_href,
        )
    )


if __name__ == "__main__":
    main()
