"""
Hello-switch: the smallest useful controller app.

When a switch connects, log it and install one rule: flood every packet.
Only safe on loop-free topologies (e.g. Mininet's 2-host default),
since flooding is exactly what causes broadcast storms.
"""

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3


class HelloSwitch(app_manager.OSKenApp):
    # We speak OpenFlow 1.3 with the switches
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_connected(self, ev):
        """Runs automatically each time a switch connects."""
        datapath = ev.msg.datapath          # the switch that just connected
        ofproto = datapath.ofproto          # OpenFlow constants (port numbers etc.)
        parser = datapath.ofproto_parser    # builds OpenFlow messages

        self.logger.info("Switch connected: id=%s", datapath.id)

        # Build the rule: "match every packet -> flood it"
        match = parser.OFPMatch()  # empty match = matches everything
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]
        rule = parser.OFPFlowMod(
            datapath=datapath,
            priority=0,
            match=match,
            instructions=instructions,
        )

        datapath.send_msg(rule)   # send the rule to the switch
        self.logger.info("  installed rule on switch %s: flood every packet", datapath.id)