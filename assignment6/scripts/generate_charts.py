#!/usr/bin/env python3
"""
Generate charts from TLP simulation results.

Reads results/all_results.json and produces visualization charts.
"""

import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).parent
RESULTS_DIR = SCRIPT_DIR.parent / "results"
IMAGES_DIR = SCRIPT_DIR.parent / "images"


def load_results():
    results_file = RESULTS_DIR / "all_results.json"
    if not results_file.exists():
        print(f"ERROR: {results_file} not found. Run experiments first.")
        sys.exit(1)
    with open(results_file) as f:
        return json.load(f)


def plot_sim_ticks_heatmap(results):
    thread_counts = sorted(set(r["num_threads"] for r in results))
    configs = sorted(set((r["op_lat"], r["issue_lat"]) for r in results))

    data = np.zeros((len(thread_counts), len(configs)))
    for r in results:
        ti = thread_counts.index(r["num_threads"])
        ci = configs.index((r["op_lat"], r["issue_lat"]))
        data[ti][ci] = r.get("simTicks", 0)

    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(data, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels([f"op={c[0]}\niss={c[1]}" for c in configs])
    ax.set_yticks(range(len(thread_counts)))
    ax.set_yticklabels([f"{t} threads" for t in thread_counts])
    ax.set_xlabel("FloatSimdFU Configuration (opLat/issueLat)")
    ax.set_ylabel("Thread Count")
    ax.set_title("Simulation Ticks by Configuration")

    for i in range(len(thread_counts)):
        for j in range(len(configs)):
            val = data[i][j]
            if val > 0:
                ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                        fontsize=7, color="black" if val < data.max() * 0.7 else "white")

    plt.colorbar(im, label="simTicks")
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "sim_ticks_heatmap.png", dpi=150)
    plt.close()
    print("  Created sim_ticks_heatmap.png")


def plot_speedup(results):
    thread_counts = sorted(set(r["num_threads"] for r in results))
    configs = sorted(set((r["op_lat"], r["issue_lat"]) for r in results))

    baseline = {}
    for r in results:
        if r["num_threads"] == 1:
            baseline[(r["op_lat"], r["issue_lat"])] = r.get("simTicks", 1)

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(configs))
    width = 0.18
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(thread_counts)))

    for idx, tc in enumerate(thread_counts):
        speedups = []
        for cfg in configs:
            base = baseline.get(cfg, 1)
            for r in results:
                if r["num_threads"] == tc and (r["op_lat"], r["issue_lat"]) == cfg:
                    ticks = r.get("simTicks", base)
                    speedups.append(base / ticks if ticks > 0 else 0)
                    break
            else:
                speedups.append(0)
        ax.bar(x + idx * width, speedups, width, label=f"{tc} threads",
               color=colors[idx])

    ax.set_xticks(x + width * (len(thread_counts) - 1) / 2)
    ax.set_xticklabels([f"op={c[0]}/iss={c[1]}" for c in configs])
    ax.set_xlabel("FloatSimdFU Configuration")
    ax.set_ylabel("Speedup (relative to 1-thread same config)")
    ax.set_title("Parallel Speedup by FloatSimdFU Design")
    ax.legend()
    ax.axhline(y=1, color="gray", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "speedup_chart.png", dpi=150)
    plt.close()
    print("  Created speedup_chart.png")


def plot_ipc_comparison(results):
    thread_counts = sorted(set(r["num_threads"] for r in results))
    configs = sorted(set((r["op_lat"], r["issue_lat"]) for r in results))

    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()

    for idx, cfg in enumerate(configs):
        ax = axes[idx]
        for r in results:
            if (r["op_lat"], r["issue_lat"]) == cfg and "per_core" in r:
                tc = r["num_threads"]
                ipcs = []
                for core_id in sorted(r["per_core"].keys(), key=int):
                    ipc = r["per_core"][core_id].get("ipc", 0)
                    ipcs.append(ipc)
                if ipcs:
                    ax.bar(
                        [f"C{i}" for i in range(len(ipcs))],
                        ipcs,
                        alpha=0.6,
                        label=f"{tc}T",
                    )

        ax.set_title(f"opLat={cfg[0]}, issueLat={cfg[1]}")
        ax.set_ylabel("IPC")
        ax.legend(fontsize=7)

    plt.suptitle("IPC per Core by Configuration", fontsize=14)
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "ipc_per_core.png", dpi=150)
    plt.close()
    print("  Created ipc_per_core.png")


def plot_ticks_vs_threads(results):
    configs = sorted(set((r["op_lat"], r["issue_lat"]) for r in results))
    thread_counts = sorted(set(r["num_threads"] for r in results))

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = plt.cm.tab10(np.linspace(0, 0.6, len(configs)))

    for idx, cfg in enumerate(configs):
        ticks = []
        for tc in thread_counts:
            for r in results:
                if r["num_threads"] == tc and (r["op_lat"], r["issue_lat"]) == cfg:
                    ticks.append(r.get("simTicks", 0))
                    break
            else:
                ticks.append(0)
        ax.plot(thread_counts, ticks, "o-", label=f"op={cfg[0]}/iss={cfg[1]}",
                color=colors[idx], linewidth=2, markersize=8)

    ax.set_xlabel("Number of Threads")
    ax.set_ylabel("Simulation Ticks")
    ax.set_title("Simulation Time vs Thread Count")
    ax.set_xticks(thread_counts)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "ticks_vs_threads.png", dpi=150)
    plt.close()
    print("  Created ticks_vs_threads.png")


def plot_cpi_comparison(results):
    thread_counts = sorted(set(r["num_threads"] for r in results))
    configs = sorted(set((r["op_lat"], r["issue_lat"]) for r in results))

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(thread_counts))
    width = 0.12
    colors = plt.cm.Set2(np.linspace(0, 1, len(configs)))

    for idx, cfg in enumerate(configs):
        cpis = []
        for tc in thread_counts:
            for r in results:
                if r["num_threads"] == tc and (r["op_lat"], r["issue_lat"]) == cfg:
                    if "per_core" in r and "0" in r["per_core"]:
                        cpis.append(r["per_core"]["0"].get("cpi", 0))
                    elif "per_core" in r and 0 in r["per_core"]:
                        cpis.append(r["per_core"][0].get("cpi", 0))
                    else:
                        ticks = r.get("simTicks", 0)
                        insts = r.get("simInsts", 1)
                        cpis.append(ticks / insts if insts > 0 else 0)
                    break
            else:
                cpis.append(0)
        ax.bar(x + idx * width, cpis, width, label=f"op={cfg[0]}/iss={cfg[1]}",
               color=colors[idx])

    ax.set_xticks(x + width * (len(configs) - 1) / 2)
    ax.set_xticklabels([f"{t}T" for t in thread_counts])
    ax.set_xlabel("Thread Count")
    ax.set_ylabel("CPI (Core 0)")
    ax.set_title("Cycles per Instruction by Configuration")
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(IMAGES_DIR / "cpi_comparison.png", dpi=150)
    plt.close()
    print("  Created cpi_comparison.png")


def main():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    results = load_results()

    valid = [r for r in results if "error" not in r and r.get("simTicks", 0) > 0]
    if not valid:
        print("No valid results found. Check simulation output.")
        sys.exit(1)

    print(f"Loaded {len(valid)} valid results out of {len(results)} total")
    print("Generating charts...")

    plot_sim_ticks_heatmap(valid)
    plot_speedup(valid)
    plot_ticks_vs_threads(valid)
    plot_cpi_comparison(valid)

    if any("per_core" in r for r in valid):
        plot_ipc_comparison(valid)

    print("\nAll charts saved to", IMAGES_DIR)


if __name__ == "__main__":
    main()
