#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""Render benchmark charts (PNG) and markdown comparison tables from
pytest-benchmark results directories.

Sync results come from ``run_all_benchmarks.py`` (``benchmark_<driver>.json``),
async results from ``run_async_benchmarks.py --all`` (``benchmark_async_*.json``);
a directory may hold either or both, and each kind gets its own charts and
table (``comparison_table.md`` / ``comparison_table_async.md``).

Several directories can be given (e.g. three reported passes): the per-driver
time of every benchmark is then the median across the directories.

Charts are rendered with matplotlib using the Google Charts colour palette:

    pip install matplotlib

Usage:
    python make_charts.py [RESULTS_DIR ...] [--out DOCS_DIR]

If no RESULTS_DIR is given, the newest ``results_*`` directory is used.
PNGs and the tables are written to DOCS_DIR (default: ../docs/benchmarks).
"""

import argparse
import glob
import json
import os
import statistics
from typing import Any, Dict, List, Tuple

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
    "pymysql": ("PyMySQL – pure Python", "#FF9900"),
    "mysql_connector (C)": ("mysql-connector – C", "#109618"),
    "mysql_connector_pure": ("mysql-connector – pure Python", "#990099"),
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
TITLES.update({
    "test_insert_batch_10k": "Batch INSERT — 10,000 rows (executemany)",
    "test_concurrent_connections": "50 threads: connect + query + close",
    "test_pool_queries": "500 queries from 20 threads through a 5–20 pool",
})
ORDER += ["test_insert_batch_10k", "test_concurrent_connections", "test_pool_queries"]

# Async suite (benchmarks/async): same colours for the two mariadb drivers.
ASYNC_DRIVERS = {
    "mariadb_c_async": ("mariadb – C extension (async)", "#3366CC"),
    "mariadb_async": ("mariadb – pure Python (async)", "#DC3912"),
    "asyncmy": ("asyncmy – C (Cython)", "#FF9900"),
    "aiomysql": ("aiomysql – pure Python", "#109618"),
}

ASYNC_TITLES = {
    "test_async_do_1": "DO 1 — command round-trip",
    "test_async_select_1": "SELECT 1 — simple query",
    "test_async_select_1000_rows": "SELECT 1000 rows",
    "test_async_select_100_cols": "SELECT 100 columns",
    "test_async_do_1000_params": "DO 1000 params",
    "test_async_insert_batch": "Batch INSERT — 100 rows (executemany)",
    "test_async_insert_batch_10k": "Batch INSERT — 10,000 rows (executemany)",
    "test_async_concurrent_connections": "50 concurrent connect + query + close",
    "test_async_pool_queries": "500 concurrent queries through a 5–20 pool",
}

ASYNC_ORDER = [
    "test_async_do_1", "test_async_select_1",
    "test_async_insert_batch", "test_async_insert_batch_10k",
    "test_async_select_1000_rows", "test_async_select_100_cols",
    "test_async_do_1000_params",
    "test_async_concurrent_connections", "test_async_pool_queries",
]


def latest_results_dir() -> str:
    dirs = sorted(glob.glob(os.path.join(HERE, "results_*")), key=os.path.getmtime)
    if not dirs:
        raise SystemExit("no results_* directory found; run run_all_benchmarks.py first")
    return dirs[-1]


def _load_one(results_dir: str, pattern: str) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Any]]:
    """Return ({base_test_name: {driver_param: mean_seconds}}, machine_info) for
    the JSON files of *results_dir* matching *pattern*."""
    data: Dict[str, Dict[str, float]] = {}
    machine: Dict[str, Any] = {}
    for jf in glob.glob(os.path.join(results_dir, pattern)):
        with open(jf) as fh:
            blob = json.load(fh)
        machine = blob.get("machine_info", machine)
        for b in blob["benchmarks"]:
            name = b["name"]
            base = name.split("[", 1)[0]
            driver = name.split("[", 1)[1].rstrip("]") if "[" in name else "?"
            data.setdefault(base, {})[driver] = b["stats"]["mean"]
    return data, machine


def load(results_dirs: List[str], kind: str) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Any]]:
    """Merge the results of several directories: per benchmark and driver, the
    median of the per-directory means. *kind* is "sync" or "async"."""
    pattern = "benchmark_async_*.json" if kind == "async" else "benchmark_[!a]*.json"
    passes: List[Dict[str, Dict[str, float]]] = []
    machine: Dict[str, Any] = {}
    for d in results_dirs:
        data, m = _load_one(d, pattern)
        if data:
            passes.append(data)
            machine = m or machine
    merged: Dict[str, Dict[str, float]] = {}
    for data in passes:
        for base, per_driver in data.items():
            for drv, mean in per_driver.items():
                merged.setdefault(base, {}).setdefault(drv, []).append(mean)  # type: ignore[arg-type]
    return ({base: {drv: statistics.median(v) for drv, v in per.items()}  # type: ignore[arg-type]
             for base, per in merged.items()}, machine)


def slug(base: str) -> str:
    return base.replace("test_async_", "", 1).replace("test_", "", 1)


def chart(base: str, per_driver: Dict[str, float], out_dir: str,
          drivers: Dict[str, Tuple[str, str]] = DRIVERS, titles: Dict[str, str] = TITLES,
          prefix: str = "") -> str:
    """Render one horizontal bar chart (ops/sec, higher is better) with matplotlib."""
    rows: List[Tuple[str, str, float, float]] = []
    for drv, mean in per_driver.items():
        if drv not in drivers or mean <= 0:
            continue
        label, colour = drivers[drv]
        rows.append((label, colour, 1.0 / mean, mean * 1000.0))
    rows.sort(key=lambda r: r[2])  # ascending -> fastest on top after barh
    labels = [r[0] for r in rows]
    colours = [r[1] for r in rows]
    ops = [r[2] for r in rows]
    ms = [r[3] for r in rows]
    top = max(ops)

    fig, ax = plt.subplots(figsize=(9, 0.30 * len(rows) + 1.2))
    bars = ax.barh(labels, ops, height=1.0, color=colours, edgecolor="white", linewidth=1.0)
    ax.set_title(titles.get(base, base), fontsize=13, fontweight="bold", pad=12)
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
    path = os.path.join(out_dir, prefix + slug(base) + ".png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def write_table(data: Dict[str, Dict[str, float]], machine: Dict[str, Any],
                out_dir: str, drivers: Dict[str, Tuple[str, str]] = DRIVERS,
                titles: Dict[str, str] = TITLES, order: List[str] = ORDER,
                filename: str = "comparison_table.md") -> str:
    cpu: str = machine.get("cpu", {}).get("brand_raw", "?")
    lines = ["| Benchmark | " + " | ".join(d[0] for d in drivers.values()) + " |",
             "|---|" + "---|" * len(drivers)]
    for base in order:
        if base not in data:
            continue
        means = {d: data[base].get(d) for d in drivers}
        fastest = min((m for m in means.values() if m), default=None)
        cells = []
        for drv in drivers:
            m = means[drv]
            if not m:
                cells.append("–")
            elif m == fastest:
                cells.append("{:,.0f} ops/s **(fastest)**".format(1.0 / m))
            else:
                assert fastest is not None  # reached only when a faster mean exists
                cells.append("{:,.0f} ops/s ({:.1f}x)".format(1.0 / m, m / fastest))
        lines.append("| " + titles.get(base, base) + " | " + " | ".join(cells) + " |")
    with open(os.path.join(out_dir, filename), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return cpu


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dirs", nargs="*", default=None,
                    help="one or more results directories (median across them)")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "docs", "benchmarks"))
    args = ap.parse_args()

    results_dirs = args.results_dirs or [latest_results_dir()]
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    made: List[str] = []
    cpu = "?"
    for kind, drivers, titles, order, prefix, table in (
            ("sync", DRIVERS, TITLES, ORDER, "", "comparison_table.md"),
            ("async", ASYNC_DRIVERS, ASYNC_TITLES, ASYNC_ORDER, "async_", "comparison_table_async.md")):
        data, machine = load(results_dirs, kind)
        if not data:
            continue
        for base in order:
            if base in data:
                made.append(chart(base, data[base], out_dir, drivers, titles, prefix))
        cpu = write_table(data, machine, out_dir, drivers, titles, order, table)
        made.append(os.path.join(out_dir, table))

    print("results dirs: %s" % ", ".join(os.path.abspath(d) for d in results_dirs))
    print("CPU         : %s" % cpu)
    print("outputs (%d) : %s" % (len(made), out_dir))
    for p in made:
        print("  " + os.path.relpath(p, os.path.join(HERE, "..")))


if __name__ == "__main__":
    main()
