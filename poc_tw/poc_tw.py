#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoC: demonstrates that ESPPRC with "per-node time windows [a_i, b_i] +
per-node service times s_i (LT)" can be solved with cspy (C++ core, SWIG
binding) using only the official custom REF mechanism (cspy.REFCallback),
with no C++ modifications.

- REF_fwd:  T_new = max(a_head, T_cur + s_tail + t_edge)  (wait until a_head on early arrival)
            if T_new > b_head, return an INF sentinel (> max_res[1]) to reject the label
- REF_bwd:  time axis reversal g = T_horizon - L (L = latest feasible service start at that node)
            g_tail = max(g_head + s_tail + t_edge, T - b_tail); reject if g_tail > T - a_tail
- REF_join: merged_time = max(a_head, f_tail + s_tail + t_edge) + g_head
            (<= T_horizon iff the joined path is time-window feasible)
- Resources: res[0] = monotone edge-count counter (critical resource), res[1] = time
- Independent verification: enumerate all elementary paths (or, when non-elementary,
  walks bounded by an edge-count cap) by brute force, compute the exact optimum with
  Fraction arithmetic, and cross-check against cspy.
"""
import sys
from fractions import Fraction

import numpy as np
import networkx as nx

from cspy import BiDirectional, REFCallback

TOL = 1e-9


# ---------------------------------------------------------------------------
# Instance definitions
# ---------------------------------------------------------------------------
def base_instance():
    """Source + 4 customer nodes + Sink. Weights represent reduced costs from a
    column-generation pricing problem (mostly negative). Designed so the time
    windows are binding:
      shortest path ignoring time windows : Source-1-2-3-4-Sink (cost -28) but violates b_3=10
      optimal path with time windows      : Source-2-3-4-Sink   (cost -21)
    """
    # node: (a_i, b_i, s_i)  -- both b_i (latest time) and s_i vary per node
    nodes = {
        "Source": (0, 100, 0),
        1: (0, 100, 2),
        2: (0, 12, 3),
        3: (0, 10, 1),
        4: (0, 20, 4),
        "Sink": (0, 100, 0),
    }
    # (tail, head, travel_time, weight)
    edges = [
        ("Source", 1, 2, -5),
        ("Source", 2, 3, -4),
        ("Source", 3, 5, 1),
        (1, 2, 3, -6),
        (1, 3, 4, -3),
        (1, 4, 8, -1),
        (2, 3, 3, -7),
        (2, 4, 4, -2),
        (3, 4, 2, -6),
        (4, "Sink", 2, -4),
        (3, "Sink", 3, 0),
        (2, "Sink", 5, 1),
        (1, "Sink", 10, 2),
    ]
    return nodes, edges


def cycle_instance():
    """Instance containing a negative-cost 2-cycle (1<->2).
    When elementary=False, using the cycle is advantageous (-13); when elementary=True,
    the elementary path is optimal (-3)."""
    nodes = {
        "Source": (0, 100, 0),
        1: (0, 100, 1),
        2: (0, 100, 2),
        "Sink": (0, 100, 0),
    }
    edges = [
        ("Source", 1, 1, 1),
        (1, 2, 1, -5),
        (2, 1, 1, -5),
        (2, "Sink", 1, 1),
    ]
    return nodes, edges


def build_graph(nodes, edges):
    G = nx.DiGraph(directed=True, n_res=2)
    for v, (a, b, s) in nodes.items():
        G.add_node(v, tw_a=float(a), tw_b=float(b), service=float(s))
    for (u, v, t, w) in edges:
        # res_cost[0]=1 (edge-count counter), res_cost[1]=travel time
        G.add_edge(u, v, res_cost=np.array([1.0, float(t)]), weight=float(w))
    return G


# ---------------------------------------------------------------------------
# Custom REFs (time windows + per-node service time)
# ---------------------------------------------------------------------------
class TWCallback(REFCallback):
    """res[0]=edge count (critical, monotone), res[1]=time (service start time)."""

    def __init__(self, max_res):
        REFCallback.__init__(self)
        self.G = None                     # injected as alg.G after BiDirectional is built (required)
        self._max_res = list(max_res)
        self.T = float(max_res[1])        # global time horizon
        self.INF = self.T + 1000.0        # exceeding max_res[1] => rejected by checkFeasibility

    def _node(self, v):
        nd = self.G.nodes[v]
        return nd["tw_a"], nd["tw_b"], nd["service"]

    def REF_fwd(self, cumul_res, tail, head, edge_res, partial_path, cumul_cost):
        new = list(cumul_res)
        new[0] += edge_res[0]                           # monotone resource
        a_h, b_h, _s_h = self._node(head)
        _a_t, _b_t, s_t = self._node(tail)
        arrival = cumul_res[1] + s_t + edge_res[1]      # travel after service at tail
        start = max(a_h, arrival)                       # wait until a_h on early arrival
        new[1] = start if start <= b_h + TOL else self.INF   # reject if b_h is exceeded
        return new

    def REF_bwd(self, cumul_res, tail, head, edge_res, partial_path, cumul_cost):
        # the backward label sits at head and extends toward tail (tail/head follow the original edge direction)
        new = list(cumul_res)
        new[0] -= edge_res[0]                           # critical resource is subtracted (cspy convention)
        a_t, b_t, s_t = self._node(tail)
        _a_h, b_h, _s_h = self._node(head)
        # g = T - L (L = latest feasible service start time). The Sink's initial label has g=0, so correct for it
        g_h = max(cumul_res[1], self.T - b_h)
        g_t = max(g_h + s_t + edge_res[1], self.T - b_t)
        new[1] = g_t if g_t <= self.T - a_t + TOL else self.INF
        return new

    def REF_join(self, fwd_res, bwd_res, tail, head, edge_res):
        merged = [0.0] * len(fwd_res)
        # critical resource: fwd + edge + (reversed bwd) => total edge count
        merged[0] = fwd_res[0] + edge_res[0] + (self._max_res[0] - bwd_res[0])
        a_h, b_h, _s_h = self._node(head)
        _a_t, _b_t, s_t = self._node(tail)
        g_h = max(bwd_res[1], self.T - b_h)
        start_h = max(a_h, fwd_res[1] + s_t + edge_res[1])
        if start_h > b_h + TOL:
            merged[1] = self.INF
        else:
            merged[1] = start_h + g_h   # <= T iff the joined path is feasible
        return merged


def run_cspy(nodes, edges, direction="forward", elementary=True, max_edges=10):
    G = build_graph(nodes, edges)
    horizon = max(b for (_a, b, _s) in nodes.values())
    max_res = [float(max_edges), float(horizon)]
    min_res = [0.0, 0.0]
    cb = TWCallback(max_res)
    alg = BiDirectional(G, max_res, min_res, direction=direction,
                        elementary=elementary, REF_callback=cb)
    cb.G = alg.G                     # official idiom: inject the graph after integer-ID conversion
    alg.run()
    res = alg.consumed_resources
    return alg.path, alg.total_cost, (list(res) if res is not None else None)


# ---------------------------------------------------------------------------
# Independent verification (brute force + exact Fraction arithmetic)
# ---------------------------------------------------------------------------
def simulate(path, nodes, emap, wait=True):
    """Forward-simulate path. Returns (feasible, cost, sink_service_start)."""
    a0, b0, _ = nodes[path[0]]
    t = Fraction(max(0, a0))
    cost = Fraction(0)
    for u, v in zip(path[:-1], path[1:]):
        if (u, v) not in emap:
            return False, None, None
        tt, w = emap[(u, v)]
        _au, _bu, su = nodes[u]
        av, bv, _sv = nodes[v]
        arrival = t + Fraction(su) + Fraction(tt)
        if arrival < Fraction(av):
            if not wait:
                return False, None, None      # used to contrast with the reject-on-early-arrival (no-wait) mode
            arrival = Fraction(av)
        if arrival > Fraction(bv):
            return False, None, None
        t = arrival
        cost += Fraction(w)
    return True, cost, t


def brute_force(nodes, edges, elementary=True, max_edges=10, wait=True,
                ignore_tw=False):
    """Brute-force all elementary paths (or walks) and return the exact optimum."""
    emap = {(u, v): (t, w) for (u, v, t, w) in edges}
    nodes_eff = nodes
    if ignore_tw:
        big = 10 ** 9
        nodes_eff = {k: (0, big, s) for k, (a, b, s) in nodes.items()}

    G = nx.DiGraph()
    G.add_edges_from(emap.keys())
    paths = []
    if elementary:
        paths = list(nx.all_simple_paths(G, "Source", "Sink"))
    else:  # enumerate edge-count-bounded walks via DFS
        stack = [["Source"]]
        while stack:
            p = stack.pop()
            if p[-1] == "Sink":
                paths.append(p)
                continue
            if len(p) - 1 >= max_edges:
                continue
            for nxt in G.successors(p[-1]):
                stack.append(p + [nxt])

    best = None
    for p in paths:
        if len(p) - 1 > max_edges:
            continue
        ok, cost, t_sink = simulate(p, nodes_eff, emap, wait=wait)
        if ok and (best is None or cost < best[1]):
            best = (p, cost, t_sink)
    return best  # (path, exact cost, exact sink time)


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
RESULTS = []


def record(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(("PASS" if ok else "FAIL") + f" | {name}\n     {detail}\n")


def compare(name, cspy_out, bf, extra=""):
    path_c, cost_c, res_c = cspy_out
    path_b, cost_b, t_b = bf
    ok = (path_c == path_b
          and abs(cost_c - float(cost_b)) < TOL
          and abs(res_c[1] - float(t_b)) < TOL)
    detail = (f"cspy: path={path_c}, cost={cost_c}, res={res_c} / "
              f"brute-force(Fraction): path={path_b}, cost={cost_b}, "
              f"sink_time={t_b}{extra}")
    record(name, ok, detail)
    return ok


def main():
    nodes, edges = base_instance()

    # --- Test 1: prove time windows are binding (brute force only) ---
    bf_tw = brute_force(nodes, edges)                    # exact optimum with TW
    bf_free = brute_force(nodes, edges, ignore_tw=True)  # shortest path ignoring TW
    ok = (bf_free[0] == ["Source", 1, 2, 3, 4, "Sink"] and bf_free[1] == -28
          and bf_tw[0] == ["Source", 2, 3, 4, "Sink"] and bf_tw[1] == -21
          and bf_free[0] != bf_tw[0])
    # also confirm that the TW-ignoring optimal path is infeasible under TW
    emap = {(u, v): (t, w) for (u, v, t, w) in edges}
    infeas = not simulate(bf_free[0], nodes, emap)[0]
    record("1. TW binding (unconstrained opt != TW opt, the former is infeasible under TW)",
           ok and infeas,
           f"ignoring TW: {bf_free[0]} cost={bf_free[1]} (infeasible under TW={infeas}) / "
           f"with TW: {bf_tw[0]} cost={bf_tw[1]}")

    # --- Test 2: base instance, direction='forward', cspy vs brute force ---
    out = run_cspy(nodes, edges, direction="forward")
    compare("2. base ESPPRC-TW forward (expected: S-2-3-4-Sink, cost=-21, t=18)",
            out, bf_tw)

    # --- Test 3(a): relaxing the time windows matches the TW-free shortest path ---
    relaxed = {k: (0, 100, s) for k, (a, b, s) in nodes.items()}
    out = run_cspy(relaxed, edges, direction="forward")
    bf = brute_force(relaxed, edges)
    same_as_free = out[0] == bf_free[0] and abs(out[1] - float(bf_free[1])) < TOL
    compare("3a. relaxed time windows (expected: S-1-2-3-4-Sink, cost=-28, t=22; matches TW-free shortest path="
            + str(same_as_free), out, bf)

    # --- Test 3(b): changing service time (s_2: 3->6) changes the optimal path ---
    nodes_b = dict(nodes)
    nodes_b[2] = (0, 12, 6)
    out = run_cspy(nodes_b, edges, direction="forward")
    bf = brute_force(nodes_b, edges)
    changed = out[0] != bf_tw[0]
    compare("3b. s_2=3->6 changes the optimal path (expected: S-1-3-4-Sink, cost=-18, t=17, "
            f"path changed={changed})", out, bf)

    # --- Test 3(c1): a case requiring waiting (a_4=13, S-2-3-4 arrives at 12 -> waits until 13) ---
    nodes_c = dict(nodes)
    nodes_c[4] = (13, 20, 4)
    out = run_cspy(nodes_c, edges, direction="forward")
    bf = brute_force(nodes_c, edges)
    # also confirm the optimum changes under reject-on-early-arrival (no wait) => proves the wait semantics matter
    bf_nowait = brute_force(nodes_c, edges, wait=False)
    compare("3c1. wait case a_4=13 (expected: S-2-3-4-Sink, cost=-21, t=19; "
            f"without waiting: {bf_nowait[0]} cost={bf_nowait[1]})", out, bf)
    record("3c1'. allowing waiting vs rejecting early arrival gives different optima (wait handling is essential)",
           bf_nowait[1] != bf[1],
           f"wait: cost={bf[1]} / no-wait: cost={bf_nowait[1]}")

    # --- Test 3(c2): wait propagation violates the Sink deadline -> optimal path changes further ---
    nodes_c2 = dict(nodes_c)
    nodes_c2["Sink"] = (0, 18, 0)
    out = run_cspy(nodes_c2, edges, direction="forward")
    bf = brute_force(nodes_c2, edges)
    compare("3c2. a_4=13 + b_Sink=18: wait propagation eliminates all paths through node 4 "
            "(expected: S-2-3-Sink, cost=-11, t=13)", out, bf)

    # --- Test 4: direction='both' (REF_bwd + REF_join) matches forward ---
    for name, nd in [("base", nodes), ("3b", nodes_b), ("3c1", nodes_c),
                     ("3c2", nodes_c2)]:
        out_f = run_cspy(nd, edges, direction="forward")
        out_b = run_cspy(nd, edges, direction="both")
        ok = out_f[0] == out_b[0] and abs(out_f[1] - out_b[1]) < TOL
        record(f"4. direction='both' == forward ({name})", ok,
               f"forward: {out_f[0]} cost={out_f[1]} / "
               f"both: {out_b[0]} cost={out_b[1]} res={out_b[2]}")

    # --- Test 5: elementary=True vs False (negative-cost 2-cycle) ---
    cnodes, cedges = cycle_instance()
    out_el = run_cspy(cnodes, cedges, direction="forward", elementary=True,
                      max_edges=6)
    bf_el = brute_force(cnodes, cedges, elementary=True, max_edges=6)
    compare("5a. elementary=True: elementary path even though the cycle would be advantageous (expected: S-1-2-Sink, "
            "cost=-3, t=6)", out_el, bf_el)
    out_ne = run_cspy(cnodes, cedges, direction="forward", elementary=False,
                      max_edges=6)
    bf_ne = brute_force(cnodes, cedges, elementary=False, max_edges=6)
    compare("5b. elementary=False: uses the negative-cost 2-cycle (expected: S-1-2-1-2-Sink, "
            "cost=-13, t=11)", out_ne, bf_ne)
    record("5c. the elementary flag changes the outcome (cycle gain -13 vs -3)",
           out_el[1] != out_ne[1],
           f"elementary=True: cost={out_el[1]} / False: cost={out_ne[1]}")

    # --- summary ---
    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    print("=" * 70)
    print(f"SUMMARY: {n_ok}/{len(RESULTS)} tests passed")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
