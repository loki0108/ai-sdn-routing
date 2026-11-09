# Module 1: NSFNet in Mininet

## Setup
- OS / kernel: Ubuntu 24.04.5 LTS, kernel 7.0.0-42-generic
- Mininet version: 2.3.0
- Topology: NSFNet, 14 nodes, 21 links (RouteNet/KDN dataset version)
- Links: 10 Mbps, 10 ms one-way; host links unlimited

## Goal
Build NSFNet in Mininet, show how a basic controller fails on a topology with
loops (broadcast storm), and show how Spanning Tree (STP) avoids it, and at what cost.

## Files
- `topologies/nsfnet.py`: the topology as pure data (nodes, links, link bandwidth
  and delay). No Mininet code, so the simulator and the GAT model can reuse it later.
- `mininet_env/build_network.py`: reads a topology file and builds it in Mininet.
  Two modes: basic controller (default) or Spanning Tree (`--stp`).

## Key ideas (in my words)
- **Topology vs. Mininet:** The topology is the "floor plan"; Mininet is the tool
  that builds it. We keep the topology in its own module because three parts need
  it (Mininet, the simulator, and the GAT model), so all three see the same network,
  and switching topologies later is easy.
- **Why host links are unlimited:** Each host represents all users of a city. Each
  city has only one access link, so if that link were the bottleneck, no routing
  decision could help. Keeping access links unlimited makes sure congestion happens
  only on the backbone, where alternative paths exist.
- **The loop problem / broadcast storm:** Some packets are broadcasts (e.g. ARP:
  "who has this IP address?"). A simple switch copies a broadcast out of every port
  except the one it came in on. In a topology with cycles, these copies travel
  around the loops forever and multiply, flooding the network.
- **How STP works and what it costs:** Switches elect a root (the lowest switch ID).
  Each switch keeps only its cheapest path towards the root and blocks its other
  ports, so the active links form a tree with no cycles. Costs: (1) a tree on 14
  switches uses only 13 links, so 8 of NSFNet's 21 links sit idle; (2) traffic must
  follow the tree, so paths between two cities can be longer than the shortest path;
  (3) switch IDs are assigned randomly at startup, so the root, and therefore the
  paths, change between runs.

## Experiment A: basic controller
- Command: `sudo python3 -m mininet_env.build_network`, then `h1 ping -c 3 h14`
- Result: `Destination Host Unreachable`, 100% packet loss
- Why: h1's ARP broadcast (to find h14's address) got trapped in the loops, so h1
  never learned h14's address and the ping was never sent.

## Experiment B: Spanning Tree
- Command: `sudo python3 -m mininet_env.build_network --stp`, wait for STP
  to settle, then `pingall` and `h1 ping -c 3 h14`
- `pingall`: 0% dropped (182/182) in both runs, so every host can reach every other host
- Shortest path h1 → h14: 0 → 2 → 5 → 13 = 3 links, predicted RTT = 3 × 10 ms × 2 = 60 ms
- Run 1: h1 → h14 = 100 ms steady (5 links each way, a detour of 2 extra links)
- Run 2: h1 → h14 = 60 ms steady (the shortest path)
- Why the runs differ: switch IDs are random at each startup, so a different root
  was elected, giving a different tree and different blocked links. In run 2 the
  tree happened to keep the shortest h1 → h14 route; in run 1 it did not.
- Side note: the first ping is slower (206 ms in run 1) because of ARP and switch
  address learning. Running `pingall` first removes this warm-up (run 2's first
  ping was 62.6 ms), but it does not change the steady-state path.

## Takeaways
- Without loop handling, a network with cycles fails completely (broadcast storm).
- STP fixes loops, but blocks 8 of 21 links and can force detours (100 ms vs 60 ms).
- STP's paths depend on a random root election, not on traffic, so they are
  arbitrary. A controller with a global view of the network can choose paths
  deliberately. That is the motivation for Module 2 (shortest-path controller)
  and, later, our AI.

## Open questions
- How GAT, the simulator, and Mininet fit together (to revisit in Modules 3–4)