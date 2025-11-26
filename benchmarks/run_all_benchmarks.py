#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""Cross-platform helper to run all benchmarks and generate a comparison report.

This script mirrors the behavior of ``run_all_benchmarks.sh`` but uses Python
only, so it works on Windows, macOS and Linux without requiring a Bash shell.

Steps performed:
- Check database connectivity using the ``mysql`` client
- Create a timestamped results directory
- Run benchmarks for each driver (mariadb, mariadb_c, pymysql)
- Generate a comparison report from the JSON results
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path


DRIVERS = ["mariadb", "mariadb_c", "pymysql", "mysql_connector"]


def check_database_connection() -> bool:
    """Check if the database is accessible using the ``mysql`` CLI tool.

    Uses the same TEST_DB_* environment variables as the shell script.
    """

    host = os.environ.get("TEST_DB_HOST", "localhost")
    port = os.environ.get("TEST_DB_PORT", "3306")
    user = os.environ.get("TEST_DB_USER", "root")
    password = os.environ.get("TEST_DB_PASSWORD", "")
    database = os.environ.get("TEST_DB_DATABASE", "testp")

    cmd = [
        "mysql",
        "-h",
        host,
        "-P",
        str(port),
        "-u",
        user,
    ]

    if password:
        cmd.append(f"-p{password}")

    cmd.append(database)
    cmd.extend(["-e", "SELECT 1"])

    print("Checking database connection...")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        # On systems without the mysql CLI (e.g. Windows without client tools),
        # skip the explicit connection check but still allow benchmarks to run.
        print("Warning: 'mysql' client not found on PATH.")
        print("Skipping database connectivity check. Benchmarks will still run,\n"
              "but may fail if the database is not reachable.")
        print("")
        return True

    if result.returncode != 0:
        print("Error: Cannot connect to database")
        print("Please set TEST_DB_* environment variables correctly.")
        return False

    print("\u2713 Database connection OK")
    print("")
    return True


def run_driver_benchmarks(results_dir: Path) -> None:
    """Run benchmarks for each driver and store JSON results in ``results_dir``."""

    for driver in DRIVERS:
        print("=" * 42)
        print(f"Running benchmarks for: {driver}")
        print("=" * 42)

        output_file = results_dir / f"benchmark_{driver}.json"

        cmd = [
            sys.executable,
            "run_benchmarks.py",
            "--driver",
            driver,
            "--json",
            str(output_file),
        ]

        result = subprocess.run(cmd)
        if result.returncode == 0:
            print(f"\u2713 {driver} benchmarks completed")
        else:
            print(f"\u2717 {driver} benchmarks failed (exit code {result.returncode})")
        print("")


def generate_comparison_report(results_dir: Path) -> None:
    """Generate a comparison report from all JSON files in ``results_dir``."""

    json_files = sorted(results_dir.glob("benchmark_*.json"))
    if not json_files:
        print("No benchmark_*.json files found to compare.")
        return

    report_path = results_dir / "comparison_report.txt"

    cmd = [
        sys.executable,
        "run_benchmarks.py",
        "--compare",
        "--compare-files",
        *[str(p) for p in json_files],
    ]

    print("=" * 42)
    print("Generating Comparison Report")
    print("=" * 42)

    with report_path.open("w", encoding="utf-8") as f:
        # Stream stdout to both console and file (simple tee behavior)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            f.write(line)
        process.wait()

    print("")
    print("Comparison report saved to:", report_path)


def main() -> int:
    print("=" * 42)
    print("MariaDB Python Connector Benchmark Suite")
    print("=" * 42)
    print("")

    if not check_database_connection():
        return 1

    # Create results directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(f"results_{timestamp}").resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"Results will be saved to: {results_dir}")
    print("")

    # Run benchmarks per driver
    run_driver_benchmarks(results_dir)

    # Generate comparison report
    generate_comparison_report(results_dir)

    print("")
    print("=" * 42)
    print("Benchmark Complete!")
    print("=" * 42)
    print(f"Results saved to: {results_dir}")
    print("")
    print("View detailed results:")
    print(f"  - JSON files: {results_dir / 'benchmark_*.json'}")
    print(f"  - Comparison: {results_dir / 'comparison_report.txt'}")
    print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
