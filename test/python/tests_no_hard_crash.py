"""Regression tests for inputs and call sequences that used to kill the
interpreter instead of raising.

Every case below was, before the accompanying fixes, an out-of-bounds access,
a null dereference or an unbounded loop inside the C++ core. None of them
raised a Python exception: the process died, which in a Jupyter notebook shows
up only as "the kernel appears to have died" with no traceback -- so the tests
here are as much about the *kind* of failure as about the failure itself.

The tests run in-process, so a regression takes the test runner down with it
rather than reporting a failure. That is intentional: a crashed runner is a
loud, unmistakable signal, and running each case in a subprocess would hide
the very thing being tested behind an exit code.
"""

from networkx import DiGraph

from cspy_tw import BiDirectional, REFCallback

from utils import TestingBase


def _simple_graph(n_res=2):
    """Source -> {A, B} -> Sink, with a negative arc between A and B."""
    G = DiGraph(directed=True, n_res=n_res)
    res_cost = [1, 2] + [1] * (n_res - 2)
    G.add_edge("Source", "A", res_cost=list(res_cost), weight=0)
    G.add_edge("Source", "B", res_cost=list(res_cost), weight=0)
    G.add_edge("A", "B", res_cost=list(res_cost), weight=-10)
    G.add_edge("B", "A", res_cost=list(res_cost), weight=-10)
    G.add_edge("A", "Sink", res_cost=list(res_cost), weight=0)
    G.add_edge("B", "Sink", res_cost=list(res_cost), weight=0)
    return G


class TestsResultsBeforeRun(TestingBase):
    """Reading a result before ``run()`` produced one.

    ``best_label_`` is allocated by ``init()``, which ``run()`` calls, so every
    result getter used to dereference a null ``shared_ptr``.
    """

    def setUp(self):
        self.alg = BiDirectional(_simple_graph(), [10, 20], [0, 0])

    def test_path_before_run_raises(self):
        with self.assertRaises(RuntimeError):
            self.alg.path

    def test_total_cost_before_run_raises(self):
        with self.assertRaises(RuntimeError):
            self.alg.total_cost

    def test_consumed_resources_before_run_raises(self):
        with self.assertRaises(RuntimeError):
            self.alg.consumed_resources

    def test_check_critical_res_before_run_raises(self):
        with self.assertRaises(RuntimeError):
            self.alg.check_critical_res()

    def test_termination_reason_before_run_is_none(self):
        # This one never crashed and must keep answering, because it is how a
        # caller distinguishes "not run yet" from a finished search.
        self.assertIsNone(self.alg.termination_reason)

    def test_results_available_after_run(self):
        self.alg.run()
        self.assertEqual(self.alg.path[0], "Source")
        self.assertEqual(self.alg.path[-1], "Sink")
        self.assertIsNotNone(self.alg.total_cost)
        self.assertIsNotNone(self.alg.consumed_resources)

    def test_cpp_getter_before_run_raises(self):
        # The Python wrapper guards this, but so must the engine: the C++
        # object is reachable on its own, and a wheel whose Python layer is
        # bypassed must still not be able to take the process down.
        with self.assertRaises(RuntimeError):
            self.alg.bidirectional_cpp.getPath()


class TestsRunIsSingleShot(TestingBase):
    """``run()`` twice on one object.

    The search containers are not rebuilt between calls. With
    ``direction='backward'`` the second call reached ``processBwdLabel`` with a
    default-constructed label -- null ``params_ptr``, empty resource vector --
    and segfaulted. Re-executing a notebook cell was enough to hit it.
    """

    def _run_twice(self, direction):
        alg = BiDirectional(_simple_graph(), [10, 20], [0, 0], direction=direction)
        alg.run()
        with self.assertRaises(RuntimeError):
            alg.run()

    def test_second_run_forward_raises(self):
        self._run_twice("forward")

    def test_second_run_backward_raises(self):
        self._run_twice("backward")

    def test_second_run_both_raises(self):
        self._run_twice("both")

    def test_fresh_object_runs_again(self):
        for _ in range(2):
            alg = BiDirectional(_simple_graph(), [10, 20], [0, 0])
            alg.run()
            self.assertEqual(alg.path[0], "Source")


class TestsCriticalResRange(TestingBase):
    """``critical_res`` is used to subscript ``max_res``, ``min_res`` and every
    label's resource vector without bounds checking, so an out-of-range index
    was an out-of-bounds write: heap corruption, and a crash whose timing
    varied from run to run."""

    def _reject(self, critical_res):
        with self.assertRaises(Exception):
            BiDirectional(
                _simple_graph(), [10, 20], [0, 0], critical_res=critical_res
            )

    def test_too_large_rejected(self):
        self._reject(5)

    def test_equal_to_n_res_rejected(self):
        self._reject(2)

    def test_negative_rejected(self):
        self._reject(-1)

    def test_bool_rejected(self):
        # bool is a subclass of int; True would silently select index 1.
        self._reject(True)

    def test_valid_index_accepted(self):
        alg = BiDirectional(_simple_graph(), [10, 20], [0, 0], critical_res=1)
        alg.run()
        self.assertIsNotNone(alg.path)

    def test_none_means_default(self):
        alg = BiDirectional(_simple_graph(), [10, 20], [0, 0], critical_res=None)
        alg.run()
        self.assertIsNotNone(alg.path)


class TestsCallbackKeepAlive(TestingBase):
    """The engine holds the REF callback as a raw pointer and does not own it.

    Keeping the reference on the wrapper alone is not enough: the C++ object
    outlives the wrapper whenever someone extracts ``bidirectional_cpp``, and
    the director object was then collected while the labelling loop was still
    calling through its pointer.
    """

    class _Additive(REFCallback):
        def REF_fwd(self, cumulative, tail, head, edge, partial_path, cost):
            return [cumulative[i] + edge[i] for i in range(len(cumulative))]

        def REF_bwd(self, cumulative, tail, head, edge, partial_path, cost):
            return [cumulative[i] + edge[i] for i in range(len(cumulative))]

        def REF_join(self, fwd, bwd, tail, head, edge):
            return [fwd[i] + bwd[i] + edge[i] for i in range(len(fwd))]

    def test_user_callback_survives_dropped_wrapper(self):
        import gc

        def build():
            alg = BiDirectional(
                _simple_graph(), [10, 20], [0, 0], direction="forward",
                REF_callback=self._Additive(),
            )
            return alg.bidirectional_cpp

        cpp = build()
        gc.collect()
        cpp.run()
        self.assertGreater(len(cpp.getPath()), 0)

    def test_temporary_callback_survives(self):
        # BiDirectional(..., REF_callback=MyCallback()) passes a temporary.
        import gc

        alg = BiDirectional(
            _simple_graph(), [10, 20], [0, 0], direction="forward",
            REF_callback=self._Additive(),
        )
        gc.collect()
        alg.run()
        self.assertIsNotNone(alg.path)

    def test_native_window_ref_survives_dropped_wrapper(self):
        import gc

        def build():
            alg = BiDirectional(
                _simple_graph(), [10, 20], [0, 0], direction="forward",
                elementary=True, time_windows={"A": (0, 8), "B": (0, 12)},
            )
            return alg.bidirectional_cpp

        cpp = build()
        gc.collect()
        cpp.run()
        self.assertGreater(len(cpp.getPath()), 0)


class TestsEmptyResourceBounds(TestingBase):
    """``max_res`` / ``min_res`` that carry no critical resource.

    ``check()`` selected which validations to run by testing the two lists for
    truthiness, and an empty list is falsy -- so ``max_res=[]`` skipped every
    resource check there is and reached the engine, which indexes both by
    ``critical_res`` (0 by default) on the very first label.
    """

    def _graph(self, n_res):
        G = DiGraph(directed=True, n_res=n_res)
        res_cost = [1] * n_res
        G.add_edge("Source", "A", res_cost=list(res_cost), weight=0)
        G.add_edge("A", "Sink", res_cost=list(res_cost), weight=0)
        return G

    def test_both_empty_rejected(self):
        with self.assertRaises(Exception):
            BiDirectional(self._graph(0), [], [])

    def test_empty_min_res_rejected(self):
        with self.assertRaises(Exception):
            BiDirectional(self._graph(1), [10], [])

    def test_empty_max_res_rejected(self):
        with self.assertRaises(Exception):
            BiDirectional(self._graph(1), [], [0])

    def test_mismatched_lengths_rejected(self):
        with self.assertRaises(Exception):
            BiDirectional(self._graph(2), [10, 20], [0])

    def test_cpp_constructor_rejects_empty(self):
        # The engine must refuse it too: the Python check is not the only way
        # in, and this constructor is reachable directly.
        from cspy_tw.algorithms.pyBiDirectionalCpp import (
            BiDirectionalCpp,
            DoubleVector,
        )

        with self.assertRaises(Exception):
            BiDirectionalCpp(2, 1, 0, 1, DoubleVector(), DoubleVector())


class _WrongLengthREF(REFCallback):
    """A REF that returns the wrong number of resources.

    Callback return values are user input: everything downstream indexes them
    positionally against ``max_res``. A short vector was the worse case -- the
    feasibility loop is bounded by the vector's own length, so the critical
    resource stopped being checked and the search never terminated, allocating
    labels until the process was killed.
    """

    def __init__(self, length):
        super().__init__()
        self.length = length

    def REF_fwd(self, cumulative, tail, head, edge, partial_path, cost):
        return [0.0] * self.length

    def REF_bwd(self, cumulative, tail, head, edge, partial_path, cost):
        return [0.0] * self.length

    def REF_join(self, fwd, bwd, tail, head, edge):
        return [0.0] * self.length


class TestsREFCallbackReturnLength(TestingBase):
    def _reject(self, length, direction):
        callback = _WrongLengthREF(length)
        alg = BiDirectional(
            _simple_graph(), [10, 20], [0, 0], direction=direction,
            REF_callback=callback,
        )
        with self.assertRaises(Exception):
            alg.run()

    def test_empty_return_forward(self):
        self._reject(0, "forward")

    def test_empty_return_both(self):
        self._reject(0, "both")

    def test_short_return_forward(self):
        self._reject(1, "forward")

    def test_short_return_both(self):
        self._reject(1, "both")

    def test_long_return_forward(self):
        self._reject(50, "forward")

    def test_correct_length_accepted(self):
        class Additive(REFCallback):
            def REF_fwd(self, cumulative, tail, head, edge, partial_path, cost):
                return [cumulative[i] + edge[i] for i in range(len(cumulative))]

            def REF_bwd(self, cumulative, tail, head, edge, partial_path, cost):
                return [cumulative[i] + edge[i] for i in range(len(cumulative))]

            def REF_join(self, fwd, bwd, tail, head, edge):
                return [fwd[i] + bwd[i] + edge[i] for i in range(len(fwd))]

        callback = Additive()
        alg = BiDirectional(
            _simple_graph(), [10, 20], [0, 0], direction="forward",
            REF_callback=callback,
        )
        alg.run()
        self.assertIsNotNone(alg.path)
