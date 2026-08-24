"""Run the Beasley-Christofides 1989 RCSPP set (rcsp1-24) and check every
cost against the published optima in results.txt.

Usage:
    python benchmarks/python/bench_beasley.py [direction] [elem|nonelem] [instances...]

    direction   forward | backward | both        (default: forward)
    elem mode   elem | nonelem                   (default: nonelem)
    instances   which rcsp numbers to run        (default: all 24)

The natural mode for this set is non-elementary: the instances have no
negative cost cycles, so the elementary restriction changes nothing about the
optimum and only slows the search (the engine warns about exactly this).
Non-elementary, all 24 instances (n = 100 to 500, 1 or 10 resources) solve in
under a second each; forcing elementary sends several of the n >= 200
instances beyond a minute.

Loading follows test/cc/test_benchmarks.cc: the per-vertex resource
consumption lines are skipped, arcs into the source and out of the sink are
dropped, and the instances that need a non-default critical resource get the
same overrides. Instances are driven through the SWIG proxy rather than the
networkx wrapper so that parallel arcs in the files stay parallel arcs.

Prints one JSON line per instance with the solve time and whether the cost
matches; exits non-zero if any run mismatches.
"""
import json
import sys
import time
from pathlib import Path

from cspy_tw.algorithms.pyBiDirectionalCpp import (
    BiDirectionalCpp,
    DoubleVector,
    IntVector,
)

DATA = Path(__file__).resolve().parents[1] / "beasley_christofides_1989"
#: Same overrides as setCriticalRes in test/cc/test_benchmarks.cc.
CRITICAL = {5: 7, 6: 7, 7: 1, 8: 2, 13: 3, 14: 0, 15: 2, 16: 2, 23: 7, 24: 7}


def dv(values):
    v = DoubleVector()
    for x in values:
        v.append(float(x))
    return v


def load_expected():
    expected = {}
    for line in (DATA / "results.txt").read_text().splitlines()[1:]:
        inst, cost = line.split()
        expected[int(inst)] = float(cost)
    return expected


def load(num):
    tokens = iter((DATA / ("rcsp%d.txt" % num)).read_text().split())
    n, m, K = int(next(tokens)), int(next(tokens)), int(next(tokens))
    lower = [float(next(tokens)) for _ in range(K)]
    upper = [float(next(tokens)) for _ in range(K)]
    for _ in range(n * K):  # per-vertex consumption: skipped, as upstream
        next(tokens)
    arcs = []
    for _ in range(m):
        tail, head = int(next(tokens)), int(next(tokens))
        weight = float(next(tokens))
        res_cost = [float(next(tokens)) for _ in range(K)]
        if tail == 1:
            arcs.append((1, head, weight, res_cost))
        elif head == 1 or tail == n:
            continue
        elif head == n:
            arcs.append((tail, n, weight, res_cost))
        else:
            arcs.append((tail, head, weight, res_cost))
    return n, m, K, lower, upper, arcs


def solve(num, direction, elementary, expected):
    n, m, K, lower, upper, arcs = load(num)
    alg = BiDirectionalCpp(n, m, 1, n, dv(upper), dv(lower))
    if direction != "both":
        alg.setDirection(direction)
    if elementary:
        alg.setElementary(True)
    if num in CRITICAL:
        alg.setCriticalRes(CRITICAL[num])
    nodes = IntVector()
    for i in range(1, n + 1):
        nodes.append(i)
    alg.addNodes(nodes)
    for tail, head, weight, res_cost in arcs:
        alg.addEdge(tail, head, weight, dv(res_cost))
    t0 = time.perf_counter()
    alg.run()
    elapsed = time.perf_counter() - t0
    cost = alg.getTotalCost()
    return {
        "inst": num,
        "n": n,
        "m": m,
        "K": K,
        "sec": round(elapsed, 4),
        "cost": cost,
        "match": abs(cost - expected[num]) < 1e-6,
    }


def main():
    args = sys.argv[1:]
    direction = args.pop(0) if args and not args[0].isdigit() else "forward"
    elementary = False
    if args and args[0] in ("elem", "nonelem"):
        elementary = args.pop(0) == "elem"
    selection = [int(a) for a in args] or list(range(1, 25))
    expected = load_expected()
    all_match = True
    for num in selection:
        result = solve(num, direction, elementary, expected)
        all_match &= result["match"]
        print(json.dumps(result), flush=True)
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
