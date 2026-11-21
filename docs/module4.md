# Module 4: Candidate Paths, Traffic Generator, Greedy Baseline

## Goal
Give routing strategies **choices** (candidate paths), **many situations** to be
tested on (random traffic), and a **strong simple baseline** (greedy) that the AI
must match or beat, not just shortest path.

## Files
| File | Role |
|---|---|
| `controller/routing.py` | New: `k_shortest_paths`, `all_candidates` (K = 4 candidates per pair) |
| `simulator/traffic.py` | Seeded random traffic generator, plus a calibration run |
| `agents/greedy.py` | Greedy hill-climbing baseline, plus Experiment C and a load sweep |

## Key ideas

### Candidate paths
- Each (source, destination) pair gets its **K = 4 shortest loop-free paths**
  (Yen's algorithm via `nx.shortest_simple_paths`).
- **Candidate 0 is forced to be exactly the Module 2 shortest path**, so
  "every flow on candidate 0" reproduces the baseline. Needed because ties
  between equal-length paths could otherwise be broken differently.
- All 182 pairs have 4 candidates on NSFNet.
- A routing decision is then a list `choice`: `choice[i]` = the candidate flow i uses.
- Not every alternative helps: e.g. h1 → h14's candidate 1 (s1→s2→s3→s6→s14)
  is longer **and** still crosses the congested s3 → s6 link.
- Coordination matters: h1's candidate 3 and h2's candidate 2 both use
  s2 → s8 → s11. Moving both there recreates the jam (each link at 100%).

### Traffic generator
- A scenario = random flows between **distinct** (src, dst) pairs
  (one flow per pair, matching the controller's per-pair rules).
- Rates uniform in **1–5 Mbps**: one flow never fills a link alone, so congestion
  comes only from sharing, which routing can fix.
- Fully determined by a **seed** (`random.Random(seed)`): every strategy is compared
  on identical scenarios, and any scenario can be recreated exactly.

Calibration (shortest path, 200 scenarios per setting, seeds 0–199):

| Flows | Congested scenarios | Mean loss |
|---|---|---|
| 10 | 20% | 1.2% |
| 20 | 82% | 5.6% |
| 30 | 100% | 12.1% |
| 40 | 100% | 20.3% |
| 50 | 100% | 29.3% |

At 20 flows the network is only ~31% utilised on average (rough estimate:
20 flows × 3 Mbps × 2.14 links ÷ 420 Mbps total capacity), yet shortest path is
congested in 82% of scenarios: **the capacity exists, shortest path puts traffic
in the wrong places.**

Choice for later: train on a **random 10–30 flows per scenario** (light to heavy),
evaluate separately at fixed loads.

### Greedy baseline (hill climbing)
1. Start from shortest path (all flows on candidate 0)
2. Try every single move (each flow → each of its other candidates), scored by the simulator
3. Apply the move that lowers cost most; cost = (total loss, then mean delay)
4. Repeat until no single move helps

Known weakness: can get **stuck** where only a combination of moves would help.

## Results (simulator)

### Experiment C
| | Loss | Mean one-way delay |
|---|---|---|
| Shortest path | 33.3% | 144.9 ms |
| Greedy (2 moves, 28 evaluations) | **0.0%** | **33.6 ms** |

Greedy moved h1 → s1→s4→s5→s6→s14 and h2 → s2→s8→s11→s10→s13: different escape
routes, avoiding the coordination trap. This matches the reroute predicted in the
TRIAD proposal.

### Random scenarios (50 per load, means)
Note: 50 scenarios per load (seeds 0–49), fewer than the 200 used for calibration,
so the shortest-path losses differ slightly from the calibration table
(e.g. 0.6% vs 1.2% at 10 flows). Both strategies are always compared on the
same scenarios.

| Flows | Loss SP → greedy | Delay SP → greedy (ms) | Moves | Evaluations | Time / scenario |
|---|---|---|---|---|---|
| 10 | 0.6% → 0.0% | 34.2 → 24.8 | 1.4 | 72 | 2.3 ms |
| 20 | 5.5% → 0.0% | 69.4 → 29.5 | 3.9 | 295 | 15.2 ms |
| 30 | 12.5% → 1.5% | 106.3 → 56.1 | 7.0 | 721 | 52.1 ms |
| 40 | 20.6% → 6.3% | 142.5 → 105.9 | 9.4 | 1,249 | 113.1 ms |
| 50 | 30.3% → 15.1% | 172.6 → 158.4 | 11.2 | 1,834 | 197.9 ms |

## Takeaways
- Load-aware rerouting removes almost all loss that shortest path causes, on the
  same links: greedy reaches 0% mean loss up to 20 flows.
- Greedy struggles under heavy load: 6.3% loss left at 40 flows, 15.1% at 50.
  How much of this is avoidable is not yet known (at 50 flows the network is
  ~76% utilised on average, so some loss is unavoidable).
- Greedy's cost grows roughly quadratically: 5× more flows → 25× more evaluations,
  86× more time.
- **Target for TRIAD:** match greedy at light/medium load, do better under heavy
  load, decide far more cheaply (one forward pass per move), and transfer to
  unseen topologies.

## Limitations
- All results are from the flow-level simulator (Mininet replay comes later).
- 198 ms per decision is still fast on NSFNet; the cost argument needs a larger
  topology (e.g. GEANT, 24 nodes) to be convincing.
- No reference for the best achievable loss yet (e.g. a stronger search) to show
  how much of greedy's remaining loss is avoidable.