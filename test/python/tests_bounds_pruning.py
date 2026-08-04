import random
import unittest

from networkx import DiGraph, all_simple_paths

from cspy import BiDirectional
from cspy.algorithms import bidirectional as bidirectional_module


class TestsBoundsPruning(unittest.TestCase):
    """
    Regression tests for two bounds_pruning bugs.

    1. The wrapper only called setBoundsPruning when bounds_pruning was
       False, so the option never reached the C++ side.
    2. lowerBoundWeight was called with the directions swapped: the forward
       search was given distances from the source instead of the cost-to-go
       to the sink (and vice versa), so checkPrimalBound pruned optimal
       labels once bug 1 no longer hid it.
    """

    def test_option_reaches_cpp(self):
        # Guard for bug 1: bounds_pruning=True must be forwarded.
        calls = []
        real_cls = bidirectional_module.BiDirectionalCpp

        class Recording(real_cls):
            def setBoundsPruning(self, value):
                calls.append(value)
                return real_cls.setBoundsPruning(self, value)

        G = DiGraph(directed=True, n_res=2)
        G.add_edge("Source", 0, res_cost=[1, 1], weight=1)
        G.add_edge(0, "Sink", res_cost=[1, 1], weight=1)
        bidirectional_module.BiDirectionalCpp = Recording
        try:
            BiDirectional(G, [10, 10], [0, 0], bounds_pruning=True)
        finally:
            bidirectional_module.BiDirectionalCpp = real_cls
        self.assertEqual(calls, [True])

    def test_matches_brute_force_on_random_instances(self):
        # Guard for bug 2: with pruning on, the optimum must not be lost.
        tested = 0
        for seed in range(20):
            rng = random.Random(seed)
            instance = self._random_instance(rng, rng.randint(6, 9))
            if instance is None:
                continue
            G, max_res, min_res = instance
            optimum = self._brute_force(G, max_res, min_res)
            if optimum is None:
                continue
            tested += 1
            for direction in ("both", "forward", "backward"):
                for bounds_pruning in (False, True):
                    alg = BiDirectional(
                        G,
                        max_res,
                        min_res,
                        direction=direction,
                        elementary=True,
                        bounds_pruning=bounds_pruning,
                    )
                    alg.run()
                    self.assertAlmostEqual(
                        alg.total_cost,
                        optimum,
                        msg=f"seed={seed} direction={direction} "
                        f"bounds_pruning={bounds_pruning}",
                    )
        # The seeds above are fixed, so this cannot flake; it only protects
        # against edits to _random_instance emptying the sweep.
        self.assertGreater(tested, 10)

    @staticmethod
    def _random_instance(rng, n_nodes):
        G = DiGraph(directed=True, n_res=2)
        nodes = list(range(n_nodes))
        for u in nodes:
            for v in nodes:
                if u != v and rng.random() < 0.35:
                    G.add_edge(
                        u,
                        v,
                        res_cost=[1, rng.randint(1, 5)],
                        weight=rng.randint(1, 10),
                    )
        for v in nodes:
            if rng.random() < 0.6:
                G.add_edge(
                    "Source",
                    v,
                    res_cost=[1, rng.randint(1, 5)],
                    weight=rng.randint(1, 10),
                )
            if rng.random() < 0.6:
                G.add_edge(
                    v,
                    "Sink",
                    res_cost=[1, rng.randint(1, 5)],
                    weight=rng.randint(1, 10),
                )
        if "Source" not in G or "Sink" not in G:
            return None
        max_res = [float(len(G.edges())), float(rng.randint(6, 15))]
        min_res = [0.0, 0.0]
        return G, max_res, min_res

    @staticmethod
    def _brute_force(G, max_res, min_res):
        best = None
        for path in all_simple_paths(G, "Source", "Sink"):
            cost = 0.0
            res = [0.0] * len(max_res)
            for u, v in zip(path[:-1], path[1:]):
                edge = G[u][v]
                cost += edge["weight"]
                res = [r + rc for r, rc in zip(res, edge["res_cost"])]
            feasible = all(
                m <= r <= M for r, m, M in zip(res, min_res, max_res)
            )
            if feasible and (best is None or cost < best):
                best = cost
        return best


if __name__ == "__main__":
    unittest.main()
