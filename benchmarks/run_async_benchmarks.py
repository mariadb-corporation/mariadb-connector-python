#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Async benchmark runner for comparing mariadb async, mariadb_c async, aiomysql, and asyncmy.

Usage:
    python run_async_benchmarks.py                          # Run all async drivers
    python run_async_benchmarks.py --driver mariadb_async   # Run specific driver
    python run_async_benchmarks.py --compare                # Compare results
"""

import sys
import os
import argparse
import subprocess
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


ASYNC_DIR = 'async'

ASYNC_BENCHMARKS = [
    f'{ASYNC_DIR}/test_bench_async_do_1.py',
    f'{ASYNC_DIR}/test_bench_async_select_1.py',
    f'{ASYNC_DIR}/test_bench_async_select_1000_rows.py',
    f'{ASYNC_DIR}/test_bench_async_select_100_cols.py',
    f'{ASYNC_DIR}/test_bench_async_do_1000_params.py',
    f'{ASYNC_DIR}/test_bench_async_insert_batch.py',
    f'{ASYNC_DIR}/test_bench_async_insert_batch_10k.py',
    f'{ASYNC_DIR}/test_bench_async_concurrent.py',
    f'{ASYNC_DIR}/test_bench_async_pool.py',
]

ASYNC_DRIVERS = ['mariadb_async', 'mariadb_c_async', 'aiomysql', 'asyncmy']


def run_async_benchmark(driver: Optional[str] = None,
                        output_json: Optional[str] = None) -> int:
    """Run async pytest-benchmark with specified parameters."""

    cmd = [sys.executable, '-m', 'pytest', '-v']
    cmd.extend(['--benchmark-only', '--benchmark-disable-gc', '--benchmark-min-rounds=1000'])
    cmd.extend(ASYNC_BENCHMARKS)

    if driver:
        cmd.extend(['-k', driver])

    if output_json:
        cmd.extend(['--benchmark-json', output_json])

    benchmarks_dir = Path(__file__).parent

    env = os.environ.copy()
    if driver == 'mariadb_async':
        env['MARIADB_PYTHON_CONNECTOR'] = 'python'
    elif driver == 'mariadb_c_async':
        env['MARIADB_PYTHON_CONNECTOR'] = 'c'

    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {benchmarks_dir}")
    if driver and 'mariadb' in driver:
        print(f"MARIADB_PYTHON_CONNECTOR={env.get('MARIADB_PYTHON_CONNECTOR')}")
    print("-" * 80)

    result = subprocess.run(cmd, cwd=benchmarks_dir, env=env)
    return result.returncode


def _fmt_time(seconds: float) -> str:
    """Format a per-call time in μs or ms depending on magnitude."""
    if seconds < 1e-3:
        return f"{seconds * 1e6:.1f}μs"
    return f"{seconds * 1e3:.2f}ms"


def generate_comparison(json_files: List[str]) -> None:
    """Generate comparison report from async benchmark JSON files."""

    results: Dict[str, Dict[str, Any]] = {}
    for jf in json_files:
        if not os.path.exists(jf) or os.path.getsize(jf) == 0:
            print(f"Warning: {jf} not found or empty (driver run failed?)")
            continue
        with open(jf) as f:
            data = json.load(f)
        driver = Path(jf).stem.replace('benchmark_async_', '')
        results[driver] = {
            b['name'].split('[')[0]: b['stats']
            for b in data.get('benchmarks', [])
        }

    if not results:
        print("No results to compare")
        return

    # Collect all benchmark names
    all_benchmarks = sorted({
        name for driver_data in results.values() for name in driver_data
    })
    drivers = sorted(results.keys())

    header = f"{'Benchmark':<35}" + "".join(f" {d:>20}" for d in drivers)
    print("\n" + "=" * len(header))
    print("ASYNC BENCHMARK COMPARISON (median per call; fastest driver = 1.00x)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for bench in all_benchmarks:
        display = bench.replace('test_async_', '').replace('test_bench_async_', '')
        medians = {d: results[d][bench]['median'] for d in drivers if bench in results[d]}
        best = min(medians.values())
        row = f"{display:<35}"
        for d in drivers:
            if d in medians:
                row += f" {_fmt_time(medians[d]):>12} {medians[d] / best:>6.2f}x"
            else:
                row += f" {'N/A':>20}"
        print(row)

    print("=" * len(header))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run async benchmarks")
    parser.add_argument('--driver', choices=ASYNC_DRIVERS, help='Specific async driver')
    parser.add_argument('--json', help='Output JSON file')
    parser.add_argument('--compare', action='store_true', help='Compare existing results')
    parser.add_argument('--compare-files', nargs='+', help='JSON files to compare')
    parser.add_argument('--all', action='store_true', help='Run all async drivers')
    args = parser.parse_args()

    if args.compare:
        files = args.compare_files or [
            f"benchmark_async_{d}.json" for d in ASYNC_DRIVERS
        ]
        generate_comparison(files)
        return 0

    if args.all:
        for driver in ASYNC_DRIVERS:
            print(f"\n{'=' * 42}")
            print(f"Running async benchmarks for: {driver}")
            print(f"{'=' * 42}")
            output = str(Path(__file__).parent / f"benchmark_async_{driver}.json")
            rc = run_async_benchmark(driver=driver, output_json=output)
            if rc == 0:
                print(f"✓ {driver} completed")
            else:
                print(f"✗ {driver} failed (exit code {rc})")
        # Auto-compare
        files = [
            str(Path(__file__).parent / f"benchmark_async_{d}.json")
            for d in ASYNC_DRIVERS
        ]
        generate_comparison(files)
        return 0

    if args.driver:
        return run_async_benchmark(driver=args.driver, output_json=args.json)

    # Default: run all
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
