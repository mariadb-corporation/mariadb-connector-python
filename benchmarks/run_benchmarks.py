#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2012-2014 Monty Program Ab
# Copyright (c) 2015-2025 MariaDB Corporation Ab

"""
Benchmark runner script for comparing mariadb, mariadb_c, pymysql, and mysql-connector-python.

Usage:
    # Run all benchmarks for all drivers
    python run_benchmarks.py
    
    # Run specific benchmark
    python run_benchmarks.py --benchmark select_1
    
    # Run for specific driver
    python run_benchmarks.py --driver mariadb_c
    python run_benchmarks.py --driver mysql_connector
    
    # Save results to JSON
    python run_benchmarks.py --json results.json
    
    # Generate comparison report
    python run_benchmarks.py --compare
"""

import sys
import os
import argparse
import subprocess
import json
from pathlib import Path


BENCHMARKS = [
    'test_bench_do_1.py',
    'test_bench_select_1.py',
    'test_bench_select_1000_rows.py',
    'test_bench_select_100_cols.py',
    'test_bench_do_1000_params.py',
    'test_bench_insert_batch.py',
]

DRIVERS = ['mariadb', 'mariadb_c', 'pymysql', 'mysql_connector']


def run_pytest_benchmark(benchmark_file=None, driver=None, output_json=None):
    """Run pytest-benchmark with specified parameters."""
    
    # Use the current Python interpreter to invoke pytest in a cross-platform
    # way, instead of relying on a "pytest" executable being present on PATH.
    cmd = [sys.executable, '-m', 'pytest', '-v']
    
    # Add benchmark options
    cmd.extend(['--benchmark-only', '--benchmark-warmup=on', '--benchmark-disable-gc'])
    cmd.extend(['--benchmark-min-rounds=2000', '--benchmark-warmup-iterations=200'])
    
    if benchmark_file:
        cmd.append(benchmark_file)
    else:
        # Run all benchmark tests
        cmd.extend([f for f in BENCHMARKS])
    
    if driver:
        # Use exact match to avoid 'mariadb' matching 'mariadb_c'
        if driver == 'mariadb':
            cmd.extend(['-k', 'mariadb and not mariadb_c'])
        else:
            cmd.extend(['-k', driver])
    
    if output_json:
        cmd.extend(['--benchmark-json', output_json])
    
    # Set working directory to benchmarks folder
    benchmarks_dir = Path(__file__).parent
    
    # Set environment variable for driver selection BEFORE running pytest
    env = os.environ.copy()
    if driver == 'mariadb':
        env['MARIADB_PYTHON_CONNECTOR'] = 'python'
    elif driver == 'mariadb_c':
        env['MARIADB_PYTHON_CONNECTOR'] = 'c'
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {benchmarks_dir}")
    if driver in ['mariadb', 'mariadb_c']:
        print(f"MARIADB_PYTHON_CONNECTOR={env.get('MARIADB_PYTHON_CONNECTOR')}")
    print("-" * 80)
    
    result = subprocess.run(cmd, cwd=benchmarks_dir, env=env)
    return result.returncode


def generate_comparison_report(json_files):
    """Generate a comparison report from multiple JSON result files."""
    
    if not json_files:
        print("No JSON files provided for comparison")
        return
    
    results = {}
    for json_file in json_files:
        if not os.path.exists(json_file):
            print(f"Warning: {json_file} not found")
            continue
        
        with open(json_file, 'r') as f:
            data = json.load(f)
            driver_name = Path(json_file).stem.replace('benchmark_', '')
            results[driver_name] = data
    
    if not results:
        print("No valid results to compare")
        return
    
    print("\n" + "=" * 120)
    print("BENCHMARK COMPARISON REPORT")
    print("=" * 120)
    
    # Group benchmarks by base name (without driver suffix)
    benchmark_groups = {}
    for driver_data in results.values():
        for bench in driver_data.get('benchmarks', []):
            # Extract base benchmark name (e.g., "test_select_1" from "test_select_1[mariadb]")
            full_name = bench['name']
            base_name = full_name.split('[')[0] if '[' in full_name else full_name
            
            if base_name not in benchmark_groups:
                benchmark_groups[base_name] = {}
            
            # Extract driver from benchmark name
            if '[' in full_name:
                driver = full_name.split('[')[1].rstrip(']')
            else:
                driver = 'unknown'
            
            benchmark_groups[base_name][driver] = bench['stats']
    
    # Print results grouped by benchmark
    for bench_name in sorted(benchmark_groups.keys()):
        drivers_data = benchmark_groups[bench_name]
        
        # Display benchmark name
        display_name = bench_name.replace('test_bench_', '').replace('_', ' ').title()
        print(f"\n{display_name}")
        print("-" * 120)
        
        # Calculate baseline (fastest driver)
        fastest_ops = 0
        fastest_driver = None
        driver_results = {}
        
        for driver, stats in drivers_data.items():
            mean_ms = stats['mean'] * 1000
            ops = 1000.0 / mean_ms
            driver_results[driver] = {'mean_ms': mean_ms, 'ops': ops, 'stddev': stats['stddev'] * 1000}
            
            if ops > fastest_ops:
                fastest_ops = ops
                fastest_driver = driver
        
        # Print header with wider driver column to accommodate "mysql_connector (Python)"
        print(f"{'Driver':<25} {'Mean (ms)':<15} {'OPS':<15} {'vs Fastest':<20}")
        print("-" * 120)
        
        # Print results sorted by OPS (descending)
        for driver in sorted(driver_results.keys(), key=lambda d: driver_results[d]['ops'], reverse=True):
            data = driver_results[driver]
            mean_ms = data['mean_ms']
            ops = data['ops']
            
            if driver == fastest_driver:
                comparison = "FASTEST"
            else:
                slowdown = fastest_ops / ops
                comparison = f"{slowdown:.2f}x slower"
            
            # Driver name is already formatted with implementation type from pytest
            print(f"{driver:<25} {mean_ms:<15.3f} {ops:<15.2f} {comparison:<20}")
    
    print("\n" + "=" * 120)


def main():
    parser = argparse.ArgumentParser(
        description='Run benchmarks comparing mariadb, mariadb_c, pymysql, and mysql-connector-python'
    )
    parser.add_argument(
        '--benchmark',
        help='Run specific benchmark (e.g., select_1, do_1)',
        choices=[b.replace('test_bench_', '').replace('.py', '') for b in BENCHMARKS]
    )
    parser.add_argument(
        '--driver',
        help='Run benchmarks for specific driver only',
        choices=DRIVERS
    )
    parser.add_argument(
        '--json',
        help='Save results to JSON file'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Generate comparison report from existing JSON files'
    )
    parser.add_argument(
        '--compare-files',
        nargs='+',
        help='JSON files to compare'
    )
    
    args = parser.parse_args()
    
    if args.compare:
        if args.compare_files:
            generate_comparison_report(args.compare_files)
        else:
            # Look for JSON files in current directory
            json_files = list(Path('.').glob('benchmark_*.json'))
            if json_files:
                generate_comparison_report([str(f) for f in json_files])
            else:
                print("No benchmark_*.json files found in current directory")
        return 0
    
    # Determine benchmark file
    benchmark_file = None
    if args.benchmark:
        benchmark_file = f'test_bench_{args.benchmark}.py'
    
    # Run benchmarks
    return run_pytest_benchmark(
        benchmark_file=benchmark_file,
        driver=args.driver,
        output_json=args.json
    )


if __name__ == '__main__':
    sys.exit(main())
