"""
Greedy baseline: improve routing one flow move at a time (hill climbing).

Problem this solves: the AI must beat a simple, sensible rule, not just
shortest path. Start from shortest path (candidate 0 for every flow), apply the
single flow move that lowers the cost most, and repeat until no move helps.
Known weakness: it can get stuck where only a COMBINATION of moves would help.
"""


def choice_to_paths(flows, candidates, choice):
    """choice[i] = which candidate flow i uses -> the actual list of paths."""
    return [candidates[(f.src, f.dst)][c] for f, c in zip(flows, choice)]


def cost(result):
    """Lower is better: total loss first, mean delay breaks ties."""
    return (round(result["total_loss"], 9), result["mean_delay_ms"])


def greedy(model, flows, candidates, max_moves=100):
    """
    Returns (choice, moves): the candidate index chosen for each flow,
    and how many moves were applied.
    """
    choice = [0] * len(flows)   # start from shortest path
    best = cost(model.evaluate(flows, choice_to_paths(flows, candidates, choice)))

    for moves in range(max_moves):
        best_move = None
        for i, f in enumerate(flows):
            for c in range(len(candidates[(f.src, f.dst)])):
                if c == choice[i]:
                    continue
                trial = choice.copy()
                trial[i] = c
                trial_cost = cost(model.evaluate(flows, choice_to_paths(flows, candidates, trial)))
                if trial_cost < best:
                    best, best_move = trial_cost, (i, c)

        if best_move is None:   # no single move helps: stop
            return choice, moves
        i, c = best_move
        choice[i] = c

    return choice, max_moves


if __name__ == "__main__":
    # Run: python -m agents.greedy
    from controller.routing import all_candidates
    from simulator.flow_model import Flow, FlowModel
    from simulator.traffic import random_flows
    from topologies import nsfnet

    model = FlowModel(nsfnet)
    candidates = all_candidates(nsfnet, k=4)

    # 1. Experiment C
    flows = [Flow(0, 13, 5.0), Flow(1, 12, 5.0), Flow(2, 5, 5.0)]
    shortest = model.evaluate(flows, choice_to_paths(flows, candidates, [0] * len(flows)))
    choice, moves = greedy(model, flows, candidates)
    result = model.evaluate(flows, choice_to_paths(flows, candidates, choice))

    print(f"Experiment C: shortest path loss {shortest['total_loss']:.1%}, "
          f"delay {shortest['mean_delay_ms']:.1f} ms")
    print(f"              greedy        loss {result['total_loss']:.1%}, "
          f"delay {result['mean_delay_ms']:.1f} ms  ({moves} moves)")
    for r, c in zip(result["flows"], choice):
        route = " -> ".join(f"s{n + 1}" for n in r["path"])
        print(f"  h{r['src'] + 1} -> h{r['dst'] + 1}: candidate {c}  {route}")

    # 2. Random scenarios: shortest path vs greedy
    scenarios = 50
    print(f"\nRandom scenarios ({scenarios} per load), mean over scenarios:")
    for num_flows in (10, 20, 30):
        sp_loss = gr_loss = sp_delay = gr_delay = 0.0
        for seed in range(scenarios):
            flows = random_flows(nsfnet.NUM_NODES, num_flows, 1.0, 5.0, seed)
            sp = model.evaluate(flows, choice_to_paths(flows, candidates, [0] * num_flows))
            ch, _ = greedy(model, flows, candidates)
            gr = model.evaluate(flows, choice_to_paths(flows, candidates, ch))
            sp_loss += sp["total_loss"]
            gr_loss += gr["total_loss"]
            sp_delay += sp["mean_delay_ms"]
            gr_delay += gr["mean_delay_ms"]
        print(f"  {num_flows} flows: loss {sp_loss / scenarios:5.1%} -> {gr_loss / scenarios:5.1%}, "
              f"delay {sp_delay / scenarios:5.1f} -> {gr_delay / scenarios:5.1f} ms")