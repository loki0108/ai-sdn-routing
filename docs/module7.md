# Module 7: Mininet Replay of TRIAD's Routing

## Goal
Install TRIAD's routing decision for Experiment C in the real OS-Ken controller and
rerun the Module 2 experiment in Mininet: does the simulator's 0% loss hold on
real packets?

## Files
| File | Role |
|---|---|
| `experiments/plan_routes.py` | Runs a trained TRIAD model on Experiment C (in the simulator) and saves each flow's path to a route plan |
| `results/route_plan.json` | The installed plan (from `results/triad_pen0.01_seed0.pt`) |
| `controller/routing.py` | New: `load_route_plan`, `plan_chooser` (follows the plan, shortest path for all other pairs; checks every planned path is real) |
| `controller/route_installer.py` | Uses a route plan if the `ROUTE_PLAN` environment variable is set; otherwise shortest path, as in Module 2 |

## Key ideas
- **Decide vs deliver:** only the path choice changed; rule installation is untouched.
  The `choose_path` plug-in point from Module 2 is used for the first time.
- **Static replay:** TRIAD decides once for a known traffic pattern, and the controller
  installs the routes before traffic starts. This is **not yet adaptive routing**
  (measuring traffic live and changing rules while running), which is future work.
- **Per-pair routing:** each direction is a separate pair. The plan covers
  h1 → h14, h2 → h13, h3 → h6; their reverse directions keep shortest path.

## The plan (TRIAD, seed 0)
| Flow | Candidate | Path |
|---|---|---|
| h1 → h14 | 2 | s1 → s4 → s5 → s6 → s14 |
| h2 → h13 | 2 | s2 → s8 → s11 → s10 → s13 |
| h3 → h6 | 0 | s3 → s6 (unchanged) |

In the simulator: loss 33.3% → 0.0%, 2 moves.

## Commands
- Plan: `python -m experiments.plan_routes`
- Controller: `ROUTE_PLAN=results/route_plan.json python -m controller.run_controller controller.route_installer`
- Network: `sudo python3 -m mininet_env.build_network --remote`
- Then the Module 2 Experiment C procedure (100-packet queue, UDP 5 Mbps target per
  flow for 60 s), with the second `tc` read taken **after** the load ended.

## Verification: the controller followed the plan
- Rules installed: **1,148** (574 forwarding steps × 2), 4 more than Module 2's 1,144:
  each rerouted flow's path is one link longer.
- Per-switch changes vs Module 2 match the reroute exactly (each hop = 2 rules):

| Switch | Module 2 | Module 7 | Reason |
|---|---|---|---|
| s3 | 80 | 76 | h1 and h2 no longer pass s3 |
| s4, s5 | 104, 96 | 106, 98 | h1's new path |
| s6 | 124 | 122 | h2 no longer passes s6 |
| s8, s10, s11 | 88, 80, 100 | 90, 82, 102 | h2's new path |

- Flow rule on s1 for h1 → h14: `actions=output:4` (towards s4); in Module 2 it was
  `output:3` (towards s3).

## Results (Mininet, single run each)
| Experiment C | Shortest path (Module 2) | TRIAD (Module 7) |
|---|---|---|
| Total loss | 37.7% (30,287 / 80,259 datagrams) | **0.0% (0 / 80,259)** |
| Loss per flow (h1→h14 / h2→h13 / h3→h6) | 2.5% / 41% / 70% | **0% / 0% / 0%** |
| Total received | 9.78 Mbps | **15.72 Mbps** (5.24 per flow) |
| h1 → h14 ping, idle | 60.8 ms | 71.1 ms |
| h1 → h14 ping, under load | 171 ms, 60% ping loss | **70.1 ms, 0% ping loss** (20/20) |
| Queue at s3 → s6 (s3-eth4) | full: backlog 100 of 100 | backlog 5 packets during load, **0 drops** |

- Each flow delivered all 26,753 of its datagrams at 5.24 Mbps.
- s3 → s6 sent 26,828 packets in total, with 0 drops: h3's 26,753 data packets plus a
  few earlier `pingall`, ARP and iperf control packets. It now carries one flow.
- Under load, h1 → h14 delay (70.1 ms) equals its idle delay (71.1 ms): no queueing.
- **Simulator vs Mininet:** the simulator predicted 0.0% loss for TRIAD's paths;
  Mininet measured 0.0%.

### Why the ping is ~70 ms, not 80 ms
The request h1 → h14 follows TRIAD's 4-link path (4 × 10 ms = 40 ms); the reply
h14 → h1 is a different pair, not in the plan, so it uses its 3-link shortest path
(30 ms). Round trip = 40 + 30 = 70 ms. (Module 2: 3 links each way = 60 ms.)

## Takeaways
- TRIAD's routing decision, installed in a real SDN controller, eliminated
  Experiment C's congestion on real packets: loss 37.7% → 0%, loaded ping
  171 ms → 70.1 ms, every flow at its full 5.24 Mbps.
- The full pipeline works end to end: topology → simulator → trained TRIAD →
  route plan → OpenFlow rules → measured improvement in Mininet.
- The simulator's prediction for the improved routing held in Mininet.

## Limitations
- Static replay of one known scenario, not adaptive routing.
- Greedy finds the same solution for Experiment C: this result validates the pipeline
  and the simulator, not TRIAD's advantage over greedy (see Module 6).
- Single Mininet run per routing; the result is clear-cut (0 of 80,259 lost vs
  30,287 of 80,259), but random multi-flow scenarios have not been replayed in Mininet.