# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [unreleased]

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
   leak into a later run's post-processing. Note that `run` remains
   single-shot per object (the search containers are not rebuilt, so a second
   call returns a degenerate result and a meaningless termination reason);
   this is now documented on `termination_reason` and in the C++ header.
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
from cspy import BiDirectional, REFCallback

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
