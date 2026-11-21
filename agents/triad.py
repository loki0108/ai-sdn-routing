"""
TRIAD encoder: routing-aligned path readout.

Problem this solves: standard GNN layers AVERAGE link information, which hides
the bottleneck (one overloaded link ruins a path). TRIAD scores each candidate
path with three readouts that combine link values the way routing metrics do:
  a = SUM over links   (like delay, hop count)
  b = MIN over links   (like spare capacity: the weakest link decides)
  m = PRODUCT over links, computed as a SUM of logs (like delivery ratio)
then a small MLP turns [a, b, m] into one score per path.
The per-link functions are learned; the way they combine along a path is built in.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

NUM_FEATURES = 4   # [utilisation, spare fraction, drop fraction, 1]


def mlp(n_in, hidden, n_out):
    """A small neural network: linear -> ReLU -> linear."""
    return nn.Sequential(nn.Linear(n_in, hidden), nn.ReLU(), nn.Linear(hidden, n_out))


def link_features(load, links, capacity):
    """One feature vector per directed link, in the order of `links`."""
    rows = []
    for link in links:
        u = load[link] / capacity                          # utilisation
        drop = max(0.0, 1 - 1 / u) if u > 0 else 0.0       # simulator's drop fraction
        rows.append([u, 1 - u, drop, 1.0])                 # 1 - u = spare fraction
    return torch.tensor(rows, dtype=torch.float32)


def path_index(paths, link_pos):
    """
    Paths -> (idx, mask), both of shape [num_paths, max_links].
    idx[p, j] = position of the j-th link of path p in the link list;
    mask[p, j] = True for real links, False for padding (paths differ in length).
    """
    max_links = max(len(p) - 1 for p in paths)
    idx = torch.zeros(len(paths), max_links, dtype=torch.long)
    mask = torch.zeros(len(paths), max_links, dtype=torch.bool)
    for i, path in enumerate(paths):
        for j, link in enumerate(zip(path, path[1:])):
            idx[i, j] = link_pos[link]
            mask[i, j] = True
    return idx, mask


def readout(add, low, mul, idx, mask):
    """
    The heart of TRIAD: combine per-link values along every path at once.
      a = SUM of add
      b = MIN of low
      m = SUM of mul  (mul holds logs, so this is a PRODUCT in disguise)
    """
    a = (add[idx] * mask).sum(dim=1)                                   # padding adds 0
    b = low[idx].masked_fill(~mask, float("inf")).min(dim=1).values    # padding never wins
    m = (mul[idx] * mask).sum(dim=1)
    return a, b, m


class TriadEncoder(nn.Module):
    def __init__(self, hidden=32):
        super().__init__()
        self.f_add = mlp(NUM_FEATURES, hidden, 1)   # learned per-link cost
        self.f_min = mlp(NUM_FEATURES, hidden, 1)   # learned per-link headroom
        self.f_mul = mlp(NUM_FEATURES, hidden, 1)   # learned per-link survival
        self.combine = mlp(3, hidden, 1)            # [a, b, m] -> one score

    def forward(self, h, idx, mask):
        """h: link features [num_links, NUM_FEATURES] -> one score per path [num_paths]."""
        add = self.f_add(h).squeeze(-1)
        low = self.f_min(h).squeeze(-1)
        mul = F.logsigmoid(self.f_mul(h)).squeeze(-1)   # log of a value in (0, 1)
        a, b, m = readout(add, low, mul, idx, mask)
        return self.combine(torch.stack([a, b, m], dim=1)).squeeze(-1)


if __name__ == "__main__":
    # Sanity checks: run `python -m agents.triad`
    import math

    from controller.routing import all_candidates
    from simulator.flow_model import Flow, FlowModel
    from topologies import nsfnet

    model = FlowModel(nsfnet)
    candidates = all_candidates(nsfnet, k=4)
    links = sorted(model.links)                       # fixed order: link -> position
    link_pos = {link: i for i, link in enumerate(links)}

    # Check 1: with f_add = 1, the SUM channel counts hops and picks the shortest path
    ones = torch.ones(len(links))
    agree = 0
    for (src, dst), paths in candidates.items():
        idx, mask = path_index(paths, link_pos)
        a, _, _ = readout(ones, ones, ones, idx, mask)
        hops = torch.tensor([len(p) - 1 for p in paths], dtype=torch.float32)
        if torch.equal(a, hops) and int(a.argmin()) == 0:
            agree += 1
    print(f"Check 1 (SUM = hop count, best = shortest path): {agree}/{len(candidates)} pairs")

    # Experiment C under shortest path: the loads the next checks read from
    flows = [Flow(0, 13, 5.0), Flow(1, 12, 5.0), Flow(2, 5, 5.0)]
    out = model.evaluate(flows, [candidates[(f.src, f.dst)][0] for f in flows])
    load = out["load"]
    spare = torch.tensor([model.capacity - load[l] for l in links])
    log_delivery = torch.tensor([math.log(min(1.0, model.capacity / load[l])) if load[l] > 0
                                 else 0.0 for l in links])
    zeros = torch.zeros(len(links))

    # Check 2: with f_min = spare capacity, the MIN channel finds each path's bottleneck
    print("\nCheck 2 (MIN = bottleneck spare capacity), h1 -> h14 in Experiment C:")
    paths = candidates[(0, 13)]
    idx, mask = path_index(paths, link_pos)
    _, b, _ = readout(zeros, spare, zeros, idx, mask)
    for c, path in enumerate(paths):
        direct = min(model.capacity - load[l] for l in zip(path, path[1:]))
        route = " -> ".join(f"s{n + 1}" for n in path)
        print(f"  candidate {c}: bottleneck {b[c].item():+.1f} Mbps "
              f"(computed directly: {direct:+.1f})  {route}")
    print(f"  widest candidate: {int(b.argmax())}")

    # Check 3: SUM of logs = PRODUCT, so exp(m) equals the simulator's delivery ratio
    print("\nCheck 3 (SUM of logs = PRODUCT), delivery ratio in Experiment C:")
    for r in out["flows"]:
        idx, mask = path_index([r["path"]], link_pos)
        _, _, m = readout(zeros, zeros, log_delivery, idx, mask)
        print(f"  h{r['src'] + 1} -> h{r['dst'] + 1}: exp(m) = {math.exp(m.item()):.3f}, "
              f"simulator 1 - loss = {1 - r['loss']:.3f}")

    # The real (untrained) encoder: one forward pass over all 12 candidates
    encoder = TriadEncoder()
    h = link_features(load, links, model.capacity)
    all_paths = [p for f in flows for p in candidates[(f.src, f.dst)]]
    idx, mask = path_index(all_paths, link_pos)
    scores = encoder(h, idx, mask)
    params = sum(p.numel() for p in encoder.parameters())
    print(f"\nUntrained encoder: {params} learnable parameters, "
          f"{tuple(scores.shape)[0]} scores (3 flows x 4 candidates)")
    print("  scores are random until training (Module 6)")