"""
Routing logic: choose paths and turn them into per-switch forwarding steps.

No OS-Ken or Mininet code here, so it can be tested on its own, and the
path-choosing function can later be swapped for the AI (GAT + DQN)
without touching anything else.
"""

import networkx as nx

from topologies.ports import HOST_PORT, build_port_map
from itertools import islice

def build_graph(topo_module):
    """Turn a topology data file into a NetworkX graph."""
    graph = nx.Graph()
    graph.add_nodes_from(range(topo_module.NUM_NODES))
    graph.add_edges_from(topo_module.LINKS)
    return graph


def shortest_path(graph, src, dst):
    """Baseline path choice: fewest links (all links are equal, so this is BFS)."""
    return nx.shortest_path(graph, src, dst)

def k_shortest_paths(graph, src, dst, k=4):
    """
    Up to k loop-free candidate paths from src to dst, shortest first.

    Candidate 0 is always exactly the Module 2 baseline path (shortest_path),
    so "every flow on candidate 0" reproduces the shortest-path controller.
    """
    first = shortest_path(graph, src, dst)
    paths = [first]
    # Yen's algorithm: shortest, next-shortest, ... (no repeated nodes)
    for path in islice(nx.shortest_simple_paths(graph, src, dst), k + 1):
        if len(paths) == k:
            break
        if path != first:
            paths.append(path)
    return paths


def all_candidates(topo_module, k=4):
    """Candidate paths for every (src, dst) pair: dict (src, dst) -> list of paths."""
    graph = build_graph(topo_module)
    return {
        (src, dst): k_shortest_paths(graph, src, dst, k)
        for src in graph.nodes
        for dst in graph.nodes
        if src != dst
    }

def path_to_hops(path, port_map):
    """
    Turn a path of nodes into forwarding steps: a list of (node, out_port).

    Example: path [0, 2, 5, 13] ->
             [(0, 3), (2, 4), (5, 5), (13, 1)]
             i.e. "on node 0 send out port 3, on node 2 out port 4, ..."
    """
    hops = []
    for i, node in enumerate(path):
        if i == len(path) - 1:
            out_port = HOST_PORT                     # last switch: deliver to host
        else:
            out_port = port_map[(node, path[i + 1])]  # towards the next switch
        hops.append((node, out_port))
    return hops


def compute_all_routes(topo_module, choose_path=shortest_path):
    """
    Compute forwarding steps for every (source, destination) pair.

    Returns a dict: (src, dst) -> list of (node, out_port).
    `choose_path` decides the path. This is where the AI will plug in later.
    """
    graph = build_graph(topo_module)
    port_map = build_port_map(topo_module.LINKS)

    routes = {}
    for src in graph.nodes:
        for dst in graph.nodes:
            if src == dst:
                continue
            path = choose_path(graph, src, dst)
            routes[(src, dst)] = path_to_hops(path, port_map)
    return routes


if __name__ == "__main__":
    # Self-check: run `python -m controller.routing` from the project root
    from topologies import nsfnet

    routes = compute_all_routes(nsfnet)
    print(f"{len(routes)} routes computed")

    candidates = all_candidates(nsfnet, k=4)
    for src, dst in [(0, 13), (1, 12)]:
        print(f"\nCandidates h{src + 1} -> h{dst + 1}:")
        for i, path in enumerate(candidates[(src, dst)]):
            route = " -> ".join(f"s{n + 1}" for n in path)
            print(f"  {i}: {route}  ({len(path) - 1} links)")

    counts = [len(c) for c in candidates.values()]
    print(f"\npairs: {len(candidates)}, candidates per pair: min {min(counts)}, max {max(counts)}")