#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Round 2 harsher stress:
 F1: tight/zero-width windows + forced waiting regime, fwd+both, elem=True
 F2: binding edge budget (max_edges=3) + TW, fwd+both, elem=True
 F3: larger instances (6 customers), fwd+both, elem=True
 F4: heavy-wait + non-elementary walks (max_edges=5), fwd
All against own brute force with independent path re-simulation.
"""
import random
import sys

sys.path.insert(0, "/private/tmp/claude-501/-Users-azzqi-workspace/"
                   "3d5a2384-483d-49ef-950a-8459c3e28405/scratchpad")
import poc_tw  # noqa: E402
from adv_verify_tw import bf_opt, bf_paths, sim, cspy_solve  # noqa: E402

BAD = []


def run_round(name, gen, n_inst, elementary=True, max_edges=10,
              directions=("forward", "both")):
    n_feas = 0
    bad = 0
    for seed in range(n_inst):
        rng = random.Random(seed)
        nodes, edges = gen(rng)
        best = bf_opt(nodes, edges, elementary, max_edges)
        if best is not None:
            n_feas += 1
        _, emap = bf_paths(nodes, edges, elementary, max_edges)
        for d in directions:
            path, cost, res = cspy_solve(nodes, edges, d, elementary,
                                         max_edges)
            if best is None:
                ok = path is None
            elif path is None:
                ok = False
            else:
                feas, c2, t2 = sim(path, nodes, emap)
                ok = feas and abs(c2 - cost) < 1e-9 \
                    and abs(cost - best[0]) < 1e-9
                if d == "forward":
                    ok = ok and abs(res[1] - t2) < 1e-9
            if not ok:
                bad += 1
                BAD.append((name, seed, d, best, path, cost, nodes, edges))
                print(f"MISMATCH {name} seed={seed} [{d}] bf={best} "
                      f"cspy={cost} path={path}")
                print(f"  nodes={nodes}")
                print(f"  edges={edges}")
    print(f"{name}: {n_inst} instances ({n_feas} feasible), "
          f"{bad} mismatches")


def gen_tight(rng):
    """Zero/small-width windows, waiting everywhere."""
    n = rng.choice([4, 5])
    nodes = {"Source": (0, 200, 0)}
    for i in range(1, n + 1):
        a = rng.randint(0, 25)
        w = 0 if rng.random() < 0.4 else rng.randint(1, 4)
        nodes[i] = (a, a + w, rng.randint(0, 4))
    nodes["Sink"] = (0, rng.randint(20, 60), 0)
    edges = []
    cust = list(range(1, n + 1))
    for i in cust:
        if rng.random() < 0.8:
            edges.append(("Source", i, rng.randint(1, 6), rng.randint(-9, 3)))
        if rng.random() < 0.8:
            edges.append((i, "Sink", rng.randint(1, 6), rng.randint(-9, 3)))
        for j in cust:
            if i != j and rng.random() < 0.55:
                edges.append((i, j, rng.randint(1, 8), rng.randint(-9, 3)))
    if not edges:
        edges.append(("Source", 1, 1, 0))
    return nodes, edges


def gen_budget(rng):
    """Loose TWs but binding edge budget interplay."""
    n = 5
    nodes = {"Source": (0, 100, 0)}
    for i in range(1, n + 1):
        a = rng.randint(0, 8)
        nodes[i] = (a, a + rng.randint(4, 30), rng.randint(0, 2))
    nodes["Sink"] = (0, rng.randint(25, 80), 0)
    edges = []
    cust = list(range(1, n + 1))
    for i in cust:
        edges.append(("Source", i, rng.randint(1, 5), rng.randint(-10, 2)))
        edges.append((i, "Sink", rng.randint(1, 5), rng.randint(-10, 2)))
        for j in cust:
            if i != j and rng.random() < 0.6:
                edges.append((i, j, rng.randint(1, 6), rng.randint(-10, 2)))
    return nodes, edges


def gen_large(rng):
    n = 6
    nodes = {"Source": (0, 200, 0)}
    for i in range(1, n + 1):
        a = rng.randint(0, 15)
        nodes[i] = (a, a + rng.randint(1, 12), rng.randint(0, 3))
    nodes["Sink"] = (0, rng.randint(18, 50), 0)
    edges = []
    cust = list(range(1, n + 1))
    for i in cust:
        if rng.random() < 0.7:
            edges.append(("Source", i, rng.randint(1, 7), rng.randint(-8, 3)))
        if rng.random() < 0.7:
            edges.append((i, "Sink", rng.randint(1, 7), rng.randint(-8, 3)))
        for j in cust:
            if i != j and rng.random() < 0.45:
                edges.append((i, j, rng.randint(1, 9), rng.randint(-8, 3)))
    if not edges:
        edges.append(("Source", 1, 1, 0))
    return nodes, edges


if __name__ == "__main__":
    run_round("F1 tight/zero-width TW", gen_tight, 80)
    run_round("F2 edge budget=3", gen_budget, 50, max_edges=3)
    run_round("F3 six customers", gen_large, 50)
    run_round("F4 walks<=5 heavy-wait", gen_tight, 40, elementary=False,
              max_edges=5, directions=("forward",))
    print("=" * 60)
    print(f"TOTAL MISMATCHES: {len(BAD)}")
