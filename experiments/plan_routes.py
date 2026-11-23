"""
Plan routes with a trained TRIAD model and save them for the controller.

Problem this solves: the controller (deliver) must install TRIAD's decisions.
This script runs the trained policy on a known scenario (Experiment C) in the
simulator and writes the chosen path of each flow to a route plan file.
Static replay: decided once for a known traffic pattern, installed before traffic starts.

Run: python -m experiments.plan_routes
"""

import argparse
import json

import torch

from agents.env import RoutingEnv
from agents.train import TriadPolicy, run_best_actions
from simulator.flow_model import Flow
from topologies import nsfnet

EXPERIMENT_C = [Flow(0, 13, 5.0), Flow(1, 12, 5.0), Flow(2, 5, 5.0)]


def main():
    parser = argparse.ArgumentParser(description="Plan routes with a trained TRIAD model")
    parser.add_argument("--model", default="results/triad_pen0.01_seed0.pt")
    parser.add_argument("--out", default="results/route_plan.json")
    args = parser.parse_args()

    env = RoutingEnv(nsfnet, move_penalty=0.01)
    policy = TriadPolicy()
    policy.load_state_dict(torch.load(args.model))
    policy.eval()

    obs = env.reset_with_flows(EXPERIMENT_C)
    start_loss = env.result["total_loss"]
    run_best_actions(env, policy, obs)

    plan = {}
    print(f"TRIAD plan for Experiment C ({args.model}):")
    for flow, c in zip(env.flows, env.choice):
        path = env.candidates[(flow.src, flow.dst)][c]
        plan[f"{flow.src}-{flow.dst}"] = path                # JSON keys must be strings
        route = " -> ".join(f"s{n + 1}" for n in path)
        print(f"  h{flow.src + 1} -> h{flow.dst + 1}: candidate {c}  {route}")
    print(f"Simulator: loss {start_loss:.1%} -> {env.result['total_loss']:.1%}, "
          f"delay {env.result['mean_delay_ms']:.1f} ms, {env.steps} moves")

    with open(args.out, "w") as f:
        json.dump({"model": args.model, "scenario": "experiment_c", "paths": plan}, f, indent=2)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()