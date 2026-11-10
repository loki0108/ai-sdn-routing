"""
Port numbering for a topology.

Problem this solves: OpenFlow rules say "send out port N", not
"send to switch X". So the controller must know, for every switch,
which port leads to which neighbour.

Rule (Mininet is told to follow it exactly):
  - port 1 on every switch connects to its own host
  - switch-to-switch links get ports 2, 3, 4, ... in the order
    they appear in the topology's LINKS list

Both mininet_env/build_network.py and the controller use this,
so they always agree.
"""

HOST_PORT = 1


def build_port_map(links):
    """
    Return a dict: (a, b) -> port number on switch a that leads to switch b.

    Example: port_map[(0, 2)] == 3 means "on node 0's switch,
    port 3 leads to node 2".
    """
    next_free = {}   # node -> next unused port number on its switch
    port_map = {}

    for a, b in links:
        # A cable has two ends, and each end uses a port on its own switch.
        for this, other in ((a, b), (b, a)):
            port = next_free.get(this, HOST_PORT + 1)   # first switch port is 2
            port_map[(this, other)] = port
            next_free[this] = port + 1

    return port_map


if __name__ == "__main__":
    # Self-check: run `python -m topologies.ports` from the project root
    from topologies import nsfnet

    port_map = build_port_map(nsfnet.LINKS)
    for node in range(nsfnet.NUM_NODES):
        ports = sorted(
            (port, other) for (this, other), port in port_map.items() if this == node
        )
        listing = ", ".join(f"port {p} -> node {o}" for p, o in ports)
        print(f"node {node:2d}: port {HOST_PORT} -> host | {listing}")