"""
Final results: shortest path vs greedy vs TRIAD on identical scenarios.

TRIAD numbers are the mean +/- standard deviation over the trained seeds
(results/eval_pen0.01_seed*.csv). Shortest path and greedy are deterministic,
so they are re-run once on the same scenarios (seeds 0-49 per load).
Also checks every trained model on Experiment C.

Run: python -m experiments.summarize
"""

import csv
import glob
import statistics
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch

from agents.env import RoutingEnv
from agents.greedy import greedy
from agents.train import TriadPolicy, run_best_actions
from simulator.flow_model import Flow
from topologies import nsfnet

LOADS = (10, 20, 30, 40, 50)
SCENARIOS = 50
TAG = "pen0.01"


def mean_std(values):
    """Mean and sample standard deviation (0 if only one value)."""
    return statistics.mean(values), (statistics.stdev(values) if len(values) > 1 else 0.0)


def run_baselines(env):
    """Shortest path and greedy on seeds 0-49 for each load."""
    rows = {}
    for n in LOADS:
        sp_loss = sp_delay = gr_loss = gr_delay = gr_moves = gr_time = 0.0
        for seed in range(SCENARIOS):
            env.reset(seed, num_flows=n)                   # starts on shortest path
            sp_loss += env.result["total_loss"]
            sp_delay += env.result["mean_delay_ms"]

            start = time.perf_counter()
            choice, moves, _ = greedy(env.model, env.flows, env.candidates)
            gr_time += time.perf_counter() - start
            env.choice = choice
            env._evaluate()
            gr_loss += env.result["total_loss"]
            gr_delay += env.result["mean_delay_ms"]
            gr_moves += moves
        k = SCENARIOS
        rows[n] = {"sp_loss": sp_loss / k, "sp_delay": sp_delay / k,
                   "gr_loss": gr_loss / k, "gr_delay": gr_delay / k,
                   "gr_moves": gr_moves / k, "gr_ms": gr_time / k * 1000}
    return rows


def load_triad_runs():
    """Collect each metric, per load, across all trained seeds."""
    files = sorted(glob.glob(f"results/eval_{TAG}_seed*.csv"))
    runs = {n: {"loss": [], "delay_ms": [], "moves": [], "ms_per_scenario": []} for n in LOADS}
    for path in files:
        with open(path) as f:
            for row in csv.DictReader(f):
                n = int(row["flows"])
                for key in runs[n]:
                    runs[n][key].append(float(row[key]))
    return files, runs


def experiment_c(env):
    """Run every trained model on Experiment C (deterministic best actions)."""
    flows = [Flow(0, 13, 5.0), Flow(1, 12, 5.0), Flow(2, 5, 5.0)]
    print("\nExperiment C with each trained model (shortest path: 33.3% loss, 144.9 ms):")
    for path in sorted(glob.glob(f"results/triad_{TAG}_seed*.pt")):
        policy = TriadPolicy()
        policy.load_state_dict(torch.load(path))
        policy.eval()
        obs = env.reset_with_flows(flows)
        run_best_actions(env, policy, obs)
        print(f"  {path.split('/')[-1]:24s} loss {env.result['total_loss']:5.1%}, "
              f"delay {env.result['mean_delay_ms']:6.1f} ms, {env.steps} moves, "
              f"candidates {env.choice}")


def main():
    env = RoutingEnv(nsfnet, move_penalty=0.01)
    files, triad = load_triad_runs()
    print(f"TRIAD runs found: {len(files)}")
    print("Running shortest path and greedy on the same scenarios...")
    base = run_baselines(env)

    print(f"\nResults ({SCENARIOS} scenarios per load; TRIAD = mean ± std over {len(files)} seeds)")
    print(f"{'flows':>5} | {'loss SP':>7} {'greedy':>7} {'TRIAD':>14} | "
          f"{'delay greedy':>12} {'TRIAD':>14} | {'moves gr':>8} {'TRIAD':>11} | "
          f"{'ms greedy':>9} {'TRIAD':>12}")
    summary = []
    for n in LOADS:
        b = base[n]
        loss_m, loss_s = mean_std(triad[n]["loss"])
        delay_m, delay_s = mean_std(triad[n]["delay_ms"])
        moves_m, moves_s = mean_std(triad[n]["moves"])
        ms_m, ms_s = mean_std(triad[n]["ms_per_scenario"])
        print(f"{n:>5} | {b['sp_loss']:7.1%} {b['gr_loss']:7.1%} "
              f"{loss_m:6.1%} ± {loss_s:5.1%} | "
              f"{b['gr_delay']:12.1f} {delay_m:6.1f} ± {delay_s:5.1f} | "
              f"{b['gr_moves']:8.1f} {moves_m:4.1f} ± {moves_s:4.1f} | "
              f"{b['gr_ms']:9.1f} {ms_m:5.1f} ± {ms_s:4.1f}")
        summary.append({"flows": n, **b,
                        "triad_loss_mean": loss_m, "triad_loss_std": loss_s,
                        "triad_delay_mean": delay_m, "triad_delay_std": delay_s,
                        "triad_moves_mean": moves_m, "triad_moves_std": moves_s,
                        "triad_ms_mean": ms_m, "triad_ms_std": ms_s})

    with open("results/summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    # Plot 1: loss vs load
    plt.figure(figsize=(6, 4))
    plt.plot(LOADS, [r["sp_loss"] * 100 for r in summary], "o-", label="shortest path")
    plt.plot(LOADS, [r["gr_loss"] * 100 for r in summary], "s-", label="greedy")
    plt.errorbar(LOADS, [r["triad_loss_mean"] * 100 for r in summary],
                 yerr=[r["triad_loss_std"] * 100 for r in summary],
                 fmt="^-", capsize=4, label="TRIAD (mean ± std)")
    plt.xlabel("number of flows")
    plt.ylabel("packet loss (%)")
    plt.title("Loss vs load (NSFNet, flow-level simulator)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig("results/loss_vs_load.png", dpi=150)

    # Plot 2: decision time vs load
    plt.figure(figsize=(6, 4))
    plt.plot(LOADS, [r["gr_ms"] for r in summary], "s-", label="greedy")
    plt.errorbar(LOADS, [r["triad_ms_mean"] for r in summary],
                 yerr=[r["triad_ms_std"] for r in summary],
                 fmt="^-", capsize=4, label="TRIAD (mean ± std)")
    plt.xlabel("number of flows")
    plt.ylabel("decision time per scenario (ms)")
    plt.title("Decision time vs load (NSFNet)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig("results/time_vs_load.png", dpi=150)
    print("\nSaved results/summary.csv, results/loss_vs_load.png, results/time_vs_load.png")

    experiment_c(env)


if __name__ == "__main__":
    main()