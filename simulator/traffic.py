"""
Random traffic generator.

Problem this solves: the AI must practise on many different traffic situations,
not just Experiment C. Each scenario is a random set of flows between distinct
(src, dst) pairs at random rates, fully determined by a seed so that every
routing strategy can be compared on identical scenarios.
"""

import random

from simulator.flow_model import Flow


def random_flows(num_nodes, num_flows, rate_min, rate_max, seed):
    """
    num_flows random flows between distinct (src, dst) pairs.
    Rates are uniform in [rate_min, rate_max] Mbps. Same seed -> same flows.
    """
    rng = random.Random(seed)   # private generator: doesn't disturb other randomness
    pairs = [(s, d) for s in range(num_nodes) for d in range(num_nodes) if s != d]
    chosen = rng.sample(pairs, num_flows)   # no pair repeated
    return [Flow(s, d, round(rng.uniform(rate_min, rate_max), 2)) for s, d in chosen]


if __name__ == "__main__":
    # Calibration: how often is shortest-path routing congested?
    # Run: python -m simulator.traffic
    from controller.routing import build_graph, shortest_path
    from simulator.flow_model import FlowModel
    from topologies import nsfnet

    model = FlowModel(nsfnet)
    graph = build_graph(nsfnet)

    example = random_flows(nsfnet.NUM_NODES, 5, 1.0, 5.0, seed=0)
    print("Example scenario (seed 0, 5 flows):")
    for f in example:
        print(f"  h{f.src + 1} -> h{f.dst + 1}: {f.rate} Mbps")
    again = random_flows(nsfnet.NUM_NODES, 5, 1.0, 5.0, seed=0)
    print(f"Same seed gives the same flows: {again == example}")

    scenarios = 200
    print(f"\nShortest-path routing, {scenarios} random scenarios per setting:")
    for num_flows in (10, 20, 30, 40, 50):
        congested = 0
        total_loss = 0.0
        for seed in range(scenarios):
            flows = random_flows(nsfnet.NUM_NODES, num_flows, 1.0, 5.0, seed)
            paths = [shortest_path(graph, f.src, f.dst) for f in flows]
            out = model.evaluate(flows, paths)
            if out["max_utilisation"] > 1.0:
                congested += 1
            total_loss += out["total_loss"]
        print(f"  {num_flows:2d} flows: congested in {congested / scenarios:4.0%} "
              f"of scenarios, mean loss {total_loss / scenarios:5.1%}")