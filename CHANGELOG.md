# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v1.2.0]

### Changed

 - **NumPy is now an optional dependency.** `pip install cspy-tw` installs
   NetworkX and nothing else; NumPy arrives only with the new `heuristics`
   extra:

   ```none
   pip install "cspy-tw[heuristics]"
   ```

   Nothing on the `BiDirectional` code path uses NumPy. The two imports that
   made it a hard requirement were both in `cspy.checking`: an `ndarray`
   isinstance check that the labelling algorithm was already exempt from
   (`"bidirectional" not in algorithm`), and a `RandomState` used by
   `check_seed`, whose only caller is PSOLGENT — the seeding call in
   `BiDirectional` has been commented out for as long as this fork has
   existed. Both are now imported where they are used, and the `ndarray`
   branch tests the algorithm name first so the import is never reached for
   `BiDirectional`.

   `cspy_tw/__init__.py` resolves `Tabu`, `GreedyElim`, `PSOLGENT` and
   `GRASP` through a PEP 562 module `__getattr__` instead of importing them
   eagerly, so `import cspy_tw` no longer drags in the heuristics (and hence
   NumPy). `from cspy_tw import GRASP`, `cspy_tw.GRASP` and `dir(cspy_tw)`
   behave exactly as before; without NumPy installed, the first two raise an
   `ImportError` naming the extra rather than a bare "No module named
   'numpy'".

   Neither this fork nor upstream pins a version of either dependency, so
   this changes what gets *installed*, not what gets *upgraded*: `pip` has
   always accepted an existing NetworkX or NumPy and left it alone.

 - **The labelling core is much faster; no result changes.** Verified by a
   sweep of 120 random instances across all five dominance modes (mandatory
   visits + windows, windows only, plain elementary, two-cycle elimination,
   and `direction="both"`), byte-identical paths and costs against the
   previous build, plus the full Python (188) and C++ (61) test suites.
   Measured effects (`benchmarks/python/bench_labelling.py`): exact TSPTW via
   `require_all_visits` n=18 drops from 181 s to 0.42 s (432x) and n=20
   becomes practical at ~2.3 s; a pricing-shaped ESPPRC is 2.3x faster.
   Three changes, in decreasing order of effect:

   - Labels at a vertex are grouped by a one-word key derived from the
     required-visit mask. Under `require_all_visits` a label can only
     dominate, be dominated by, or equal a label with the same mask, so the
     quadratic dominance-and-duplicate pass now never visits the pairs that
     could not interact. Without the mandatory-visit mode every label lands
     in one group and the pass visits exactly what it always visited. The
     mask test is also hoisted to the top of `Label::checkDominance`, so the
     rare cross-group comparisons that still happen (via `fullDominance`)
     settle on one word-compare.
   - `Label::unreachable_nodes` is a sorted `std::vector<int>` instead of a
     `std::set<int>`. The subset test inside every elementary dominance check
     (`std::includes`) walks two contiguous arrays instead of chasing
     red-black-tree nodes -- tree iteration alone was ~30% of a
     pricing-shaped run -- and copying a label copies one buffer instead of
     rebuilding a tree.
   - `Label` is movable. The user-declared `~Label(){}` suppressed the
     implicit move operations, so every heap sift, erase-shift and vector
     reallocation deep-copied both vectors and the unreachable set of every
     label it touched; `labelling::operator==` also compares the two-entry
     resource vector before the potentially long paths.

### Fixed

 - `test/cc/test_issue89.cc` gave `max_res` a third entry that nothing read
   ({10.0, 100, 0} against two-resource edges and a two-entry `min_res`);
   the equal-length contract now enforced by the `BiDirectional` constructor
   (v1.1.1) rejects it, which is how the stray entry was noticed. The C++
   suite had not been run since that guard was added: it needs CMake, which
   the v1.1.1 verification environment lacked.

## [v1.1.1]

### Fixed

 - **No call through the documented Python interface can kill the interpreter
   any more.** Eight ways to do so were found and closed. Each one used to end
   the process outright -- an out-of-bounds access, a null dereference or a
   loop that never terminated -- which in a Jupyter notebook surfaces only as
   *"The kernel appears to have died. It will restart automatically."*, with
   no traceback naming the mistake. All eight now raise an ordinary Python
   exception saying what was wrong. Regression tests are in
   `test/python/tests_no_hard_crash.py`.

   - Reading `path`, `total_cost`, `consumed_resources` or calling
     `check_critical_res()` **before `run()`** dereferenced a null
     `best_label_`, which `init()` only allocates once `run()` is under way.
     All four now raise `RuntimeError`, in the engine
     (`BiDirectional::checkHasRun`) as well as in the wrapper, so bypassing
     the Python layer is no longer a way around the check.
     `termination_reason` was already safe and still answers `None`.
   - Calling **`run()` twice on the same object** with
     `direction='backward'` reached `processBwdLabel` with a
     default-constructed label -- null `params_ptr`, empty resource vector --
     and segfaulted. `run` was already documented as single-shot; it now
     enforces that and raises `RuntimeError` on the second call instead of
     returning a degenerate result. Re-executing a notebook cell was enough
     to trigger the crash. `processBwdLabel` also returns the dummy label
     rather than indexing through it.
   - An out-of-range **`critical_res`** was never validated, and it indexes
     `max_res`, `min_res` and every label's resource vector: an out-of-bounds
     *write*, so the process died at an unpredictable later point (SIGSEGV or
     SIGABRT from the corrupted heap, varying between runs of the same
     input). Now rejected by `cspy.checking.check_critical_res` and by
     `BiDirectional::setCriticalRes`. `True` is rejected too: `bool` is a
     subclass of `int` and would have silently selected index 1.
   - A custom **`REF_callback` returning the wrong number of resources**.
     Everything downstream indexes the returned vector positionally against
     `max_res`. A longer vector over-read `max_res`/`min_res`; an empty one
     segfaulted; and a short one was worse than either -- the feasibility
     loop is bounded by the vector's own length, so the critical resource
     stopped being checked, the search never terminated, and labels were
     allocated until the process was killed. `Label::extend` and
     `mergeLabels` now check the length and raise.
   - `DiGraph::getNodeIdFromUserId` dereferenced `vertices.end()` for an
     unknown node id and fed the garbage it read to
     `lemon::SmartDigraph::nodeFromId`; `addNodes` wrote past `vertices` when
     given more nodes than the constructor was told about, and left
     `source`/`sink` holding indeterminate ids when the graph contained
     neither. All three now throw `std::invalid_argument`.
   - An **empty `max_res` / `min_res`**, or two of different lengths.
     `cspy.checking.check` chose which validations to run by testing the two
     lists for truthiness, and an empty list is falsy -- so `max_res=[]`
     skipped every resource check there is and reached the engine, which
     indexes both by `critical_res` on the first label. The dispatch now
     tests `is not None`, `_check_res` rejects empty lists, and the
     `BiDirectional` C++ constructor rejects both an empty `max_res` and a
     length mismatch.
   - A user **`REF_callback` outliving the wrapper that held it**. The engine
     stores the callback as a raw pointer and does not own it, and the only
     reference was kept on the Python `BiDirectional` wrapper -- not on the
     C++ proxy whose lifetime actually matters. Extracting
     `alg.bidirectional_cpp` and dropping `alg` collected the SWIG director
     object while the labelling loop was still calling through its pointer.
     The callback is now also tied to the proxy
     (`_ref_callback_keepalive`), as the native window REF already was.
   - `labelling::halfwayCheck` compared paths with the three-iterator
     `std::equal`, reading `l.partial_path.size()` elements out of a
     `partial_path` that may be shorter. Now uses the four-iterator overload,
     which compares the lengths first.

 - **The extension module now carries the interpreter's ABI tag.**
   `swig_add_library` produced a bare `_pyBiDirectionalCpp.so` /
   `_pyBiDirectionalCpp.pyd`; it is now
   `_pyBiDirectionalCpp.cpython-312-x86_64-linux-gnu.so`,
   `_pyBiDirectionalCpp.cp312-win_amd64.pyd` and so on, taken from
   `sysconfig.get_config_var('EXT_SUFFIX')` of the Python being built against.

   The bare suffix is in importlib's `EXTENSION_SUFFIXES` for *every* CPython,
   so a module built against one version was silently loaded by another
   instead of being skipped. On Windows that is fatal rather than merely
   wrong: `src/cc/python/CMakeLists.txt` links the module against a specific
   `pythonXY.lib`, so the `.pyd` imports `python310.dll`, and loading it into
   a `python312.exe` pulls a second CPython runtime into the process. The
   module then initialises against an uninitialised interpreter state and the
   process dies with an access violation and no traceback — in Jupyter, "the
   kernel appears to have died". This is reachable whenever one environment's
   `site-packages` is visible to another interpreter (a `--user` install, a
   `PYTHONPATH` entry, a copied environment), which is easy to arrange by
   accident and gives no warning. With the tag present the same situation is
   an ordinary `ImportError` naming the module.
 - `DiGraph::all_resources_positive` was read uninitialised for a graph with
   no arcs, and `addEdge` assigned rather than accumulated it, so the last
   arc added decided it on its own and a negative resource on any earlier arc
   went unnoticed. It now starts `true` and accumulates. It gates only a
   warning about `elementary`, so the visible effect is limited to that
   warning.
 - `operator<<(std::ostream&, const Label&)` fell off the end of a
   value-returning function without returning the stream (undefined
   behaviour). It now returns `os`.
 - `Params::~Params` read `ref_callback = nullptr; delete ref_callback;`,
   which deletes a null pointer and so already did nothing. It is now
   `= default` with the ownership rule spelled out, because "fixing" it into
   a real `delete` would double-free the SWIG director object that Python is
   still holding.
 - `BiDirectional::checkCriticalRes` iterated over the label's resource
   vector while indexing `max_res`, which a custom `REF_callback` can make
   the longer of the two.

## [v1.1.0]

### Added

 - `BiDirectional(..., threshold_strict=True)`: make the `threshold`
   comparison strict, so the search stops only on a complete path with total
   cost strictly below the threshold (instead of the upstream `<=`). Passing
   the value of a known incumbent solution as `threshold` then stops the
   search exactly when a strictly better solution is found, and otherwise
   runs it to completion. Requires `threshold` to be set to a real number:
   `None`, `NaN` and non-numeric values are rejected by the new
   `cspy.checking.check_threshold_strict`, as is a non-`bool`
   `threshold_strict`. The default `False` keeps the upstream comparison
   unchanged.
 - `BiDirectional.termination_reason`: after `run()`, reports why the search
   stopped as one of `'completed'` (every generated label processed; this
   certifies optimality only when the dominance rule is sound for the
   resource extensions in use, which is why the value is not named
   `'optimal'`), `'threshold_reached'` (the first path meeting the threshold
   is returned; not necessarily the best found so far), `'time_limit_reached'`
   (a complete path found before the limit is still returned; a degenerate
   result means the instance status is unknown) and `'no_feasible_path'`
   (the exhausted search proved that no resource-feasible `Source`-`Sink`
   path exists). `None` before `run()`. This distinguishes a genuinely
   infeasible instance from a search truncated before its first complete
   path, which previously returned byte-identical degenerate results.
   Backed by the new C++ enumeration `TerminationReason` and
   `BiDirectional::getTerminationReason` (exposed to Python through SWIG);
   the recording is write-only and never read by the search, so the default
   behaviour is unchanged.
 - `BiDirectional(..., require_all_visits=True, required_nodes=...)`: restrict
   the search to `Source`-`Sink` paths visiting every node of a given set, so
   that the Traveling Salesman Problem with Time Windows (TSPTW) can be solved
   without encoding one visit indicator resource per customer. Requires
   `elementary=True` and `direction='forward'`; both are rejected with an
   explanatory error otherwise. New C++ entry point
   `BiDirectional::setRequiredNodes` (exposed to Python through SWIG).
 - Dominance is restricted, under that option only, to labels visiting exactly
   the same required nodes, and forward extensions into the sink are refused
   until every required node has been visited. The standard rule is unsound
   here: a cheaper label with a proper subset visited set can dominate and
   prune the only label that could still cover the rest.
 - `cspy.checking.check_required_visits` validating the new arguments. It
   materialises `required_nodes` once and returns the resulting list, which is
   what `BiDirectional` then uses, so that an iterable which can only be
   traversed once (a generator, `map`, `filter`, `iter(...)`) is handled
   correctly instead of silently yielding an empty required set and disabling
   the whole requirement.
 - An empty required set is rejected, in the Python layer and in
   `BiDirectional::setRequiredNodes`, instead of silently reducing the problem
   to a plain elementary shortest path problem.

Both new code paths are guarded by the option and are inactive by default; the
default behaviour was verified to be byte-identical to the previous build over
3222 solver runs.

### Fixed

 - `BiDirectional::run` now resets the internal early-termination flag at the
   start of each call, so a stale flag from a previous call can no longer
   leak into a later run's post-processing.
 - `BiDirectional` now keeps a reference to a user supplied `REF_callback`.
   The C++ side stores only a raw pointer, so passing a temporary
   (`BiDirectional(..., REF_callback=MyCallback())`) used to let the object be
   collected and crash the interpreter with a segmentation fault during
   `run()`. Pre-existing behaviour, unrelated to the mandatory-visit option.

## [v1.0.3]

### Fixed

 - Fixed #108: Non-elementary checks for 2-cycles (`i->j->i` are not allowed).
   Thanks @felizce

## [v1.0.2]

### Changed

 - Refactored Python and C++ unittests.
 - Added C# interface.
 - Moved documentation from readthedocs to github pages.
 - Non-elementary checks for 2-cycles (`i->j->i` are not allowed)

### Added
 - Logger using [`sdplog`](https://github.com/gabime/spdlog).

### Fixed
 - Issue: Bidirectional algorithm is not finding valid paths when using non-zero minimum resource values #89
 - Issue: Bidirectional not finding valid path when using negative resource
   consumption # 90
 - Issue: Dominance check for elementary paths #94

## [v1.0.1]

### Changed

 - Fix minimum number of nodes on path condition for `PSOLGENT`.
 - Force node sorting to start with "Source" and end with "Sink" in `PSOLGENT`.
 - Force inclusion of Source and Sink nodes in `PSOLGENT` paths.

 - Clean up:
  1. `BiDirectional` to use search objects again.
  2. `labelling.*` remove `LabelExtension` unified with `Params`.

### Added
 - Record `rand` value used to generate `PSOLGENT` paths from positions.
 - Make upper and lower bound of `PSOLGENT` initial positions optional arguments.
 - 2opt in `PSOLGENT` for better evaluation of solutions.

 - Critical resource as a parameter to `BiDirectional`
 - [EXPERIMENTAL] Add critical resource preprocessing attempt using longest paths

### Fixed
 - Issue #79

## [v1.0.0]

### Changed

 - Graph implementation replaced with [LEMON](https://lemon.cs.elte.hu/trac/lemon). This brings significant improvement.

### Added
 - Benchmarks against boost's r_c_shortest_paths (#65)

### Fixed
 - Issues #66, #68, #69, #72

## [v1.0.0-alpha]

### Changed

Rewrite of the bidirectional algorithm in C++ interfaced with Python using SWIG.

The algorithm improvements include:
 - Faster joining procedure (when `direction="both"`) with lower bounding and sorted labels
 - Bounds pruning using shortest path algorithm lower bounds and the primal bound obtained during the search (experimental).
 - Backwards incompatible change to do with custom REFs. Now, instead of specifying each function separately, you can implement them in class that inherits from `REFCallback`. and then pass them to the algorithm using the `REF_callback` parameter. This change applies to all algorithms.
 Note that:
   1. the naming of the functions has to match (`REF_fwd`, `REF_bwd` and `REF_join`)
   2. so does the number of arguments (not necessarily the naming of the variables though)
   3. not all three have to be implemented. If for example, one is just using `direction="forward"`, then only `REF_fwd` would suffice. In the case of the callback being passed and only part of the functions implemented, the default implementation will used for the missing ones.

e.g.
```python
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
```

### Added
 - Benchmarks (and comp results for BiDirectional) from Beasley and Christofides (1989)

### Fixed

 - [BiDirectional] Bug fix for non-elementary paths (#52)
 - [PSOLGENT] Bug fix for local search (#57)

### Removed
 - BiDirectional python implementation (can be found [here](https://github.com/torressa/cspy/tree/fba830cac02c1914670ca2def90c5c3447fd61e1))
 - BiDirectional `method="random"` see issues (hopefully only temporary).

## [v0.1.2] - 31/07/2020

### Added

- New paramenters: `time_limit` and `threshold`.
- Custom REF, backward incompatible change: additional argument for more flexibility. These are the current partial path and the accumulated cost. Note that these are optional and do not have to be used. However, a slight modificiation to the function has to be made, simply add `**kwargs` as well as the existing arguments.

## [v0.1.1] - 21/05/2020

### Changed
- BiDirectional:
  - Reverted backward REF as it is required for some problems.
  - Added REF join parameter that is required when joining forward and backward labels using custom REFs.
- Moved notes and examples from docstrings to the docs folder.
- Final JOSS paper changes

## [v0.1.0] - 14/04/2020

### Added

- BiDirectional:
  - Option to chose method for direction selection.
- [vrpy](https://github.com/Kuifje02/vrpy) submodule.

### Changed

- BiDirectional:
  - Label storage, divided into unprocessed, generated and non-dominated labels
  - Restricted join algorithm to non-dominated label
  - Changed backward resource extensions to avoid complex and computationally costly inversion. Additionally, it removes the requirement of an explicit backward REF.
  - Filtering for backward labels in join algorithm.
  - Cleaned up unused label operator overloads.
  - Removed costly comparison in `_propagate_label`.
  - Changed generated labels attributes from dict of deques to dict of int with count.

- Rework of path and algorithm attributes to avoid duplication
- Replaced `networkx.astar` algorithm with a procedure that finds a short simple
path using `networkx.shortest_simple_paths`.

### Removed

- Negative edge cycle assumption

## [v0.0.14] - 01/04/2020

### Removed

- Bidirectional
  - Removed use of halway point filtering for labels

## [v0.0.13] - 26/03/2020

### Added

- Included dev requirements file with new package for testing and examples requirements.

### Changed

- BiDirectional algorithm:
  - Resource based comparisons for label extension
  - Simplified attributes.
  - Implemented full path joining procedure from [Righini and Salani (2006)](https://www.sciencedirect.com/science/article/pii/S1572528606000417).
  - Rectified half-way check.
- parameterized some tests.

## [v0.0.12] - 14/03/2020

### Changed

- Documentation.
- BiDirectional algorithm:
  - **Removed** termination criteria.
  - Implemented half way procedure from [Righini and Salani (2006)](https://www.sciencedirect.com/science/article/pii/S1572528606000417) in `self._half_way` (Closes #21).
  - Changed label dominance to an equivalent but more elegant function.
  - Changed final label saving to account for when neither of two labels dominate.
- Backwards incompatible path, cost and total_resource feature.
- Preprocessing functions.

## [v0.0.11] - 06/03/2020

## Fixed

- BiDirectional algorithm: returning path with edge not in graph (Closes #17 :pray:).
- Heuristic used in Tabu for input in the networkx.astar_path algorithm (Closes #20).

### Changed

- Documentation.
- BiDirectional algorithm:

  - Final label comparisons.
  - Seed handling for testing.
  - Renamed variables to avoid confusion. - Avoiding getting stuck processing cycles of input graphs. - Ensuring that edges in path correspond to an edge in the input graph. - Avoid overwriting inputs (`max_res` and `min_res`). - Removed loops in `_get_next_label` and `_check_dominance` in favour of list comprehensions. - Use of `collections`. - logs for debugging in BiDirectional.
  - added `_save_current_best_label`.
  - Changed type of `self.finalLabel["direction"]` from list to `Label`.

- Re-organised. Moved `label.py` and `path.py` into `algorithms/`.

## [v0.0.10] - 09/02/2020

## Added

- PuLP example.

## Changed

- Documentation.
- Translated `examples/cgar` from gurobipy to pulp.
- CI build.

## [v0.0.9] - 25/12/2019

## Added

- Added example directory with column generation example.
- Check for negative cost cycles.

### Changed

- PSOLGENT seed handling.
- Improved documentation.
- unit tests structure.

## [v0.0.8] - 15/07/2019

### Added

- Generic resource extension functions options.

### Changed

- numpy.array integration.

## [v0.0.5] - 9/07/2019

### Added

- `PSOLGENT`.
- `GreedyElim` simple test.

### Changed

- Fixed prune_graph preprocessing routine.
- YAPF google style.

## [v0.0.3] - 9/07/2019

### Added

- `GRASP`.

### Changed

- Documentation updates.
- Updated README.
- Removed duplicate code in `tabu.py` and `greedy_elimination.py`.

## [v0.0.1] - 1/07/2019

### Added

- assertLogs tests for bidirectional algorithm classification.
- Personal MIT LICENSE.
- `GreedyElim` Procedure.

### Changed

- Documentation updates.
- Docstring modifications to include maths.
- Updated README.

[unreleased]: https://github.com/torressa/cspy/compare/v1.0.3...HEAD
[v1.0.3]: https://github.com/torressa/cspy/compare/v1.0.3...v1.0.3
[v1.0.2]: https://github.com/torressa/cspy/compare/v1.0.1...v1.0.2
[v1.0.1]: https://github.com/torressa/cspy/compare/v1.0.0...v1.0.1
[v1.0.0]: https://github.com/torressa/cspy/compare/v1.0.0-alpha...v1.0.0
[v1.0.0-alpha]: https://github.com/torressa/cspy/compare/v0.1.2...v1.0.0-alpha
[v0.1.2]: https://github.com/torressa/cspy/compare/v0.1.1...v0.1.2
[v0.1.1]: https://github.com/torressa/cspy/compare/v0.1.0...v0.1.1
[v0.1.0]: https://github.com/torressa/cspy/compare/v0.0.14...v0.1.0
[v0.0.14]: https://github.com/torressa/cspy/compare/v0.0.13...v0.0.14
[v0.0.13]: https://github.com/torressa/cspy/compare/v0.0.12...v0.0.13
[v0.0.12]: https://github.com/torressa/cspy/compare/v0.0.11...v0.0.12
[v0.0.11]: https://github.com/torressa/cspy/compare/v0.0.10...v0.0.11
[v0.0.11]: https://github.com/torressa/cspy/compare/v0.0.10...v0.0.11
[v0.0.10]: https://github.com/torressa/cspy/compare/v0.0.9...v0.0.10
[v0.0.9]: https://github.com/torressa/cspy/compare/v0.0.8...v0.0.9
[v0.0.8]: https://github.com/torressa/cspy/compare/0.0.5...v0.0.8
[v0.0.5]: https://github.com/torressa/cspy/compare/0.0.3...0.0.5
[v0.0.3]: https://github.com/torressa/cspy/compare/0.0.1...0.0.3
[v0.0.1]: https://github.com/torressa/cspy/releases/tag/v0.0.1
