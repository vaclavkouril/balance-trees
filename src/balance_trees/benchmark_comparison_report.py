"""Render the parallel target-strategy comparison as portable HTML and SVG."""

import argparse
import html
import json
import math
import shutil
from collections import Counter
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

LABELS = {
    "geometric-target-local-repair": "Geometric repair",
    "geometric-target-local-repair-alternate": "Geometric repair · alternate",
    "interval-target-local-repair": "Interval repair",
    "random-level": "Random level · leaf promotion",
    "treap": "Stored-priority treap",
    "geometric-target-local-repair-native": "C++ geometric repair",
    "geometric-three-quarters-native": "C++ geometric repair · p = 3/4",
}
COLORS = (
    "#2563eb",
    "#9333ea",
    "#059669",
    "#d97706",
    "#dc2626",
    "#0891b2",
    "#be185d",
    "#475569",
)
METRICS = {
    "mean_rotations": "Mean rotations / key",
    "maximum_height": "Maximum final height · edges",
    "mean_depth": "Mean final node depth · edges",
    "mean_random_bits": "Mean random bits / key",
}


def escaped(value):
    return html.escape(str(value), quote=True)


def formatted(value, metric):
    return f"{value:,.0f}" if metric == "maximum_height" else f"{value:.3f}"


def strategy_label(metadata: dict, strategy: str) -> str:
    return LABELS.get(
        strategy, metadata.get("catalog", {}).get(strategy, {}).get("name", strategy)
    )


def chart_height(strategies: list[str]) -> int:
    return max(425, 359 + math.ceil(len(strategies) / 2) * 22 + 22)


def log_reference_constant(results: dict, order: str, metric: str) -> float:
    """Align the guide with the largest measured endpoint ratio, never below 1."""
    endpoints = {}
    for row in results["summaries"]:
        if row["order"] != order or row["status"] != "complete":
            continue
        previous = endpoints.get(row["strategy"])
        if previous is None or row["n"] > previous["n"]:
            endpoints[row["strategy"]] = row
    return (
        max(1.0, *(row[metric] / math.log2(row["n"]) for row in endpoints.values()))
        if endpoints
        else 1.0
    )


def chart_svg(results: dict, order: str, metric: str) -> str:
    metadata = results["metadata"]
    attempted_sizes = [
        row["n"] for row in results["trials"] if row["status"] != "not_run"
    ]
    attempted_ceiling = max(attempted_sizes, default=metadata["sizes"][0])
    sizes = [size for size in metadata["sizes"] if size <= attempted_ceiling]
    groups = {
        (row["strategy"], row["n"]): row
        for row in results["summaries"]
        if row["order"] == order and row["status"] == "complete"
    }
    upper = max(
        (row[metric] + (row.get(metric + "_se") or 0) for row in groups.values()),
        default=1,
    )
    show_log_reference = metric in ("maximum_height", "mean_depth", "mean_random_bits")
    constant = log_reference_constant(results, order, metric)
    guide_label = f"{constant:.3g}·log₂(n) · endpoint guide"
    if show_log_reference:
        upper = max(upper, constant * math.log2(sizes[-1]))
    ymax = max(1, upper) * 1.12
    left, top, width, height = 70, 66, 620, 226
    title = f"{order.capitalize()} · {METRICS[metric]}"
    identity = order + "-" + metric
    reference_description = (
        f" Dashed gray line: {guide_label}. c=max(1, largest endpoint value/log₂(n) across implementations). Descriptive scaling, not a proven bound."
        if show_log_reference
        else ""
    )

    def x(size):
        return left + width * math.log(size / sizes[0]) / max(
            1, math.log(sizes[-1] / sizes[0])
        )

    def y(value):
        return top + height * (1 - value / ymax)

    canvas_height = chart_height(metadata["strategies"])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 {canvas_height}" role="img" aria-labelledby="{identity}-title {identity}-desc">',
        f'<title id="{identity}-title">{escaped(title)}</title>',
        f'<desc id="{identity}-desc">Measurements for {len(metadata["strategies"])} implementations. Logarithmic key counts and linear vertical scale. Only complete groups are plotted; missing or censored groups leave gaps. Whiskers show one standard error for averages when repeated trials exist. Maximum final height is the maximum observed across those trials.{reference_description}</desc>',
        "<style>text{font:12px system-ui,sans-serif;fill:#334155}.grid{stroke:#e2e8f0}</style>",
        f'<rect width="720" height="{canvas_height}" rx="12" fill="white"/>',
        f'<text x="22" y="28" style="font-size:17px;font-weight:650">{escaped(title)}</text>',
        f'<text x="22" y="48" style="font-size:11px;fill:#64748b">{len(metadata["strategies"])} implementations · source and seeds recorded · no timing comparison</text>',
    ]
    for tick in range(6):
        value = ymax * tick / 5
        yy = y(value)
        parts.append(
            f'<path class="grid" d="M{left},{yy:.2f}h{width}"/><text x="{left - 9}" y="{yy + 4:.2f}" text-anchor="end">{value:.3g}</text>'
        )
    indices = sorted({round(i * (len(sizes) - 1) / 5) for i in range(6)})
    for index in indices:
        size = sizes[index]
        xx = x(size)
        label = f"{size / 1048576:g}M" if size >= 1048576 else f"{size / 1024:g}k"
        parts.append(
            f'<path class="grid" d="M{xx:.2f},{top}v{height}"/><text x="{xx:.2f}" y="313" text-anchor="middle">{label}</text>'
        )
    if show_log_reference:
        # Multiplication changes the numeric guide, never just its pixel offset.
        parts.append(
            f'<path class="log-reference" data-constant="{constant:.17g}" d="M{x(sizes[0]):.2f},{y(constant * math.log2(sizes[0])):.2f}L{x(sizes[-1]):.2f},{y(constant * math.log2(sizes[-1])):.2f}" stroke="#64748b" stroke-width="2" stroke-dasharray="7 5" fill="none"><title>{guide_label}: descriptive scaling, not a proven bound</title></path>'
        )
    for position, strategy in enumerate(metadata["strategies"]):
        color = COLORS[position % len(COLORS)]
        previous = None
        dashed = ' stroke-dasharray="6 4"' if "alternate" in strategy else ""
        for size in sizes:
            row = groups.get((strategy, size))
            if row is None:
                previous = None
                continue
            xx, yy = x(size), y(row[metric])
            if previous is not None:
                parts.append(
                    f'<path d="M{previous[0]:.2f},{previous[1]:.2f}L{xx:.2f},{yy:.2f}" stroke="{color}" stroke-width="2" fill="none"{dashed}/>'
                )
            error = row.get(metric + "_se")
            if error is not None:
                parts.append(
                    f'<path d="M{xx:.2f},{y(row[metric] - error):.2f}V{y(row[metric] + error):.2f}" stroke="{color}"/>'
                )
            parts.append(
                f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="3" fill="{color}"><title>{escaped(strategy_label(metadata, strategy))}: n={size:,}; {METRICS[metric]}={row[metric]:.6g}; {row["completed_trials"]} trials</title></circle>'
            )
            previous = xx, yy
        legend_x, legend_y = 22 + position % 2 * 350, 351 + position // 2 * 22
        parts.append(
            f'<path d="M{legend_x},{legend_y}h20" stroke="{color}" stroke-width="3"{dashed}/><text x="{legend_x + 27}" y="{legend_y + 4}">{escaped(strategy_label(metadata, strategy))}</text>'
        )
    if show_log_reference:
        legend_y = canvas_height - 30
        parts.append(
            f'<path d="M372,{legend_y}h20" stroke="#64748b" stroke-width="2" stroke-dasharray="7 5"/><text x="399" y="{legend_y + 4}">{guide_label}</text>'
        )
    parts.append(
        '<text x="70" y="332" style="font-size:11px;fill:#64748b">Keys (base-2 counts: k = 1,024; M = 1,048,576) · whiskers ±1 SE</text></svg>'
    )
    return "\n".join(parts)


def metric_cells(row):
    cells = []
    for metric in METRICS:
        value = formatted(row[metric], metric)
        error = row.get(metric + "_se")
        if error is not None:
            value += " ± " + f"{error:.3f}"
        cells.append(f"<td>{value}</td>")
    return "".join(cells)


def render_native_appendix(results: dict, output: Path) -> str:
    metadata = results["metadata"]
    native_strategies = [
        strategy for strategy in metadata["strategies"] if strategy.endswith("-native")
    ]
    records = [row for row in results["trials"] if row["strategy"] in native_strategies]
    if not records:
        return ""
    native_only = len(native_strategies) == len(metadata["strategies"])
    native_results = {
        "metadata": {**metadata, "strategies": native_strategies},
        "trials": records,
        "summaries": [
            row for row in results["summaries"] if row["strategy"] in native_strategies
        ],
    }
    table_rows, figures, overview = [], [], []
    canvas_height = chart_height(native_strategies)
    for order_index, order in enumerate(metadata["orders"]):
        for strategy in native_strategies:
            completed = [
                row
                for row in native_results["summaries"]
                if row["order"] == order
                and row["strategy"] == strategy
                and row["status"] == "complete"
            ]
            if completed:
                last = max(completed, key=lambda row: row["n"])
                table_rows.append(
                    f'<tr data-order="{order}"><td>{order}</td><td>{escaped(strategy_label(metadata, strategy))}</td><td>{last["n"]:,}</td>{metric_cells(last)}'
                    f"<td>{last['elapsed_seconds']:.4f}</td><td>{last['peak_rss_mib']:.1f}</td>"
                    f"<td>{last['node_storage_bytes'] / last['n']:.1f}</td></tr>"
                )
        order_figures = []
        for metric_index, metric in enumerate(METRICS):
            svg = chart_svg(native_results, order, metric).replace(
                f"{order}-{metric}", f"native-{order}-{metric}"
            )
            filename = f"native-{order}-{metric}.svg"
            (output / "figures" / filename).write_text(svg)
            order_figures.append(
                f'<figure>{svg}<figcaption><a href="./figures/{filename}" download>Download native SVG</a></figcaption></figure>'
            )
            inner = svg[svg.index(">") + 1 : svg.rindex("</svg>")]
            overview.append(
                f'<g transform="translate({metric_index * 720},{order_index * canvas_height})">{inner}</g>'
            )
        figures.append(
            f'<div data-order="{order}"><h3>{order.capitalize()}</h3><div class="charts">{"".join(order_figures)}</div></div>'
        )
    height = len(metadata["orders"]) * canvas_height
    (output / "native-all-sequences.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="2880" height="{height}" viewBox="0 0 2880 {height}"><rect width="100%" height="100%" fill="white"/>{"".join(overview)}</svg>'
    )
    complete_count = sum(row["status"] == "complete" for row in records)
    introduction = (
        f"This standalone C++ run has {complete_count} completed trials across {len(native_strategies)} implementations and {len(metadata['orders'])} input families. Each implementation receives identical input keys and rotation seed values."
        if native_only
        else f"The original Python measurements are retained. C++ adds {complete_count} completed trials across {len(native_strategies)} native implementations using the recorded input generators, input seeds, size schedule and rotation seed values. The combined charts include every implementation; the native-only SVGs below compare the C++ curves."
    )
    stream_note = (
        "Native implementations start from the same SplitMix64 seed, but different samplers consume different numbers of bits, so their later Bernoulli trials are not paired."
        if native_only
        else "Seed values drive different PRNGs (SplitMix64 vs Mersenne Twister), so these benchmark histories and shape metrics need not match exactly and are not paired random streams."
    )
    title = (
        "C++ geometric repair · native benchmark extension"
        if not native_only and len(native_strategies) == 1
        else "C++ geometric repair · native measurements"
    )
    settings = metadata["native_settings"]
    sampling = escaped(
        metadata.get("native_sampling", "Buffered SplitMix64 fair bits.")
    )
    timing = escaped(
        metadata.get(
            "native_timing",
            "Insertion and counters only; input preparation, capacity reservation and validation excluded.",
        )
    )
    build = escaped(metadata.get("native_build", "CMake Release; C++20."))
    return f"""<section id="native-implementation"><h2>{title}</h2>
<p>{introduction}</p>
<p><strong>Implementation:</strong> signed 64-bit keys and three 32-bit indices in separate contiguous arrays: 20 bytes of reserved array payload per key. No priorities, heights or balance fields persist in nodes. Nodes are reserved before timing. SplitMix64 supplies buffered words without discarding unused bits. Rotation traces are disabled; counters stay enabled. Each trial uses a fresh strategy.</p>
<p><strong>Sampling:</strong> {sampling} {stream_note} Means have ±1 SE only for repeated seeds; largest final height is the maximum across seeds.</p>
<p><strong>Timing and memory:</strong> native trials run sequentially in isolated Linux processes with a {settings["memory_mib"]} MiB address-space cap and {settings["timeout_seconds"]:g}-second wall deadline. {timing} RSS includes input storage, tree arrays, validation and process overhead. Compiler: {escaped(metadata["compiler"])}. Build: {build} The recorded configuration and CMake sources are available in config.json and the source archive.</p>
<p><strong>Validation:</strong> every completed native tree passes iterative BST ordering, parent-link, acyclicity and reachability checks; all stored keys match their input slots. Resource boundaries and size ceilings are recorded per implementation and input family. These finite runs establish neither logarithmic height nor constant traversal work.</p>
<h3>Largest completed native group per implementation and input family</h3><div class="table-wrap"><table><thead><tr><th>Input</th><th>Implementation</th><th>Keys</th>{"".join(f"<th>{escaped(title)}</th>" for title in METRICS.values())}<th>Insert seconds</th><th>Peak RSS MiB</th><th>Node bytes/key</th></tr></thead><tbody>{"".join(table_rows)}</tbody></table></div>
<p><a href="./native-all-sequences.svg" download>Download all native charts as one SVG</a> · <a href="./source.zip" download>Download measured sources</a> · <a href="./trials.csv" download>All native timings and memory measurements</a></p>
<details><summary>Native geometric repair · {len(metadata["orders"]) * len(METRICS)} standalone SVGs</summary>{"".join(figures)}</details></section>"""


def generate_report(
    source: Path,
    output: Path | None = None,
    *,
    visualizer_href: str | None = None,
    proof_href: str | None = None,
) -> Path:
    results = json.loads((source / "results.json").read_text())
    metadata, records, summaries = (
        results["metadata"],
        results["trials"],
        results["summaries"],
    )
    native_strategies = [
        strategy for strategy in metadata["strategies"] if strategy.endswith("-native")
    ]
    native_only = len(native_strategies) == len(metadata["strategies"])
    output = output or source / "report"
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    complete = [row for row in summaries if row["status"] == "complete"]
    lookup = {(row["strategy"], row["order"], row["n"]): row for row in complete}
    common_sizes = [
        size
        for size in metadata["sizes"]
        if all(
            (strategy, order, size) in lookup
            for strategy in metadata["strategies"]
            for order in metadata["orders"]
        )
    ]
    common_size = max(common_sizes, default=None)
    statuses = Counter(row["status"] for row in records)
    table_header = (
        "<thead><tr><th>Input</th><th>Implementation</th><th>Keys</th><th>Trials</th>"
        + "".join(f"<th>{escaped(title)}</th>" for title in METRICS.values())
        + "</tr></thead>"
    )
    common_rows, reach_rows, all_rows = [], [], []
    for order in metadata["orders"]:
        for strategy in metadata["strategies"]:
            if common_size is not None:
                row = lookup[strategy, order, common_size]
                common_rows.append(
                    f'<tr data-order="{order}"><td>{order}</td><td>{escaped(strategy_label(metadata, strategy))}</td><td>{common_size:,}</td><td>{row["completed_trials"]}</td>{metric_cells(row)}</tr>'
                )
            available = [
                row
                for row in complete
                if row["strategy"] == strategy and row["order"] == order
            ]
            failures = [
                row
                for row in records
                if row["strategy"] == strategy
                and row["order"] == order
                and row["status"] not in ("complete", "not_run")
            ]
            reached = max(available, key=lambda row: row["n"], default=None)
            stop = next(iter(failures), None)
            if stop:
                limit = f"{stop['status']} at {stop['n']:,}"
            elif metadata.get("global_stop_reason") or (
                metadata.get("python_stop_reason") and not strategy.endswith("-native")
            ):
                limit = "Larger probes stopped at shared validation-memory boundary"
            else:
                limit = "Reached configured size ceiling"
            reach_rows.append(
                f'<tr data-order="{order}"><td>{order}</td><td>{escaped(strategy_label(metadata, strategy))}</td><td>{reached["n"]:,}</td><td>{escaped(limit)}</td></tr>'
                if reached
                else f"<tr><td>{order}</td><td>{escaped(strategy_label(metadata, strategy))}</td><td>—</td><td>{escaped(limit)}</td></tr>"
            )
            for row in sorted(available, key=lambda row: row["n"]):
                all_rows.append(
                    f'<tr data-order="{order}"><td>{order}</td><td>{escaped(strategy_label(metadata, strategy))}</td><td>{row["n"]:,}</td><td>{row["completed_trials"]}</td>{metric_cells(row)}</tr>'
                )
    canvas_height = chart_height(metadata["strategies"])
    charts = []
    overview_groups = []
    for order_index, order in enumerate(metadata["orders"]):
        order_figures = []
        for metric_index, metric in enumerate(METRICS):
            svg = chart_svg(results, order, metric)
            filename = f"{order}-{metric}.svg"
            (figures / filename).write_text(svg)
            order_figures.append(
                f'<figure>{svg}<figcaption><a href="./figures/{filename}" download>Download SVG</a></figcaption></figure>'
            )
            inner = svg[svg.index(">") + 1 : svg.rindex("</svg>")]
            overview_groups.append(
                f'<g transform="translate({metric_index * 720},{order_index * canvas_height})">{inner}</g>'
            )
        charts.append(
            f'<section data-order="{order}"><h2>{order.capitalize()} input</h2><div class="charts">{"".join(order_figures)}</div></section>'
        )
    overview = f'<svg xmlns="http://www.w3.org/2000/svg" width="2880" height="{len(metadata["orders"]) * canvas_height}" viewBox="0 0 2880 {len(metadata["orders"]) * canvas_height}"><rect width="100%" height="100%" fill="white"/>{"".join(overview_groups)}</svg>'
    (output / "all-sequences.svg").write_text(overview)
    for filename in (
        "results.json",
        "summary.csv",
        "trials.csv",
        "config.json",
        "trials.jsonl",
    ):
        shutil.copyfile(source / filename, output / filename)
    with ZipFile(output / "source.zip", "w", compression=ZIP_DEFLATED) as archive:
        archive.write(Path(__file__), "report_renderer.py")
        for path in sorted((source / "source").rglob("*")):
            if path.is_file() and path.suffix in (".py", ".cpp", ".hpp", ".txt", ".md"):
                archive.write(path, path.relative_to(source / "source"))
    pairs = {
        (row["order"], row["n"], row["trial"]): row
        for row in records
        if row["strategy"] == "geometric-target-local-repair"
        and row["status"] == "complete"
    }
    compared = 0
    mismatch = 0
    for row in records:
        if (
            row["strategy"] != "geometric-target-local-repair-alternate"
            or row["status"] != "complete"
        ):
            continue
        partner = pairs.get((row["order"], row["n"], row["trial"]))
        if partner:
            compared += 1
            mismatch += any(
                row["metrics"][key] != partner["metrics"][key]
                for key in row["metrics"]
                if key != "peak_rss_mib"
            )
    options = '<option value="all">All sequence types</option>' + "".join(
        f'<option value="{order}">{order.capitalize()}</option>'
        for order in metadata["orders"]
    )
    downloads = "".join(
        f'<a href="./{name}" download>{name}</a>'
        for name in (
            "all-sequences.svg",
            "summary.csv",
            "trials.csv",
            "results.json",
            "config.json",
            "trials.jsonl",
            "source.zip",
        )
    )
    common_label = f"{common_size:,}" if common_size else "No common completed size"
    stop_reason = metadata.get("global_stop_reason") or metadata.get(
        "python_stop_reason"
    )
    boundary_note = (
        '<p class="note">Recorded boundary: ' + escaped(stop_reason) + "</p>"
        if stop_reason
        else ""
    )
    findings = []
    for order in ("random", "converging"):
        geometric = lookup.get(("geometric-target-local-repair", order, common_size))
        treap = lookup.get(("treap", order, common_size))
        if geometric and treap:
            findings.append(
                f"<p><strong>{order.capitalize()} input at {common_size:,} keys:</strong> "
                f"geometric repair used {geometric['mean_rotations']:.3f} rotations/key "
                f"and {geometric['mean_random_bits']:.3f} random bits/key; "
                f"treap used {treap['mean_rotations']:.3f} rotations/key "
                f"and {treap['mean_random_bits']:.3f} random bits/key. "
                f"Their final heights were {geometric['maximum_height']:,} and "
                f"{treap['maximum_height']:,} edges, with mean node depths "
                f"{geometric['mean_depth']:.3f} and {treap['mean_depth']:.3f}, respectively.</p>"
            )
    findings_section = (
        "<section><h2>Measured tradeoffs</h2>" + "".join(findings) + "</section>"
        if findings
        else ""
    )
    links = []
    if visualizer_href:
        links.append(f'<a href="{escaped(visualizer_href)}">← Tree visualizer</a>')
    if proof_href:
        links.append(
            f'<a href="{escaped(proof_href)}">Read the geometric repair proof (PDF)</a>'
        )
    navigation = (
        f'<nav aria-label="Lab pages">{" · ".join(links)}</nav>' if links else ""
    )
    native_appendix = render_native_appendix(results, output)
    if native_appendix:
        navigation += '<p><a href="#native-implementation">Jump to C++ results and implementation notes ↓</a></p>'
    title = (
        "C++ geometric probability comparison"
        if native_only
        else "Target strategy comparison"
    )
    settings = metadata["native_settings"] if native_only else metadata
    workers = 1 if native_only else metadata["workers"]
    worker_label = "C++ worker" if native_only else "Python workers"
    environment = (
        "C++ · " + escaped(metadata["compiler"])
        if native_only
        else "Python " + escaped(metadata["python"].split()[0])
    )
    stream_note = (
        "Native strategies start from identical SplitMix64 seed values; different samplers consume different numbers of bits."
        if native_only
        else "Python random streams are paired across strategies; C++ uses a different PRNG."
    )
    validation_note = (
        "Every completed tree passes BST order, parent-pointer, cycle and full-key-set checks."
        + (
            " Stored treap depths also match an independently reconstructed Cartesian tree."
            if "treap" in metadata["strategies"]
            else ""
        )
    )
    execution_note = (
        "Native trials run sequentially in isolated processes. Insertion timing excludes input preparation, capacity reservation and final validation."
        if native_only
        else "Python trials run concurrently in isolated processes; any native extension runs sequentially. Cross-language runtime comparisons are omitted."
    )
    implementation_names = ", ".join(
        escaped(strategy_label(metadata, strategy))
        for strategy in metadata["strategies"]
    )
    paired_note = (
        f"<li>The two Python geometric implementations match on all operation/shape metrics in {compared} paired completed trials; mismatches: {mismatch}. Their curves can overlap. The alternate additionally records the sampled move count in an insertion annotation, which is not one of the reported metrics.</li>"
        if compared
        else ""
    )
    html_text = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f8;color:#17283c;font:15px/1.6 system-ui,sans-serif}}main{{max-width:1500px;margin:auto;padding:28px}}h1{{font-size:clamp(30px,4vw,48px);line-height:1.15;letter-spacing:-1px}}h2{{font-size:22px}}a{{color:#245fd0}}section,details{{background:white;border:1px solid #dce3eb;border-radius:14px;padding:22px;margin:22px 0}}.stats,.charts{{display:grid;gap:16px}}.stats{{grid-template-columns:repeat(4,1fr)}}.stat{{background:white;padding:18px;border:1px solid #dce3eb;border-radius:12px}}.stat strong{{display:block;font-size:27px}}.stat span,.note{{color:#526275;font-size:13px}}.charts{{grid-template-columns:repeat(2,minmax(0,1fr))}}figure{{margin:0;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden}}figure svg{{width:100%;display:block}}figcaption{{padding:0 14px 10px;text-align:right;font-size:12px}}.table-wrap{{overflow:auto;max-height:75vh}}table{{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}}th,td{{padding:8px;border-bottom:1px solid #dce3eb;text-align:right}}th{{background:#eef2f7;position:sticky;top:0}}th:nth-child(-n+2),td:nth-child(-n+2){{text-align:left}}.downloads{{display:flex;gap:18px;flex-wrap:wrap}}select{{font:inherit;padding:8px;border:1px solid #ccd5e0;border-radius:8px;background:white}}[hidden]{{display:none!important}}summary{{cursor:pointer;font-weight:bold}}@media(max-width:800px){{main{{padding:14px}}.charts{{grid-template-columns:1fr}}.stats{{grid-template-columns:repeat(2,1fr)}}section,details{{padding:14px}}}}</style></head><body><main>
{navigation}<header><p class="note">Rotation Lab · measurements on this computer</p><h1>{title}</h1><p>{len(metadata["orders"])} sequence families. {len(metadata["strategies"])} implementations. Compare rotations, final tree depths and logical random-bit use as key counts increase.</p></header>
<div class="stats"><div class="stat"><strong>{statuses["complete"]:,}</strong><span>completed trials</span></div><div class="stat"><strong>{common_label}</strong><span>largest size completed by every pair</span></div><div class="stat"><strong>{max((r["n"] for r in records if r["status"] == "complete"), default=0):,}</strong><span>largest completed tree</span></div><div class="stat"><strong>{workers}</strong><span>{worker_label} · {settings["memory_mib"]} MiB cap each</span></div></div>
<p class="note">{escaped(metadata["cpu"])} · {environment} · seed {metadata["seed"]} · per-trial deadline {settings["timeout_seconds"]:g} s. Outcomes: {escaped(dict(statuses))}.</p>
<p><label for="workload">Sequence type </label><select id="workload">{options}</select></p>
{findings_section}
<section><h2>Comparison at the largest common size: {common_label}</h2><p class="note">Averages are over completed trials; ± one standard error when repeats exist. {stream_note} Maximum final height is the largest final node depth observed across those trials, not height averaged across seeds or time. Larger partially completed groups are excluded.</p><div class="table-wrap"><table>{table_header}<tbody>{"".join(common_rows)}</tbody></table></div></section>
{"".join(charts)}
<section><h2>How large did each implementation reach?</h2><p>Trials advance through increasing sizes. Direct resource failures and probes stopped at a shared pipeline boundary are distinguished below. These are resource-limited measurements of these implementations and validators, not algorithmic size limits.</p>{boundary_note}<div class="table-wrap"><table><thead><tr><th>Input</th><th>Implementation</th><th>Largest complete size</th><th>Next boundary</th></tr></thead><tbody>{"".join(reach_rows)}</tbody></table></div></section>
<details><summary>All {len(complete)} fully completed measurement groups</summary><div class="table-wrap"><table>{table_header}<tbody>{"".join(all_rows)}</tbody></table></div></details>
<section><h2>Method and interpretation</h2><ul>
<li>Measured implementations: {implementation_names}. The source archive and config.json record their exact versions and settings.</li>
{paired_note}
<li>{metadata["small_trials"]} seeds per group through {metadata["repeat_through"]:,} keys; one seed above that size. Inputs are fixed per size and shared across strategies. {stream_note} Single large trials give no uncertainty estimate.</li>
<li>Root depth is zero. Mean depth averages all nodes in the final tree. Rotations and random bits are totals divided by inserted keys. Maximum final height is the greatest final depth across all completed seeds in that group.</li>
<li>Height, mean-depth and random-bit charts include a dashed gray c·log₂(n) guide. For each chart, c is the largest value/log₂(n) ratio at each implementation's last completed point, with a minimum of 1. The legend states c. This descriptive endpoint scaling is not a proven bound; random bits per key can remain constant even though the guide grows.</li>
<li>{validation_note} Validation is included in the process memory cap and deadline.</li>
<li>{execution_note} Memory limits and wall deadlines include instrumentation and validation overhead. Raw outcomes and missing measurements are retained, never treated as zeros.</li>
<li>The worker source was copied before running and its SHA-256 checksums recorded. Source snapshot: the parent run directory's source folder. No logarithmic-height guarantee or general performance claim follows from these finite samples.</li>
</ul></section>{native_appendix}<section><h2>Downloads</h2><div class="downloads">{downloads}</div></section>
</main><script>document.getElementById('workload').addEventListener('change',event=>{{for(const element of document.querySelectorAll('[data-order]'))element.hidden=event.target.value!=='all'&&element.dataset.order!==event.target.value;}});</script></body></html>"""
    destination = output / "index.html"
    destination.write_text(html_text)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--visualizer-href", help="optional return link for a published report"
    )
    parser.add_argument("--proof-href", help="optional link to the proof PDF")
    args = parser.parse_args()
    print(
        generate_report(
            args.input,
            args.output,
            visualizer_href=args.visualizer_href,
            proof_href=args.proof_href,
        )
    )


if __name__ == "__main__":
    main()
