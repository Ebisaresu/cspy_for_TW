#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Teaching example: solve the Traveling Salesman Problem with Time Windows
(TSPTW) using a custom REF (Resource Extension Function) in cspy.

Problem setup
    Starting from the depot (0), visit each customer 1..n exactly once
    within its time window [a_i, b_i] (if arriving early, wait until a_i;
    arriving later than b_i is not allowed), then return to the depot.
    Visiting customer i consumes a service time s_i. The objective is to
    minimize total travel time (waiting time and service time are not part
    of the cost).

Reduction to cspy (a Resource Constrained Shortest Path / RCSP solver)
    - Split the depot into a Source (departure) and a Sink (return), and
      search for a Source -> customer -> ... -> Sink path. elementary=True
      restricts the search to elementary paths that visit each node at
      most once.
    - Resource vector res (n_res = 2 + n):
        res[0]      edge-count counter (critical resource, a monotone
                    resource that the REF increments by res_cost[0]=1 on
                    every edge)
        res[1]      time = the service start time at that node
        res[2+i-1]  visit flag for customer i (unvisited 0 / visited -1)
                    -- see "dominance" below
    - Time is propagated by a custom REF (REF_fwd of cspy.REFCallback):
          T_new = max(a_head, T + s_tail + t_edge)
      and if T_new > b_head, a sentinel value exceeding max_res[1] is
      returned so that cspy's resource check (Label::checkFeasibility)
      rejects the label.

Enforcing "all customers visited" (Hamiltonicity) -- two approaches were
compared experimentally, and (b) was adopted
    (a) Impose min_res[0] = n+1 on the critical resource -> does NOT work
        (immediately returns the degenerate path ['Source']).
        cspy treats the min_res of the critical resource not as a "lower
        bound at the Sink" but as the floor for the halfway point of the
        bidirectional search (bidirectional.cc updateHalfWayPoints), and
        during extension, checkFeasibility always compares only the
        critical resource against min_res (labelling.cc). With
        min_res[0]=7, the very first edge (res[0]=1 < 7) becomes
        infeasible immediately, killing every label and returning the
        degenerate path ['Source'].
        (Note: imposing min_res on a "non-critical duplicate counter
         resource" instead works, via the terminal
         checkFeasibility(soft=false), and yields the correct answer, but
         this adds one more resource and relies on the internal semantics
         of the soft check, so it was not adopted.)
    (b) Inside REF_fwd, when head==Sink and len(partial_path) < n+1,
        return a sentinel value for the time resource to reject the label
        -> robust. Adopted in this file.
        (partial_path is the partial path *before* extension, so once all
         customers have been visited it contains Source + n customers =
         n+1 nodes.)

Why the visit-flag resources res[2..] are needed (the key point of this
teaching example)
    cspy's dominance check (labelling.cc checkDominance) requires "cost <=
    and all resources <=", and when elementary=True it additionally
    requires a Feillet-style containment condition
    (checkSameFeasibleExtensionElementary: the winner's unreachable_nodes
    must be a subset of the loser's). This is sound whenever every
    elementary path is a feasible ESPPRC solution, but it is not sufficient for
    TSPTW: this containment condition allows a label whose visited set is
    a proper subset to dominate a label with a superset visited set, which
    prunes away Hamiltonian paths that can only be completed by extending
    the superset label. Decrementing the flag from 0 to -1 when customer i
    is visited makes "all resources <=" require containment (superset, >=)
    of the visited sets, and combined with "size <=" on res[0] this
    restricts domination to labels whose visited sets coincide exactly,
    making dominance sound.
    Note: the reverse direction, 0 -> +1, does not work: it flips the
    containment direction (subset, <=), leaving in place exactly the
    unsoundness we want to eliminate -- "a cheap label whose visited set
    is a subset dominates a label with a superset visited set."
    Without the flags (n_res=2), this instance has no solution
    (['Source']) (demonstrated by V8 of --verify:
    solve_tsptw(use_flags=False)).

Usage
    $ python3 tsptw_cspy.py              # print the solution and schedule
    $ python3 tsptw_cspy.py --verify     # cross-check against an exhaustive
                                          # search over all permutations
                                          # (6!=720)
    $ python3 tsptw_cspy.py --infeasible # demo of handling an infeasible
                                          # instance
"""
from __future__ import annotations

import argparse
import itertools
import sys
import unicodedata
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Sequence

import networkx as nx
import numpy as np

from cspy_tw import BiDirectional, REFCallback

TOL = 1e-9  # for floating-point comparisons (moot in practice, since all data in this example are integers)


# ---------------------------------------------------------------------------
# 1. Instance definition
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TSPTWInstance:
    """A TSPTW instance. Index 0 is the depot, 1..n are the customers."""

    n: int                       # number of customers
    travel: tuple[tuple[int, ...], ...]  # travel time travel[i][j] (asymmetric)
    tw_a: tuple[int, ...]        # time-window lower bound a_i (wait until a_i if early)
    tw_b: tuple[int, ...]        # time-window upper bound b_i (arriving later is not allowed)
    service: tuple[int, ...]     # service time s_i (0 for the depot)

    @property
    def horizon(self) -> int:
        """Time horizon (= depot return deadline b_0)."""
        return self.tw_b[0]


# Design rationale (confirmed by exhaustive search):
#   - The time-window-free optimal tour 0-6-1-4-2-3-5-0 (cost 29) is
#     infeasible under the time windows; the TSPTW optimum is
#     0-2-5-4-1-6-3-0 (cost 33) -> the time windows are binding
#   - In the optimal tour, customer 4 is reached early at time 20 and waits
#     12 units until a_4=32 (also includes the tight case of arriving at
#     customer 5 exactly at the deadline b_5=13)
#   - Service times differ across all customers; setting them all to s=3
#     changes the optimal order
INSTANCE = TSPTWInstance(
    n=6,
    travel=(
        # 0   1   2   3   4   5   6
        (0, 11,  8,  5,  8,  5,  7),   # from 0 (depot)
        (9,  0,  7, 12,  3, 11,  7),   # from 1
        (8, 12,  0,  4,  8,  3, 11),   # from 2
        (3,  4, 10,  0,  8,  3,  8),   # from 3
        (10, 3,  3,  6,  0,  8,  4),   # from 4
        (5,  8,  5, 12,  4,  0, 10),   # from 5
        (8,  4,  7,  5, 12,  4,  0),   # from 6
    ),
    tw_a=(0, 39, 2, 38, 32, 2, 42),
    tw_b=(200, 59, 18, 60, 57, 13, 60),
    service=(0, 6, 2, 4, 5, 3, 1),
)


# ---------------------------------------------------------------------------
# 2. Custom REF: time-window propagation + Hamiltonicity enforcement
# ---------------------------------------------------------------------------
class TSPTWCallback(REFCallback):
    """Defines only the forward Resource Extension Function (REF_fwd)
    (used with direction='forward').

    Note: if direction='both' is used without also defining REF_bwd, the
    backward direction is extended using the C++-side default REF (adds
    res_cost for non-critical resources, subtracts it for the critical
    resource; ref_callback.cc additiveBackwardREF). cspy proceeds without
    raising an error or a warning (the warning branch in checking.py
    _check_REF does not fire, because the SWIG base class always exposes
    REF_bwd as callable), so a "silently wrong solution" can be returned.
    Using forward direction only is recommended.
    """

    def __init__(self, inst: TSPTWInstance, enforce_hamiltonian: bool = True,
                 use_flags: bool = True):
        REFCallback.__init__(self)
        # cspy internally works with a graph whose nodes have been
        # converted to integer IDs, so alg.G must be injected here after
        # the BiDirectional object is constructed (the official idiom; see
        # test/python/tests_issue32.py). Node attributes carry over
        # unchanged, and the original_label attribute maps back to the
        # original node name ("Source"/1..n/"Sink").
        self.G: Optional[nx.DiGraph] = None
        self._n = inst.n
        # Returning a value exceeding max_res[1] (= horizon) makes
        # checkFeasibility reject the label
        self._inf = float(inst.horizon) + 1000.0
        self._enforce = enforce_hamiltonian
        self._use_flags = use_flags

    def REF_fwd(self, cumul_res: Sequence[float], tail: int, head: int,
                edge_res: Sequence[float], partial_path: Sequence[int],
                cumul_cost: float) -> list[float]:
        """Return the resource vector after extension (a list of length n_res).

        Arguments as passed in via SWIG:
            cumul_res     cumulative resources upon reaching tail
            tail, head    cspy's internal integer node IDs (map back via
                          original_label)
            edge_res      the edge's res_cost
            partial_path  the partial path *before* extension (a sequence
                          of integer IDs; head is not yet included)
            cumul_cost    cumulative weight upon reaching tail (unused in
                          this example)
        """
        new = list(cumul_res)

        # --- res[0]: edge-count counter (critical resource, res_cost[0]=1 on every edge) ---
        new[0] += edge_res[0]

        nd_tail = self.G.nodes[tail]
        nd_head = self.G.nodes[head]
        head_orig = nd_head["original_label"]   # original node name (int or str)

        # --- res[2+i-1]: visit flag for customer i, 0 -> -1 ---
        # A resource that restricts dominance to labels whose visited sets
        # coincide exactly. See the module docstring for details.
        # use_flags=False demonstrates the resulting unsoundness (V8).
        if self._use_flags and isinstance(head_orig, int):
            new[2 + head_orig - 1] = cumul_res[2 + head_orig - 1] - 1.0

        # --- Enforcing Hamiltonicity (approach (b), the one adopted) ---
        # partial_path is the partial path *before* extension (head is not
        # included). Once all customers have been visited, it must contain
        # Source + n customers = n+1 nodes, so reject with a sentinel any
        # label that reaches the Sink before that.
        if (self._enforce and head_orig == "Sink"
                and len(partial_path) < self._n + 1):
            new[1] = self._inf
            return new

        # --- res[1]: time propagation  T_new = max(a_head, T + s_tail + t_edge) ---
        #   T          = cumul_res[1]        (service start time at tail)
        #   s_tail     = nd_tail["service"]  (service time at tail)
        #   t_edge     = edge_res[1]         (travel time on the edge)
        #   a_head     = nd_head["tw_a"]     (wait until a_head if early)
        # This instance has a_Source=0, so tail==Source needs no special
        # handling here (note that an instance with a_Source>0 would need
        # to adjust the initial time).
        arrival = cumul_res[1] + nd_tail["service"] + edge_res[1]
        start = max(nd_head["tw_a"], arrival)
        # Above b_head: return a sentinel (checkFeasibility rejects it for us)
        new[1] = start if start <= nd_head["tw_b"] + TOL else self._inf
        return new


# ---------------------------------------------------------------------------
# 3. Graph construction
# ---------------------------------------------------------------------------
def build_graph(inst: TSPTWInstance, use_flags: bool = True) -> nx.DiGraph:
    """Build the complete graph over the Source/Sink-split depot and the customers.

    cspy's requirements: a graph attribute n_res, and on every edge a
    weight and a res_cost of length n_res (a numpy array is recommended;
    BiDirectional only checks the length and also accepts a list, but
    other algorithms also check the ndarray type; see checking.py
    _check_edge_attr). Contents of res_cost:
        [0] = 1    edge count (REF_fwd adds edge_res[0])
        [1] = travel time (REF_fwd reads it as edge_res[1])
        [2..] = 0  dummy values for the visit flags (the REF builds the
                   flags from node attributes, so edge_res[2..] is never
                   read)
    use_flags=False builds a reduced n_res=2 version without the
    visit-flag resources (demonstrates the resulting unsoundness of
    dominance, --verify's V8).
    """
    n_res = (2 + inst.n) if use_flags else 2
    # Note: the directed=True kwarg seen in nx.DiGraph(directed=True, ...)
    # in cspy's official examples is just a plain graph attribute that
    # neither networkx nor cspy reads, so it is omitted here.
    G = nx.DiGraph(n_res=n_res)

    # Nodes: carry time windows and service time as attributes (read by the REF)
    G.add_node("Source", tw_a=0.0, tw_b=float(inst.horizon), service=0.0)
    G.add_node("Sink", tw_a=0.0, tw_b=float(inst.horizon), service=0.0)
    for i in range(1, inst.n + 1):
        G.add_node(i, tw_a=float(inst.tw_a[i]), tw_b=float(inst.tw_b[i]),
                   service=float(inst.service[i]))

    def res_cost(t: int) -> np.ndarray:
        return np.array([1.0, float(t)] + [0.0] * (n_res - 2))

    for i in range(1, inst.n + 1):
        t = inst.travel[0][i]
        G.add_edge("Source", i, res_cost=res_cost(t), weight=float(t))
        t = inst.travel[i][0]
        G.add_edge(i, "Sink", res_cost=res_cost(t), weight=float(t))
        for j in range(1, inst.n + 1):
            if i != j:
                t = inst.travel[i][j]
                G.add_edge(i, j, res_cost=res_cost(t), weight=float(t))
    return G


# ---------------------------------------------------------------------------
# 4. Solving
# ---------------------------------------------------------------------------
@dataclass
class ScheduleRow:
    node: str          # node name for display
    arrival: int       # arrival time (before waiting)
    wait: int          # waiting time
    start: int         # service start time (= max(a, arrival))
    departure: int     # departure time (= start + service time)


@dataclass
class Solution:
    tour: list[str | int]        # ["Source", i1, ..., in, "Sink"]
    cost: float                  # total travel time
    consumed: list[float]        # cspy's consumed_resources
    schedule: list[ScheduleRow]  # schedule (recomputed by compute_schedule)
    total_wait: int


def compute_schedule(inst: TSPTWInstance,
                     tour: list) -> tuple[list[ScheduleRow], int]:
    """Forward-simulate the tour to build the schedule (exact integer arithmetic)."""

    def data_idx(v) -> int:
        return 0 if v in ("Source", "Sink") else v

    rows = [ScheduleRow("Source", 0, 0, 0, 0)]
    t = 0
    for u, v in zip(tour[:-1], tour[1:]):
        iu, iv = data_idx(u), data_idx(v)
        arrival = t + inst.service[iu] + inst.travel[iu][iv]
        a, b = (0, inst.horizon) if v == "Sink" else \
            (inst.tw_a[iv], inst.tw_b[iv])
        start = max(a, arrival)
        assert start <= b, f"time-window violation: node {v}"
        s = 0 if v == "Sink" else inst.service[iv]
        rows.append(ScheduleRow(str(v), arrival, start - arrival, start,
                                start + s))
        t = start
    total_wait = sum(r.wait for r in rows)
    return rows, total_wait


def solve_tsptw(inst: TSPTWInstance, enforce: str = "sentinel",
                use_flags: bool = True) -> Optional[Solution]:
    """Solve TSPTW with cspy (BiDirectional, forward).

    enforce: how Hamiltonicity is enforced
        "sentinel"         approach (b), the one adopted: reject early
                            arrival at the Sink inside the REF (default)
        "min_res_critical" approach (a), not adopted: min_res on the
                            critical resource (demonstrates that it does
                            not work)
        "none"             no enforcement (demonstrates customer skipping)
    use_flags: if False, drop the visit-flag resources res[2..]
        (demonstrates that dominance becomes unsound and yields no
        solution, --verify's V8)
    Returns None if infeasible (or if there is no Hamiltonian path).
    """
    G = build_graph(inst, use_flags=use_flags)
    # Resource bounds. res[0] goes up to exactly n+1 edges; res[1] up to
    # horizon. The visit flags range over [-1, 0] (a second visit is
    # already prevented by elementary=True).
    n_flags = inst.n if use_flags else 0
    max_res = [float(inst.n + 1), float(inst.horizon)] + [0.0] * n_flags
    min_res = [0.0, 0.0] + [-1.0] * n_flags
    if enforce == "min_res_critical":
        min_res[0] = float(inst.n + 1)

    cb = TSPTWCallback(inst, enforce_hamiltonian=(enforce == "sentinel"),
                       use_flags=use_flags)
    # Note: REF_callback cannot be combined with find_critical_res=True.
    #       Also, the prune_graph preprocessing step is always skipped.
    alg = BiDirectional(G, max_res, min_res, direction="forward",
                        elementary=True, REF_callback=cb)
    cb.G = alg.G          # inject the graph with internal IDs into the REF (required)
    alg.run()

    path = alg.path
    # Gotcha: when infeasible, cspy returns the degenerate path ['Source']
    # instead of raising an exception
    if not path or path[-1] != "Sink":
        return None
    schedule, total_wait = compute_schedule(inst, path)
    return Solution(tour=path, cost=alg.total_cost,
                    consumed=list(alg.consumed_resources),
                    schedule=schedule, total_wait=total_wait)


def _rjust_cjk(s: str, width: int) -> str:
    """Right-justify a string, counting full-width characters as 2 columns
    (for aligning table columns in the terminal)."""
    disp = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    return " " * max(0, width - disp) + s


def print_solution(inst: TSPTWInstance, sol: Solution) -> None:
    tour_str = " -> ".join(str(v) for v in sol.tour)
    print(f"Optimal tour   : {tour_str}")
    print(f"Total travel time : {sol.cost:g}   Total wait time : {sol.total_wait}")
    print(f"Consumed resources : edges={sol.consumed[0]:g}, "
          f"depot return (service start) time={sol.consumed[1]:g}")
    print()
    widths = (6, 10, 8, 6, 6, 6, 6)
    header = ("Node", "Window", "Service", "Arrive", "Wait", "Start", "Depart")
    print(" ".join(_rjust_cjk(h, w) for h, w in zip(header, widths)))
    for r in sol.schedule:
        # The depot (Source/Sink) uses data index 0 (tw=[0,horizon], service=0)
        i = 0 if r.node in ("Source", "Sink") else int(r.node)
        cells = (r.node, f"[{inst.tw_a[i]},{inst.tw_b[i]}]",
                 str(inst.service[i]), str(r.arrival), str(r.wait),
                 str(r.start), str(r.departure))
        print(" ".join(_rjust_cjk(c, w) for c, w in zip(cells, widths)))


# ---------------------------------------------------------------------------
# 5. Exhaustive-search verification (--verify)
# ---------------------------------------------------------------------------
def simulate_tour_exact(inst: TSPTWInstance, perm: tuple,
                        use_windows: bool = True
                        ) -> Optional[tuple[Fraction, Fraction, Fraction]]:
    """Exactly evaluate permutation perm using Fraction.
    Returns (cost, total wait, return time) or None."""
    t = Fraction(0)
    cost = Fraction(0)
    wait = Fraction(0)
    seq = [0, *perm, 0]
    for u, v in zip(seq[:-1], seq[1:]):
        arrival = t + Fraction(inst.service[u]) + Fraction(inst.travel[u][v])
        cost += Fraction(inst.travel[u][v])
        a = Fraction(inst.tw_a[v]) if (use_windows and v != 0) else Fraction(0)
        b = Fraction(inst.tw_b[v]) if use_windows else Fraction(10 ** 9)
        if arrival < a:
            wait += a - arrival
            arrival = a
        if arrival > b:
            return None
        t = arrival
    return cost, wait, t


def brute_force(inst: TSPTWInstance, use_windows: bool = True
                ) -> Optional[tuple[tuple, Fraction, Fraction, Fraction]]:
    """Exactly evaluate all n! permutations and return the best.
    Returns (permutation, cost, wait, return time)."""
    best = None
    for perm in itertools.permutations(range(1, inst.n + 1)):
        r = simulate_tour_exact(inst, perm, use_windows)
        if r is not None and (best is None or r[0] < best[1]):
            best = (perm, *r)
    return best


def verify(inst: TSPTWInstance) -> bool:
    """Cross-check cspy's solution against the exhaustive exact solution,
    and also confirm the instance's design properties."""
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))
        print(("PASS" if ok else "FAIL") + f" | {name}\n     {detail}\n")

    # Precondition guard: if INSTANCE is modified into an infeasible one,
    # fail explicitly here instead of hitting a TypeError from indexing
    # None later (in case someone experiments with modifying the instance).
    sol = solve_tsptw(inst)
    bf = brute_force(inst)
    if sol is None or bf is None:
        print("FAIL | precondition: INSTANCE has no feasible tour "
              f"(cspy={'no solution' if sol is None else sol.tour}, "
              f"brute force={'no solution' if bf is None else bf[0]}).\n"
              "     If you modified INSTANCE, relax the time windows to "
              "restore feasibility "
              "(see --infeasible for the infeasible-handling behaviour).")
        return False

    # V1: cspy == brute force (tour and cost match)
    tour_bf = ["Source", *bf[0], "Sink"]
    ok = (sol is not None and sol.tour == tour_bf
          and abs(sol.cost - float(bf[1])) < TOL)
    record("V1: cspy == exhaustive exact solution (6!=720 permutations)", ok,
           f"cspy: {sol.tour} cost={sol.cost:g} / "
           f"brute force: {tour_bf} cost={bf[1]}")

    # V2: the depot return time (consumed_resources[1]) also matches
    ok = abs(sol.consumed[1] - float(bf[3])) < TOL
    record("V2: depot return time matches", ok,
           f"cspy res[1]={sol.consumed[1]:g} / brute force={bf[3]}")

    # V3: the time windows are binding (the time-window-free optimal tour
    # differs and is infeasible under the time windows)
    bf_free = brute_force(inst, use_windows=False)
    infeas = simulate_tour_exact(inst, bf_free[0]) is None
    ok = bf_free[0] != bf[0] and float(bf_free[1]) < float(bf[1]) and infeas
    record("V3: time windows are binding", ok,
           f"TW-free: 0-{'-'.join(map(str, bf_free[0]))}-0 cost={bf_free[1]} "
           f"(infeasible under TW={infeas}) / with TW: cost={bf[1]}")

    # V4: waiting occurs in the optimal tour
    record("V4: waiting (early arrival) occurs in the optimal tour", sol.total_wait > 0,
           f"total wait={sol.total_wait} "
           f"(locations: {[(r.node, r.wait) for r in sol.schedule if r.wait > 0]})")

    # V5: service time affects the solution (setting all to s=3 changes the optimal order)
    inst_eq = TSPTWInstance(inst.n, inst.travel, inst.tw_a, inst.tw_b,
                            (0,) + (3,) * inst.n)
    sol_eq = solve_tsptw(inst_eq)
    bf_eq = brute_force(inst_eq)
    orig_perm = tuple(v for v in sol.tour if isinstance(v, int))
    orig_infeas_eq = simulate_tour_exact(inst_eq, orig_perm) is None
    ok = (sol_eq is not None and bf_eq is not None
          and sol_eq.tour == ["Source", *bf_eq[0], "Sink"]
          and abs(sol_eq.cost - float(bf_eq[1])) < TOL
          and bf_eq[0] != bf[0] and orig_infeas_eq)
    record("V5: service time affects the solution (s≡3 changes the optimal order)", ok,
           "s≡3 has no solution (was INSTANCE modified?)" if sol_eq is None else
           f"s≡3: {sol_eq.tour} cost={sol_eq.cost:g} "
           f"(the original optimal order is infeasible under s≡3={orig_infeas_eq})")

    # V6: without Hamiltonicity enforcement, a shorter path skipping customers is returned
    sol_none = solve_tsptw(inst, enforce="none")
    visited = set() if sol_none is None else \
        {v for v in sol_none.tour if isinstance(v, int)}
    ok = (sol_none is not None and len(visited) < inst.n
          and sol_none.cost < sol.cost)
    record("V6: no enforcement -> shorter path that skips customers", ok,
           "no solution even without enforcement (unexpected result)" if sol_none is None else
           f"path={sol_none.tour} cost={sol_none.cost:g} "
           f"(customers visited {len(visited)}/{inst.n})")

    # V7: the rejected approach (a), critical-resource min_res[0]=n+1,
    # yields a degenerate path (demonstrates why it was not adopted)
    sol_a = solve_tsptw(inst, enforce="min_res_critical")
    record("V7: approach (a) min_res[0]=n+1 does not work (-> approach (b) adopted)", sol_a is None,
           f"solve_tsptw(enforce='min_res_critical') -> "
           f"{'None (degenerate path)' if sol_a is None else sol_a.tour}")

    # V8: dropping the visit-flag resources makes dominance unsound and
    # the solution disappears (the key point of this teaching example).
    # A feasible Hamiltonian path exists (V1), yet a cheap label whose
    # visited set is a subset dominates and prunes away the label with the
    # superset visited set, so cspy returns the degenerate path ['Source'].
    sol_nf = solve_tsptw(inst, use_flags=False)
    record("V8: without flags (n_res=2) there is no solution (demonstrates unsound dominance)",
           sol_nf is None,
           f"solve_tsptw(use_flags=False) -> "
           f"{'None (degenerate path)' if sol_nf is None else sol_nf.tour}")

    n_ok = sum(1 for _, ok, _ in results if ok)
    print("=" * 60)
    print(f"Verification result: {n_ok}/{len(results)} PASS")
    return n_ok == len(results)


# ---------------------------------------------------------------------------
# 6. Infeasible demo (--infeasible)
# ---------------------------------------------------------------------------
def infeasible_demo() -> bool:
    """Handling of an infeasible instance where customer 2's deadline is
    tightened to b_2=6.

    Even a direct trip from the depot arrives at 8 > 6, and no route via
    another customer can make it in time either, so no feasible tour
    exists. cspy does not raise an exception but returns the degenerate
    path ['Source'], which is detected by the path[-1]=='Sink' check in
    solve_tsptw.
    """
    tw_b = list(INSTANCE.tw_b)
    tw_b[2] = 6
    inst = TSPTWInstance(INSTANCE.n, INSTANCE.travel, INSTANCE.tw_a,
                         tuple(tw_b), INSTANCE.service)
    print("Infeasible instance: customer 2's time window changed to [2, 6] "
          "(even a direct trip from the depot arrives at 8 > 6)")
    sol = solve_tsptw(inst)
    bf = brute_force(inst)   # brute force should also find zero feasible permutations
    if sol is None and bf is None:
        print("=> solve_tsptw returned None (cspy's degenerate path detected). "
              "Confirmed 0/720 feasible permutations by brute force as well.")
        return True
    print(f"=> unexpected result: cspy={sol}, brute force={bf}")
    return False


# ---------------------------------------------------------------------------
# 7. main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Teaching example: solving TSPTW with a custom cspy REF")
    ap.add_argument("--verify", action="store_true",
                    help="cross-check against an exhaustive search over all permutations")
    ap.add_argument("--infeasible", action="store_true",
                    help="demo handling of an infeasible instance")
    args = ap.parse_args()

    if args.infeasible:
        return 0 if infeasible_demo() else 1
    if args.verify:
        return 0 if verify(INSTANCE) else 1

    sol = solve_tsptw(INSTANCE)
    if sol is None:
        print("No feasible tour exists")
        return 1
    print_solution(INSTANCE, sol)
    return 0


if __name__ == "__main__":
    sys.exit(main())
