# Wrapper for BiDirectionalCpp
from typing import Dict, Hashable, Iterable, List, Optional, Tuple, Union

from networkx import DiGraph, convert_node_labels_to_integers, get_node_attributes
from cspy.preprocessing import preprocess_graph
from cspy.checking import check, check_native_windows, check_required_visits

# Import from the SWIG output file
from .pyBiDirectionalCpp import (
    BiDirectionalCpp,
    REFCallback,
    DoubleVector,
    IntVector,
    NodeWindowREF,
    POLICY_ADDITIVE,
    POLICY_WINDOW_WAIT,
    POLICY_WINDOW_HARD,
)

#: Mapping from user-facing policy names to native enum values
_POLICY_MAP = {
    "additive": POLICY_ADDITIVE,
    "window_wait": POLICY_WINDOW_WAIT,
    "window_hard": POLICY_WINDOW_HARD,
}


class BiDirectional:
    """
    Python wrapper for the bidirectional labelling algorithm with dynamic
    half-way point (`Tilk 2017`_).

    Parameters
    ----------
    G : object instance :class:`nx.Digraph()`
        must have ``n_res`` graph attribute and all edges must have
        ``res_cost`` attribute.

    max_res : list of floats
        :math:`[H_F, M_1, M_2, ..., M_{n\_res}]` upper bounds for resource
        usage (including initial forward stopping point).
        We must have ``len(max_res)`` :math:`=` ``len(max_res)``

    min_res : list of floats
        :math:`[H_B, L_1, L_2, ..., L_{n\_res}]` lower bounds for resource
        usage (including initial backward stopping point).
        We must have ``len(min_res)`` :math:`=` ``len(max_res)``

    preprocess : bool, optional
        enables preprocessing routine. Default : False.

    direction : string, optional
        preferred search direction.
        Either "both", "forward", or, "backward". Default : "both".

    method : string, optional
        preferred method for determining search direction.
        Either "generated" (direction with least number of generated
        labels), "processed" (direction with least number of processed labels),
        or, "unprocessed" (direction with least number of unprocessed labels).
        Default: "unprocessed"

    time_limit : float or int, optional
        time limit in seconds.
        Default: None

    threshold : float, optional
        specify a threshold for a an acceptable resource feasible path with
        total cost <= threshold.
        Note this typically causes the search to terminate early.
        Default: None

    elementary : bool, optional
        whether the problem is elementary. i.e. no cycles are allowed in the
        final path. Note, True increases run time.
        Default: False

    bounds_pruning : bool, optional
        whether lower bounds based on shortest paths are used when pruning labels
        using primal bounds.
        Note this is an experimental feature. See issues.
        Default: False

    find_critical_res : bool, optional
        bool with whether critical resource is found at the preprocessing stage.
        Note1: this is an experimental feature. See issues.
        Note2: overrides critical_res value.
        Default false.

    critical_res : int, optional
        Resource index to use as primary resource. Note: corresponding resource
        has to fulfil some conditions (e.g. monotonicity). See `REFs`_.
        Default: 0

    seed : None or int, optional
        *Disabled*
        seed for random method class. Default : None.

    REF_callback : REFCallback, optional
        Custom resource extension callback. See `REFs`_ for more details.
        Default : None

    two_cycle_elimination: bool, optional
        whether 2-cycles should be eliminated for non-elementary RCSPP

    time_windows : dict, optional
        Native (C++-side) time windows: ``{node: (a_v, b_v)}`` with the
        original node names as keys. Sets policy ``window_wait`` on resource
        ``time_res`` (default 1). The propagated resource value is the
        *service start time* at the node, with transition
        ``T_head = max(a_head, T_tail + s_tail + t_edge)`` where ``t_edge`` is
        ``res_cost[time_res]`` (travel time) and rejection when
        ``T_head > b_head`` (waiting until ``a_head`` is allowed).
        Unspecified nodes default to ``(0, max_res[time_res])``.
        ``res[0]`` must remain a monotone critical resource (e.g. edge count
        with ``res_cost[0] = 1`` on every edge). The
        arrival-then-service convention (windows on arrival, value = departure
        time) is feasibility-equivalent with the same parameters; only the
        reported value differs by ``+s_v``.
        Notes: cannot be combined with ``REF_callback`` or
        ``find_critical_res=True``; ``preprocess=True`` is a no-op (pruning is
        always skipped, as with ``REF_callback``); for ``direction='both'``
        the reported window resource in ``consumed_resources`` is a
        feasibility surrogate (``start_h + g_h``), and for
        ``direction='backward'`` it is on the reversed time axis.
        Default : None

    service_times : dict, optional
        ``{node: s_v}`` with ``s_v >= 0``, added on departure from the node
        (unspecified nodes default to 0). Only usable with ``time_windows``.
        Default : None

    time_res : int, optional
        resource index used by ``time_windows``. Must differ from the
        critical resource index. Default : 1

    node_windows : dict, optional
        general native interface: ``{res_idx: {node: (lb, ub)}}``.
        Default : None

    node_consumption : dict, optional
        general native interface: ``{res_idx: {node: c_v}}``. For policy
        ``additive`` the consumption of the *head* node is added on arrival
        (visit flags: ``c = -1`` with ``min_res[r] <= -1``); for window
        policies it is added on departure from the *tail* node (service
        time). Default : None

    window_policy : dict, optional
        ``{res_idx: 'additive' | 'window_wait' | 'window_hard'}``; missing
        resources default to ``'additive'``. ``'window_hard'`` (reject early
        arrivals instead of waiting) requires ``direction='forward'``.
        Default : None

    window_eps : float, optional
        tolerance used in native window comparisons. Default : 1e-9

    require_all_visits : bool, optional
        When True, only ``Source`` -> ``Sink`` paths that visit every node of
        ``required_nodes`` are accepted, and the dominance rule is restricted
        so that a label may only dominate another label visiting exactly the
        same required nodes. This makes it possible to solve the Traveling
        Salesman Problem with Time Windows (TSPTW) directly, without encoding
        one visit indicator resource per customer.
        Requires ``elementary=True`` and ``direction='forward'``.
        The restriction of the dominance rule is what makes the search sound
        here: the standard rule lets a label whose visited set is a proper
        subset dominate a label with a superset visited set, which prunes
        away the only labels that can still cover every required node.
        Note the assumptions inherited from the standard dominance rule are
        unchanged: resource extension functions must be monotone (a custom
        ``REF_callback`` that is not monotone, or the ``'window_hard'``
        policy, can still prune optimal labels), and feasibility of
        non-critical resources is assumed to be decided by upper bounds only.
        A strictly positive lower bound on a non-critical resource
        (``min_res[r] > 0`` for ``r != critical_res``) breaks that assumption
        and can make the search report "no solution" for an instance that has
        one -- a wrong answer, not merely a weaker bound. Model such a lower
        bound on the critical resource instead. A warning is logged.
        Default: False

    required_nodes : iterable of node labels, optional
        The nodes that every accepted path must visit, given with the
        original node labels of ``G``. Defaults to every node of ``G`` other
        than ``'Source'`` and ``'Sink'``. Only usable together with
        ``require_all_visits=True``. Duplicates are ignored and the order is
        irrelevant. An iterable that can only be traversed once (a generator,
        ``map``, ``filter``, ``iter(...)``) is accepted: it is materialised
        once during validation. An empty required set is rejected, because it
        would silently reduce the problem to a plain elementary shortest path
        problem.
        Default : None

    Notes
    -----
    When no resource-feasible ``Source -> Sink`` path exists, the reported
    result is a *degenerate* one that differs by direction:
    ``direction='forward'`` yields ``path == ['Source']`` with
    ``total_cost == 0.0``, ``'both'`` yields ``path is None`` and
    ``'backward'`` yields ``path == ['Sink']`` (pre-existing engine
    behaviour, native windows or not). Always check for a degenerate result
    before interpreting ``total_cost`` -- in column generation pricing,
    ``total_cost == 0.0`` from a degenerate path must not be read as
    "no improving column"::

        infeasible = (alg.path is None or len(alg.path) <= 1
                      or alg.path[0] != "Source" or alg.path[-1] != "Sink")

    A search stopped early by ``time_limit`` (or by ``threshold``) before any
    complete ``Source -> Sink`` path was accepted reports exactly the same
    degenerate result as a genuinely infeasible instance; nothing
    distinguishes the two. This matters in particular with
    ``require_all_visits=True``, where the first accepted path is much harder
    to reach than in the plain elementary shortest path problem. Either leave
    ``time_limit`` unset, or treat a degenerate result from a time limited run
    as "unknown" rather than as "infeasible".

    .. _REFs : https://cspy.readthedocs.io/en/latest/ref.html
    .. _Tilk 2017: https://www.sciencedirect.com/science/article/pii/S0377221717302035
    .. _Righini and Salani (2006): https://www.sciencedirect.com/science/article/pii/S1572528606000417
    """

    def __init__(
        self,
        G: DiGraph,
        max_res: List[float],
        min_res: List[float],
        preprocess: Optional[bool] = False,
        direction: Optional[str] = "both",
        method: Optional[str] = "unprocessed",
        time_limit: Optional[Union[float, int]] = None,
        threshold: Optional[float] = None,
        elementary: Optional[bool] = False,
        bounds_pruning: Optional[bool] = False,
        find_critical_res: Optional[bool] = False,
        critical_res: Optional[int] = None,
        # seed: Union[int] = None,
        REF_callback: Optional[REFCallback] = None,
        two_cycle_elimination: Optional[bool] = False,
        # --- native time windows (simple interface) ---
        time_windows: Optional[Dict[Hashable, Tuple[float, float]]] = None,
        service_times: Optional[Dict[Hashable, float]] = None,
        time_res: int = 1,
        # --- native windows (general interface) ---
        node_windows: Optional[Dict[int, Dict[Hashable, Tuple[float, float]]]] = None,
        node_consumption: Optional[Dict[int, Dict[Hashable, float]]] = None,
        window_policy: Optional[Dict[int, str]] = None,
        window_eps: float = 1e-9,
        # --- mandatory visits ---
        require_all_visits: bool = False,
        required_nodes: Optional[Iterable[Hashable]] = None,
    ):
        # Check inputs
        check(G, max_res, min_res, direction, REF_callback, __name__)
        # check_seed(seed, __name__)
        check_native_windows(
            G,
            max_res,
            min_res,
            direction,
            REF_callback,
            critical_res,
            find_critical_res,
            preprocess,
            time_windows,
            service_times,
            time_res,
            node_windows,
            node_consumption,
            window_policy,
        )
        # The validation materialises `required_nodes` into a list and returns
        # it. Rebinding the name here is what guarantees that the argument is
        # traversed exactly once: an iterable that can only be traversed once
        # (a generator, ``map``, ``filter``, ``iter(...)``) would otherwise be
        # empty on the second traversal, which would silently disable the
        # whole requirement.
        required_nodes = check_required_visits(
            G,
            direction,
            elementary,
            require_all_visits,
            required_nodes,
            max_res,
            min_res,
            critical_res,
            window_policy,
        )
        # Node labels every accepted path must visit (None = feature off).
        # The validation guarantees that this set is never empty.
        self._required_nodes = None
        if require_all_visits:
            self._required_nodes = (
                set(required_nodes)
                if required_nodes is not None
                else set(G.nodes) - {"Source", "Sink"}
            )
        # Normalised native window specs: {r: (policy, windows, consumption)}
        window_specs = self._normalize_window_specs(
            time_windows,
            service_times,
            time_res,
            node_windows,
            node_consumption,
            window_policy,
        )
        # Preprocess and save graph. Native windows behave like a custom REF:
        # pruning is always skipped.
        self.G: DiGraph = preprocess_graph(
            G, max_res, min_res, preprocess, REF_callback or bool(window_specs)
        )
        # Dictionary with graph label -> original label
        self._original_node_labels = None
        # Vertex id with source/sink
        self._source_id: int = None
        self._sink_id: int = None

        max_res_vector = _list_to_double_vector(max_res)
        min_res_vector = _list_to_double_vector(min_res)

        # Pass graph
        self._init_graph()
        self.bidirectional_cpp = BiDirectionalCpp(
            len(self.G.nodes()),
            len(self.G.edges()),
            self._source_id,
            self._sink_id,
            max_res_vector,
            min_res_vector,
        )
        self._load_graph()
        if self._required_nodes is not None:
            self.bidirectional_cpp.setRequiredNodes(self._required_node_ids())
        # pass solving attributes
        if direction != "both":
            self.bidirectional_cpp.setDirection(direction)
        if method in ["random", "generated", "processed"]:
            self.bidirectional_cpp.setMethod(method)
        if time_limit is not None and isinstance(time_limit, (int, float)):
            self.bidirectional_cpp.setTimeLimit(time_limit)
        if threshold is not None and isinstance(threshold, (int, float)):
            self.bidirectional_cpp.setThreshold(threshold)
        if isinstance(elementary, bool) and elementary:
            self.bidirectional_cpp.setElementary(True)
        if isinstance(bounds_pruning, bool) and bounds_pruning:
            self.bidirectional_cpp.setBoundsPruning(True)
        if isinstance(find_critical_res, bool) and find_critical_res:
            self.bidirectional_cpp.setFindCriticalRes(True)
        if isinstance(critical_res, int) and critical_res != 0:
            self.bidirectional_cpp.setCriticalRes(critical_res)
        # The C++ side only holds a raw pointer to the custom resource
        # extension function, so keep a reference here as well: a caller
        # writing BiDirectional(..., REF_callback=MyCallback()) would
        # otherwise let the temporary be collected and the labelling loop
        # would dereference freed memory (a segmentation fault).
        self._ref_callback = REF_callback
        if REF_callback is not None:
            # Add a Python callback (caller owns the callback, so we
            # disown it first by calling __disown__).
            # see: https://github.com/swig/swig/blob/b6c2438d7d7aac5711376a106a156200b7ff1056/Examples/python/callback/runme.py#L36
            self.bidirectional_cpp.setREFCallback(REF_callback)
        # Native windows REF (pure C++, non-director proxy: REF calls during
        # the labelling loop never cross the Python boundary).
        self._window_ref = None
        if window_specs:
            self._window_ref = self._build_native_windows(
                max_res,
                critical_res if isinstance(critical_res, int) else 0,
                window_specs,
                window_eps,
            )
            # Ownership: `self` keeps the (Python-owned, thisown=True)
            # reference for the lifetime of bidirectional_cpp. Params never
            # deletes its ref_callback pointer (Params::~Params nulls it
            # before delete), so there is no double free. Do NOT __disown__
            # (that would leak the object).
            self.bidirectional_cpp.setREFCallback(self._window_ref)
            # Also tie the native REF's lifetime to the C++ proxy itself, so
            # extracting `bidirectional_cpp` and dropping this wrapper cannot
            # leave the C++ side with a dangling callback pointer.
            self.bidirectional_cpp._window_ref_keepalive = self._window_ref
        # if isinstance(seed, int) and seed is not None:
        #     self.bidirectional_cpp.setSeed(seed)
        if isinstance(two_cycle_elimination, bool) and two_cycle_elimination:
            self.bidirectional_cpp.setTwoCycleElimination(True)

    def run(self):
        "Run the algorithm in series"
        self.bidirectional_cpp.run()

    def run_parallel(self):
        "Run the algorithm in parallel"
        raise NotImplementedError("Coming soon")

    @property
    def path(self):
        """Get list with nodes in calculated path."""
        path = self.bidirectional_cpp.getPath()
        # format as list on return as SWIG returns "tuple"
        if len(path) <= 0:
            return None
        return [self.G.nodes[p]["original_label"] for p in path]

    @property
    def total_cost(self):
        """Get accumulated cost along the path."""
        path = self.bidirectional_cpp.getPath()
        return self.bidirectional_cpp.getTotalCost() if len(path) > 0 else None

    @property
    def consumed_resources(self):
        """Get accumulated resources consumed along the path."""
        path = self.bidirectional_cpp.getPath()
        res = self.bidirectional_cpp.getConsumedResources()
        if len(path) > 0 and len(res) > 0:
            return list(res)
        else:
            return None

    def check_critical_res(self):
        """After running the algorithm, one can check if critical resource is
        tight (difference between final resource and maximum) and prints a
        message if it doesn't match to the one chosen (or default one).
        """
        self.bidirectional_cpp.checkCriticalRes()

    def _init_graph(self):
        # Convert node label to integers and saves original labels in
        # new node attribute "original_label"
        self.G = convert_node_labels_to_integers(
            self.G, label_attribute="original_label"
        )
        self._original_node_labels = get_node_attributes(self.G, "original_label")
        # Save source and sink node ids (integers)
        self._source_id = self._get_original_node_label("Source")
        self._sink_id = self._get_original_node_label("Sink")

    def _load_graph(self):
        # Load nodes
        self.bidirectional_cpp.addNodes(list(self.G.nodes()))
        # Load each edge independently
        for edge in self.G.edges(data=True):
            res_cost = _list_to_double_vector(edge[2]["res_cost"])
            self.bidirectional_cpp.addEdge(
                edge[0], edge[1], edge[2]["weight"], res_cost
            )

    def _required_node_ids(self):
        """Map the required node labels to the internal integer ids used by
        the C++ engine (the same mapping as :meth:`_build_native_windows`)."""
        rev = {v: k for k, v in self._original_node_labels.items()}
        ids = IntVector()
        # Sorting only makes the bit order (and hence any debug output)
        # reproducible; it does not affect the result.
        for name in sorted(self._required_nodes, key=repr):
            try:
                ids.append(rev[name])
            except KeyError:
                raise KeyError(
                    "Required node {} not found in the graph (was it pruned by"
                    " preprocess=True, or misspelled?)".format(name)
                )
        return ids

    @staticmethod
    def _normalize_window_specs(
        time_windows,
        service_times,
        time_res,
        node_windows,
        node_consumption,
        window_policy,
    ):
        """Merge the simple (time_windows) and general (node_windows/...)
        native interfaces into ``{r: (policy_int, {node: (lb, ub)},
        {node: consumption})}`` keyed by resource index."""
        specs = {}
        general_res = set()
        for d in (node_windows, node_consumption, window_policy):
            if d is not None:
                general_res.update(d.keys())
        for r in general_res:
            policy = _POLICY_MAP[(window_policy or {}).get(r, "additive")]
            specs[r] = (
                policy,
                dict((node_windows or {}).get(r, {})),
                dict((node_consumption or {}).get(r, {})),
            )
        if time_windows is not None:
            specs[time_res] = (
                _POLICY_MAP["window_wait"],
                dict(time_windows),
                dict(service_times or {}),
            )
        return specs

    def _build_native_windows(self, max_res, critical_res, specs, eps):
        """Translate original-node-name keyed specs to internal integer id
        arrays and build the native :class:`NodeWindowREF`."""
        n = len(self.G.nodes())
        # original node name -> internal integer id
        rev = {v: k for k, v in self._original_node_labels.items()}
        ref = NodeWindowREF(
            n,
            _list_to_double_vector(max_res),
            self._source_id,
            self._sink_id,
            critical_res,
            eps,
        )
        for r, (policy, windows, cons) in specs.items():
            # Default: unspecified nodes have window [0, max_res[r]] and
            # zero consumption
            lb = [0.0] * n
            ub = [float(max_res[r])] * n
            cc = [0.0] * n
            for name, (a, b) in windows.items():
                try:
                    i = rev[name]
                except KeyError:
                    raise KeyError(
                        "Window node {} not found in graph (was it pruned"
                        " or misspelled?)".format(name)
                    )
                lb[i], ub[i] = float(a), float(b)
            for name, c in cons.items():
                try:
                    cc[rev[name]] = float(c)
                except KeyError:
                    raise KeyError(
                        "Consumption node {} not found in graph".format(name)
                    )
            ref.setResourcePolicy(
                r,
                policy,
                _list_to_double_vector(lb),
                _list_to_double_vector(ub),
                _list_to_double_vector(cc),
            )
        return ref

    def _get_original_node_label(self, node_label):
        matching_labels = [
            k for k, v in self._original_node_labels.items() if v == node_label
        ]
        if len(matching_labels) == 1:
            return matching_labels[0]
        else:
            raise Exception("Node label not found")


def _list_of_tuple_to_int_pair_vector(input_list: List[Tuple[int, int]]):
    int_pair_vector = IntPairVector()
    for (elem1, elem2) in input_list:
        int_pair_vector.append(IntPair(elem1, elem2))
    return int_pair_vector


def _list_to_double_vector(input_list: List[float]):
    double_vector = DoubleVector()
    for elem in input_list:
        double_vector.append(float(elem))
    return double_vector
