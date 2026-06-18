#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""Render benchmark charts (PNG) and a markdown comparison table from a
pytest-benchmark results directory produced by ``run_all_benchmarks.py``.

Charts are rendered with matplotlib using the Google Charts colour palette:

    pip install matplotlib

Usage:
    python make_charts.py [RESULTS_DIR] [--out DOCS_DIR]

If RESULTS_DIR is omitted, the newest ``results_*`` directory is used.
PNGs and ``comparison_table.md`` are written to DOCS_DIR
(default: ../docs/benchmarks).
"""

import argparse
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# Driver param (as it appears in the pytest-benchmark test id) -> (display label, colour).
# Colours are the Google Charts default series palette, one fixed colour per
# driver so the legend stays consistent across every chart.
DRIVERS = {
    "mariadb_c": ("mariadb – C extension", "#3366CC"),
    "mariadb": ("mariadb – pure Python", "#DC3912"),
    "pymysql": ("PyMySQL", "#FF9900"),
    "mysql_connector (C)": ("mysql-connector – C", "#109618"),
    "mysql_connector_pure": ("mysql-connector – pure", "#990099"),
}

TITLES = {
    "test_do_1": "DO 1 — command round-trip",
    "test_select_1": "SELECT 1 — simple query",
    "test_select_1000_rows_binary": "SELECT 1000 rows — binary protocol",
    "test_select_1000_rows_text": "SELECT 1000 rows — text protocol",
    "test_select_100_cols_binary": "SELECT 100 columns — binary protocol",
    "test_select_100_cols_text": "SELECT 100 columns — text protocol",
    "test_do_1000_params_binary": "DO 1000 params — binary protocol",
    "test_do_1000_params_text": "DO 1000 params — text protocol",
    "test_insert_batch": "Batch INSERT — 100 rows (executemany)",
    "test_insert_row": "INSERT — mixed types (single row)",
}

ORDER = [
    "test_do_1", "test_select_1",
    "test_insert_row", "test_insert_batch",
    "test_select_1000_rows_binary", "test_select_1000_rows_text",
    "test_select_100_cols_binary", "test_select_100_cols_text",
    "test_do_1000_params_binary", "test_do_1000_params_text",
]


def latest_results_dir():
    dirs = sorted(glob.glob(os.path.join(HERE, "results_*")), key=os.path.getmtime)
    if not dirs:
        raise SystemExit("no results_* directory found; run run_all_benchmarks.py first")
    return dirs[-1]


def load(results_dir):
    """Return ({base_test_name: {driver_param: mean_seconds}}, machine_info)."""
    data = {}
    machine = {}
    for jf in glob.glob(os.path.join(results_dir, "benchmark_*.json")):
        with open(jf) as fh:
            blob = json.load(fh)
        machine = blob.get("machine_info", machine)
        for b in blob["benchmarks"]:
            name = b["name"]
            base = name.split("[", 1)[0]
            driver = name.split("[", 1)[1].rstrip("]") if "[" in name else "?"
            data.setdefault(base, {})[driver] = b["stats"]["mean"]
    return data, machine


def slug(base):
    return base.replace("test_", "", 1)


def chart(base, per_driver, out_dir):
    """Render one horizontal bar chart (ops/sec, higher is better) with matplotlib."""
    rows = []
    for drv, mean in per_driver.items():
        if drv not in DRIVERS or mean <= 0:
            continue
        label, colour = DRIVERS[drv]
        rows.append((label, colour, 1.0 / mean, mean * 1000.0))
    rows.sort(key=lambda r: r[2])  # ascending -> fastest on top after barh
    labels = [r[0] for r in rows]
    colours = [r[1] for r in rows]
    ops = [r[2] for r in rows]
    ms = [r[3] for r in rows]
    top = max(ops)

    fig, ax = plt.subplots(figsize=(9, 0.30 * len(rows) + 1.2))
    bars = ax.barh(labels, ops, height=1.0, color=colours, edgecolor="white", linewidth=1.0)
    ax.set_title(TITLES.get(base, base), fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("operations / second  (higher is better)", fontsize=10)
    ax.set_xlim(0, top * 1.20)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.tick_params(labelsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    for bar, o, m in zip(bars, ops, ms):
        rel = "fastest" if o == top else "%.1fx slower" % (top / o)
        ax.text(o + top * 0.012, bar.get_y() + bar.get_height() / 2,
                "{:,.0f} ops/s  ({:.3f} ms)  {}".format(o, m, rel),
                va="center", fontsize=8.5)
    fig.tight_layout()
    path = os.path.join(out_dir, slug(base) + ".png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def write_table(data, machine, out_dir):
    cpu = machine.get("cpu", {}).get("brand_raw", "?")
    lines = ["| Benchmark | " + " | ".join(d[0] for d in DRIVERS.values()) + " |",
             "|---|" + "---|" * len(DRIVERS)]
    for base in ORDER:
        if base not in data:
            continue
        means = {d: data[base].get(d) for d in DRIVERS}
        fastest = min((m for m in means.values() if m), default=None)
        cells = []
        for drv in DRIVERS:
            m = means[drv]
            if not m:
                cells.append("–")
            elif m == fastest:
                cells.append("{:,.0f} ops/s **(fastest)**".format(1.0 / m))
            else:
                cells.append("{:,.0f} ops/s ({:.1f}x)".format(1.0 / m, m / fastest))
        lines.append("| " + TITLES.get(base, base) + " | " + " | ".join(cells) + " |")
    with open(os.path.join(out_dir, "comparison_table.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return cpu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir", nargs="?", default=None)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "docs", "benchmarks"))
    args = ap.parse_args()

    results_dir = args.results_dir or latest_results_dir()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    data, machine = load(results_dir)
    made = []
    for base in ORDER:
        if base in data:
            made.append(chart(base, data[base], out_dir))
    cpu = write_table(data, machine, out_dir)

    print("results dir : %s" % os.path.abspath(results_dir))
    print("CPU         : %s" % cpu)
    print("charts (%d)  : %s" % (len(made), out_dir))
    for p in made:
        print("  " + os.path.relpath(p, os.path.join(HERE, "..")))
    print("  " + os.path.relpath(os.path.join(out_dir, "comparison_table.md"),
                                 os.path.join(HERE, "..")))


if __name__ == "__main__":
    main()
