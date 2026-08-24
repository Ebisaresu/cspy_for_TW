"""ESPPRC with native time windows and NO mandatory visits: how far does the
engine scale, and how much do the windows prune?

Usage:
    python benchmarks/python/bench_tw_scaling.py sanity
    python benchmarks/python/bench_tw_scaling.py <n> <hops> <none|wide|tight>

One (n, hops, regime) combination per invocation, so that a driver can put a
timeout and a memory cap around each point, e.g.:

    for n in 50 100 200 400; do for h in 4 6 8 10; do for reg in none wide tight; do
      timeout 60 python benchmarks/python/bench_tw_scaling.py $n $h $reg
    done; done; done

The three regimes share the same graph for the same (n, hops): a dense random
digraph whose interior arcs are mostly negative in cost (deliberately harsher
than a real pricing subproblem, where negative reduced costs are sparse).
`none` is the windowless ESPPRC baseline; `wide`/`tight` give every customer
a window of width 0.6*T / 0.25*T on the time resource, with waiting allowed
(POLICY_WINDOW_WAIT) and a service time per customer. T = 3*hops.

What this shows (measured on the optimised build): windows are a pruning
device, not a burden. At hops=6 the windowless search stops finishing beyond
n=100, while tight windows solve n=400 in under a second; tight windows at
hops=8 keep n=200 under 15 s. The exponential axis is the hop budget; the
windows suppress it.

`sanity` re-solves the README quick-start instance through the same
hand-wired NodeWindowREF path and asserts the known answer, so a refactor of
this script cannot silently start measuring a different problem.

Prints one JSON line: time, cost, feasibility, peak RSS of this process.
"""
import json
import random
import resource
import sys
import time

from cspy_tw.algorithms.pyBiDirectionalCpp import (
    BiDirectionalCpp,
    DoubleVector,
    IntVector,
    NodeWindowREF,
    POLICY_WINDOW_WAIT,
)

MEMORY_CAP_GB = 12


def dv(values):
    v = DoubleVector()
    for x in values:
        v.append(float(x))
    return v


def build(n, seed, degree=8):
    """ids 0..n-1, source 0, sink n-1; dense mostly-negative interior."""
    rng = random.Random(seed)
    arcs = []
    for u in range(1, n - 1):
        for _ in range(degree):
            v = rng.randint(1, n - 2)
            if v != u:
                arcs.append((u, v, round(rng.uniform(-4, 2), 2),
                             [1.0, round(rng.uniform(0.5, 2), 2)]))
    for u in range(1, n - 1):
        if rng.random() < 0.3:
            arcs.append((0, u, round(rng.uniform(0, 3), 2), [1.0, 1.0]))
        if rng.random() < 0.3:
            arcs.append((u, n - 1, round(rng.uniform(0, 3), 2), [1.0, 1.0]))
    arcs.append((0, 1, 1.0, [1.0, 1.0]))
    arcs.append((n - 2, n - 1, 1.0, [1.0, 1.0]))
    return arcs


def run(n, hops, regime, seed):
    horizon = 3.0 * hops
    arcs = build(n, seed)
    alg = BiDirectionalCpp(n, len(arcs), 0, n - 1,
                           dv([hops, horizon]), dv([0.0, 0.0]))
    alg.setDirection("forward")
    alg.setElementary(True)
    nodes = IntVector()
    for i in range(n):
        nodes.append(i)
    alg.addNodes(nodes)
    for tail, head, weight, res_cost in arcs:
        alg.addEdge(tail, head, weight, dv(res_cost))
    if regime != "none":
        width = (0.6 if regime == "wide" else 0.25) * horizon
        rng = random.Random(seed + 1)
        lower, upper, service = [0.0] * n, [horizon] * n, [0.0] * n
        for i in range(1, n - 1):
            start = rng.uniform(0, 0.55 * horizon)
            lower[i] = round(start, 2)
            upper[i] = round(min(start + width, horizon), 2)
            service[i] = round(rng.uniform(0, 1), 2)
        ref = NodeWindowREF(n, dv([hops, horizon]), 0, n - 1, 0, 1e-9)
        ref.setResourcePolicy(
            1, POLICY_WINDOW_WAIT, dv(lower), dv(upper), dv(service))
        alg.setREFCallback(ref)
        # The engine holds the callback as a raw pointer; this reference is
        # what keeps the wrapper object alive for the run.
        alg._window_ref_keepalive = ref
    t0 = time.perf_counter()
    alg.run()
    elapsed = time.perf_counter() - t0
    path = list(alg.getPath())
    feasible = len(path) > 1
    return {
        "n": n, "hops": hops, "regime": regime,
        "sec": round(elapsed, 4),
        "cost": round(alg.getTotalCost(), 2) if feasible else None,
        "feasible": feasible,
        "rss_mb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }


def sanity():
    """The README quick-start instance, hand-wired: known answer asserted."""
    n = 4  # Source=0, A=1, B=2, Sink=3
    max_res = [10.0, 20.0]
    alg = BiDirectionalCpp(n, 6, 0, 3, dv(max_res), dv([0.0, 0.0]))
    alg.setDirection("forward")
    alg.setElementary(True)
    nodes = IntVector()
    for i in range(n):
        nodes.append(i)
    alg.addNodes(nodes)
    for tail, head, weight, res_cost in [
            (0, 1, 0, [1, 2]), (0, 2, 0, [1, 5]), (1, 2, -10, [1, 3]),
            (2, 1, -10, [1, 3]), (1, 3, 0, [1, 2]), (2, 3, 0, [1, 2])]:
        alg.addEdge(tail, head, weight, dv(res_cost))
    ref = NodeWindowREF(n, dv(max_res), 0, 3, 0, 1e-9)
    ref.setResourcePolicy(
        1, POLICY_WINDOW_WAIT,
        dv([0.0, 0.0, 8.0, 0.0]),      # A: (0, 4), B: (8, 12)
        dv([20.0, 4.0, 12.0, 20.0]),
        dv([0.0, 1.0, 1.0, 0.0]))      # service times
    alg.setREFCallback(ref)
    alg._window_ref_keepalive = ref
    alg.run()
    assert list(alg.getPath()) == [0, 1, 2, 3], list(alg.getPath())
    assert alg.getTotalCost() == -10.0, alg.getTotalCost()
    assert list(alg.getConsumedResources()) == [3.0, 11.0]
    print("sanity ok: path [0, 1, 2, 3], cost -10.0, consumed [3.0, 11.0]")


def main():
    if sys.argv[1:2] == ["sanity"]:
        sanity()
        return
    n, hops, regime = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    if regime not in ("none", "wide", "tight"):
        raise SystemExit("regime must be none, wide or tight")
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_CAP_GB * 1024**3,) * 2)
    print(json.dumps(run(n, hops, regime, 1000 + n)), flush=True)


if __name__ == "__main__":
    main()
