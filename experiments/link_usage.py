"""
Count how many routes cross each link under a routing strategy.

Problem this solves: shows WHERE routing concentrates traffic, i.e. which
link is the bottleneck, which flows cross it, and which links sit idle.
Later we run the same analysis on the AI's routes and compare.
"""

from collections import Counter

from controller.routing import compute_all_routes
from topologies import nsfnet


def route_nodes(hops):
    """Forwarding steps [(node, port), ...] -> just the nodes [node, ...]."""
    return [node for node, _ in hops]


def link_usage(routes):
    """Return a Counter: link (a, b) with a < b -> number of routes crossing it."""
    usage = Counter()
    for hops in routes.values():
        nodes = route_nodes(hops)
        for a, b in zip(nodes, nodes[1:]):        # consecutive pairs = links crossed
            usage[tuple(sorted((a, b)))] += 1     # (2,5) and (5,2) count as one link
    return usage


def routes_through(routes, link):
    """List the (src, dst) pairs whose route crosses `link` (either direction)."""
    a, b = link
    pairs = []
    for (src, dst), hops in routes.items():
        nodes = route_nodes(hops)
        crossed = set(zip(nodes, nodes[1:]))
        if (a, b) in crossed or (b, a) in crossed:
            pairs.append((src, dst))
    return pairs


if __name__ == "__main__":
    routes = compute_all_routes(nsfnet)
    usage = link_usage(routes)

    print("Routes crossing each link (shortest-path routing):")
    for (a, b), count in usage.most_common():
        print(f"  s{a + 1:<2} - s{b + 1:<2}: {count:3d}")

    total = sum(usage.values())
    unused = [l for l in nsfnet.LINKS if tuple(sorted(l)) not in usage]
    print(f"total link crossings: {total}")
    print(f"links used by no route: {len(unused)}")

    busiest, count = usage.most_common(1)[0]
    pairs = routes_through(routes, busiest)
    print(f"\nBusiest link s{busiest[0] + 1} - s{busiest[1] + 1} ({count} routes):")
    print("  " + ", ".join(f"h{s + 1}->h{d + 1}" for s, d in pairs))