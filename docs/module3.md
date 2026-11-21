# Module 3: Flow-Level Simulator

## Goal
Mininet sends real packets and needs about a minute per experiment. Training an AI
needs thousands of evaluations, so we built a flow-level (fluid) model that
computes link loads, loss and delay from flow rates in microseconds.

## Files
- `simulator/flow_model.py`: the model (`Flow`, `FlowModel.evaluate`), plus a
  validation run that reproduces Experiment C

## Key ideas
- **Flow:** a stream of packets from one source to one destination at a rate
  (e.g. h1 → h14 at 5 Mbps). One flow per source–destination pair.
- **Traffic matrix:** the set of all flows at one moment ("who sends how much to whom").
- **Flow-level vs packet-level:** Mininet simulates every packet; the flow model
  treats each flow as a steady rate, like water in pipes.

## The model
1. Load on a directed link = sum of rates of flows crossing it
   (each cable is two directed links, 10 Mbps each)
2. Link drop fraction = max(0, 1 − capacity / load)
3. Flow delivered fraction = **product** of (1 − drop) over its links
4. Flow delay = **sum** of (10 ms propagation + queueing delay) over its links;
   queueing uses the M/M/1 formula ρ/(1−ρ) × packet time, capped at a full queue
   (100 packets × 1.2 ms = 120 ms)
5. Path spare capacity = **minimum** of (capacity − load) over its links

Delay adds, spare capacity takes the minimum, delivery ratio multiplies:
the same three combinations TRIAD's path encoder is built on.

## Validation against Mininet (Experiment C)
| | Mininet | Simulator |
|---|---|---|
| Overloaded link | s3 → s6 (queue full) | s3 → s6 at 150% |
| Total loss | 37.7% (≈15.7 Mbps actually sent) | 33.3% at 15 Mbps; ≈36% at 15.7 Mbps |
| h1 → h14 round trip | 171 ms | 182 ms (+6%) |

The small delay gap comes from assuming full-size packets in the queue; real
traffic drains slightly faster. The model errs on the pessimistic side, equally
for every routing strategy.

## Simplifications
- Fluid rates, not individual packets
- Every flow on an overloaded link loses the same fraction
  (Mininet showed loss is actually uneven, but totals match)
- Each flow's offered rate is used on every link of its path: exact when no flow
  crosses more than one overloaded link, slightly pessimistic otherwise

## Bug fixed during development
Evaluating an idle path (a zero-rate flow) divided by a total rate of 0.
Fixed by handling "no traffic" separately: an edge case to check whenever code divides.