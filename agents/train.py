"""
PPO training for the TRIAD routing agent.

Loop: play episodes with the current policy (sampling = exploration), compute how
much better than expected each action turned out (advantage = return - critic's
prediction), then nudge the policy towards better-than-expected actions, with
PPO's clipping keeping each update small and stable.

Training scenarios use seeds from 100,000 upwards; evaluation uses seeds 0-49,
the same scenarios as the greedy table in Module 4, never seen in training.

Run: python -m agents.train --move-penalty 0.01 --seed 0
"""

import argparse
import csv
import os
import random
import time

import matplotlib
matplotlib.use("Agg")          # save plots to files; no window needed
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
from torch.distributions import Categorical

from agents.env import RoutingEnv
from agents.greedy import greedy
from agents.triad import TriadEncoder, mlp
from topologies import nsfnet

MASKED = -1e9   # logit for impossible actions (not -inf, which breaks the entropy maths)


class TriadPolicy(nn.Module):
    """Actor: TRIAD scores -> move probabilities. Critic: expected return of a state."""

    def __init__(self, hidden=32):
        super().__init__()
        self.encoder = TriadEncoder(hidden)
        self.stop_logit = nn.Parameter(torch.zeros(1))   # learned "is any move worth it?" threshold
        self.critic = mlp(4, hidden, 1)

    def forward(self, obs, k):
        scores = self.encoder.score_entries(obs["feats"], obs["mask"]).view(-1, k)  # [flows, k]
        current = obs["current"].view(-1, k)
        stay = (scores * current).sum(dim=1, keepdim=True)   # score of each flow's current path
        gain = (scores - stay).view(-1)                       # how much better each move looks
        gain = gain.masked_fill(obs["current"], MASKED)       # can't move to where it already is
        logits = torch.cat([gain, self.stop_logit])           # last entry = STOP
        value = self.critic(obs["global"]).squeeze(-1)
        return logits, value


def collect(env, policy, seeds):
    """Play one episode per seed. Returns all steps (with return-to-go) and episode returns."""
    samples, returns = [], []
    for seed in seeds:
        obs = env.reset(seed)
        steps, done = [], False
        while not done:
            with torch.no_grad():
                logits, value = policy(obs, env.k)
                dist = Categorical(logits=logits)
                action = dist.sample()                        # sample, don't take the max: explore
            next_obs, reward, done = env.step(int(action))
            steps.append([obs, action, dist.log_prob(action), value, reward])
            obs = next_obs
        future = 0.0
        for step in reversed(steps):                          # return-to-go: this + all later rewards
            future += step[4]
            step.append(future)
        returns.append(future)                                # = the whole episode's return
        samples.extend(steps)
    return samples, returns


def ppo_update(policy, optimizer, samples, k, epochs=4, clip=0.2):
    """One PPO update from a batch of collected steps."""
    rets = torch.tensor([s[5] for s in samples])
    values = torch.stack([s[3] for s in samples])
    adv = rets - values                                       # better or worse than expected?
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)             # normalise for steadier learning

    for _ in range(epochs):
        policy_loss = value_loss = entropy = 0.0
        for (obs, action, old_logp, _, _, ret), a in zip(samples, adv):
            logits, value = policy(obs, k)
            dist = Categorical(logits=logits)
            ratio = torch.exp(dist.log_prob(action) - old_logp)   # new prob / old prob
            # PPO's clipped objective: gain from the advantage, but never trust a big change
            policy_loss -= torch.min(ratio * a, torch.clamp(ratio, 1 - clip, 1 + clip) * a)
            value_loss += (value - ret) ** 2                       # critic learns to predict returns
            entropy += dist.entropy()                              # keep some randomness: explore
        n = len(samples)
        loss = (policy_loss + 0.5 * value_loss - 0.01 * entropy) / n
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
        optimizer.step()


def reference_returns(env, episodes=100):
    """Mean episode return of a random policy and of greedy, with this env's settings."""
    rng = random.Random(0)
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
        choice, moves, _ = greedy(env.model, env.flows, env.candidates)
        env.choice = choice
        env._evaluate()
        greedy_total += (env.start_cost - env.cost) * env.reward_scale - moves * env.move_penalty
    return random_total / episodes, greedy_total / episodes


def run_best_actions(env, policy, obs):
    """Evaluation: always take the highest-probability action (no randomness)."""
    done = False
    while not done:
        with torch.no_grad():
            logits, _ = policy(obs, env.k)
        obs, _, done = env.step(int(logits.argmax()))


def evaluate(env, policy, csv_path, loads=(10, 20, 30, 40, 50), scenarios=50):
    """Same scenarios as the greedy table (seeds 0-49). Prints a table and saves a CSV."""
    print(f"\nTRIAD evaluation ({scenarios} scenarios per load, seeds 0-{scenarios - 1}):")
    print(f"{'flows':>5} | {'loss':>6} | {'delay (ms)':>10} | {'moves':>5} | {'ms/scenario':>11}")
    rows = []
    for num_flows in loads:
        loss = delay = moves = elapsed = 0.0
        for seed in range(scenarios):
            obs = env.reset(seed, num_flows=num_flows)
            start = time.perf_counter()
            run_best_actions(env, policy, obs)
            elapsed += time.perf_counter() - start
            loss += env.result["total_loss"]
            delay += env.result["mean_delay_ms"]
            moves += env.steps
        n = scenarios
        row = {"flows": num_flows, "loss": loss / n, "delay_ms": delay / n,
               "moves": moves / n, "ms_per_scenario": elapsed / n * 1000}
        rows.append(row)
        print(f"{num_flows:>5} | {row['loss']:6.1%} | {row['delay_ms']:10.1f} | "
              f"{row['moves']:5.1f} | {row['ms_per_scenario']:11.1f}")

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Train TRIAD with PPO")
    parser.add_argument("--move-penalty", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=150)
    parser.add_argument("--episodes-per-iter", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()

    tag = f"pen{args.move_penalty}_seed{args.seed}"
    os.makedirs("results", exist_ok=True)
    torch.manual_seed(args.seed)
    env = RoutingEnv(nsfnet, move_penalty=args.move_penalty)

    print(f"Run {tag}: computing reference returns...")
    random_ref, greedy_ref = reference_returns(env)
    print(f"  random policy {random_ref:+.3f}, greedy {greedy_ref:+.3f}")

    policy = TriadPolicy()
    optimizer = torch.optim.Adam(policy.parameters(), lr=args.lr)

    curve = []
    next_seed = 100_000 + args.seed * 10_000   # each run sees its own scenarios; never seeds 0-49
    start = time.perf_counter()
    for it in range(1, args.iterations + 1):
        seeds = range(next_seed, next_seed + args.episodes_per_iter)
        next_seed += args.episodes_per_iter
        samples, returns = collect(env, policy, seeds)
        ppo_update(policy, optimizer, samples, env.k)
        curve.append(sum(returns) / len(returns))
        if it == 1 or it % 10 == 0:
            print(f"iter {it:4d} | mean return {curve[-1]:+.3f} | "
                  f"steps/episode {len(samples) / len(returns):4.1f} | "
                  f"{time.perf_counter() - start:5.0f} s")

    torch.save(policy.state_dict(), f"results/triad_{tag}.pt")

    # Learning curve, with a moving average and the two reference points
    window = 10
    smooth = [sum(curve[max(0, i - window + 1):i + 1]) / len(curve[max(0, i - window + 1):i + 1])
              for i in range(len(curve))]
    plt.figure(figsize=(7, 4))
    plt.plot(curve, alpha=0.3, label="mean return per iteration")
    plt.plot(smooth, label=f"moving average ({window})")
    plt.axhline(random_ref, linestyle="--", color="gray", label="random policy")
    plt.axhline(greedy_ref, linestyle="--", color="green", label="greedy")
    plt.xlabel("training iteration")
    plt.ylabel("mean episode return")
    plt.title(f"TRIAD + PPO on NSFNet ({tag})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"results/curve_{tag}.png", dpi=150)
    print(f"\nSaved results/triad_{tag}.pt and results/curve_{tag}.png")

    evaluate(env, policy, f"results/eval_{tag}.csv")


if __name__ == "__main__":
    main()