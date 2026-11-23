"""
Route installer: delivers routes to the switches as OpenFlow rules.

Routes are decided in controller/routing.py. This app only turns them
into rules and installs them when each switch connects (proactive).
It does not care HOW paths were chosen, so it stays unchanged when the
AI replaces shortest-path routing.

By default every pair uses its shortest path. To install a route plan
(e.g. paths chosen by TRIAD, from experiments/plan_routes.py), set the
ROUTE_PLAN environment variable; pairs not in the plan keep shortest path:

    ROUTE_PLAN=results/route_plan.json python -m controller.run_controller controller.route_installer

Packets that match no rule are dropped: no flooding, so no broadcast storms.
"""

import os
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3

from controller.routing import compute_all_routes, load_route_plan, plan_chooser
from topologies import nsfnet

ETH_TYPE_IPV4 = 0x0800
ETH_TYPE_ARP = 0x0806


def host_ip(node):
    """Topology node number -> its host's IP (node 0 -> h1 -> 10.0.0.1)."""
    return f"10.0.0.{node + 1}"


class RouteInstaller(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Decide all routes once, at startup: a route plan if given, else shortest path
        plan_file = os.environ.get("ROUTE_PLAN")
        if plan_file:
            plan = load_route_plan(plan_file)
            routes = compute_all_routes(nsfnet, choose_path=plan_chooser(plan))
            self.logger.info("Using route plan %s (%d planned pairs)", plan_file, len(plan))
        else:
            routes = compute_all_routes(nsfnet)
            self.logger.info("Using shortest-path routing")

        # Regroup by switch: node -> list of (src, dst, out_port)
        self.rules_for = {}
        for (src, dst), hops in routes.items():
            for node, out_port in hops:
                self.rules_for.setdefault(node, []).append((src, dst, out_port))

        self.logger.info("Computed %d routes", len(routes))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_connected(self, ev):
        """When a switch connects, install every rule it needs."""
        datapath = ev.msg.datapath
        node = datapath.id - 1   # switch s1 has id 1 -> topology node 0

        rules = self.rules_for.get(node, [])
        for src, dst, out_port in rules:
            self.install_rule(datapath, ETH_TYPE_IPV4, src, dst, out_port)
            self.install_rule(datapath, ETH_TYPE_ARP, src, dst, out_port)

        self.logger.info("s%d connected: installed %d rules", datapath.id, 2 * len(rules))

    def install_rule(self, datapath, eth_type, src, dst, out_port):
        """Install one rule: packets of this type from src to dst -> out_port."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        if eth_type == ETH_TYPE_IPV4:
            match = parser.OFPMatch(
                eth_type=eth_type, ipv4_src=host_ip(src), ipv4_dst=host_ip(dst)
            )
        else:  # ARP: its addresses live in different fields
            match = parser.OFPMatch(
                eth_type=eth_type, arp_spa=host_ip(src), arp_tpa=host_ip(dst)
            )

        actions = [parser.OFPActionOutput(out_port)]
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]
        rule = parser.OFPFlowMod(
            datapath=datapath, priority=10, match=match, instructions=instructions
        )
        datapath.send_msg(rule)