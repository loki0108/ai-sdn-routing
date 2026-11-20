"""
Flow-level (fluid) network model.

Problem this solves: Mininet sends real packets and needs about a minute per
experiment. Training an AI needs thousands of evaluations, so this module
computes link loads, loss and delay from flow RATES, in microseconds.

Model:
  1. load on a directed link  = sum of rates of flows crossing it
  2. link drop fraction       = max(0, 1 - capacity / load)
  3. flow delivered fraction  = PRODUCT of (1 - drop) over its links
  4. flow delay               = SUM of (propagation + queueing) over its links
  5. path spare capacity      = MINIMUM of (capacity - load) over its links

Simplifications (stated in the report):
  - fluid rates, not individual packets
  - every flow on an overloaded link loses the same fraction
  - each flow's offered rate is used on every link of its path
    (exact when no flow crosses more than one overloaded link)
"""

from dataclasses import dataclass

PACKET_BITS = 1500 * 8   # a full-size Ethernet packet, in bits


@dataclass
class Flow:
    src: int      # topology node number (0-based)
    dst: int
    rate: float   # offered rate in Mbps


class FlowModel:
    def __init__(self, topo_module):
        self.capacity = topo_module.LINK_BW_MBPS        # Mbps per direction
        self.prop_delay = topo_module.LINK_DELAY_MS     # ms per link

        # Time to put one packet onto a link (ms): 1500 B at 10 Mbps = 1.2 ms
        self.tx_time = PACKET_BITS / (self.capacity * 1e6) * 1000
        # A full queue: every packet ahead must be sent first (~120 ms)
        self.max_queue_delay = topo_module.LINK_QUEUE_PKTS * self.tx_time

        # Every cable is two directed links, each with its own capacity
        self.links = set()
        for a, b in topo_module.LINKS:
            self.links.add((a, b))
            self.links.add((b, a))

    def queue_delay(self, load):
        """Waiting time (ms) in a link's queue, given the load on it (Mbps)."""
        utilisation = load / self.capacity
        if utilisation >= 1.0:
            return self.max_queue_delay   # overloaded: the queue stays full
        # M/M/1 waiting time: rho / (1 - rho) x packet time, capped at a full queue
        wait = utilisation / (1 - utilisation) * self.tx_time
        return min(wait, self.max_queue_delay)

    def evaluate(self, flows, paths):
        """
        flows: list of Flow
        paths: list of node lists; paths[i] is the path of flows[i]
        Returns a dict with link loads, per-flow results and network totals.
        """
        # Step 1: link loads
        load = {link: 0.0 for link in self.links}
        for flow, path in zip(flows, paths):
            for link in zip(path, path[1:]):
                load[link] += flow.rate

        # Step 2: drop fraction on each link (0 unless overloaded)
        drop = {}
        for link, x in load.items():
            drop[link] = max(0.0, 1 - self.capacity / x) if x > 0 else 0.0

        # Steps 3-5: per-flow results along each path
        results = []
        for flow, path in zip(flows, paths):
            delivered = 1.0           # product
            delay = 0.0               # sum
            spare = float("inf")      # minimum
            for link in zip(path, path[1:]):
                delivered *= 1 - drop[link]
                delay += self.prop_delay + self.queue_delay(load[link])
                spare = min(spare, self.capacity - load[link])
            results.append({
                "src": flow.src,
                "dst": flow.dst,
                "rate": flow.rate,
                "path": path,
                "loss": 1 - delivered,
                "delay_ms": delay,
                "spare_mbps": spare,
            })

        # Network totals (weighted by each flow's rate)
        total_rate = sum(f.rate for f in flows)
        if total_rate > 0:
            total_loss = sum(r["rate"] * r["loss"] for r in results) / total_rate
            mean_delay = sum(r["rate"] * r["delay_ms"] for r in results) / total_rate
        else:
            # No traffic at all (e.g. probing an idle path): nothing can be lost,
            # and the delay is a plain average
            total_loss = 0.0
            mean_delay = (sum(r["delay_ms"] for r in results) / len(results)
                          if results else 0.0)

        return {
            "load": load,
            "flows": results,
            "total_loss": total_loss,
            "mean_delay_ms": mean_delay,
            "max_utilisation": max(load.values()) / self.capacity,
        }


if __name__ == "__main__":
    # Validation: reproduce Experiment C (run: python -m simulator.flow_model)
    from controller.routing import build_graph, shortest_path
    from topologies import nsfnet

    model = FlowModel(nsfnet)
    graph = build_graph(nsfnet)

    flows = [Flow(0, 13, 5.0), Flow(1, 12, 5.0), Flow(2, 5, 5.0)]
    paths = [shortest_path(graph, f.src, f.dst) for f in flows]
    out = model.evaluate(flows, paths)

    print("Loaded links:")
    for (a, b), x in sorted(out["load"].items(), key=lambda item: -item[1]):
        if x > 0:
            print(f"  s{a + 1} -> s{b + 1}: {x:.1f} Mbps ({x / model.capacity:.0%})")

    print("\nFlows:")
    for r in out["flows"]:
        route = " -> ".join(f"s{n + 1}" for n in r["path"])
        print(f"  h{r['src'] + 1} -> h{r['dst'] + 1}: loss {r['loss']:.1%}, "
              f"one-way delay {r['delay_ms']:.1f} ms  ({route})")

    print(f"\nTotal loss: {out['total_loss']:.1%}")
    print(f"Max link utilisation: {out['max_utilisation']:.0%}")

    # Ping round trip h1 -> h14: forward delay (loaded) + reverse path (idle)
    reverse = model.evaluate([Flow(13, 0, 0.0)], [list(reversed(paths[0]))])
    rtt = out["flows"][0]["delay_ms"] + reverse["flows"][0]["delay_ms"]
    print(f"h1 -> h14 round trip: {rtt:.0f} ms   (Mininet measured: 171 ms)")