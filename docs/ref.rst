Resource Extension Functions (REFs)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pre-requirements
****************

For the :class:`BiDirectional` algorithm, there is a number of assumptions required by definition (`Tilk et al 2017`_).

1. The first resource must be a monotone resource;
2. The resource extension functions are invertible.

For assumption 1, the resource can be either artificial,
such as the number of edges in the graph, or real, for example time.
This allows for the monotone resource to be comparable for the forward and backward directions.
In practice, this means, that ``res_cost[0]``, ``max_res[0]``,
and ``min_res[0]`` correspond to the monotone resource.

The bounds chosen for the monotone resource
(``max_res[0]`` and ``min_res[0]``), effectively represent the halfway points for the
algorithm. Hence unless ``max_res[0]`` :math`>` ``min_res[0]``, the searches will not reach
either end of the graph and the resulting path will be erroneous.
Additionally, occasionally, the resource limits do not allow for a feasible path to be found.
Some preprocessing routines have been implemented for the case of additive REFs.

For assumption 2, if resource extension functions are additive, these are clearly invertible.
However, when using custom resource extension functions (discussed below),
it is up to the user to define them appropriately!

Additive REFs
*************

Additive resource extension functions (REFs), are implemented by default in all the algorithms.
If left unchanged, this means that resources propagate in the following fashion.
Suppose we are considering extending partial path :math:`p_i`
(a path from the source to node :math:`i`), along edge :math:`(i, j)`.
Under the assumption that edge :math:`(i, j)` has a resource cost defined
(one for each of the resources);
the partial path :math:`p_j` (a path from the source to node :math:`j` passing
through node :math:`i`) will have a resource consumption equal to the total resource accumulated along :math:`p_i` plus the resource cost of edge :math:`(i, j)`.
If for instance, this resource consumption for a given resource exceeds the limit given in
As discussed above, the resource costs are defined by the user in the input graph.

Custom REFs
***********

Additionally, users can implement their own custom REFs.
This allows the modelling of more complex relationships and more realistic evolution
of resources.
However, it is up the users to ensure that the custom REFs are well defined,
it may be the case that the algorithm fails to find a feasible path, or gets stuck.

For theoretical information on what REFs are we refer you to the paper by `Inrich 2005`_.
For a brief overview with a practical implementation see any of the `examples`_.

Custom REF template
*******************

Practically, if you want more control on the propagation of resources,
some custom REFs can be defined according to the following template:

.. code-block:: python

        from cspy_tw import REFCallback

        class MyCallback(REFCallback):

            def REF_fwd(self, cumul_res, tail, head, edge_res, partial_path,
                        cumul_cost):
                res_new = list(cumul_res) # local copy
                return res_new

            def REF_bwd(self, cumul_res, tail, head, edge_res, partial_path,
                        cumul_cost):
                res_new = list(cumul_res) # local copy
                return res_new

            def REF_join(self, fwd_resources, bwd_resources, tail, head, edge_res):
                fwd_res = list(fwd_resources) # local copy
                return fwd_res


First, for forward and backward REFs, the overload requires several inputs:

1. ``cumulative_res``, a cumulative resource array,
2. Some edge attributes to consider for the extension of the current partial path:
  1. ``tail``, tail node (in str format)
  2. ``head``, head node (in str format)
  3. ``edge_res``, the resource consumption along the edge (in tuple format)
  4. ``partial_path``, the current partial path (in tuple format)
  5. ``cumul_cost``, the current partial path (float)

Second, for specifying label joining operations, ``REF_join`` requires several inputs

1. ``fwd_resources``, ``bwd_resources``, cumulative resources for the forward and backward labels being joined
2. And, similarly as before, some edge attributes (along the edge being joined):
  1. ``tail``, tail node (in str format)
  2. ``head``, head node (in str format)
  3. ``edge_res``, the resource consumption along the edge (in tuple format)

Depending on the application, you may choose not to use all of the arguments provided.

**IMPORTANT NOTE**

 1. the naming of the functions has to match (`REF_fwd`, `REF_bwd` and `REF_join`)
 2. so does the number of arguments (not necessarily the naming of the variables though)
 3. not all three have to be implemented. If for example, one is just using `direction="forward"`, then only `REF_fwd` would suffice. In the case of the callback being passed and only part of the functions implemented, the default implementation will used for the missing ones.


As a word of warning, it is up to the user to ensure the custom REF behaves appropriately.
Otherwise, you will most likely either stall the algorithms, get an exception saying that a resource
feasible path could not be found, or get a path that's not very meaningful.

A full skeleton with custom attributes could be as follows:

e.g.

.. code-block:: python

        from cspy_tw import BiDirectional, REFCallback

        class MyCallback(REFCallback):

            def __init__(self, arg1, arg2):
                # You can use custom arguments and save for later use
                REFCallback.__init__(self) # Init parent
                self._arg1: int = arg1
                self._arg2: bool = arg2

            def REF_fwd(self, cumul_res, tail, head, edge_res, partial_path,
                        cumul_cost):
                res_new = list(cumul_res) # local copy
                # do some operations on `res_new` maybe using `self._arg1/2`
                return res_new

            def REF_bwd(self, cumul_res, tail, head, edge_res, partial_path,
                        cumul_cost):
                res_new = list(cumul_res) # local copy
                # do some operations on `res_new` maybe using `self._arg1/2`
                return res_new

            def REF_join(self, fwd_resources, bwd_resources, tail, head, edge_res):
                fwd_res = list(fwd_resources) # local copy
                # do some operations on `res_new` maybe using `self._arg1/2`
                return fwd_res

        # Load G, max_res, min_res
        alg = BiDirectional(G, max_res, min_res, REF_callback=MyCallback(1, True))

For a simple example of custom REFs, please see the `unittest`_.

For more advanced examples, see the `examples`_ folder.

Native node windows (time windows without Python callbacks)
***********************************************************

For the common case of *node resource windows* -- most prominently time
windows with waiting and service times -- :class:`BiDirectional` ships a
native C++ REF (``NodeWindowREF``) so that no Python callback is invoked
inside the labelling loop. This matters e.g. for column generation pricing,
where the SWIG director round-trip of a Python ``REF_callback`` dominates the
run time.

Simple interface (time windows):

.. code-block:: python

        from cspy_tw import BiDirectional

        # res[0] = monotone critical resource (e.g. edge count,
        #          res_cost[0] = 1 on every edge)
        # res[1] = time; res_cost[1] = travel time
        alg = BiDirectional(
            G, max_res, min_res,
            time_windows={node: (a, b) for ...},   # original node names
            service_times={node: s for ...},       # optional, s >= 0
            time_res=1,                            # default
        )

The propagated value of the time resource is the *service start time* at each
node: ``T_head = max(a_head, T_tail + s_tail + t_edge)``, waiting until
``a_head`` on early arrival and rejecting when the start would exceed
``b_head``. The arrival-then-service convention (windows checked on arrival,
value = departure time) is feasibility-equivalent with the same parameters via
``D_v = T_v + s_v``; only the reported resource value differs by ``+s_v``.

General interface: per-resource policies via ``window_policy``
(``'additive'`` (default) / ``'window_wait'`` / ``'window_hard'``),
``node_windows={r: {node: (lb, ub)}}`` and
``node_consumption={r: {node: c}}``. ``additive`` adds the head node's
consumption on arrival (visit flags: ``c = -1`` with ``min_res[r] <= -1``);
window policies add the tail node's consumption on departure (service time).

Requirements and caveats:

1. The critical resource (``res[0]`` by default) must stay additive and
   monotone with zero node consumption -- as for any custom REF. Positive
   ``res_cost`` on every edge for the critical resource is recommended.
   ``find_critical_res=True`` cannot be combined with native windows.
   Note ``min_res[0]`` acts as the halfway-point floor of the bidirectional
   search, *not* as a lower bound at the Sink.
2. ``REF_callback`` and native windows are mutually exclusive; as with
   ``REF_callback``, graph pruning (``preprocess=True``) is skipped.
3. ``direction='both'`` and ``'backward'`` are natively supported for
   ``window_wait``. For ``direction='both'`` the reported window resource in
   ``consumed_resources`` is a feasibility surrogate (forward start time plus
   reversed backward value), not the service start time at the Sink; for
   ``direction='backward'`` it is on the reversed time axis. Use
   ``direction='forward'`` when the actual schedule value matters.
4. ``window_hard`` (reject early arrivals instead of waiting) requires
   ``direction='forward'``: backward extensions can only track upper bounds.
5. ``min_res[time_res] = 0`` is recommended: positive lower bounds on
   non-critical resources are only enforced at the final feasibility check,
   *and* when such a lower bound is binding the engine's dominance rule
   (component-wise ``<=``) may discard the label that would satisfy it --
   a suboptimal path or a spurious "no solution" can result.
6. ``max_res[r]`` must be *finite* for every resource with a window policy
   (enforced at construction): the internal rejection sentinel must exceed
   ``max_res[r]``, which is impossible with ``inf``.
7. Numerical tolerances are asymmetric: node-window comparisons use
   ``window_eps`` (default ``1e-9``), but the engine's global
   ``max_res``/``min_res`` feasibility checks are exact. A path within
   ``~window_eps`` of the horizon can therefore still be rejected by the
   engine -- borderline solutions are dropped on the safe (infeasible) side.
8. When no feasible path exists the result is *degenerate* and
   direction-dependent (``'forward'``: ``path == ['Source']`` with
   ``total_cost == 0.0``; ``'both'``: ``path is None``; ``'backward'``:
   ``path == ['Sink']``) -- pre-existing engine behaviour. Check
   ``path is None or len(path) <= 1 or path[0] != 'Source' or
   path[-1] != 'Sink'`` before interpreting ``total_cost`` (crucial in
   column generation, where ``0.0`` would be misread as "no improving
   column").


.. _jpath: https://github.com/torressa/cspy/tree/master/examples/jpath
.. _cgar: https://github.com/torressa/cspy/blob/master/examples/cgar/cgar.pdf
.. _Tilk et al 2017: https://www.sciencedirect.com/science/article/pii/S0377221717302035
.. _Inrich 2005: https://www.researchgate.net/publication/227142556_Shortest_Path_Problems_with_Resource_Constraints
.. _unittest: https://github.com/torressa/cspy/tree/master/test/python/tests_issue32.py
.. _Input Requirements: https://cspy.readthedocs.io/en/latest/how_to.html#input-requirements
.. _examples: https://github.com/torressa/cspy/tree/master/examples/
