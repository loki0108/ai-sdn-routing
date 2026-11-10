"""
Routing logic: choose paths and turn them into per-switch forwarding steps.

No OS-Ken or Mininet code here, so it can be tested on its own, and the
path-choosing function can later be swapped for the AI (GAT + DQN)
without touching anything else.
"""

import networkx as nx

from topologies.ports import HOST_PORT, build_port_map


def build_graph(topo_module):
    """Turn a topology data file into a NetworkX graph."""
    graph = nx.Graph()
    graph.add_nodes_from(range(topo_module.NUM_NODES))
    graph.add_edges_from(topo_module.LINKS)
    return graph


def shortest_path(graph, src, dst):
    """Baseline path choice: fewest links (all links are equal, so this is BFS)."""
    return nx.shortest_path(graph, src, dst)


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

    hops = routes[(0, 13)]
    print("h1 -> h14 path:", " -> ".join(f"s{node + 1}" for node, _ in hops))
    for node, port in hops:
        print(f"  on s{node + 1}: send out port {port}")

    total_steps = sum(len(h) for h in routes.values())
    print(f"forwarding steps across all routes: {total_steps}")