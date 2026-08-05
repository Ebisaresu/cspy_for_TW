"""Tests for the native (C++-side) node windows / time windows interface of
BiDirectional (NodeWindowREF).

Reference values for the small ESPPRC-TW instance were independently verified
against exhaustive enumeration with exact (Fraction) arithmetic in the
poc_tw/tsptw_example studies; the randomised tests below re-verify against a
brute force over all simple paths with integer arithmetic.
"""
import gc
import itertools
import random
import sys
import unittest

import networkx as nx
import numpy as np

from cspy_tw import BiDirectional, REFCallback

# Small ESPPRC-TW instance (negative weights = pricing reduced costs).
# node: (a, b, service)
TW_NODES = {
    "Source": (0, 100, 0),
    1: (0, 100, 2),
    2: (0, 12, 3),
    3: (0, 10, 1),
    4: (0, 20, 4),
    "Sink": (0, 100, 0),
}
# (tail, head, travel_time, weight)
TW_EDGES = [
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


def _build_graph(edges):
    G = nx.DiGraph(n_res=2)
    for (u, v, t, w) in edges:
        G.add_edge(u, v, res_cost=np.array([1.0, float(t)]), weight=float(w))
    return G


def _solve_native(nodes, edges, direction, elementary=True, max_edges=10,
                  min_res=None):
    G = _build_graph(edges)
    horizon = max(b for (_a, b, _s) in nodes.values())
    alg = BiDirectional(
        G,
        [float(max_edges), float(horizon)],
        min_res or [0.0, 0.0],
        direction=direction,
        elementary=elementary,
        time_windows={v: (float(a), float(b)) for v, (a, b, _s) in nodes.items()},
        service_times={v: float(s) for v, (_a, _b, s) in nodes.items()},
    )
    alg.run()
    res = alg.consumed_resources
    return alg.path, alg.total_cost, (list(res) if res else None)


def _simulate(path, nodes, emap):
    """Forward integer simulation (waiting allowed).
    Returns (feasible, cost, sink service start)."""
    a0 = nodes[path[0]][0]
    t = a0
    cost = 0
    for u, v in zip(path[:-1], path[1:]):
        if (u, v) not in emap:
            return False, None, None
        tt, w = emap[(u, v)]
        su = nodes[u][2]
        av, bv = nodes[v][0], nodes[v][1]
        arrival = t + su + tt
        start = max(av, arrival)
        if start > bv:
            return False, None, None
        t = start
        cost += w
    return True, cost, t


def _brute_force(nodes, edges, max_edges=10):
    emap = {(u, v): (t, w) for (u, v, t, w) in edges}
    G = nx.DiGraph()
    G.add_edges_from(emap.keys())
    if not nx.has_path(G, "Source", "Sink"):
        return None
    best = None
    for p in nx.all_simple_paths(G, "Source", "Sink"):
        if len(p) - 1 > max_edges:
            continue
        ok, cost, t_sink = _simulate(p, nodes, emap)
        if ok and (best is None or cost < best[1]):
            best = (p, cost, t_sink)
    return best


class TestNativeTimeWindowsESPPRC(unittest.TestCase):
    """Known-optimum checks on the exhaustively verified instance."""

    def test_forward(self):
        path, cost, res = _solve_native(TW_NODES, TW_EDGES, "forward")
        self.assertEqual(path, ["Source", 2, 3, 4, "Sink"])
        self.assertAlmostEqual(cost, -21.0)
        self.assertAlmostEqual(res[1], 18.0)  # sink service start time

    def test_both_matches_forward(self):
        path, cost, _ = _solve_native(TW_NODES, TW_EDGES, "both")
        self.assertEqual(path, ["Source", 2, 3, 4, "Sink"])
        self.assertAlmostEqual(cost, -21.0)

    def test_backward_matches_forward(self):
        path, cost, _ = _solve_native(TW_NODES, TW_EDGES, "backward")
        self.assertEqual(path, ["Source", 2, 3, 4, "Sink"])
        self.assertAlmostEqual(cost, -21.0)

    def test_waiting(self):
        # a_4 = 13 forces waiting on arrival at node 4 (arrive 12, wait to 13)
        nodes = dict(TW_NODES)
        nodes[4] = (13, 20, 4)
        path, cost, res = _solve_native(nodes, TW_EDGES, "forward")
        self.assertEqual(path, ["Source", 2, 3, 4, "Sink"])
        self.assertAlmostEqual(cost, -21.0)
        self.assertAlmostEqual(res[1], 19.0)  # waiting propagated to Sink
        # both direction agrees on path/cost
        path_b, cost_b, _ = _solve_native(nodes, TW_EDGES, "both")
        self.assertEqual(path_b, path)
        self.assertAlmostEqual(cost_b, cost)

    def test_waiting_propagation_hits_sink_deadline(self):
        # a_4 = 13 and b_Sink = 18: node 4 routes become infeasible
        nodes = dict(TW_NODES)
        nodes[4] = (13, 20, 4)
        nodes["Sink"] = (0, 18, 0)
        path, cost, res = _solve_native(nodes, TW_EDGES, "forward")
        self.assertEqual(path, ["Source", 2, 3, "Sink"])
        self.assertAlmostEqual(cost, -11.0)
        self.assertAlmostEqual(res[1], 13.0)

    def test_relaxed_windows_match_unconstrained(self):
        nodes = {k: (0, 100, s) for k, (a, b, s) in TW_NODES.items()}
        path, cost, res = _solve_native(nodes, TW_EDGES, "forward")
        self.assertEqual(path, ["Source", 1, 2, 3, 4, "Sink"])
        self.assertAlmostEqual(cost, -28.0)
        self.assertAlmostEqual(res[1], 22.0)

    def test_source_release_time(self):
        # a_Source > 0: initial label resource is 0, the native REF clamps to
        # lb[Source] on departure. Verify against brute force, fwd and both.
        nodes = dict(TW_NODES)
        nodes["Source"] = (5, 100, 0)
        bf = _brute_force(nodes, TW_EDGES)
        for direction in ("forward", "both"):
            path, cost, res = _solve_native(nodes, TW_EDGES, direction)
            self.assertEqual(path, bf[0])
            self.assertAlmostEqual(cost, float(bf[1]))
            if direction == "forward":
                self.assertAlmostEqual(res[1], float(bf[2]))

    def test_both_with_positive_min_res_no_segfault(self):
        # Upstream bug: direction='both' + positive time min_res used to
        # segfault (null best_labels dereference in joinLabels).
        path, cost, _ = _solve_native(TW_NODES, TW_EDGES, "both",
                                      min_res=[0.0, 5.0])
        self.assertEqual(path, ["Source", 2, 3, 4, "Sink"])
        self.assertAlmostEqual(cost, -21.0)


class TestNativeRandomised(unittest.TestCase):
    """Randomised integer instances vs brute force over all simple paths."""

    N_INSTANCES = 40

    def _random_instance(self, rng, with_source_release=False):
        customers = [1, 2, 3, 4]
        horizon = 60
        nodes = {"Source": (rng.randint(1, 5) if with_source_release else 0,
                            horizon, 0),
                 "Sink": (0, horizon, 0)}
        for i in customers:
            a = rng.randint(0, 25)
            b = a + rng.randint(3, 25)
            nodes[i] = (a, b, rng.randint(0, 3))
        edges = []
        for i in customers:
            edges.append(("Source", i, rng.randint(1, 9), rng.randint(-9, 3)))
            edges.append((i, "Sink", rng.randint(1, 9), rng.randint(-9, 3)))
        for i in customers:
            for j in customers:
                if i != j and rng.random() < 0.7:
                    edges.append((i, j, rng.randint(1, 9), rng.randint(-9, 3)))
        return nodes, edges

    def test_forward_and_both_vs_brute_force(self):
        rng = random.Random(20260731)
        n_checked = 0
        for k in range(self.N_INSTANCES):
            nodes, edges = self._random_instance(
                rng, with_source_release=(k % 2 == 0))
            bf = _brute_force(nodes, edges)
            path_f, cost_f, res_f = _solve_native(nodes, edges, "forward")
            if bf is None:
                self.assertTrue(path_f is None or path_f[-1] != "Sink",
                                "instance %d: expected infeasible" % k)
                continue
            self.assertIsNotNone(path_f, "instance %d" % k)
            self.assertAlmostEqual(cost_f, float(bf[1]),
                                   msg="instance %d fwd cost" % k)
            # returned path must itself be feasible with the same cost
            emap = {(u, v): (t, w) for (u, v, t, w) in edges}
            ok, cost_sim, t_sim = _simulate(path_f, nodes, emap)
            self.assertTrue(ok, "instance %d: infeasible path" % k)
            self.assertAlmostEqual(cost_sim, cost_f)
            self.assertAlmostEqual(res_f[1], float(t_sim),
                                   msg="instance %d sink time" % k)
            path_b, cost_b, _ = _solve_native(nodes, edges, "both")
            self.assertAlmostEqual(cost_b, float(bf[1]),
                                   msg="instance %d both cost" % k)
            ok_b, cost_sim_b, _ = _simulate(path_b, nodes, emap)
            self.assertTrue(ok_b, "instance %d: infeasible both path" % k)
            self.assertAlmostEqual(cost_sim_b, cost_b)
            n_checked += 1
        # Make sure the loop actually exercised feasible instances
        self.assertGreater(n_checked, self.N_INSTANCES // 2)


class TestNativeTSPTW(unittest.TestCase):
    """TSPTW via the general native interface: WINDOW_WAIT time resource +
    visit-flag resources (additive, consumption -1, sound dominance) +
    a visit-counter resource (additive, consumption +1, min_res = n enforced
    at the final non-soft feasibility check)."""

    def test_tsptw_instance(self):
        n = 6
        travel = (
            (0, 11, 8, 5, 8, 5, 7),
            (9, 0, 7, 12, 3, 11, 7),
            (8, 12, 0, 4, 8, 3, 11),
            (3, 4, 10, 0, 8, 3, 8),
            (10, 3, 3, 6, 0, 8, 4),
            (5, 8, 5, 12, 4, 0, 10),
            (8, 4, 7, 5, 12, 4, 0),
        )
        tw_a = (0, 39, 2, 38, 32, 2, 42)
        tw_b = (200, 59, 18, 60, 57, 13, 60)
        service = (0, 6, 2, 4, 5, 3, 1)
        horizon = tw_b[0]
        n_res = 2 + n + 1  # edges, time, n visit flags, visit counter
        G = nx.DiGraph(n_res=n_res)

        def rc(t):
            return np.array([1.0, float(t)] + [0.0] * (n_res - 2))

        for i in range(1, n + 1):
            G.add_edge("Source", i, res_cost=rc(travel[0][i]),
                       weight=float(travel[0][i]))
            G.add_edge(i, "Sink", res_cost=rc(travel[i][0]),
                       weight=float(travel[i][0]))
            for j in range(1, n + 1):
                if i != j:
                    G.add_edge(i, j, res_cost=rc(travel[i][j]),
                               weight=float(travel[i][j]))

        max_res = [float(n + 1), float(horizon)] + [0.0] * n + [float(n)]
        min_res = [0.0, 0.0] + [-1.0] * n + [float(n)]
        node_consumption = {2 + n: {i: 1.0 for i in range(1, n + 1)}}
        for i in range(1, n + 1):
            node_consumption[2 + i - 1] = {i: -1.0}

        alg = BiDirectional(
            G, max_res, min_res, direction="forward", elementary=True,
            time_windows={i: (float(tw_a[i]), float(tw_b[i]))
                          for i in range(1, n + 1)},
            service_times={i: float(service[i]) for i in range(1, n + 1)},
            node_consumption=node_consumption,
        )
        alg.run()
        # Known optimum (verified against all 6! = 720 permutations with
        # exact arithmetic in tsptw_example)
        self.assertEqual(alg.path, ["Source", 2, 5, 4, 1, 6, 3, "Sink"])
        self.assertAlmostEqual(alg.total_cost, 33.0)
        consumed = alg.consumed_resources
        self.assertAlmostEqual(consumed[1], 66.0)  # depot return (start) time
        for i in range(1, n + 1):  # all visit flags consumed
            self.assertAlmostEqual(consumed[2 + i - 1], -1.0)
        self.assertAlmostEqual(consumed[2 + n], float(n))


#: Six customer Traveling Salesman Problem with Time Windows (TSPTW)
#: instance. Index 0 is the depot; the optimum was verified against all
#: 6! = 720 permutations with exact arithmetic in tsptw_example.
TSPTW_TRAVEL = (
    (0, 11, 8, 5, 8, 5, 7),
    (9, 0, 7, 12, 3, 11, 7),
    (8, 12, 0, 4, 8, 3, 11),
    (3, 4, 10, 0, 8, 3, 8),
    (10, 3, 3, 6, 0, 8, 4),
    (5, 8, 5, 12, 4, 0, 10),
    (8, 4, 7, 5, 12, 4, 0),
)
TSPTW_TW_A = (0, 39, 2, 38, 32, 2, 42)
TSPTW_TW_B = (200, 59, 18, 60, 57, 13, 60)
TSPTW_SERVICE = (0, 6, 2, 4, 5, 3, 1)
TSPTW_N = 6


def _build_tsptw_graph(n, travel, n_res=2):
    """Complete graph over a depot split into Source/Sink plus n customers."""
    G = nx.DiGraph(n_res=n_res)

    def res_cost(t):
        return np.array([1.0, float(t)] + [0.0] * (n_res - 2))

    for i in range(1, n + 1):
        G.add_edge("Source", i, res_cost=res_cost(travel[0][i]),
                   weight=float(travel[0][i]))
        G.add_edge(i, "Sink", res_cost=res_cost(travel[i][0]),
                   weight=float(travel[i][0]))
        for j in range(1, n + 1):
            if i != j:
                G.add_edge(i, j, res_cost=res_cost(travel[i][j]),
                           weight=float(travel[i][j]))
    return G


def _solve_required_visits(n, travel, tw_a, tw_b, service,
                           required_nodes=None, max_edges=None, **kwargs):
    """Solve a TSPTW instance with the mandatory visit interface, using only
    the two resources (edge counter + time)."""
    G = _build_tsptw_graph(n, travel)
    alg = BiDirectional(
        G,
        [float(max_edges if max_edges is not None else n + 1),
         float(tw_b[0])],
        [0.0, 0.0],
        direction="forward",
        elementary=True,
        time_windows={i: (float(tw_a[i]), float(tw_b[i]))
                      for i in range(1, n + 1)},
        service_times={i: float(service[i]) for i in range(1, n + 1)},
        require_all_visits=True,
        required_nodes=required_nodes,
        **kwargs
    )
    alg.run()
    res = alg.consumed_resources
    return alg.path, alg.total_cost, (list(res) if res else None)


def _simulate_tour(n, travel, tw_a, tw_b, service, order):
    """Forward integer simulation of depot -> order -> depot.
    Returns (cost, depot return time) or None when time infeasible."""
    t = 0
    cost = 0
    sequence = [0, *order, 0]
    for u, v in zip(sequence[:-1], sequence[1:]):
        arrival = t + service[u] + travel[u][v]
        lower, upper = (0, tw_b[0]) if v == 0 else (tw_a[v], tw_b[v])
        start = max(lower, arrival)
        if start > upper:
            return None
        cost += travel[u][v]
        t = start
    return cost, t


def _brute_force_tours(n, travel, tw_a, tw_b, service, required):
    """Exhaustive optimum over every elementary tour visiting at least the
    nodes in `required`. Returns (order, cost, return time) or None."""
    best = None
    customers = list(range(1, n + 1))
    for size in range(len(required), n + 1):
        for subset in itertools.combinations(customers, size):
            if not required.issubset(subset):
                continue
            for order in itertools.permutations(subset):
                outcome = _simulate_tour(n, travel, tw_a, tw_b, service, order)
                if outcome is not None and (best is None
                                            or outcome[0] < best[1]):
                    best = (order, outcome[0], outcome[1])
    return best


class TestRequiredVisitsTSPTW(unittest.TestCase):
    """Mandatory visits (require_all_visits): the Traveling Salesman Problem
    with Time Windows solved without one visit indicator resource per
    customer."""

    def test_known_optimum_with_two_resources(self):
        path, cost, res = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE)
        self.assertEqual(path, ["Source", 2, 5, 4, 1, 6, 3, "Sink"])
        self.assertAlmostEqual(cost, 33.0)
        self.assertAlmostEqual(res[0], float(TSPTW_N + 1))  # edges used
        self.assertAlmostEqual(res[1], 66.0)  # depot return (start) time
        self.assertEqual(len(res), 2)  # no visit indicator resources

    def test_matches_visit_indicator_encoding(self):
        """Same answer as the visit indicator resource encoding, which is the
        reference implementation of the same pruning rule."""
        n = TSPTW_N
        n_res = 2 + n + 1
        G = _build_tsptw_graph(n, TSPTW_TRAVEL, n_res=n_res)
        max_res = [float(n + 1), float(TSPTW_TW_B[0])] + [0.0] * n + [float(n)]
        min_res = [0.0, 0.0] + [-1.0] * n + [float(n)]
        node_consumption = {2 + n: {i: 1.0 for i in range(1, n + 1)}}
        for i in range(1, n + 1):
            node_consumption[2 + i - 1] = {i: -1.0}
        reference = BiDirectional(
            G, max_res, min_res, direction="forward", elementary=True,
            time_windows={i: (float(TSPTW_TW_A[i]), float(TSPTW_TW_B[i]))
                          for i in range(1, n + 1)},
            service_times={i: float(TSPTW_SERVICE[i]) for i in range(1, n + 1)},
            node_consumption=node_consumption,
        )
        reference.run()
        path, cost, res = _solve_required_visits(
            n, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE)
        self.assertEqual(path, reference.path)
        self.assertAlmostEqual(cost, reference.total_cost)
        self.assertAlmostEqual(res[1], reference.consumed_resources[1])

    def test_without_the_feature_dominance_prunes_every_tour(self):
        """Control experiment: with the same two resources but without
        require_all_visits, a label whose visited set is a proper subset
        dominates the labels that could still cover every customer, and the
        engine returns the degenerate path even though a tour exists."""
        n = TSPTW_N
        G = _build_tsptw_graph(n, TSPTW_TRAVEL)
        alg = BiDirectional(
            G, [float(n + 1), float(TSPTW_TW_B[0])], [0.0, 0.0],
            direction="forward", elementary=True,
            time_windows={i: (float(TSPTW_TW_A[i]), float(TSPTW_TW_B[i]))
                          for i in range(1, n + 1)},
            service_times={i: float(TSPTW_SERVICE[i]) for i in range(1, n + 1)},
        )
        alg.run()
        self.assertNotEqual(alg.path, ["Source", 2, 5, 4, 1, 6, 3, "Sink"])

    def test_matches_exhaustive_enumeration(self):
        best = _brute_force_tours(TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A,
                                  TSPTW_TW_B, TSPTW_SERVICE,
                                  set(range(1, TSPTW_N + 1)))
        path, cost, res = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE)
        self.assertEqual(path, ["Source", *best[0], "Sink"])
        self.assertAlmostEqual(cost, float(best[1]))
        self.assertAlmostEqual(res[1], float(best[2]))

    def test_subset_of_required_nodes(self):
        """With a proper subset of required nodes, the remaining customers
        may be visited or skipped, whichever is cheaper."""
        required = {2, 5}
        best = _brute_force_tours(TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A,
                                  TSPTW_TW_B, TSPTW_SERVICE, required)
        path, cost, _ = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
            required_nodes=sorted(required))
        visited = {v for v in path if isinstance(v, int)}
        self.assertTrue(required.issubset(visited))
        self.assertLess(len(visited), TSPTW_N)  # skipping is allowed here
        self.assertAlmostEqual(cost, float(best[1]))

    def test_required_nodes_order_and_duplicates_are_irrelevant(self):
        reference = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
            required_nodes=[1, 2, 3, 4, 5, 6])
        shuffled = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
            required_nodes=[4, 1, 6, 6, 2, 5, 3, 4])
        self.assertEqual(reference[0], shuffled[0])
        self.assertAlmostEqual(reference[1], shuffled[1])

    def test_default_required_nodes_are_all_but_source_and_sink(self):
        explicit = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
            required_nodes=list(range(1, TSPTW_N + 1)))
        implicit = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE)
        self.assertEqual(explicit[0], implicit[0])
        self.assertAlmostEqual(explicit[1], implicit[1])

    def test_infeasible_instance_returns_degenerate_path(self):
        # Tightening the deadline of customer 2 to 6 makes every tour
        # infeasible (a direct trip from the depot already arrives at 8).
        tw_b = list(TSPTW_TW_B)
        tw_b[2] = 6
        self.assertIsNone(
            _brute_force_tours(TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, tuple(tw_b),
                               TSPTW_SERVICE, set(range(1, TSPTW_N + 1))))
        path, _cost, _res = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, tuple(tw_b), TSPTW_SERVICE)
        self.assertEqual(path, ["Source"])

    def test_no_tour_when_the_edge_budget_forbids_full_coverage(self):
        # Only n edges are allowed, one short of the n + 1 a full tour needs.
        path, _cost, _res = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
            max_edges=TSPTW_N)
        self.assertEqual(path, ["Source"])

    def test_combined_with_threshold(self):
        path, cost, _res = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
            threshold=40.0)
        self.assertEqual(path[0], "Source")
        self.assertEqual(path[-1], "Sink")
        self.assertEqual({v for v in path if isinstance(v, int)},
                         set(range(1, TSPTW_N + 1)))
        self.assertLessEqual(cost, 40.0)

    def test_single_pass_iterables_give_the_same_answer(self):
        """`required_nodes` is materialised exactly once. An iterable that can
        only be traversed once (generator, map, filter, iter(...)) used to be
        drained by the validation and then read again as an empty set, which
        silently disabled the whole requirement."""
        customers = list(range(1, TSPTW_N + 1))
        reference = _solve_required_visits(
            TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
            required_nodes=customers)
        self.assertEqual(reference[0][0], "Source")
        self.assertEqual(reference[0][-1], "Sink")
        for make in (
                lambda: (v for v in customers),
                lambda: iter(customers),
                lambda: map(int, customers),
                lambda: filter(lambda v: v > 0, customers),
                lambda: (a for a, _b in zip(customers, customers)),
        ):
            outcome = _solve_required_visits(
                TSPTW_N, TSPTW_TRAVEL, TSPTW_TW_A, TSPTW_TW_B, TSPTW_SERVICE,
                required_nodes=make())
            self.assertEqual(outcome[0], reference[0])
            self.assertAlmostEqual(outcome[1], reference[1])


class TestRequiredVisitsRandomised(unittest.TestCase):
    """Randomised mandatory-visit instances against exhaustive enumeration."""

    N_INSTANCES = 30

    @staticmethod
    def _random_instance(rng, n):
        travel = tuple(
            tuple(0 if i == j else rng.randint(1, 12) for j in range(n + 1))
            for i in range(n + 1)
        )
        tw_a, tw_b = [0], [500]
        for _ in range(n):
            lower = rng.randint(0, 30)
            tw_a.append(lower)
            tw_b.append(lower + rng.randint(3, 40))
        service = (0,) + tuple(rng.randint(0, 5) for _ in range(n))
        return travel, tuple(tw_a), tuple(tw_b), service

    def test_full_coverage_vs_exhaustive_enumeration(self):
        rng = random.Random(20260804)
        n_feasible = 0
        for k in range(self.N_INSTANCES):
            n = rng.choice([3, 4, 5])
            travel, tw_a, tw_b, service = self._random_instance(rng, n)
            required = set(range(1, n + 1))
            best = _brute_force_tours(n, travel, tw_a, tw_b, service, required)
            path, cost, _res = _solve_required_visits(
                n, travel, tw_a, tw_b, service)
            if best is None:
                self.assertEqual(path, ["Source"], "instance %d" % k)
                continue
            n_feasible += 1
            self.assertEqual(path[-1], "Sink", "instance %d" % k)
            visited = tuple(v for v in path if isinstance(v, int))
            self.assertEqual(set(visited), required, "instance %d" % k)
            self.assertAlmostEqual(cost, float(best[1]),
                                   msg="instance %d cost" % k)
            self.assertIsNotNone(
                _simulate_tour(n, travel, tw_a, tw_b, service, visited),
                "instance %d: returned tour violates a window" % k)
        self.assertGreater(n_feasible, self.N_INSTANCES // 2)

    def test_subset_coverage_vs_exhaustive_enumeration(self):
        rng = random.Random(20260805)
        n_feasible = 0
        for k in range(self.N_INSTANCES):
            n = rng.choice([3, 4, 5])
            travel, tw_a, tw_b, service = self._random_instance(rng, n)
            required = set(rng.sample(range(1, n + 1), max(1, n - 1)))
            best = _brute_force_tours(n, travel, tw_a, tw_b, service, required)
            path, cost, _res = _solve_required_visits(
                n, travel, tw_a, tw_b, service,
                required_nodes=sorted(required))
            if best is None:
                self.assertEqual(path, ["Source"], "instance %d" % k)
                continue
            n_feasible += 1
            visited = tuple(v for v in path if isinstance(v, int))
            self.assertTrue(required.issubset(visited), "instance %d" % k)
            self.assertAlmostEqual(cost, float(best[1]),
                                   msg="instance %d cost" % k)
        self.assertGreater(n_feasible, self.N_INSTANCES // 2)


class TestRequiredVisitsChecks(unittest.TestCase):
    """Input validation for require_all_visits / required_nodes."""

    def _make(self, **kwargs):
        G = _build_graph(TW_EDGES)
        return BiDirectional(G, [10.0, 100.0], [0.0, 0.0], **kwargs)

    def test_direction_both_rejected_with_actionable_message(self):
        with self.assertRaises(Exception) as caught:
            self._make(elementary=True, require_all_visits=True)
        self.assertIn("direction='forward'", str(caught.exception))

    def test_direction_backward_rejected(self):
        with self.assertRaises(Exception):
            self._make(direction="backward", elementary=True,
                       require_all_visits=True)

    def test_non_elementary_rejected(self):
        with self.assertRaises(Exception) as caught:
            self._make(direction="forward", require_all_visits=True)
        self.assertIn("elementary=True", str(caught.exception))

    def test_required_nodes_without_require_all_visits_rejected(self):
        with self.assertRaises(Exception):
            self._make(direction="forward", elementary=True,
                       required_nodes=[1, 2])

    def test_unknown_required_node_rejected(self):
        with self.assertRaises(Exception):
            self._make(direction="forward", elementary=True,
                       require_all_visits=True, required_nodes=[1, 99])

    def test_source_or_sink_as_required_node_rejected(self):
        with self.assertRaises(Exception):
            self._make(direction="forward", elementary=True,
                       require_all_visits=True, required_nodes=["Source"])
        with self.assertRaises(Exception):
            self._make(direction="forward", elementary=True,
                       require_all_visits=True, required_nodes=["Sink"])

    def test_string_required_nodes_rejected(self):
        with self.assertRaises(Exception):
            self._make(direction="forward", elementary=True,
                       require_all_visits=True, required_nodes="123")

    def test_non_boolean_require_all_visits_rejected(self):
        with self.assertRaises(Exception):
            self._make(direction="forward", elementary=True,
                       require_all_visits=1)

    def test_empty_required_nodes_rejected(self):
        """An empty required set would silently reduce the problem to a plain
        elementary shortest path problem, so it is rejected instead."""
        for empty in ([], set(), tuple(), (name for name in []), iter([])):
            with self.assertRaises(Exception) as caught:
                self._make(direction="forward", elementary=True,
                           require_all_visits=True, required_nodes=empty)
            self.assertIn("empty", str(caught.exception))

    def test_graph_without_customers_rejected(self):
        """The default required set (every node other than Source and Sink)
        being empty is user error as well."""
        G = nx.DiGraph(n_res=2)
        G.add_edge("Source", "Sink", res_cost=np.array([1.0, 1.0]),
                   weight=1.0)
        with self.assertRaises(Exception) as caught:
            BiDirectional(G, [10.0, 100.0], [0.0, 0.0], direction="forward",
                          elementary=True, require_all_visits=True)
        self.assertIn("vacuous", str(caught.exception))

    def test_default_is_unchanged_when_feature_is_off(self):
        alg = self._make(direction="forward", elementary=True)
        alg.run()
        reference = self._make(direction="forward", elementary=True,
                               require_all_visits=False)
        reference.run()
        self.assertEqual(alg.path, reference.path)
        self.assertAlmostEqual(alg.total_cost, reference.total_cost)

    @staticmethod
    def _native_engine(add_nodes=True):
        """A bare C++ engine on a four vertex graph 0 -> {1, 2} -> 3."""
        from cspy_tw.algorithms.pyBiDirectionalCpp import (
            BiDirectionalCpp,
            DoubleVector,
        )

        def double_vector(values):
            vector = DoubleVector()
            for value in values:
                vector.append(float(value))
            return vector

        engine = BiDirectionalCpp(
            4, 6, 0, 3, double_vector([10.0, 100.0]), double_vector([0.0, 0.0])
        )
        if add_nodes:
            engine.addNodes([0, 1, 2, 3])
            for tail, head in ((0, 1), (0, 2), (1, 2), (2, 1), (1, 3), (2, 3)):
                engine.addEdge(tail, head, 1.0, double_vector([1.0, 1.0]))
        return engine

    def test_native_engine_rejects_direction_both(self):
        # The C++ engine must refuse the same combinations, so that callers
        # bypassing the Python layer cannot silently get unsound answers.
        # The default direction of the engine is 'both'.
        engine = self._native_engine()
        engine.setRequiredNodes([1, 2])
        engine.setElementary(True)
        with self.assertRaises(RuntimeError):
            engine.run()

    def test_native_engine_rejects_non_elementary(self):
        engine = self._native_engine()
        engine.setDirection("forward")
        engine.setRequiredNodes([1, 2])
        with self.assertRaises(RuntimeError):
            engine.run()

    def test_native_engine_rejects_source_or_sink_as_required(self):
        engine = self._native_engine()
        with self.assertRaises(RuntimeError):
            engine.setRequiredNodes([0])
        with self.assertRaises(RuntimeError):
            engine.setRequiredNodes([3])

    def test_native_engine_rejects_required_nodes_before_add_nodes(self):
        engine = self._native_engine(add_nodes=False)
        with self.assertRaises(RuntimeError):
            engine.setRequiredNodes([1])

    def test_native_engine_forward_run_covers_required_nodes(self):
        engine = self._native_engine()
        engine.setDirection("forward")
        engine.setElementary(True)
        engine.setRequiredNodes([1, 2])
        engine.run()
        # Both coverings (0-1-2-3 and 0-2-1-3) cost the same here.
        path = list(engine.getPath())
        self.assertEqual(path[0], 0)
        self.assertEqual(path[-1], 3)
        self.assertEqual(set(path), {0, 1, 2, 3})

    def test_native_engine_rejects_empty_required_nodes(self):
        engine = self._native_engine()
        with self.assertRaises(RuntimeError):
            engine.setRequiredNodes([])

    def test_native_engine_sparse_user_ids_are_cheap(self):
        """The bit index table must be sized by the number of required nodes
        and not by the largest user id, otherwise sparse ids allocate
        gigabytes."""
        from cspy_tw.algorithms.pyBiDirectionalCpp import (
            BiDirectionalCpp,
            DoubleVector,
        )

        def double_vector(values):
            vector = DoubleVector()
            for value in values:
                vector.append(float(value))
            return vector

        ids = [0, 1, 10 ** 9]  # source, one customer, sink
        engine = BiDirectionalCpp(
            3, 2, ids[0], ids[-1],
            double_vector([10.0, 100.0]), double_vector([0.0, 0.0]))
        engine.addNodes(ids)
        engine.addEdge(ids[0], ids[1], 1.0, double_vector([1.0, 1.0]))
        engine.addEdge(ids[1], ids[-1], 1.0, double_vector([1.0, 1.0]))
        engine.setRequiredNodes([ids[1]])
        engine.setDirection("forward")
        engine.setElementary(True)
        engine.run()
        self.assertEqual(list(engine.getPath()), ids)


class TestRequiredVisitsBitSet(unittest.TestCase):
    """The required-visit bit set must behave the same inline (at most 64
    required nodes, one word) and on the heap (more than 64 required nodes,
    several words)."""

    @staticmethod
    def _solve_chain(n_customers):
        """A path graph Source -> 1 -> 2 -> ... -> n -> Sink, in which the
        only Source-Sink path covering every customer is the full chain, plus
        a shortcut Source -> Sink that the requirement must reject."""
        G = nx.DiGraph(n_res=2)
        sequence = ["Source", *range(1, n_customers + 1), "Sink"]
        for tail, head in zip(sequence[:-1], sequence[1:]):
            G.add_edge(tail, head, res_cost=np.array([1.0, 1.0]), weight=1.0)
        G.add_edge("Source", "Sink", res_cost=np.array([1.0, 1.0]),
                   weight=0.5)
        alg = BiDirectional(
            G, [float(n_customers + 2), float(n_customers + 2)], [0.0, 0.0],
            direction="forward", elementary=True, require_all_visits=True)
        alg.run()
        return alg.path, alg.total_cost, sequence

    def test_inline_word_up_to_64_required_nodes(self):
        for n in (1, 63, 64):
            path, cost, sequence = self._solve_chain(n)
            self.assertEqual(path, sequence, "n = %d" % n)
            self.assertAlmostEqual(cost, float(n + 1), msg="n = %d" % n)

    def test_heap_words_beyond_64_required_nodes(self):
        for n in (65, 128, 129, 200):
            path, cost, sequence = self._solve_chain(n)
            self.assertEqual(path, sequence, "n = %d" % n)
            self.assertAlmostEqual(cost, float(n + 1), msg="n = %d" % n)


class TestNativeNoPythonCallback(unittest.TestCase):
    """The native REF must not cross the Python boundary during run()."""

    def test_zero_python_calls_in_labelling_loop(self):
        G = _build_graph(TW_EDGES)
        alg = BiDirectional(
            G, [10.0, 100.0], [0.0, 0.0], direction="forward",
            elementary=True,
            time_windows={v: (float(a), float(b))
                          for v, (a, b, _s) in TW_NODES.items()},
            service_times={v: float(s)
                           for v, (_a, _b, s) in TW_NODES.items()},
        )
        events = []

        def prof(frame, event, arg):
            if event == "call":
                events.append(
                    (frame.f_code.co_filename, frame.f_code.co_name))

        cpp_run = alg.bidirectional_cpp.run  # bind before profiling
        sys.setprofile(prof)
        try:
            cpp_run()
        finally:
            sys.setprofile(None)
        # The only allowed Python-level call is the SWIG proxy entry (run in
        # pyBiDirectionalCpp.py); anything else came from inside the C++ loop
        # (e.g. a director round-trip).
        crossings = [e for e in events
                     if not (e[0].endswith("pyBiDirectionalCpp.py")
                             and e[1] == "run")]
        self.assertEqual(crossings, [])
        self.assertEqual(alg.path, ["Source", 2, 3, 4, "Sink"])


class TestNativeChecks(unittest.TestCase):
    """Input validation of the native window arguments."""

    def _kwargs(self, **overrides):
        kwargs = dict(
            time_windows={v: (float(a), float(b))
                          for v, (a, b, _s) in TW_NODES.items()},
            service_times={v: float(s)
                           for v, (_a, _b, s) in TW_NODES.items()},
        )
        kwargs.update(overrides)
        return kwargs

    def _make(self, **kwargs):
        G = _build_graph(TW_EDGES)
        return BiDirectional(G, [10.0, 100.0], [0.0, 0.0], **kwargs)

    def test_ref_callback_conflict(self):
        with self.assertRaises(Exception):
            self._make(REF_callback=REFCallback(), **self._kwargs())

    def test_find_critical_res_conflict(self):
        with self.assertRaises(Exception):
            self._make(find_critical_res=True, **self._kwargs())

    def test_time_res_equals_critical(self):
        with self.assertRaises(Exception):
            self._make(**self._kwargs(time_res=0))

    def test_window_hard_requires_forward(self):
        with self.assertRaises(Exception):
            self._make(direction="both",
                       node_windows={1: {2: (0.0, 12.0)}},
                       window_policy={1: "window_hard"})
        # forward is accepted
        alg = self._make(direction="forward",
                         node_windows={1: {2: (0.0, 12.0)}},
                         window_policy={1: "window_hard"})
        self.assertIsNotNone(alg)

    def test_invalid_policy(self):
        with self.assertRaises(Exception):
            self._make(window_policy={1: "bogus"},
                       node_windows={1: {2: (0.0, 12.0)}})

    def test_double_configuration_of_time_res(self):
        with self.assertRaises(Exception):
            self._make(**self._kwargs(node_windows={1: {2: (0.0, 12.0)}}))

    def test_lb_greater_than_ub(self):
        with self.assertRaises(Exception):
            self._make(time_windows={2: (13.0, 12.0)})

    def test_negative_service_time(self):
        with self.assertRaises(Exception):
            self._make(time_windows={2: (0.0, 12.0)},
                       service_times={2: -1.0})

    def test_service_times_without_time_windows(self):
        with self.assertRaises(Exception):
            self._make(service_times={2: 1.0})

    def test_unknown_node(self):
        with self.assertRaises(Exception):
            self._make(time_windows={"NoSuchNode": (0.0, 12.0)})

    def test_critical_resource_general_interface_guard(self):
        with self.assertRaises(Exception):
            self._make(node_windows={0: {2: (0.0, 12.0)}},
                       window_policy={0: "window_wait"})
        with self.assertRaises(Exception):
            self._make(node_consumption={0: {2: 1.0}})

    def test_infinite_max_res_rejected_simple(self):
        # Sentinel collision: with max_res[time_res] = inf window-violating
        # paths would pass the engine check (inf <= inf). Must be rejected.
        G = _build_graph(TW_EDGES)
        with self.assertRaises(Exception):
            BiDirectional(G, [10.0, float("inf")], [0.0, 0.0],
                          **self._kwargs())

    def test_infinite_max_res_rejected_general(self):
        G = _build_graph(TW_EDGES)
        with self.assertRaises(Exception):
            BiDirectional(G, [10.0, float("inf")], [0.0, 0.0],
                          direction="forward",
                          node_windows={1: {2: (0.0, 5.0)}},
                          window_policy={1: "window_wait"})

    def test_infinite_max_res_rejected_native_cpp(self):
        # The C++ guard itself (bypassing the Python-side check)
        from cspy_tw.algorithms.bidirectional import (
            NodeWindowREF, POLICY_WINDOW_WAIT, _list_to_double_vector)
        ref = NodeWindowREF(
            3, _list_to_double_vector([10.0, float("inf")]), 0, 2, 0, 1e-9)
        v = _list_to_double_vector
        with self.assertRaises(RuntimeError):
            ref.setResourcePolicy(1, POLICY_WINDOW_WAIT,
                                  v([0.0] * 3), v([5.0] * 3), v([0.0] * 3))

    def test_windows_with_additive_policy_rejected(self):
        # Forgetting window_policy (default 'additive') used to silently
        # ignore the windows entirely; now it is an error.
        with self.assertRaises(Exception):
            self._make(node_windows={1: {2: (0.0, 12.0)}})

    def test_non_mapping_containers_rejected(self):
        # Clear errors instead of raw AttributeError
        with self.assertRaises(Exception):
            self._make(node_windows={1: [(2, (0.0, 5.0))]},
                       window_policy={1: "window_wait"})
        with self.assertRaises(Exception):
            self._make(node_windows="not a dict")
        with self.assertRaises(Exception):
            self._make(node_consumption={1: [1.0, 2.0]})

    def test_non_numeric_values_rejected(self):
        with self.assertRaises(Exception):
            self._make(time_windows={2: (0.0, "twelve")})
        with self.assertRaises(Exception):
            self._make(time_windows={2: (0.0, 12.0)},
                       service_times={2: "three"})
        with self.assertRaises(Exception):
            self._make(node_consumption={1: {2: "x"}})

    def test_direct_ref_call_argument_guards(self):
        # NodeWindowREF methods are exposed to Python for testing; direct
        # calls with bad node ids / short vectors must raise (RuntimeError
        # via the SWIG %exception handler), not crash the interpreter.
        alg = self._make(direction="forward", **self._kwargs())
        ref = alg._window_ref
        with self.assertRaises(RuntimeError):
            ref.REF_fwd([0.0, 0.0], 0, 999999, [1.0, 1.0], [0], 0.0)
        with self.assertRaises(RuntimeError):
            ref.REF_fwd([0.0, 0.0], -1, 1, [1.0, 1.0], [0], 0.0)
        with self.assertRaises(RuntimeError):
            ref.REF_fwd([0.0], 0, 1, [1.0, 1.0], [0], 0.0)  # short cum. res
        with self.assertRaises(RuntimeError):
            ref.REF_bwd([0.0, 0.0], 0, 999999, [1.0, 1.0], [0], 0.0)
        with self.assertRaises(RuntimeError):
            ref.REF_join([0.0, 0.0], [0.0], 0, 1, [1.0, 1.0])  # short bwd
        # valid call still works
        out = ref.REF_fwd([0.0, 0.0], alg._source_id, alg._sink_id,
                          [1.0, 1.0], [0], 0.0)
        self.assertEqual(len(out), 2)

    def test_cpp_proxy_outlives_wrapper(self):
        # Extracting the C++ proxy and dropping the wrapper must not leave
        # a dangling native REF pointer (keepalive on the proxy itself).
        alg = self._make(direction="forward", elementary=True,
                         **self._kwargs())
        cpp = alg.bidirectional_cpp
        del alg
        gc.collect()
        cpp.run()
        self.assertGreater(len(cpp.getPath()), 1)

    def test_ref_callback_still_works(self):
        # Backward compatibility: plain Python director REF unaffected
        class _CB(REFCallback):
            def REF_fwd(self, cumul_res, tail, head, edge_res, partial_path,
                        cumul_cost):
                new = list(cumul_res)
                new[0] += edge_res[0]
                new[1] += edge_res[1]
                return new

        cb = _CB()
        alg = self._make(direction="forward", REF_callback=cb)
        alg.run()
        self.assertEqual(alg.path[-1], "Sink")
        del cb

    def test_temporary_ref_callback_is_kept_alive(self):
        """The C++ side holds a raw pointer to the callback, so BiDirectional
        keeps a reference of its own. Passing a temporary used to leave a
        dangling pointer and crash the interpreter during run()."""
        class _CB(REFCallback):
            def REF_fwd(self, cumul_res, tail, head, edge_res, partial_path,
                        cumul_cost):
                new = list(cumul_res)
                new[0] += edge_res[0]
                new[1] += edge_res[1]
                return new

        alg = self._make(direction="forward", REF_callback=_CB())
        gc.collect()
        alg.run()
        self.assertEqual(alg.path[-1], "Sink")


if __name__ == "__main__":
    unittest.main()
