"""
Routing environment: the "game" the RL agent plays.

Problem this solves: PPO needs a loop of state -> action -> reward. One episode =
one traffic scenario: start from shortest path (every flow on candidate 0), then
each step either moves one flow to another candidate or STOPs.

  reward of a move = (cost before - cost after) x scale - small penalty per move
  cost             = total loss + delay_weight x mean delay (ms)

Rewards telescope: their sum = (start cost - final cost) x scale - penalties,
so maximising total reward = ending with the lowest cost in few moves.
"""

import random

import torch

from agents.greedy import choice_to_paths
from agents.triad import NUM_FEATURES
from controller.routing import all_candidates
from simulator.flow_model import FlowModel
from simulator.traffic import random_flows


class RoutingEnv:
    def __init__(self, topo_module, k=4, min_flows=10, max_flows=30, max_steps=20,
                 delay_weight=0.0001, move_penalty=0.001, reward_scale=10.0):
        self.model = FlowModel(topo_module)
        self.num_nodes = topo_module.NUM_NODES
        self.k = k
        self.candidates = all_candidates(topo_module, k)
        assert all(len(c) == k for c in self.candidates.values()), \
            "this version assumes every pair has exactly k candidates"
        self.min_flows, self.max_flows = min_flows, max_flows
        self.max_steps = max_steps
        self.delay_weight = delay_weight    # 100 ms of delay costs as much as 1% loss
        self.move_penalty = move_penalty    # price of changing switch rules
        self.reward_scale = reward_scale    # costs are small numbers; scale for learning

    # ---- episode control ----
    def reset(self, seed, num_flows=None):
        """Start a random scenario (10-30 flows unless num_flows is given)."""
        if num_flows is None:
            num_flows = random.Random(seed).randint(self.min_flows, self.max_flows)
        return self.reset_with_flows(random_flows(self.num_nodes, num_flows, 1.0, 5.0, seed))

    def reset_with_flows(self, flows):
        """Start a given scenario (e.g. Experiment C) from shortest path."""
        self.flows = flows
        self.choice = [0] * len(flows)
        self.steps = 0
        self._evaluate()
        self.start_cost = self.cost
        return self.observation()

    @property
    def stop_action(self):
        """Actions 0 .. n*k-1 mean (flow, candidate) = divmod(action, k); the last is STOP."""
        return len(self.flows) * self.k

    @property
    def num_actions(self):
        return self.stop_action + 1

    def step(self, action):
        """Apply one action -> (observation, reward, done)."""
        if action == self.stop_action:
            return self.observation(), 0.0, True
        i, c = divmod(action, self.k)
        if c == self.choice[i]:
            raise ValueError("moving a flow to the path it is already on is not allowed")
        before = self.cost
        self.choice[i] = c
        self._evaluate()
        self.steps += 1
        reward = (before - self.cost) * self.reward_scale - self.move_penalty
        return self.observation(), reward, self.steps >= self.max_steps

    # ---- simulator and observation ----
    def _evaluate(self):
        paths = choice_to_paths(self.flows, self.candidates, self.choice)
        self.result = self.model.evaluate(self.flows, paths)
        self.cost = self.result["total_loss"] + self.delay_weight * self.result["mean_delay_ms"]

    def observation(self):
        """
        Everything the agent sees:
          feats   [n*k, max_links, NUM_FEATURES]: "what-if" features for every candidate:
                  link loads as they would be IF that flow moved to that candidate
          mask    [n*k, max_links]: which entries are real links (paths differ in length)
          current [n*k]: True where a flow currently is (moving there is not allowed)
          global  [4]: max and mean utilisation, current loss, number of flows (for the critic)
        """
        load = self.result["load"]
        cap = self.model.capacity
        all_paths = [p for f in self.flows for p in self.candidates[(f.src, f.dst)]]
        max_links = max(len(p) - 1 for p in all_paths)

        feats = [[[0.0] * NUM_FEATURES for _ in range(max_links)] for _ in all_paths]
        mask = [[False] * max_links for _ in all_paths]
        current = []
        for i, (flow, ch) in enumerate(zip(self.flows, self.choice)):
            cands = self.candidates[(flow.src, flow.dst)]
            on_now = set(zip(cands[ch], cands[ch][1:]))   # links the flow uses right now
            for c, path in enumerate(cands):
                p = i * self.k + c
                current.append(c == ch)
                for j, link in enumerate(zip(path, path[1:])):
                    extra = 0.0 if link in on_now else flow.rate   # what if it moved here?
                    u = (load[link] + extra) / cap
                    drop = max(0.0, 1 - 1 / u) if u > 0 else 0.0
                    feats[p][j] = [u, 1 - u, drop, 1.0]
                    mask[p][j] = True

        util = [x / cap for x in load.values()]
        glob = [max(util), sum(util) / len(util), self.result["total_loss"],
                len(self.flows) / self.max_flows]
        return {
            "feats": torch.tensor(feats, dtype=torch.float32),
            "mask": torch.tensor(mask),
            "current": torch.tensor(current),
            "global": torch.tensor(glob, dtype=torch.float32),
        }


if __name__ == "__main__":
    # Self-check: run `python -m agents.env`
    from agents.greedy import greedy
    from simulator.flow_model import Flow
    from topologies import nsfnet

    env = RoutingEnv(nsfnet)

    # 1. Experiment C, replaying greedy's two moves, then STOP
    obs = env.reset_with_flows([Flow(0, 13, 5.0), Flow(1, 12, 5.0), Flow(2, 5, 5.0)])
    print(f"Experiment C start: cost {env.cost:.4f} (loss {env.result['total_loss']:.1%}, "
          f"delay {env.result['mean_delay_ms']:.1f} ms)")
    print(f"  {env.num_actions} actions (3 flows x 4 candidates + STOP), "
          f"features {tuple(obs['feats'].shape)}")
    total = 0.0
    for name, action in [("h1 -> candidate 2", 0 * env.k + 2),
                         ("h2 -> candidate 2", 1 * env.k + 2),
                         ("STOP", env.stop_action)]:
        obs, reward, done = env.step(action)
        total += reward
        print(f"  {name:18s} reward {reward:+.4f}  cost {env.cost:.4f}  done {done}")
    expected = (env.start_cost - env.cost) * env.reward_scale - 2 * env.move_penalty
    print(f"  sum of rewards {total:+.4f}  vs  (start - end) x 10 - penalties {expected:+.4f}")

    # 2. Reference points for the learning curve: random policy vs greedy
    rng = random.Random(0)
    episodes = 100
    random_total = greedy_total = 0.0
    for seed in range(episodes):
        obs = env.reset(seed)
        done, ret = False, 0.0
        while not done:
            valid = [a for a in range(env.num_actions)
                     if a == env.stop_action or not obs["current"][a]]
            obs, reward, done = env.step(rng.choice(valid))
            ret += reward
        random_total += ret

        env.reset(seed)
        ch, moves, _ = greedy(env.model, env.flows, env.candidates)
        env.choice = ch
        env._evaluate()
        greedy_total += (env.start_cost - env.cost) * env.reward_scale - moves * env.move_penalty

    print(f"\nMean episode return over {episodes} random scenarios (10-30 flows):")
    print(f"  random policy: {random_total / episodes:+.3f}")
    print(f"  greedy:        {greedy_total / episodes:+.3f}")
    print("  (a trained TRIAD should climb from near the random value towards greedy)")