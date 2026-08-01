#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adversarial verification of the PoC (poc_tw.py):
 A. Independent brute force (own implementation, pure int arithmetic) vs the
    PoC's brute force on all PoC scenarios.
 B. Binding check: relax the TWs of the base instance -> optimum must change
    to the unconstrained one (-28); tighten -> must change again.
 C. New hand-designed instances, each independently verified:
    C1 chained waiting across 3 consecutive nodes (+ deadline variant)
    C2 dominance trap: cheap-but-late vs expensive-but-early label at same node
    C3 non-triangle travel times: direct extension infeasible, indirect feasible
       (probes cspy's "add to unreachable on failed extension" heuristic)
    C4 a_Source > 0 edge case (documented model caveat check)
 D. Random stress: many random instances, cspy fwd + both (elementary=True)
    vs own brute force; independent re-simulation of cspy's returned path.
 E. Random stress: elementary=False (walks, bounded edges) fwd vs walk DFS.
"""
import random
import sys

sys.path.insert(0, "/private/tmp/claude-501/-Users-azzqi-workspace/"
                   "3d5a2384-483d-49ef-950a-8459c3e28405/scratchpad")
import poc_tw  # noqa: E402  (reuse run_cspy / TWCallback only)

FAILURES = []
CHECKS = [0]


def check(name, ok, detail=""):
    CHECKS[0] += 1
    tag = "OK  " if ok else "FAIL"
    print(f"{tag} | {name}" + (f" | {detail}" if detail else ""))
    if not ok:
        FAILURES.append((name, detail))


# ---------------------------------------------------------------------------
# Own, independent model implementation (integers only)
# ---------------------------------------------------------------------------
def sim(path, nodes, emap):
    """Forward-simulate a path. nodes: v -> (a, b, s). Returns
    (feasible, cost, sink_service_start) using exact int arithmetic."""
    t = nodes[path[0]][0]  # start at a_source (PoC uses max(0, a0); ints >=0)
    cost = 0
    for u, v in zip(path[:-1], path[1:]):
        if (u, v) not in emap:
            return False, None, None
        tt, w = emap[(u, v)]
        arr = t + nodes[u][2] + tt          # service at u, then travel
        start = max(nodes[v][0], arr)       # wait if early
        if start > nodes[v][1]:             # too late
            return False, None, None
        t = start
        cost += w
    return True, cost, t


def bf_paths(nodes, edges, elementary=True, max_edges=10):
    """Own enumeration: all simple paths (or all walks with <= max_edges
    edges) Source->Sink. No pruning other than max_edges."""
    adj = {}
    emap = {}
    for (u, v, tt, w) in edges:
        adj.setdefault(u, []).append(v)
        emap[(u, v)] = (tt, w)
    out = []

    def dfs(path):
        u = path[-1]
        if u == "Sink":
            out.append(list(path))
            return
        if len(path) - 1 >= max_edges:
            return
        for v in adj.get(u, []):
            if elementary and v in path:
                continue
            path.append(v)
            dfs(path)
            path.pop()

    dfs(["Source"])
    return out, emap


def bf_opt(nodes, edges, elementary=True, max_edges=10):
    """Own exact optimum: (best_cost, one_best_path, sink_time) or None."""
    paths, emap = bf_paths(nodes, edges, elementary, max_edges)
    best = None
    for p in paths:
        ok, c, t = sim(p, nodes, emap)
        if ok and (best is None or c < best[0]):
            best = (c, p, t)
    return best


def cspy_solve(nodes, edges, direction, elementary=True, max_edges=10):
    """Run cspy via the PoC's own harness. Returns (path, cost, res) with
    path=None if no complete Source..Sink path was produced."""
    path, cost, res = poc_tw.run_cspy(nodes, edges, direction=direction,
                                      elementary=elementary,
                                      max_edges=max_edges)
    if path is None or len(path) < 2 or path[0] != "Source" \
            or path[-1] != "Sink":
        return None, None, None
    return path, cost, res


def cross_check(name, nodes, edges, elementary=True, max_edges=10,
                directions=("forward", "both"), check_time=True):
    """cspy (fwd/both) vs own brute force; also re-simulate cspy's path."""
    best = bf_opt(nodes, edges, elementary, max_edges)
    _, emap = bf_paths(nodes, edges, elementary, max_edges)
    all_ok = True
    for d in directions:
        path, cost, res = cspy_solve(nodes, edges, d, elementary, max_edges)
        if best is None:
            ok = path is None
            det = f"[{d}] bf=infeasible, cspy path={path}"
        elif path is None:
            ok = False
            det = f"[{d}] bf cost={best[0]} path={best[1]}, cspy found none"
        else:
            feas, c2, t2 = sim(path, nodes, emap)  # independent re-simulation
            ok = (feas and abs(c2 - cost) < 1e-9
                  and abs(cost - best[0]) < 1e-9)
            if d == "forward" and check_time and feas:
                ok = ok and abs(res[1] - t2) < 1e-9  # res[1] == sink time
            det = (f"[{d}] cspy={cost} path={path} feas={feas} "
                   f"(resim cost={c2}, t={t2}) vs bf={best[0]} path={best[1]}")
        check(f"{name} [{d}]", ok, det)
        all_ok = all_ok and ok
    return all_ok


# ---------------------------------------------------------------------------
# A. Own brute force vs PoC's brute force on all PoC scenarios
# ---------------------------------------------------------------------------
def part_A():
    print("--- A. own brute force vs PoC brute force ---")
    nodes, edges = poc_tw.base_instance()
    scen = {"base": nodes,
            "3b": {**nodes, 2: (0, 12, 6)},
            "3c1": {**nodes, 4: (13, 20, 4)},
            "3c2": {**nodes, 4: (13, 20, 4), "Sink": (0, 18, 0)},
            "relaxed": {k: (0, 100, s) for k, (a, b, s) in nodes.items()}}
    for nm, nd in scen.items():
        mine = bf_opt(nd, edges)
        poc = poc_tw.brute_force(nd, edges)
        ok = (mine is not None and poc is not None
              and mine[0] == poc[1] and mine[2] == poc[2])
        check(f"A: bf-agree {nm}", ok, f"mine={mine} poc={poc}")
    # cycle instance, non-elementary
    cn, ce = poc_tw.cycle_instance()
    mine = bf_opt(cn, ce, elementary=False, max_edges=6)
    poc = poc_tw.brute_force(cn, ce, elementary=False, max_edges=6)
    check("A: bf-agree cycle (walks)", mine[0] == poc[1],
          f"mine={mine[:1]} poc={poc[1]}")


# ---------------------------------------------------------------------------
# B. Binding checks by mutation
# ---------------------------------------------------------------------------
def part_B():
    print("--- B. binding checks ---")
    nodes, edges = poc_tw.base_instance()
    # 1) as-is: -21 through TW
    p, c, r = cspy_solve(nodes, edges, "forward")
    check("B1: base cspy=-21", c == -21.0 and p == ["Source", 2, 3, 4, "Sink"],
          f"cspy={c} {p}")
    # 2) fully relax all b_i -> must equal unconstrained optimum -28
    relax = {k: (0, 100000, s) for k, (a, b, s) in nodes.items()}
    p, c, r = cspy_solve(relax, edges, "forward")
    b = bf_opt(relax, edges)
    check("B2: TW relaxed -> -28 (binding proven)",
          c == -28.0 and b[0] == -28 and p == ["Source", 1, 2, 3, 4, "Sink"],
          f"cspy={c} {p} bf={b[0]}")
    # 3) relax ONLY node 3 (the violated one) -> also -28
    relax3 = {**nodes, 3: (0, 100, 1)}
    p, c, r = cspy_solve(relax3, edges, "forward")
    b = bf_opt(relax3, edges)
    check("B3: only b_3 relaxed -> -28", c == float(b[0]) and b[0] == -28,
          f"cspy={c} bf={b[0]}")
    # 4) tighten b_4 -> node 4 unusable -> optimum changes again
    tight = {**nodes, 4: (0, 5, 4)}
    cross_check("B4: b_4=5 tightened", tight, edges)


# ---------------------------------------------------------------------------
# C. New hand-designed instances
# ---------------------------------------------------------------------------
def part_C():
    print("--- C. new adversarial instances ---")
    # C1: chained waiting (three consecutive waits), tight sink deadline
    nodes = {"Source": (0, 100, 0), 1: (5, 6, 1), 2: (10, 11, 1),
             3: (20, 20, 2), "Sink": (0, 25, 0)}
    edges = [("Source", 1, 1, -1), (1, 2, 1, -1), (2, 3, 1, -1),
             (3, "Sink", 2, -1), ("Source", 2, 1, -3), (2, "Sink", 1, 1),
             (1, "Sink", 1, 0), ("Source", 3, 25, -10)]
    # manual: S-1-2-3-Sink: arr1=1->w5, svc->6, arr2=7->w10, svc->11,
    # arr3=12->w20, svc->22, sink=24<=25, cost -4
    # S-2-3-Sink: arr2=1->w10,svc->11,arr3=12->w20,svc22,sink24, cost=-3-1-1=-5
    # S-3(t=25): arr=25>b_3=20 infeasible.
    b = bf_opt(nodes, edges)
    check("C1: manual expected (-5, S-2-3-Sink, t=24)",
          b == (-5, ["Source", 2, 3, "Sink"], 24), f"bf={b}")
    cross_check("C1 chained waiting", nodes, edges)
    # C1': sink deadline 23 kills node-3 routes entirely
    nodes2 = {**nodes, "Sink": (0, 23, 0)}
    b2 = bf_opt(nodes2, edges)
    check("C1': manual expected (-2, S-2-Sink)",
          b2[0] == -2 and b2[1] == ["Source", 2, "Sink"], f"bf={b2}")
    cross_check("C1' sink deadline kills chain", nodes2, edges)

    # C2: dominance trap - cheap&late vs expensive&early at node 3
    nodes = {"Source": (0, 100, 0), 1: (0, 100, 0), 2: (0, 100, 0),
             3: (0, 100, 0), 4: (0, 5, 0), "Sink": (0, 100, 0)}
    edges = [("Source", 1, 1, -5), (1, 3, 10, -5),   # L1: cost -10, t=11
             ("Source", 2, 1, 0), (2, 3, 1, 0),      # L2: cost 0,  t=2
             (3, 4, 1, 0), (4, "Sink", 1, -20),      # only L2 fits b_4=5
             (3, "Sink", 1, 0)]
    b = bf_opt(nodes, edges)
    check("C2: manual expected (-20 via S-2-3-4-Sink)",
          b[0] == -20 and b[1] == ["Source", 2, 3, 4, "Sink"], f"bf={b}")
    cross_check("C2 dominance trap (must keep dominated-in-cost label)",
                nodes, edges)

    # C3: non-triangle travel: direct 1->3 infeasible, indirect 1->2->3 ok
    nodes = {"Source": (0, 100, 0), 1: (0, 100, 0), 2: (0, 100, 0),
             3: (0, 6, 0), "Sink": (0, 200, 0)}
    edges = [("Source", 1, 1, 0), (1, 3, 100, 0), (1, 2, 1, 0),
             (2, 3, 1, -50), (3, "Sink", 1, 0), (1, "Sink", 1, 0),
             (2, "Sink", 1, 0)]
    b = bf_opt(nodes, edges)
    check("C3: manual expected (-50 via S-1-2-3-Sink)",
          b[0] == -50 and b[1] == ["Source", 1, 2, 3, "Sink"], f"bf={b}")
    cross_check("C3 non-triangle (failed direct ext must not block indirect)",
                nodes, edges)

    # C4: a_Source > 0 (edge case, PoC never uses it): does cspy's clock
    # start at a_Source? PoC REF starts the clock at 0 regardless.
    nodes = {"Source": (5, 100, 0), 1: (0, 3, 0), "Sink": (0, 100, 0)}
    edges = [("Source", 1, 1, -10), (1, "Sink", 1, 0),
             ("Source", "Sink", 1, -1)]
    # true model (clock starts at a_Source=5): arrival at 1 = 6 > b_1=3 =>
    # only S-Sink feasible, cost -1. Clock-at-0 model: arrival 1 <= 3, cost -10
    b = bf_opt(nodes, edges)
    p, c, r = cspy_solve(nodes, edges, "forward")
    check("C4: a_Source>0 caveat (expected mismatch: bf=-1 vs cspy=-10)",
          b[0] == -1 and c == -10.0, f"bf={b} cspy={c} {p}  <- known caveat",)


# ---------------------------------------------------------------------------
# D/E. Random stress
# ---------------------------------------------------------------------------
def rand_instance(rng, n_cust):
    nodes = {"Source": (0, 60, 0)}
    for i in range(1, n_cust + 1):
        a = rng.randint(0, 12)
        nodes[i] = (a, a + rng.randint(2, 15), rng.randint(0, 3))
    nodes["Sink"] = (0, rng.randint(15, 45), 0)
    edges = []
    cust = list(range(1, n_cust + 1))
    for i in cust:
        if rng.random() < 0.75:
            edges.append(("Source", i, rng.randint(1, 8), rng.randint(-10, 4)))
        if rng.random() < 0.75:
            edges.append((i, "Sink", rng.randint(1, 8), rng.randint(-10, 4)))
    for i in cust:
        for j in cust:
            if i != j and rng.random() < 0.5:
                edges.append((i, j, rng.randint(1, 10), rng.randint(-10, 4)))
    if not any(u == "Source" for (u, v, _, _) in edges):
        edges.append(("Source", 1, 1, 0))
    if not any(v == "Sink" for (u, v, _, _) in edges):
        edges.append((n_cust, "Sink", 1, 0))
    return nodes, edges


def part_D(n_inst=60):
    print("--- D. random stress (elementary=True, fwd + both) ---")
    bad = 0
    n_feasible = 0
    for seed in range(n_inst):
        rng = random.Random(1000 + seed)
        n_cust = rng.choice([4, 5])
        nodes, edges = rand_instance(rng, n_cust)
        best = bf_opt(nodes, edges)
        if best is not None:
            n_feasible += 1
        _, emap = bf_paths(nodes, edges)
        for d in ("forward", "both"):
            path, cost, res = cspy_solve(nodes, edges, d)
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
                check(f"D seed={seed} [{d}]", False,
                      f"bf={best} cspy={cost} path={path} nodes={nodes} "
                      f"edges={edges}")
    check(f"D: {n_inst} random instances x2 dirs "
          f"({n_feasible} feasible)", bad == 0, f"{bad} mismatches")


def part_E(n_inst=25):
    print("--- E. random stress (elementary=False, walks<=6 edges, fwd) ---")
    bad = 0
    for seed in range(n_inst):
        rng = random.Random(9000 + seed)
        nodes, edges = rand_instance(rng, 4)
        best = bf_opt(nodes, edges, elementary=False, max_edges=6)
        _, emap = bf_paths(nodes, edges, elementary=False, max_edges=6)
        path, cost, res = cspy_solve(nodes, edges, "forward",
                                     elementary=False, max_edges=6)
        if best is None:
            ok = path is None
        elif path is None:
            ok = False
        else:
            feas, c2, t2 = sim(path, nodes, emap)
            ok = feas and abs(c2 - cost) < 1e-9 \
                and abs(cost - best[0]) < 1e-9 and abs(res[1] - t2) < 1e-9
        if not ok:
            bad += 1
            check(f"E seed={seed}", False,
                  f"bf={best} cspy={cost} path={path} nodes={nodes} "
                  f"edges={edges}")
    check(f"E: {n_inst} random non-elementary instances", bad == 0,
          f"{bad} mismatches")


if __name__ == "__main__":
    part_A()
    part_B()
    part_C()
    part_D()
    part_E()
    print("=" * 70)
    print(f"TOTAL: {CHECKS[0]} checks, {len(FAILURES)} failures")
    for nm, det in FAILURES:
        print(f"  FAIL: {nm}: {det}")
