#!/usr/bin/env python3
"""
Run all TLP simulation experiments.

Iterates over FloatSimdFU opLat/issueLat combos (sum=7) and thread counts,
collects stats, and writes results to JSON.

Usage:
    python3 run_experiments.py [--gem5 <gem5_binary>] [--binary <daxpy_binary>]
                               [--array-size <size>] [--outdir <results_dir>]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

OPLAT_ISSUELAT_COMBOS = [
    (1, 6), (2, 5), (3, 4), (4, 3), (5, 2), (6, 1),
]

THREAD_COUNTS = [1, 2, 4, 8]

DEFAULT_ARRAY_SIZE = 1024

SCRIPT_DIR = Path(__file__).parent
CONFIG_SCRIPT = SCRIPT_DIR / "tlp_simulation.py"


def parse_stats(stats_file):
    stats = {}
    if not os.path.exists(stats_file):
        return stats

    with open(stats_file, "r") as f:
        content = f.read()

    patterns = {
        "simTicks": r"simTicks\s+(\d+)",
        "simOps": r"simOps\s+(\d+)",
        "simInsts": r"simInsts\s+(\d+)",
        "simSeconds": r"simSeconds\s+([\d.e+-]+)",
        "hostSeconds": r"hostSeconds\s+([\d.e+-]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            try:
                stats[key] = int(match.group(1))
            except ValueError:
                stats[key] = float(match.group(1))

    cpu_pattern = re.compile(
        r"system\.cpu(\d*)\."
        r"(numCycles|committedInsts|committedOps|cpi|ipc)"
        r"\s+([\d.e+naninf-]+)"
    )
    per_core = {}
    for m in cpu_pattern.finditer(content):
        core_str = m.group(1)
        core_id = int(core_str) if core_str else 0
        metric = m.group(2)
        val_str = m.group(3)
        try:
            val = int(val_str)
        except ValueError:
            try:
                val = float(val_str)
            except ValueError:
                val = val_str
        per_core.setdefault(core_id, {})[metric] = val

    if per_core:
        stats["per_core"] = per_core

    issued_pattern = re.compile(
        r"system\.cpu(\d*)\.issuedInstType_0::"
        r"(Float\w+|Simd\w+)"
        r"\s+(\d+)"
    )
    float_simd_issued = {}
    for m in issued_pattern.finditer(content):
        core_str = m.group(1)
        core_id = int(core_str) if core_str else 0
        count = int(m.group(3))
        float_simd_issued[core_id] = float_simd_issued.get(core_id, 0) + count

    if float_simd_issued:
        stats["floatsimd_issued"] = float_simd_issued

    return stats


def run_single_experiment(gem5_bin, binary, num_threads, array_size,
                          op_lat, issue_lat, outdir):
    run_name = f"threads{num_threads}_op{op_lat}_iss{issue_lat}"
    run_dir = os.path.join(outdir, run_name)
    os.makedirs(run_dir, exist_ok=True)

    cmd = [
        gem5_bin,
        f"--outdir={run_dir}",
        str(CONFIG_SCRIPT),
        str(binary),
        str(num_threads),
        str(array_size),
        str(op_lat),
        str(issue_lat),
    ]

    print(f"\n{'='*60}")
    print(f"Running: threads={num_threads}, opLat={op_lat}, issueLat={issue_lat}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
        stdout_file = os.path.join(run_dir, "stdout.txt")
        stderr_file = os.path.join(run_dir, "stderr.txt")
        with open(stdout_file, "w") as f:
            f.write(result.stdout)
        with open(stderr_file, "w") as f:
            f.write(result.stderr)

        if result.returncode != 0:
            print(f"  WARNING: gem5 exited with code {result.returncode}")
            print(f"  stderr (last 5 lines):")
            for line in result.stderr.strip().split("\n")[-5:]:
                print(f"    {line}")
        else:
            print(f"  Completed successfully")

        stats_file = os.path.join(run_dir, "stats.txt")
        stats = parse_stats(stats_file)
        stats["run_name"] = run_name
        stats["num_threads"] = num_threads
        stats["op_lat"] = op_lat
        stats["issue_lat"] = issue_lat
        stats["array_size"] = array_size
        stats["returncode"] = result.returncode
        return stats

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 600s")
        return {
            "run_name": run_name,
            "num_threads": num_threads,
            "op_lat": op_lat,
            "issue_lat": issue_lat,
            "array_size": array_size,
            "error": "timeout",
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        return {
            "run_name": run_name,
            "num_threads": num_threads,
            "op_lat": op_lat,
            "issue_lat": issue_lat,
            "array_size": array_size,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gem5",
        default=str(SCRIPT_DIR.parent.parent / "gem5" / "build" / "X86" / "gem5.opt"),
    )
    parser.add_argument(
        "--binary",
        default=str(SCRIPT_DIR / "daxpy_worker"),
    )
    parser.add_argument("--array-size", type=int, default=DEFAULT_ARRAY_SIZE)
    parser.add_argument(
        "--outdir",
        default=str(SCRIPT_DIR.parent / "results"),
    )
    args = parser.parse_args()

    if not os.path.exists(args.gem5):
        print(f"ERROR: gem5 binary not found: {args.gem5}")
        sys.exit(1)
    if not os.path.exists(args.binary):
        print(f"ERROR: daxpy binary not found: {args.binary}")
        sys.exit(1)

    all_results = []

    for num_threads in THREAD_COUNTS:
        for op_lat, issue_lat in OPLAT_ISSUELAT_COMBOS:
            stats = run_single_experiment(
                args.gem5, args.binary, num_threads, args.array_size,
                op_lat, issue_lat, args.outdir,
            )
            all_results.append(stats)

    results_json = os.path.join(args.outdir, "all_results.json")
    with open(results_json, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nAll results saved to {results_json}")

    print("\n" + "=" * 70)
    print("Summary Table")
    print("=" * 70)
    print(f"{'Threads':>8} {'opLat':>6} {'issLat':>7} {'simTicks':>14} {'simInsts':>10}")
    print("-" * 70)
    for r in all_results:
        ticks = r.get("simTicks", "N/A")
        insts = r.get("simInsts", "N/A")
        print(f"{r['num_threads']:>8} {r['op_lat']:>6} {r['issue_lat']:>7} "
              f"{ticks:>14} {insts:>10}")


if __name__ == "__main__":
    main()
