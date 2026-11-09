"""
NSFNet topology: the 'floor plan' of our network.

14 nodes (cities), 21 bidirectional links.
Numbering follows the RouteNet / KDN datasets: nodes 0..13.

This file contains ONLY data. It does not import Mininet,
so the simulator and the GAT model can reuse it too.
"""

NAME = "NSFNet"

NUM_NODES = 14

# Each pair (a, b) is one cable between node a and node b.
# Links are bidirectional: (0, 1) means 0 <-> 1.
LINKS = [
    (0, 1), (0, 2), (0, 3),
    (1, 2), (1, 7),
    (2, 5),
    (3, 4), (3, 8),
    (4, 5), (4, 6),
    (5, 12), (5, 13),
    (6, 7),
    (7, 10),
    (8, 9), (8, 11),
    (9, 10), (9, 12),
    (10, 11), (10, 13),
    (11, 12),
]

# Default link properties (same for every link, for now).
LINK_BW_MBPS = 10      # bandwidth in Mbit/s
LINK_DELAY_MS = 10     # one-way propagation delay in ms


def neighbours(node):
    """Return the sorted list of nodes directly connected to `node`."""
    result = []
    for a, b in LINKS:
        if a == node:
            result.append(b)
        elif b == node:
            result.append(a)
    return sorted(result)


if __name__ == "__main__":
    # Quick self-check: run `python3 topologies/nsfnet.py`
    print(f"{NAME}: {NUM_NODES} nodes, {len(LINKS)} links")
    for node in range(NUM_NODES):
        print(f"  node {node:2d} -> neighbours {neighbours(node)}")