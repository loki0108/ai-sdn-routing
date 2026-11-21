# Module 5: TRIAD Encoder

## Goal
Build the novel part of the proposed architecture: an encoder that scores each
candidate path by combining link information the way routing metrics combine
(sum, min, product), instead of averaging as standard GNN layers do.
Verify it is correct **before** any training.

## Files
- `agents/triad.py`: link features, path indexing, the readout, the `TriadEncoder`
  network, and sanity checks

## Key ideas

### Why not a standard GNN layer?
GCN, GAT and Graph Transformers mostly **average** information. An average hides
the bottleneck:

| | Link utilisations | Average | Worst link |
|---|---|---|---|
| Path A | 0.5, 0.5, 0.5 | 0.5 | 0.5 (fine) |
| Path B | 0.1, 0.1, 1.3 | 0.5 | 1.3 (overloaded) |

Same average (and same sum), completely different quality. Path quality combines
in three ways (see Module 3), and average is not one of them.

### The three readouts
For each candidate path p:
- **Additive:** a_p = **sum** over links of f_add(h_l): accumulating costs (delay, hops)
- **Bottleneck:** b_p = **min** over links of f_min(h_l): the weakest link decides
- **Multiplicative:** m_p = **sum** over links of log σ(f_mul(h_l)): a product of
  per-link survival chances, computed as a sum of logs for numerical stability
- **Score:** z_p = MLP([a_p, b_p, m_p]), one number per candidate path

f_add, f_min, f_mul are small learned networks (the per-link values are learned);
the way values combine along a path is built in.

### Link features
Each directed link: `[utilisation, spare fraction (1 − utilisation), drop fraction, 1]`.
Spare capacity is a fraction of capacity, not Mbps, so features mean the same on
networks with different link speeds (useful for transfer to unseen topologies).

### Where the "graph" is
TRIAD works on a graph of links and paths: each path is connected to the links it
uses, and information flows from links to paths (message passing with sum / min /
product aggregation). This link–path structure is the one used by RouteNet; the
new part is how messages are combined.

### Implementation notes
- Paths differ in length, so they are **padded** into a rectangle with a **mask**:
  padding adds 0 to sums and is set to +∞ for the min, so it never affects results.
- `add[idx]` looks up every link of every path at once (no Python loops), so one
  forward pass scores all candidates cheaply.

## Sanity checks (hand-set per-link values, before any training)
| Check | Input per link | Result |
|---|---|---|
| 1. Sum channel | 1 | Equals hop count; minimum is candidate 0 (shortest path) for **182/182** pairs |
| 2. Min channel | spare capacity (Experiment C loads) | Bottlenecks for h1 → h14: −5, −5, +5, +10 Mbps, identical to direct computation |
| 3. Product channel | log(link delivery) | exp(m) = **0.667** = simulator delivery ratio for all three flows |
| Encoder | random (untrained) weights | Runs end to end: **740** learnable parameters, 12 scores for Experiment C |

The readout reproduces shortest-path, widest-path and delivery-ratio computations
exactly: **TRIAD contains the classical algorithms as special cases.**

Widest-path routing judging h1 → h14 alone picks candidate 3, whose links are also
needed by h2 → h13: a per-flow rule falls into the coordination trap. The RL policy
(Module 6) sees all flows' scores together and can learn to avoid it.

## Status
- Encoder implemented and verified (correct by construction)
- **Not yet trained**: whether TRIAD learns to route well is tested in Module 6

## Limitations
- No message passing between links yet (link features already include current
  load); whether adding it helps is a later experiment
- Novelty rests on one literature search; to be confirmed on Google Scholar