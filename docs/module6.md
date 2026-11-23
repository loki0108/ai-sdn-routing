# Module 6: PPO Training and Results

## Goal
Train TRIAD with reinforcement learning (PPO) to reroute flows, then compare it
with shortest path and the greedy baseline on identical scenarios.

## Files
| File | Role |
|---|---|
| `agents/triad.py` | Updated: `combine_along_paths` shared by both scoring modes; new `score_entries` for "what-if" features |
| `agents/env.py` | The RL environment: state, actions, reward, episodes |
| `agents/train.py` | Policy (TRIAD + STOP threshold + critic), PPO loop, evaluation, CSV output |
| `experiments/summarize.py` | Final table over all seeds, plots, Experiment C check |

## Key ideas

### RL in routing terms
| RL term | Here |
|---|---|
| State | Current routing (which candidate each flow uses) and the resulting link loads |
| Action | Move one flow to another of its candidates, or STOP |
| Reward | Cost improvement of the move × 10, minus a move penalty |
| Episode | One scenario: start from shortest path, move until STOP (max 20 moves) |

### Reward design
- cost = total loss + 0.0001 × mean delay (ms): 100 ms of delay costs as much as 1% loss
- reward = (cost before − cost after) × 10 − move penalty; STOP gives 0 and ends the episode
- Rewards **telescope**: their sum = (start cost − final cost) × 10 − penalties, so
  maximising total reward = ending with the lowest cost in few moves.
  Verified on Experiment C: sum of rewards +3.4427 = (start − end) × 10 − penalties +3.4427.

### From scores to decisions
- TRIAD scores every candidate of every flow using **"what-if" features**: link loads as
  they would be IF that flow moved there (links already on its path unchanged, new
  links + its rate). Without this, a flow's current path looks worse than it is.
- Value of a move = score(candidate) − score(current path); STOP = one learned threshold.
- Softmax turns these into probabilities. Training **samples** (exploration: can discover
  move sequences greedy never tries); evaluation takes the most likely action.

### PPO
1. Play episodes with the current policy
2. Advantage = return-to-go − critic's prediction (better or worse than expected?)
3. Make better-than-expected actions more likely, worse ones less likely
4. **Clipping** limits each update (probability ratio within 0.8–1.2) for stability

The critic is a small MLP on 4 global numbers (max and mean utilisation, current loss,
number of flows) that predicts expected return.

## Training setup
- Scenarios: random 10–30 flows, rates 1–5 Mbps
- 150 iterations × 16 episodes; Adam, learning rate 1e-3; 4 PPO epochs per update;
  clip 0.2; value loss weight 0.5; entropy bonus 0.01; gradient clipping 0.5
- Training seeds from 100,000 + 10,000 × run seed; evaluation seeds 0–49 (the same
  scenarios as the greedy table), never seen in training
- About 4–6 minutes per run on the lab PC's CPU
- 5 independent runs (seeds 0–4)

## Move penalty experiment (seed 0)
The first run (penalty 0.001) learned to route but never learned to STOP:

| Flows | Penalty 0.001: loss / moves / ms | Penalty 0.01: loss / moves / ms |
|---|---|---|
| 10 | 0.0% / 10.4 / 11.8 | 0.0% / 1.5 / 3.0 |
| 20 | 0.1% / 9.4 / 11.7 | 0.3% / 4.3 / 7.5 |
| 30 | 2.2% / 9.3 / 14.2 | 2.7% / 6.1 / 11.4 |
| 40 | 7.8% / 10.7 / 20.6 | 8.3% / 8.1 / 16.7 |
| 50 | 16.9% / 11.9 / 32.3 | 17.4% / 9.7 / 24.5 |

Penalty 0.01 (a move must improve cost by > 0.001, about 0.1% loss or 10 ms delay) cut
unnecessary moves by ~85% at light load (10.4 → 1.5) for at most 0.5 percentage points
of extra loss. Used from then on: in a real network, every move rewrites switch rules.

Reference returns (100 scenarios, 10–30 flows): penalty 0.001: random −0.876, greedy +0.534;
penalty 0.01: random −1.019, greedy +0.496.

## Results (simulator; 50 scenarios per load; TRIAD = mean ± std over 5 seeds)
| Flows | Loss SP | Loss greedy | Loss TRIAD | Delay greedy (ms) | Delay TRIAD (ms) | Moves greedy | Moves TRIAD | Time greedy (ms) | Time TRIAD (ms) |
|---|---|---|---|---|---|---|---|---|---|
| 10 | 0.6% | 0.0% | 0.0% ± 0.0 | 24.8 | 25.4 ± 0.4 | 1.4 | 1.6 ± 0.4 | 2.2 | 2.6 ± 0.3 |
| 20 | 5.5% | 0.0% | 0.3% ± 0.2 | 29.5 | 32.9 ± 1.5 | 3.9 | 3.9 ± 0.6 | 15.3 | 5.8 ± 1.3 |
| 30 | 12.5% | 1.5% | 2.7% ± 0.3 | 56.1 | 60.6 ± 3.3 | 7.0 | 6.0 ± 0.5 | 52.0 | 10.4 ± 1.6 |
| 40 | 20.6% | 6.3% | 8.2% ± 0.2 | 105.9 | 103.7 ± 1.8 | 9.4 | 8.0 ± 0.6 | 113.7 | 14.9 ± 2.2 |
| 50 | 30.3% | 15.1% | 17.5% ± 0.4 | 158.4 | 152.1 ± 3.1 | 11.2 | 9.7 ± 0.6 | 199.6 | 24.8 ± 4.2 |

Share of greedy's loss reduction captured by TRIAD:

| Flows | 20 | 30 | 40 | 50 |
|---|---|---|---|---|
| Share | 94% | 89% | 87% | 84% |

Decision-time speed-up of TRIAD over greedy: ≈1× at 10 flows, 2.6× at 20, 5.0× at 30,
7.6× at 40, 8.0× at 50.

Plots: `results/loss_vs_load.png`, `results/time_vs_load.png`, learning curves
`results/curve_pen0.01_seed*.png`.

### Experiment C (never seen in training: 3 flows, training used 10–30)
All 5 models: **0.0% loss, 33.6 ms mean delay, 2 moves, candidates [2, 2, 0]**:
h1 → s1→s4→s5→s6→s14, h2 → s2→s8→s11→s10→s13, h3 unchanged. The same coordinated
solution as greedy, avoiding the s2→s8→s11 trap that per-flow widest-path routing
falls into.

## Takeaways
- TRIAD learns: mean return rises from around or below the random policy's level
  towards greedy's, consistently across 5 seeds (loss std ≤ 0.4 percentage points).
- TRIAD captures 84–94% of greedy's loss reduction while deciding 2.6–8× faster
  (from 20 flows up); the speed advantage grows with load.
- TRIAD does not beat greedy on loss; it has lower delay than greedy at 40–50 flows
  and makes fewer moves under heavy load.
- It generalises beyond its training range: Experiment C (3 flows) is solved
  perfectly by every model.

## Limitations
- All results are from the flow-level simulator; Mininet replay is Module 7
- Timings are Python on NSFNet; the speed argument should be confirmed on a larger
  topology (e.g. GEANT)
- Not yet tested on unseen topologies (the core novelty claim) or against an
  averaging-readout ablation
- TRIAD's decision time includes building observations in Python, which could be optimised