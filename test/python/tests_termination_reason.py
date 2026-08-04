"""Tests for the termination reason interface and the strict threshold
comparison of BiDirectional (``termination_reason`` / ``threshold_strict``).

The six customer TSPTW instance and its optimum (33) are the ones verified
against all 6! = 720 permutations with exact arithmetic in tsptw_example (see
tests_native_time_windows.py).
"""
import random
import unittest

import networkx as nx
import numpy as np

from cspy import BiDirectional

# Small acyclic instance with negative weights. Complete path costs:
#   Source-1-Sink: -3, Source-2-Sink: -6, Source-1-2-Sink: -13,
#   Source-1-3-Sink: -14, Source-2-3-Sink: -17, Source-1-2-3-Sink: -24
DAG_EDGES = [
    ("Source", 1, -5),
    ("Source", 2, -4),
    (1, 2, -6),
    (1, 3, -3),
    (2, 3, -7),
    (3, "Sink", -6),
    (2, "Sink", -2),
    (1, "Sink", 2),
]
DAG_OPTIMUM = -24.0

DIRECTIONS = ("forward", "backward", "both")

# Six customer TSPTW instance (known optimum 33)
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
TSPTW_OPTIMUM = 33.0


def _build_dag(res_per_edge=1.0):
    G = nx.DiGraph(n_res=2)
    for (u, v, w) in DAG_EDGES:
        G.add_edge(u, v, res_cost=np.array([1.0, float(res_per_edge)]),
                   weight=float(w))
    return G


def _solve_dag(direction, res_per_edge=1.0, max_res=None, **kwargs):
    alg = BiDirectional(
        _build_dag(res_per_edge),
        max_res if max_res is not None else [10.0, 10.0],
        [0.0, 0.0],
        direction=direction,
        **kwargs,
    )
    alg.run()
    return alg


def _solve_tsptw(tw_b=TSPTW_TW_B, **kwargs):
    n = TSPTW_N
    G = nx.DiGraph(n_res=2)

    def rc(t):
        return np.array([1.0, float(t)])

    for i in range(1, n + 1):
        G.add_edge("Source", i, res_cost=rc(TSPTW_TRAVEL[0][i]),
                   weight=float(TSPTW_TRAVEL[0][i]))
        G.add_edge(i, "Sink", res_cost=rc(TSPTW_TRAVEL[i][0]),
                   weight=float(TSPTW_TRAVEL[i][0]))
        for j in range(1, n + 1):
            if i != j:
                G.add_edge(i, j, res_cost=rc(TSPTW_TRAVEL[i][j]),
                           weight=float(TSPTW_TRAVEL[i][j]))
    alg = BiDirectional(
        G,
        [float(n + 1), float(tw_b[0])],
        [0.0, 0.0],
        direction="forward",
        elementary=True,
        time_windows={i: (float(TSPTW_TW_A[i]), float(tw_b[i]))
                      for i in range(1, n + 1)},
        service_times={i: float(TSPTW_SERVICE[i]) for i in range(1, n + 1)},
        require_all_visits=True,
        **kwargs,
    )
    alg.run()
    return alg


def _build_large_elementary_instance():
    """Complete DAG over 22 nodes with negative weights: the first complete
    Source-Sink paths appear within milliseconds while exhausting the
    elementary search takes far longer than any limit used here."""
    random.seed(7)
    m = 22
    G = nx.DiGraph(n_res=2)
    names = ["Source"] + list(range(1, m - 1)) + ["Sink"]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            G.add_edge(names[i], names[j], res_cost=np.array([1.0, 1.0]),
                       weight=float(random.randint(-10, -1)))
    return G, float(m)


class TestTerminationReason(unittest.TestCase):
    def test_none_before_run(self):
        alg = BiDirectional(_build_dag(), [10.0, 10.0], [0.0, 0.0])
        self.assertIsNone(alg.termination_reason)

    def test_completed_all_directions(self):
        for direction in DIRECTIONS:
            with self.subTest(direction=direction):
                alg = _solve_dag(direction)
                self.assertEqual(alg.termination_reason, "completed")
                self.assertAlmostEqual(alg.total_cost, DAG_OPTIMUM)

    def test_threshold_reached_all_directions(self):
        for direction in DIRECTIONS:
            with self.subTest(direction=direction):
                alg = _solve_dag(direction, threshold=-20)
                self.assertEqual(alg.termination_reason, "threshold_reached")
                self.assertLessEqual(alg.total_cost, -20)
                self.assertEqual(alg.path[0], "Source")
                self.assertEqual(alg.path[-1], "Sink")

    def test_no_feasible_path_all_directions(self):
        # Every complete path uses at least two edges, each consuming 5 of
        # resource 1, and max_res[1] = 8 < 10: no feasible path exists.
        for direction in DIRECTIONS:
            with self.subTest(direction=direction):
                alg = _solve_dag(direction, res_per_edge=5.0,
                                 max_res=[10.0, 8.0])
                self.assertEqual(alg.termination_reason, "no_feasible_path")
                self.assertTrue(alg.path is None or len(alg.path) <= 1)

    def test_time_limit_without_interim_solution(self):
        G, m = _build_large_elementary_instance()
        alg = BiDirectional(G, [m, m], [0.0, 0.0], direction="forward",
                            elementary=True, time_limit=0.0)
        alg.run()
        self.assertEqual(alg.termination_reason, "time_limit_reached")
        # Degenerate result: the status is unknown, not proven infeasible
        self.assertTrue(alg.path is None or len(alg.path) <= 1)

    def test_time_limit_with_interim_solution(self):
        G, m = _build_large_elementary_instance()
        alg = BiDirectional(G, [m, m], [0.0, 0.0], direction="forward",
                            elementary=True, time_limit=0.2)
        alg.run()
        self.assertEqual(alg.termination_reason, "time_limit_reached")
        self.assertEqual(alg.path[0], "Source")
        self.assertEqual(alg.path[-1], "Sink")
        self.assertLess(alg.total_cost, 0)


class TestThresholdStrict(unittest.TestCase):
    def test_non_strict_stops_at_equal_cost(self):
        # Legacy behaviour (threshold alone): <= comparison, so a path whose
        # cost equals the threshold stops the search.
        for direction in DIRECTIONS:
            with self.subTest(direction=direction):
                alg = _solve_dag(direction, threshold=DAG_OPTIMUM)
                self.assertEqual(alg.termination_reason, "threshold_reached")
                self.assertAlmostEqual(alg.total_cost, DAG_OPTIMUM)

    def test_strict_completes_at_equal_cost(self):
        # Strict comparison with the optimum as threshold: no strictly
        # better path exists, so the search must run to completion and
        # return the optimum.
        for direction in DIRECTIONS:
            with self.subTest(direction=direction):
                alg = _solve_dag(direction, threshold=DAG_OPTIMUM,
                                 threshold_strict=True)
                self.assertEqual(alg.termination_reason, "completed")
                self.assertAlmostEqual(alg.total_cost, DAG_OPTIMUM)

    def test_strict_stops_below_threshold(self):
        # The optimum (-24) is strictly below the threshold (-23), so the
        # strict threshold stop may fire.
        for direction in DIRECTIONS:
            with self.subTest(direction=direction):
                alg = _solve_dag(direction, threshold=-23,
                                 threshold_strict=True)
                self.assertEqual(alg.termination_reason, "threshold_reached")
                self.assertLess(alg.total_cost, -23)

    def test_strict_requires_threshold(self):
        with self.assertRaises(Exception):
            BiDirectional(_build_dag(), [10.0, 10.0], [0.0, 0.0],
                          threshold_strict=True)

    def test_strict_must_be_bool(self):
        with self.assertRaises(Exception):
            BiDirectional(_build_dag(), [10.0, 10.0], [0.0, 0.0],
                          threshold=1.0, threshold_strict=1)

    def test_strict_rejects_nan_threshold(self):
        # A NaN threshold is silently ignored by the algorithm, which would
        # silently disable the strict comparison as well.
        with self.assertRaises(Exception):
            BiDirectional(_build_dag(), [10.0, 10.0], [0.0, 0.0],
                          threshold=float("nan"), threshold_strict=True)

    def test_strict_rejects_non_numeric_threshold(self):
        # A non-numeric threshold is never forwarded to the C++ engine, which
        # would silently disable the strict comparison as well. Booleans are
        # rejected too: bool is an int subclass but not a threshold.
        for bad_threshold in ("cheap", True):
            with self.subTest(threshold=bad_threshold):
                with self.assertRaises(Exception):
                    BiDirectional(_build_dag(), [10.0, 10.0], [0.0, 0.0],
                                  threshold=bad_threshold,
                                  threshold_strict=True)


class TestTerminationReasonWithRequiredVisits(unittest.TestCase):
    """Interaction with the mandatory-visit mode (require_all_visits)."""

    def test_completed(self):
        alg = _solve_tsptw()
        self.assertEqual(alg.termination_reason, "completed")
        self.assertAlmostEqual(alg.total_cost, TSPTW_OPTIMUM)

    def test_threshold_reached_returns_full_tour(self):
        alg = _solve_tsptw(threshold=40)
        self.assertEqual(alg.termination_reason, "threshold_reached")
        self.assertLessEqual(alg.total_cost, 40)
        # The early-stopped tour must still cover every customer
        self.assertEqual(set(alg.path[1:-1]), set(range(1, TSPTW_N + 1)))

    def test_strict_with_optimum_completes(self):
        alg = _solve_tsptw(threshold=TSPTW_OPTIMUM, threshold_strict=True)
        self.assertEqual(alg.termination_reason, "completed")
        self.assertAlmostEqual(alg.total_cost, TSPTW_OPTIMUM)

    def test_strict_above_optimum_stops(self):
        alg = _solve_tsptw(threshold=TSPTW_OPTIMUM + 1, threshold_strict=True)
        self.assertEqual(alg.termination_reason, "threshold_reached")
        self.assertLess(alg.total_cost, TSPTW_OPTIMUM + 1)
        self.assertEqual(set(alg.path[1:-1]), set(range(1, TSPTW_N + 1)))

    def test_no_feasible_path(self):
        # Customer 2 can never be served: its window closes at time 2 while
        # the earliest possible arrival is 3, and every tour must visit it.
        tight = list(TSPTW_TW_B)
        tight[2] = 2
        alg = _solve_tsptw(tw_b=tuple(tight))
        self.assertEqual(alg.termination_reason, "no_feasible_path")
        self.assertTrue(alg.path is None or len(alg.path) <= 1)


if __name__ == "__main__":
    unittest.main()
