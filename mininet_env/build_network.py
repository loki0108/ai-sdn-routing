"""
Build a topology from topologies/ inside Mininet.

Run from the project root:
    sudo python3 -m mininet_env.build_network          # basic controller (expect loops!)
    sudo python3 -m mininet_env.build_network --stp    # Spanning Tree, no controller
    sudo python3 -m mininet_env.build_network --remote # connect to a controller you run separately
"""

import argparse
import time

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.node import OVSBridge, OVSSwitch, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel, info

from topologies import nsfnet
from topologies.ports import HOST_PORT, build_port_map

from functools import partial


def switch_name(node):
    """Topology node number (0-based) -> Mininet switch name (s1, s2, ...)."""
    return f"s{node + 1}"


def host_name(node):
    """Topology node number (0-based) -> Mininet host name (h1, h2, ...)."""
    return f"h{node + 1}"


class TopologyFromData(Topo):
    """Turns a topology data file (like nsfnet.py) into a Mininet network."""

    def build(self, topo_module, stp=False):
        port_map = build_port_map(topo_module.LINKS)

        # One switch + one host per node, connected by an unlimited access link.
        # The host plugs into port HOST_PORT (1) on its switch.
        for node in range(topo_module.NUM_NODES):
            self.addSwitch(switch_name(node), stp=stp)
            self.addHost(host_name(node))
            self.addLink(host_name(node), switch_name(node), port2=HOST_PORT)

        # The real network: switch-to-switch links with bandwidth and delay,
        # using exactly the port numbers from the port map.
        for a, b in topo_module.LINKS:
            self.addLink(
                switch_name(a),
                switch_name(b),
                port1=port_map[(a, b)],   # port on a's switch leading to b
                port2=port_map[(b, a)],   # port on b's switch leading to a
                bw=topo_module.LINK_BW_MBPS,
                delay=f"{topo_module.LINK_DELAY_MS}ms",
                max_queue_size=topo_module.LINK_QUEUE_PKTS,
            )

def wait_for_stp(seconds):
    """Spanning Tree needs ~30 s before ports start forwarding. Show a countdown."""
    for remaining in range(seconds, 0, -1):
        print(f"\r*** Waiting for Spanning Tree to settle: {remaining:2d} s ",
              end="", flush=True)
        time.sleep(1)
    print("\r*** Spanning Tree ready." + " " * 30)

def main():
    parser = argparse.ArgumentParser(description="Build a topology in Mininet")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--stp",
        action="store_true",
        help="use Spanning Tree switches instead of a controller",
    )
    mode.add_argument(
        "--remote",
        action="store_true",
        help="connect switches to an external controller at 127.0.0.1:6653 (OpenFlow 1.3)",
    )
    args = parser.parse_args()

    setLogLevel("info")
    topo = TopologyFromData(topo_module=nsfnet, stp=args.stp)

    if args.stp:
        # Standalone switches running Spanning Tree, no controller
        net = Mininet(topo=topo, link=TCLink, switch=OVSBridge, controller=None)
    elif args.remote:
        # Our own controller (e.g. controller.route_installer), running separately
        net = Mininet(
            topo=topo,
            link=TCLink,
            switch=partial(OVSSwitch, protocols="OpenFlow13"),
            controller=partial(RemoteController, ip="127.0.0.1", port=6653),
        )
    else:
        # Mininet's basic controller (a simple learning switch)
        net = Mininet(topo=topo, link=TCLink)

    net.start()

    if args.stp:
        wait_for_stp(40)

    CLI(net)     # hand control to you: the mininet> prompt
    net.stop()   # clean up when you type 'exit'


if __name__ == "__main__":
    main()