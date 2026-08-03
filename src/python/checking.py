from collections.abc import Iterable, Mapping
from math import isfinite
from time import time
from typing import Union
from logging import getLogger

from networkx import DiGraph, NetworkXException, has_path
from numpy import ndarray
from numpy.random import RandomState

LOG = getLogger(__name__)


def check(
    G, max_res=None, min_res=None, direction=None, REF_callback=None, algorithm=None
):
    """
    Checks whether inputs and the graph are of the appropriate types and
    have the required properties.
    For non-specified REFs, removes nodes that cannot be reached due to
    resource limits.

    Parameters
    ----------
    G : object instance :class:`nx.Digraph()`
        must have ``n_res`` graph attribute and all edges must have
        ``res_cost`` attribute.

    max_res : list of floats, optional
        :math:`[M_1, M_2, ..., M_{n\_res}]`
        upper bound for resource usage.
        We must have ``len(max_res)`` :math:`\geq 1`

    min_res : list of floats, optional
        :math:`[L_1, L_2, ..., L_{nres}]` lower bounds for resource usage.
        We must have ``len(min_res)`` :math:`=` ``len(max_res)`` :math:`\geq 1`

    direction : string, optional
        preferred search direction. Either 'both','forward', or, 'backward'.
        Default : 'both'.

    REF_forward, REF_backward, REF_join : functions, optional
        Custom resource extension function. See `REFs`_ for more details.

    .. _REFs : https://cspy.readthedocs.io/en/latest/how_to.html#refs

    :raises: Raises exceptions if incorrect input is given.
        If multiple exceptions are raised, an exception with a list of
        errors is raised.
    """
    errors = []
    if REF_callback:
        try:
            _check_REF(REF_callback)
        except Exception as e:
            errors.append(e)
    # Select checks to perform based on the input provided
    if max_res and min_res and direction:
        check_funcs = [
            _check_res,
            _check_direction,
            _check_graph_attr,
            _check_edge_attr,
            _check_path,
        ]
    elif max_res and min_res:
        check_funcs = [_check_res, _check_graph_attr, _check_edge_attr, _check_path]
    else:
        check_funcs = [_check_path]
    # Check all functions in check_funcs
    for func in check_funcs:
        try:
            func(G, max_res, min_res, direction, algorithm)
        except Exception as e:
            errors.append(e)  # if check fails save error message
    if errors:
        # if any check has failed raise an exception with all the errors
        raise Exception("\n".join("{}".format(item) for item in errors))


#: Valid policies for :func:`check_native_windows` / native node windows
WINDOW_POLICIES = ("additive", "window_wait", "window_hard")


def check_native_windows(
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
):
    """Validate the native node-window arguments of
    :class:`cspy.BiDirectional` (``time_windows`` / ``service_times`` /
    ``node_windows`` / ``node_consumption`` / ``window_policy``).

    :raises: Raises an exception listing all violations found.
    """
    has_native = any(
        x is not None
        for x in (
            time_windows,
            service_times,
            node_windows,
            node_consumption,
            window_policy,
        )
    )
    if not has_native:
        return
    # --- container types first (clear errors instead of AttributeError);
    # nothing below can be checked meaningfully with wrong top-level types ---
    type_errors = []
    for arg_name, d in (
        ("time_windows", time_windows),
        ("service_times", service_times),
        ("node_windows", node_windows),
        ("node_consumption", node_consumption),
        ("window_policy", window_policy),
    ):
        if d is not None and not isinstance(d, Mapping):
            type_errors.append(
                TypeError(
                    "{} must be a dict, got {}".format(
                        arg_name, type(d).__name__
                    )
                )
            )
    if type_errors:
        raise Exception("\n".join("{}".format(item) for item in type_errors))
    errors = []
    n_res = G.graph.get("n_res", len(max_res))
    c_res = critical_res if isinstance(critical_res, int) else 0

    if REF_callback is not None:
        errors.append(
            TypeError("Native windows cannot be combined with REF_callback")
        )
    if find_critical_res:
        errors.append(
            TypeError(
                "Native windows cannot be combined with find_critical_res=True"
                " (the critical resource index must be fixed)"
            )
        )
    if preprocess:
        LOG.warning(
            "preprocess=True is a no-op with native windows"
            " (prune_graph is always skipped, as with REF_callback)"
        )

    # --- simple interface: time_windows / service_times / time_res ---
    if service_times is not None and time_windows is None:
        errors.append(TypeError("service_times requires time_windows"))
    if time_windows is not None:
        if n_res < 2:
            errors.append(
                TypeError("time_windows requires n_res >= 2 "
                          "(res[0] critical + time resource)")
            )
        if not isinstance(time_res, int) or not 0 <= time_res < n_res:
            errors.append(
                TypeError("time_res must be an int in [0, n_res)")
            )
        elif time_res == c_res:
            errors.append(
                TypeError(
                    "time_res must differ from the critical resource index"
                    " ({})".format(c_res)
                )
            )
        else:
            if not isfinite(float(max_res[time_res])):
                errors.append(
                    TypeError(
                        "time_windows requires a finite max_res[{}] (the"
                        " rejection sentinel must exceed the horizon; with"
                        " inf, window-infeasible paths would be accepted)"
                        .format(time_res)
                    )
                )
            _check_window_dict(
                G, "time_windows", time_windows, max_res, time_res, errors
            )
        for name, s in (service_times or {}).items():
            if name not in G.nodes:
                errors.append(
                    TypeError(
                        "service_times key {} is not a node of G".format(name)
                    )
                )
            try:
                s_val = float(s)
            except (TypeError, ValueError):
                errors.append(
                    TypeError(
                        "service_times[{}] must be a number, got"
                        " {!r}".format(name, s)
                    )
                )
                continue
            if s_val < 0:
                errors.append(
                    TypeError(
                        "service_times must be >= 0 (node {})".format(name)
                    )
                )

    # --- general interface ---
    policies = {}
    general_res = set()
    for d in (node_windows, node_consumption, window_policy):
        if d is not None:
            general_res.update(d.keys())
    for r in general_res:
        if not isinstance(r, int) or not 0 <= r < n_res:
            errors.append(
                TypeError("Resource index {} out of range [0, n_res)".format(r))
            )
            continue
        if time_windows is not None and r == time_res:
            errors.append(
                TypeError(
                    "Resource {} configured both via time_windows/time_res"
                    " and via the general interface".format(r)
                )
            )
        policy = (window_policy or {}).get(r, "additive")
        if policy not in WINDOW_POLICIES:
            errors.append(
                TypeError(
                    "window_policy[{}] must be one of {}".format(
                        r, WINDOW_POLICIES
                    )
                )
            )
            continue
        policies[r] = policy
        # Inner containers must be dicts too (clear message, no AttributeError)
        windows_r = (node_windows or {}).get(r, None)
        if windows_r is not None and not isinstance(windows_r, Mapping):
            errors.append(
                TypeError(
                    "node_windows[{}] must be a dict {{node: (lb, ub)}},"
                    " got {}".format(r, type(windows_r).__name__)
                )
            )
            windows_r = None
        cons_r = (node_consumption or {}).get(r, {})
        if not isinstance(cons_r, Mapping):
            errors.append(
                TypeError(
                    "node_consumption[{}] must be a dict {{node: c}},"
                    " got {}".format(r, type(cons_r).__name__)
                )
            )
            cons_r = {}
        # Windows are only enforced by the window policies; with 'additive'
        # (the default!) they would be silently ignored -- reject instead of
        # returning window-violating paths without warning.
        if policy == "additive" and windows_r:
            errors.append(
                TypeError(
                    "node_windows[{r}] is set but window_policy[{r}] resolves"
                    " to 'additive' (the default): the windows would be"
                    " silently ignored. Set window_policy[{r}] to"
                    " 'window_wait' or 'window_hard'.".format(r=r)
                )
            )
        # Window policies need a finite horizon (rejection sentinel must
        # exceed max_res[r]; REF_bwd computes max_res[r] - ub)
        if policy in ("window_wait", "window_hard") and not isfinite(
            float(max_res[r])
        ):
            errors.append(
                TypeError(
                    "window_policy[{}] = '{}' requires a finite"
                    " max_res[{}]".format(r, policy, r)
                )
            )
        cons_vals = []
        for name, c in cons_r.items():
            if name not in G.nodes:
                errors.append(
                    TypeError(
                        "node_consumption[{}] key {} is not a node of"
                        " G".format(r, name)
                    )
                )
            try:
                cons_vals.append(float(c))
            except (TypeError, ValueError):
                errors.append(
                    TypeError(
                        "node_consumption[{}][{}] must be a number, got"
                        " {!r}".format(r, name, c)
                    )
                )
        if r == c_res:
            if policy != "additive":
                errors.append(
                    TypeError(
                        "Critical resource {} must keep policy"
                        " 'additive'".format(r)
                    )
                )
            if any(c != 0 for c in cons_vals):
                errors.append(
                    TypeError(
                        "Critical resource {} must have zero"
                        " node_consumption".format(r)
                    )
                )
        if windows_r is not None:
            _check_window_dict(
                G, "node_windows[{}]".format(r), windows_r, max_res, r, errors
            )
        if (
            policy == "additive"
            and any(c < 0 for c in cons_vals)
            and min_res[r] > 0
        ):
            LOG.warning(
                "Resource %s: negative node_consumption with min_res > 0;"
                " the final (non-soft) feasibility check may reject all"
                " labels. For visit flags use min_res[r] = -(max visits).",
                r,
            )

    # --- direction restrictions ---
    hard_res = [r for r, p in policies.items() if p == "window_hard"]
    if hard_res and direction != "forward":
        errors.append(
            TypeError(
                "window_policy 'window_hard' (resources {}) requires"
                " direction='forward' (backward/join extensions only track"
                " upper bounds)".format(hard_res)
            )
        )
    has_wait = time_windows is not None or any(
        p == "window_wait" for p in policies.values()
    )
    if has_wait and direction == "backward":
        LOG.warning(
            "direction='backward' with window resources: reported"
            " consumed_resources for window resources are on the reversed"
            " time axis (g = max_res[r] - latest start time)."
        )
    if errors:
        raise Exception("\n".join("{}".format(item) for item in errors))


def check_required_visits(
    G,
    direction,
    elementary,
    require_all_visits,
    required_nodes,
    max_res=None,
    min_res=None,
    critical_res=None,
    window_policy=None,
):
    """Validate the mandatory-visit arguments of :class:`cspy.BiDirectional`
    (``require_all_visits`` / ``required_nodes``).

    Parameters
    ----------
    G : object instance :class:`nx.Digraph()`

    direction : string
        preferred search direction. Only ``'forward'`` supports mandatory
        visits.

    elementary : bool
        whether the problem is elementary. Mandatory visits require ``True``.

    require_all_visits : bool
        whether every accepted path must visit all of ``required_nodes``.

    required_nodes : iterable of node labels or None
        the nodes every accepted path must visit. ``None`` means every node
        of ``G`` other than ``'Source'`` and ``'Sink'``.

    Returns
    -------
    list of node labels or None
        ``required_nodes`` materialised into a list, or ``None`` when it was
        ``None`` (or when ``require_all_visits`` is False). The caller must
        use the returned value and never the original argument: an iterable
        that can only be traversed once (a generator, ``map``, ``filter``,
        ``iter(...)``, a file or a ``csv.reader``) is consumed by this
        validation, and reading it a second time would silently yield an
        empty required set and hence disable the whole requirement.

    :raises: Raises an exception listing all violations found.
    """
    errors = []
    if not isinstance(require_all_visits, bool):
        raise Exception(
            "{}".format(
                TypeError(
                    "require_all_visits must be a bool, got {}".format(
                        type(require_all_visits).__name__
                    )
                )
            )
        )
    if not require_all_visits:
        if required_nodes is not None:
            raise Exception(
                "{}".format(
                    TypeError("required_nodes requires require_all_visits=True")
                )
            )
        return None

    if not (isinstance(elementary, bool) and elementary):
        errors.append(
            TypeError(
                "require_all_visits=True requires elementary=True: the"
                " dominance argument relies on elementary paths"
            )
        )
    if direction != "forward":
        errors.append(
            TypeError(
                "require_all_visits=True requires direction='forward' (got"
                " '{}'). The backward search and the label joining step cannot"
                " yet certify that all required nodes are visited; pass"
                " direction='forward'.".format(direction)
            )
        )
    # `names` is the single materialisation of `required_nodes`; it is what
    # the caller must use from here on (see the Returns section).
    names = None
    if required_nodes is not None:
        if isinstance(required_nodes, (str, bytes)):
            errors.append(
                TypeError(
                    "required_nodes must be an iterable of node labels, not a"
                    " string"
                )
            )
        elif not isinstance(required_nodes, Iterable):
            errors.append(
                TypeError(
                    "required_nodes must be an iterable of node labels, got"
                    " {}".format(type(required_nodes).__name__)
                )
            )
        else:
            names = list(required_nodes)
            if not names:
                errors.append(
                    TypeError(
                        "required_nodes is empty: with require_all_visits=True"
                        " an empty required set would make the requirement"
                        " vacuous and give a plain elementary shortest path"
                        " answer. Pass require_all_visits=False instead, or"
                        " required_nodes=None for every node other than"
                        " 'Source' and 'Sink'. Note that an iterable which can"
                        " only be traversed once (a generator, map, filter,"
                        " iter(...)) also lands here when it has already been"
                        " consumed."
                    )
                )
            for name in names:
                if name in ("Source", "Sink"):
                    errors.append(
                        TypeError(
                            "required_nodes must not contain 'Source' or"
                            " 'Sink' (they are on every path by construction)"
                        )
                    )
                elif name not in G.nodes:
                    errors.append(
                        TypeError(
                            "required_nodes entry {} is not a node of"
                            " G".format(name)
                        )
                    )
    else:
        if not (set(G.nodes) - {"Source", "Sink"}):
            errors.append(
                TypeError(
                    "require_all_visits=True but the graph has no node other"
                    " than 'Source' and 'Sink', so the requirement would be"
                    " vacuous. Pass require_all_visits=False instead."
                )
            )

    # --- interactions that weaken the dominance assumptions (warnings only) ---
    hard_res = [
        r for r, p in (window_policy or {}).items() if p == "window_hard"
    ]
    if hard_res:
        LOG.warning(
            "require_all_visits with window_policy 'window_hard' (resources"
            " %s): early arrivals are rejected instead of postponed, so the"
            " resource extension function is not monotone and dominance on"
            " those resources is not sound (a pre-existing property,"
            " independent of require_all_visits).",
            hard_res,
        )
    if min_res is not None:
        c_res = critical_res if isinstance(critical_res, int) else 0
        for r, value in enumerate(min_res):
            if r != c_res and value > 0:
                LOG.warning(
                    "min_res[%s] > 0 on a non-critical resource: the dominance"
                    " rule assumes that feasibility of non-critical resources"
                    " is decided by upper bounds only, so a lower bound on"
                    " such a resource can discard feasible paths and report"
                    " 'no solution' for an instance that has one. This is a"
                    " property of the standard dominance rule, not of"
                    " require_all_visits, but require_all_visits makes it"
                    " easier to hit. Model the lower bound on the critical"
                    " resource (critical_res) instead.",
                    r,
                )
    if errors:
        raise Exception("\n".join("{}".format(item) for item in errors))
    return names


def _check_window_dict(G, what, windows, max_res, r, errors):
    """Validate one {node: (lb, ub)} dictionary for resource ``r``."""
    for name, bounds in windows.items():
        if name not in G.nodes:
            errors.append(
                TypeError("{} key {} is not a node of G".format(what, name))
            )
            continue
        try:
            a, b = bounds
        except (TypeError, ValueError):
            errors.append(
                TypeError(
                    "{}[{}] must be a (lower, upper) pair".format(what, name)
                )
            )
            continue
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            errors.append(
                TypeError(
                    "{}[{}]: bounds must be numbers, got {!r}".format(
                        what, name, bounds
                    )
                )
            )
            continue
        if a > b:
            errors.append(
                TypeError(
                    "{}[{}]: lower bound {} > upper bound {}".format(
                        what, name, a, b
                    )
                )
            )
        if b > max_res[r]:
            LOG.warning(
                "%s[%s]: upper bound %s exceeds max_res[%s]=%s; the engine"
                " bound is the binding one (value used as given, no clamp).",
                what,
                name,
                b,
                r,
                max_res[r],
            )


def check_seed(seed, algorithm=None):
    """Check whether given seed can be used to seed a numpy.random.RandomState
    :return: numpy.random.RandomState (seeded if seed given)
    """
    if algorithm and "bidirectional" in algorithm:
        if not isinstance(seed, int):
            raise TypeError("{} cannot be used to seed".format(seed))
    if seed is None:
        return RandomState()
    elif isinstance(seed, int):
        return RandomState(seed)
    elif isinstance(seed, RandomState):
        return seed
    else:
        raise TypeError("{} cannot be used to seed".format(seed))


def check_time_limit_breached(start_time: float, time_limit: Union[int, None]) -> bool:
    """Check time limit.
    :return: True if difference between current time and start time
    exceeds the time limit. False otherwise.
    """
    if time_limit is not None:
        return time_limit - (time() - start_time) <= 0.0
    return False


def _check_res(G, max_res, min_res, direction, algorithm):
    if isinstance(max_res, list) and isinstance(min_res, list):
        if len(max_res) == len(min_res):
            if not (
                (
                    all(isinstance(i, (float, int)) for i in max_res)
                    and all(isinstance(i, (float, int)) for i in min_res)
                )
            ):
                raise TypeError("Elements of input lists must be numbers")
        else:
            raise TypeError("Input lists have to be equal length")
    else:
        raise TypeError("Inputs have to be lists")


def _check_direction(G, max_res, min_res, direction, algorithm):
    if direction not in ["forward", "backward", "both"]:
        raise TypeError("Input direction has to be 'forward', 'backward', or 'both'")


def _check_graph_attr(G, max_res, min_res, direction, algorithm):
    """Checks whether input graph has n_res attribute"""
    if isinstance(G, DiGraph):
        if "n_res" not in G.graph:
            raise TypeError("Input graph must have 'n_res' attribute")
    else:
        raise TypeError("Input must be a nx.Digraph()")


def _check_edge_attr(G, max_res, min_res, direction, algorithm):
    """Checks whether edges in input graph have res_cost attribute"""
    if any("res_cost" not in edge[2] for edge in G.edges(data=True)):
        raise TypeError("Input graph must have edges with 'res_cost' attribute")
    if any(len(edge[2]["res_cost"]) != G.graph["n_res"] for edge in G.edges(data=True)):
        raise TypeError(
            "Edges must have 'res_cost' attribute with length equal to 'n_res'"
        )
    if any(
        not len(edge[2]["res_cost"]) == len(max_res) == len(min_res)
        for edge in G.edges(data=True)
    ):
        raise TypeError(
            "Edges must have 'res_cost' attribute with length equal to"
            + " 'min_res' == 'max_res"
        )
    if (
        not all(isinstance(edge[2]["res_cost"], ndarray) for edge in G.edges(data=True))
        and "bidirectional" not in algorithm
    ):
        raise TypeError("The edge 'res_cost' attribute must be a numpy.array")


def _check_path(G, max_res, min_res, direction, algorithm):
    """Checks whether a 'Source' -> 'Sink' path exists and if there are
    negative edge cycles in the graph.
    Also covers nodes missing and other standard networkx exceptions"""
    try:
        if not has_path(G, "Source", "Sink"):
            raise NetworkXException("Disconnected Graph")
    except NetworkXException as e:
        raise Exception("An error occurred: {}".format(e))


def _check_REF(REF_callback):
    if REF_callback and not (
        callable(REF_callback.REF_fwd)
        or callable(REF_callback.REF_bwd)
        or callable(REF_callback.REF_join)
    ):
        raise TypeError("At least one REF function must be callable")
    if (
        REF_callback
        and callable(REF_callback.REF_fwd)
        and callable(REF_callback.REF_bwd)
        and not callable(REF_callback.REF_join)
    ):
        LOG.warning("Default criteria used for joining paths.")
    if (
        REF_callback
        and callable(REF_callback.REF_fwd)
        and not callable(REF_callback.REF_bwd)
        and not callable(REF_callback.REF_join)
    ):
        LOG.warning(
            "Forward REF set but not backward REF."
            " This may lead to unexpected results."
        )
        LOG.warning("Default criteria used for joining paths.")
