# Module 2: Shortest-Path SDN Controller

## Setup
- OS: Ubuntu 24.04.5 LTS, Python 3.12.3
- Mininet 2.3.0, Open vSwitch, OpenFlow 1.3
- Controller framework: OS-Ken 4.2.2 (maintained fork of Ryu), NetworkX 3.7, in a venv
- Topology: NSFNet, 14 nodes, 21 links (RouteNet/KDN dataset version)
- Links: 10 Mbps, 10 ms one-way, queue limit 100 packets; host links unlimited

## Goal
Replace Mininet's basic controller and STP with our own SDN controller that knows
the whole topology and installs shortest paths. This is the **baseline** the AI
must beat. Then load the network to show where shortest-path routing fails.

## Files
| File | Role |
|---|---|
| `topologies/ports.py` | Computes the port map: which switch port leads to which neighbour |
| `mininet_env/build_network.py` | Now builds links with explicit ports from the port map; new `--remote` mode connects switches to our controller |
| `controller/run_controller.py` | Starts OS-Ken apps (OS-Ken 4.2.2 no longer ships the `osken-manager` command) |
| `controller/hello_switch.py` | Test app: installs one "flood everything" rule (loop-free topologies only) |
| `controller/routing.py` | **Decides** paths and turns them into per-switch forwarding steps. No OS-Ken code |
| `controller/route_installer.py` | **Delivers** those steps to the switches as OpenFlow rules |
| `experiments/link_usage.py` | Counts how many routes cross each link, to find the bottleneck |

## Key ideas

### Three ways to forward packets
| | Learning switch (Mininet's basic controller) | OSPF (classic routing) | SDN controller (ours) |
|---|---|---|---|
| Knows the topology? | No: learns addresses by watching traffic | Yes: every router builds its own map | Yes: one central map |
| Who decides paths? | Nobody: floods unknown destinations | Each router runs Dijkstra itself | The controller, for all switches |
| Handles loops? | No → broadcast storm | Yes | Yes |
| Easy to add smarter logic (AI)? | No | Hard: every router must change | Yes: change one program |

### OpenFlow basics
- **OpenFlow** is the protocol between the controller and the switches.
- Each switch has a **flow table** of rules. A rule has a **match** (which packets),
  **actions** (what to do, e.g. "output port 3") and a **priority** (highest wins).
- A **packet-in** is a switch asking the controller what to do with a packet
  that matches no rule. This causes the slower first ping seen in Module 1.
- Controller apps are **event-driven**: we write functions and OS-Ken calls them
  when an event happens (e.g. `EventOFPSwitchFeatures` = a switch connected).
- In OpenFlow, a switch is called a **datapath**; in Mininet, `s1` has id 1.

### Why a port map is needed
A flow rule cannot say "send to s3"; it can only say "send out port 3". So the
controller must know which port leads where. Rule used:
- port 1 on every switch → its own host
- switch-to-switch links → ports 2, 3, 4, ... in the order of the `LINKS` list

`topologies/ports.py` computes this once; **both** Mininet (when building) and the
controller (when routing) use it, so they can never disagree. Verified with
Mininet's `net` command (e.g. `s1-eth3:s3-eth2`).

### Proactive vs reactive
- **Reactive:** wait for a packet-in, then compute and install that path.
- **Proactive (ours):** as soon as each switch connects, install every rule it
  will ever need. No first-packet delay, no flooding, simpler code. NSFNet is small
  (14 × 13 = 182 pairs), so installing everything up front is cheap.

### Why rules match on source AND destination
Classic routing tables only look at the destination. We match on (source,
destination) so each pair can have its **own** path. The AI will later choose
different paths for different pairs (e.g. h1→h14 one way, h2→h14 another) to
spread load. This rule format already supports that.

### ARP and no flooding
ARP ("who has 10.0.0.14?") is a broadcast and caused the storm in Module 1.
Our controller installs ARP rules (`arp_spa` = sender IP, `arp_tpa` = target IP)
along the same paths as IPv4 traffic (`eth_type` 0x0806 for ARP, 0x0800 for IPv4).
No flood rule exists, and packets matching no rule are dropped, so broadcast
storms are impossible.

### "Decide" vs "deliver": where the AI plugs in
- `routing.py` decides paths. `compute_all_routes(topo, choose_path=shortest_path)`
  takes the path-choosing function as a parameter.
- `route_installer.py` only delivers rules and does not care how paths were chosen.
- The AI will replace `shortest_path` with its own path choice; nothing else changes.
  ("Same controller, different brain.")

### Link queue size
Each link direction has a queue. When traffic exceeds 10 Mbps, packets wait in the
queue (delay) and, once it is full, are dropped (loss).
Mininet's default queue is 1,000 packets, far larger than realistic. We size it to
roughly one **bandwidth–delay product**:
10 Mbps × 100 ms = 125 KB ≈ 83 packets → **100 packets** (≈ 120 ms max queueing delay).

## Experiment A: Shortest-path controller on NSFNet
- Commands:
  - Terminal 1: `python -m controller.run_controller controller.route_installer`
  - Terminal 2: `sudo python3 -m mininet_env.build_network --remote`
- Rules installed: **1,144** in total (572 forwarding steps × 2 for IPv4 + ARP),
  exactly as predicted by `routing.py`
- `pingall`: 0% dropped (182/182), with no 40 s STP wait
- h1 → h14: **60 ms every run** (path s1 → s3 → s6 → s14)
- Rules per switch vary widely: s6 has 124, s12 has 52. Shortest path funnels
  many routes through central switches.

| | STP (Module 1) | Shortest-path controller |
|---|---|---|
| Reachability | 182/182 | 182/182 |
| Startup wait | 40 s | none |
| h1 → h14 | 60 or 100 ms (depends on random root) | 60 ms, deterministic |
| Links usable | 13 of 21 | all 21 |
| Flooding | yes (inside the tree) | none |

## Experiment B: Link usage under shortest-path routing
- Command: `python -m experiments.link_usage`
- Total link crossings: **390** (= 572 steps − 182 final host deliveries) ✓
- All 21 links are used, but **unevenly**:
  - busiest: s3–s6, s4–s9, s8–s11 (28 routes each, a three-way tie)
  - quietest: s12–s13 (6 routes)
  - busiest links carry **4.7×** the routes of the quietest
- s3–s6 was chosen as the bottleneck to load (first of the tied links; it also
  touches s6, the switch with the most rules)

## Experiment C: Congesting the bottleneck (s3 → s6)
- Flows chosen so they share **only** the s3 → s6 link:
  h1 → h14 (s1→s3→s6→s14), h2 → h13 (s2→s3→s6→s13), h3 → h6 (s3→s6)
- Traffic: UDP, 5 Mbps per flow for 60 s → 15 Mbps into a 10 Mbps link
- UDP because it sends at a fixed rate (TCP slows down and hides congestion),
  which also makes runs repeatable
- Procedure: warm up (`pingall`) → idle ping → start UDP receivers → start senders
  → `tc` queue snapshot → ping under load → stop receivers → read their reports

### Results (single run, queue = 100 packets)
| Metric | Idle | Under load |
|---|---|---|
| h1 → h14 delay | 60.8 ms | **171 ms** (2.8×) |
| Ping loss | 0% | 60% (only 20 pings, small sample) |
| Queue at s3 → s6 | — | full (backlog 100 of 100 packets) |

| Flow | Sent | Received | Loss |
|---|---|---|---|
| h1 → h14 | 5 Mbps | 5.10 Mbps | 2.5% |
| h2 → h13 | 5 Mbps | 3.08 Mbps | 41% |
| h3 → h6 | 5 Mbps | 1.60 Mbps | 70% |
| **Total** | 15 Mbps | **9.78 Mbps** | **35%** |

- Total delivered ≈ link capacity (10 Mbps): the link was full.
- Overall loss 35% ≈ the excess traffic (15 in, 10 out).
- Loss was **uneven** between flows and changed completely between runs:
  under congestion, who suffers is essentially random.
- Packet accounting at s3-eth4: delivered + dropped = all packets sent, so all loss
  happened at the targeted bottleneck.

### Effect of queue size (same experiment)
| Queue limit | Loaded delay | Overall loss |
|---|---|---|
| 1,000 packets (Mininet default) | 1,258 ms | 35% |
| 100 packets (≈ 1 BDP, used from now on) | 171 ms | 35% |

Queue size changes **how long** packets wait, not **how many** fit through.

## Limitations (honest notes)
- Experiment C numbers are from **single manual runs**; runs vary (one early run
  showed no delay increase, probably a timing issue). An automated script with
  repeated runs and averages is needed before comparing against the AI.
- The ping used only 20 probes, which is too few for a reliable loss estimate.
- The topology is hard-coded (`from topologies import nsfnet`) in the controller.
- No link-failure detection yet (needed for robustness tests later).
- Each cable has 10 Mbps per direction; `link_usage.py` counts both directions together.

## Takeaways
- An SDN controller with a global view fixes both earlier problems: no broadcast
  storm, no STP detours, all links usable, deterministic shortest paths.
- But shortest-path routing **ignores load**: it loads its busiest links 4.7× more
  than its quietest and keeps sending traffic into a full link.
- Under congestion: delay nearly triples (60 → 171 ms), 35% of traffic is lost,
  and loss is distributed unfairly and unpredictably.
- Alternative paths exist, but shortest path never uses them. Choosing paths based
  on the current network state is the job of the AI (GAT + RL).

## Open questions
- (add anything still unclear here)