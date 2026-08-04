| OS     | C++ | Python | Dotnet |
|:-------|-----|--------|--------|
| Unix (linux + macos) | [![Status][cpp_unix_svg]][cpp_unix_link] | [![Status][python_unix_svg]][python_unix_link]| [![Status][dotnet_unix_svg]][dotnet_unix_link] |
| Windows  | [![Status][cpp_win_svg]][cpp_win_link] | [![Status][python_win_svg]][python_win_link] |[![Status][dotnet_win_svg]][dotnet_win_link] |


[cpp_unix_svg]: https://github.com/torressa/cspy/workflows/Cpp/badge.svg
[cpp_unix_link]: https://github.com/torressa/cspy/actions?query=workflow%3A%22Cpp%22
[python_unix_svg]: https://github.com/torressa/cspy/workflows/Python/badge.svg
[python_unix_link]: https://github.com/torressa/cspy/actions?query=workflow%3A%22Python%22
[dotnet_unix_svg]: https://github.com/torressa/cspy/workflows/Dotnet/badge.svg
[dotnet_unix_link]: https://github.com/torressa/cspy/actions?query=workflow%3A%22Dotnet%22

[cpp_win_svg]: https://github.com/torressa/cspy/workflows/Windows%20Cpp/badge.svg
[cpp_win_link]: https://github.com/torressa/cspy/actions?query=workflow%3A%22Windows+Cpp%22
[python_win_svg]: https://github.com/torressa/cspy/workflows/Windows%20Python/badge.svg
[python_win_link]: https://github.com/torressa/cspy/actions?query=workflow%3A%22Windows+Python%22
[dotnet_win_svg]: https://github.com/torressa/cspy/workflows/Windows%20Dotnet/badge.svg
[dotnet_win_link]: https://github.com/torressa/cspy/actions?query=workflow%3A%22Windows+Dotnet%22

[![PyPI version](https://badge.fury.io/py/cspy.svg)](https://badge.fury.io/py/cspy)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/c28f50e92dae4bcc921f1bd142370608)](https://www.codacy.com/app/torressa/cspy?utm_source=github.com&utm_medium=referral&utm_content=torressa/cspy&utm_campaign=Badge_Grade)
[![JOSS badge](https://joss.theoj.org/papers/25eda55801a528b982d03a6a61f7730d/status.svg)](https://joss.theoj.org/papers/25eda55801a528b982d03a6a61f7730d)


# cspy

A collection of algorithms for the (resource) Constrained Shortest Path (CSP) problem.

> **This is a fork.** [`Ebisaresu/cspy_for_TW`](https://github.com/Ebisaresu/cspy_for_TW)
> is a fork of [`torressa/cspy`](https://github.com/torressa/cspy) (MIT) which adds
> native C++ support for time windows, and more generally for per-node resource
> windows, to the bidirectional labeling algorithm, plus an option to require
> that every node of a given set is visited. See
> [Time windows (this fork)](#time-windows-this-fork).
>
> These additions are **not on PyPI**: `pip install cspy` installs the upstream
> package and does not contain them, so this fork has to be
> [built from source](#installing-this-fork). The badges above are the upstream
> repository's, and do not reflect the state of this fork.

Documentation [here](https://torressa.github.io/cspy/).

The CSP problem was popularised by [Inrich and Desaulniers (2005)](https://www.researchgate.net/publication/227142556_Shortest_Path_Problems_with_Resource_Constraints). It was initially introduced as a subproblem for the bus driver scheduling problem, and has since then widely studied in a variety of different settings including: the vehicle routing problem with time windows (VRPTW), the technician routing and scheduling problem, the capacitated arc-routing problem, on-demand transportation systems, and, airport ground movement; among others.

More generally, in the applied column generation framework, particularly in the scheduling related literature, the CSP problem is commonly employed to generate columns.

Therefore, this library is of interest to the operational research community, students and academics alike, that wish to solve an instance of the CSP problem.

## Algorithms

Currently, the exact and metaheuristic algorithms implemented include:

- [x] Bidirectional labeling algorithm with dynamic halfway point (exact) (also monodirectional) [Tilk et al. (2017)](https://www.sciencedirect.com/science/article/pii/S0377221717302035);
- [x] Heuristic Tabu search (metaheuristic);
- [x] Greedy elimination procedure (metaheuristic);
- [x] Greedy Randomised Adaptive Search Procedure (GRASP) (metaheuristic). Adapted from [Ferone et al. (2019)](https://www.tandfonline.com/doi/full/10.1080/10556788.2018.1548015);
- [x] Particle Swarm Optimization with combined Local and Global Expanding Neighborhood Topology (PSOLGENT) (metaheuristic) [Marinakis et al. (2017)](https://www.sciencedirect.com/science/article/pii/S0377221717302357).

Please see the [docs](https://cspy.readthedocs.io/en/latest/index.html) for individual algorithms Python or C++ API documentation, as well as some toy examples and further details.


- [Bidirectional and monodirectional algorithms](https://torressa.github.io/cspy/python_api/cspy.BiDirectional.html)
- [Heuristic Tabu Search](https://torressa.github.io/cspy/python_api/cspy.Tabu.html)
- [Greedy Elimination Procedure](https://torressa.github.io/cspy/python_api/cspy.GreedyElim.html)
- [GRASP](https://torressa.github.io/cspy/python_api/cspy.GRASP.html)
- [PSOLGENT](https://torressa.github.io/cspy/python_api/cspy.PSOLGENT.html)

## Getting Started

### Prerequisites

Conceptual background and input formatting is discussed in the [docs](https://torressa.github.io/cspy/how_to.html).

Module dependencies are:

- [NetworkX](https://networkx.github.io/documentation/stable/)
- [NumPy](https://docs.scipy.org/doc/numpy/reference/)

Note that [requirements.txt](requirements.txt) contains modules for development purposes.

### Installing

Installing the `cspy` package with `pip` should also install all the required packages. You can do this by running the following command in your terminal

```none
pip install cspy
```

or

```none
python3 -m pip install cspy
```

Note that this installs the upstream package from PyPI, which does **not** include
this fork's native time windows. Those require a
[source build](#installing-this-fork).

### Quick start

#### Python

```python
# Imports
from cspy import BiDirectional
from networkx import DiGraph
from numpy import array

max_res, min_res = [4, 20], [1, 0]
# Create a DiGraph
G = DiGraph(directed=True, n_res=2)
G.add_edge("Source", "A", res_cost=[1, 2], weight=0)
G.add_edge("A", "B", res_cost=[1, 0.3], weight=0)
G.add_edge("A", "C", res_cost=[1, 0.1], weight=0)
G.add_edge("B", "C", res_cost=[1, 3], weight=-10)
G.add_edge("B", "Sink", res_cost=[1, 2], weight=10)
G.add_edge("C", "Sink", res_cost=[1, 10], weight=0)

# init algorithm
bidirec = BiDirectional(G, max_res, min_res)

# Call and query attributes
bidirec.run()
print(bidirec.path)
print(bidirec.total_cost)
print(bidirec.consumed_resources)
```

For more details see the [Python API](https://cspy.readthedocs.io/en/latest/python_api/cspy.BiDirectional.html)

#### Cpp

```cpp
#include "bidirectional.h"

namespace bidirectional {

void wrap() {
  // Init
  const std::vector<double> max_res         = {4.0, 20.0};
  const std::vector<double> min_res         = {1.0, 0.0};
  const int                 number_vertices = 5;
  const int                 number_edges    = 5;
  auto                      bidirectional   = std::make_unique<BiDirectional>(
      number_vertices, number_edges, 0, 4, max_res, min_res);

  // Populate graph
  bidirectional->addNodes({0, 1, 2, 3, 4});
  bidirectional->addEdge(0, 1, 0.0, {1, 2});
  bidirectional->addEdge(1, 2, 0.0, {1, 0.3});
  bidirectional->addEdge(2, 3, -10.0, {1, 3});
  bidirectional->addEdge(2, 4, 10.0, {1, 2});
  bidirectional->addEdge(3, 4, 0.0, {1, 10});

  // Run and query attributes
  bidirectional->run();

  auto path = bidirectional->getPath();
  auto res  = bidirectional->getConsumedResources();
  auto cost = bidirectional->getTotalCost();
}

} // namespace bidirectional
```

#### C#

```csharp
DoubleVector max_res = new DoubleVector(new List<double>() {4.0, 20.0});
DoubleVector min_res = new DoubleVector(new List<double>() {0.0, 0.0});
int number_vertices = 5;
int number_edges = 5;
BiDirectionalCpp alg = new BiDirectionalCpp(number_vertices, number_edges, 0, 4, max_res, min_res);

// Populate graph
alg.addNodes(new IntVector(new List<int>() {0, 1, 2, 3, 4}));
alg.addEdge(0, 1, -1.0, new DoubleVector(new List<double>() {1, 2}));
alg.addEdge(1, 2, -1.0, new DoubleVector(new List<double>() {1, 0.3}));
alg.addEdge(2, 3, -10.0, new DoubleVector(new List<double>() {1, 3}));
alg.addEdge(2, 4, 10.0, new DoubleVector(new List<double>() {1, 2}));
alg.addEdge(3, 4, -1.0, new DoubleVector(new List<double>() {1, 10}));
alg.setDirection("forward");

// Run and query attributes
alg.run();

IntVector path = alg.getPath();
DoubleVector res = alg.getConsumedResources();
double cost = alg.getTotalCost();
```

### Examples

- [`vrpy`](https://github.com/Kuifje02/vrpy) : External vehicle routing framework which uses `cspy` to solve different variants of the vehicle routing problem using column generation. Particulatly, see  [`subproblem_cspy.py`](https://github.com/Kuifje02/vrpy/blob/master/vrpy/subproblem_cspy.py).
- [`jpath`](examples/jpath) : Simple example showing the necessary graph adptations and the use of custom resource extension functions.


## Time windows (this fork)

Everything in this section is specific to
[`Ebisaresu/cspy_for_TW`](https://github.com/Ebisaresu/cspy_for_TW), and is
released under the same MIT terms as the upstream code it extends (the original
[LICENSE.txt](LICENSE.txt) is kept unchanged). Please report bugs in these
additions on the
[fork's issue tracker](https://github.com/Ebisaresu/cspy_for_TW/issues): the
[Issues](#issues) and [Seeking Support](#seeking-support) sections below are
upstream's and refer to upstream `cspy`.

Upstream, time windows have to be written as a Python `REF_callback`, which is
called through the SWIG director on every label extension, and which needs
consistent backward and join REFs of its own before `direction="both"` can be used.
This fork adds a native (C++, non-director) resource extension function,
[`NodeWindowREF`](src/cc/node_window_ref.h). Each resource `r` carries a
per-node window `[lb_r(v), ub_r(v)]`, a per-node consumption `c_r(v)`, and one of
three propagation policies:

| Policy | Propagation along edge `(i, j)` | Use |
|:-------|---------------------------------|-----|
| `additive` (default) | `T + t_ij + c_r(j)`, `c_r(j)` added on arrival at the head | Backward compatible (identical to the default REF when `c_r` is 0). `c_r(v) = -1` gives a visit flag, `+1` a visit counter |
| `window_wait` | `max(lb_r(j), T + c_r(i) + t_ij)`, rejected if above `ub_r(j)`; `c_r(i)` added on departure from the tail | Time-like: early arrivals wait until `lb_r(j)` |
| `window_hard` | rejected whenever `T + c_r(i) + t_ij` falls outside `[lb_r(j), ub_r(j)]` | Resources where early arrival must be rejected instead of waiting (`direction="forward"` only) |

Time windows are then the special case of `window_wait` on the time resource with
`lb = a_v`, `ub = b_v` and `c_r(v) = s_v` (service time), giving the usual
`T_j = max(a_j, T_i + s_i + t_ij)` rejected when `T_j > b_j`. Only the resource
extension hooks (`REF_fwd`, `REF_bwd`, `REF_join`) are implemented: for the
window resources there are no changes to the dominance rules or to the
halfway-point logic, and `direction="both"` is supported. The existing
`REF_callback` mechanism and the rest of the API are unchanged.

The [mandatory visits](#mandatory-visits) option is the one feature that does
change the labeling core, because the rule it has to change *is* the dominance
rule. Every added code path is guarded by the option, which is off by default;
with it off the engine was checked to produce byte-identical output to the
unmodified build over 3222 solver runs. The other C++ change is a pair of
defensive null guards in `joinLabels()`
([`src/cc/bidirectional.cc`](src/cc/bidirectional.cc)), which fix an upstream
segfault reachable with `direction="both"` and a binding `min_res` on a
non-critical resource, independently of time windows.

### Installing this fork

This fork is not published on PyPI, so it has to be built from source. This needs
[CMake](https://cmake.org/download/), a standard C++ toolchain and
[SWIG](https://www.swig.org/), the last of which is missing from the upstream
requirements list under [Building](#building) below:

```none
cmake -S . -Bbuild -DBUILD_PYTHON=ON
cmake --build build
python3 -m pip install build/python/dist/cspy-*.whl
```

The full procedure, including how to rebuild after changing the C++ side, is in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md#7-rebuild-procedure).

### Quick start (time windows)

```python
# Imports
from cspy import BiDirectional
from networkx import DiGraph

# res[0] = edge counter (critical resource, stays additive), res[1] = time
max_res, min_res = [10, 20], [0, 0]
# Create a DiGraph
G = DiGraph(directed=True, n_res=2)
G.add_edge("Source", "A", res_cost=[1, 2], weight=0)
G.add_edge("Source", "B", res_cost=[1, 5], weight=0)
G.add_edge("A", "B", res_cost=[1, 3], weight=-10)
G.add_edge("B", "A", res_cost=[1, 3], weight=-10)
G.add_edge("A", "Sink", res_cost=[1, 2], weight=0)
G.add_edge("B", "Sink", res_cost=[1, 2], weight=0)

# init algorithm with time windows (a_v, b_v) and service times s_v
bidirec = BiDirectional(G, max_res, min_res, direction="forward", elementary=True,
                        time_windows={"A": (0, 4), "B": (8, 12)},
                        service_times={"A": 1, "B": 1})

# Call and query attributes
bidirec.run()
print(bidirec.path)
print(bidirec.total_cost)
print(bidirec.consumed_resources)
```

Output:

```none
['Source', 'A', 'B', 'Sink']
-10.0
[3.0, 11.0]
```

`Source -> B -> A -> Sink` is rejected because the label first waits at `B` until
`a_B = 8`, so service at `A` would start at `8 + 1 + 3 = 12 > b_A = 4`. On
`Source -> A -> B -> Sink` the same wait at `B` is feasible and the label reaches
the sink at time `11`. Nodes missing from `time_windows`/`service_times` default
to `(0, max_res[time_res])` and `0` respectively.

Two requirements are easy to miss: `res[0]` (the critical resource, index `0` by
default) must remain a monotone additive resource, e.g. an edge counter with
`res_cost[0] = 1` everywhere; and `max_res[r]` must be finite for any resource that
carries a window. Native windows cannot be combined with `REF_callback` or
`find_critical_res=True`, and `preprocess=True` becomes a no-op. Only
`direction="forward"` reports the actual service start times in
`consumed_resources`; the full list of caveats is in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md).

### General interface

`time_windows`/`service_times`/`time_res` are syntactic sugar for the general
arguments `node_windows={r: {node: (lb, ub)}}`, `node_consumption={r: {node: c_v}}`
and `window_policy={r: "additive"|"window_wait"|"window_hard"}` (plus
`window_eps`), which apply windows, node consumptions and policies to any
resource, including `additive` with `c_r(v) = -1` to express visit flags.

### Mandatory visits

`require_all_visits=True` restricts the search to `Source -> Sink` paths that
visit every node of `required_nodes` (default: every node other than `"Source"`
and `"Sink"`; a proper subset is also accepted), so that adding it to the time
windows above solves the Traveling Salesman Problem with Time Windows (TSPTW)
with a resource vector of length two — an edge counter and time — instead of one
visit indicator resource per customer. The standard dominance rule is unsound
once coverage is required — a cheaper label whose visited set is a proper subset
could prune the only label still able to cover the rest — so the option also
restricts dominance to labels that visit exactly the same required nodes, which
is why it needs `elementary=True` and `direction="forward"` and rejects anything
else with an explanatory error. Two things to keep in mind: an exact TSPTW solve
is exponential in the number of customers (on an Apple M1 with 8 GB, well under
a second up to about twelve customers, seconds to minutes at fourteen to
sixteen, impractical beyond about eighteen), and a run cut short by `time_limit`
returns the same degenerate `["Source"]` as a genuinely infeasible instance —
check the `termination_reason` property (see
[Stopping at a target value](#stopping-at-a-target-value)) to tell the two
apart. Worked examples, the soundness argument, the comparison against the
visit indicator encoding and the remaining caveats are in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md) Section 9.

### Stopping at a target value

The upstream `threshold` argument stops the search at the first complete path
of total cost at most the given value; this fork adds `threshold_strict=True`,
which stops only on a strictly smaller cost, so the value of a known incumbent
solution can be passed as the threshold to stop exactly when a true improvement
is found (for a maximisation objective, negate the edge weights and the
target). After `run()`, the new `termination_reason` property reports why the
search stopped — `'completed'`, `'threshold_reached'`, `'time_limit_reached'`
or `'no_feasible_path'` — which in particular distinguishes a proven-infeasible
instance from a search truncated before it found any complete path. Executed
examples, the exact meaning of each value and the full list of caveats are in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md) Section 10.

### Performance

Measured on ESPPRC-TW pricing instances with `elementary=True`. Against an
equivalent Python `REF_callback`, dropping the Python boundary is worth 1.3-1.9x
in forward search on small instances and only 1.0-1.1x on larger ones, where the
labeling core's dominance checks dominate the run time. The larger effect is
`direction="both"`, which the native REFs provide out of the box instead of
requiring hand-written backward and join REFs: on CVRPTW pricing with a tight
critical resource (n = 50, at most 4 customers per route), the same native run
takes 8.1 s with `direction="forward"` and 30 ms with `direction="both"`. With a
loose bound on the critical resource, `both` is instead several times slower than
`forward`, so the direction has to be chosen per instance. Full tables are in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md).

### Further reading

- [`tsptw_example/NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md) : guide to this native implementation, with the full API reference, REF formulas, rebuild steps, benchmarks and limitations.
- [`tsptw_example/TSPTW_GUIDE.md`](tsptw_example/TSPTW_GUIDE.md) : teaching guide on solving TSPTW exactly with a Python REF, and the modelling background (visit flags, dominance) both interfaces share.
- [`tsptw_example/tsptw_cspy.py`](tsptw_example/tsptw_cspy.py) : runnable TSPTW example.
- [`test/python/tests_native_time_windows.py`](test/python/tests_native_time_windows.py) : regression tests for the native interface.
- [`test/python/tests_termination_reason.py`](test/python/tests_termination_reason.py) : regression tests for `threshold_strict` and `termination_reason`.


## Building

### Docker

Using docker, docker-compose is the easiest way.

To run the tests first, clone the repository into a path in your machine `~/path/newfolder` by running

```none
git clone https://github.com/torressa/cspy.git ~/path/newfolder
```

#### Running the Cpp tests

```
cd ~/path/newfolder/tools/dev
./build
```

#### Running the Python tests

```
cd ~/path/newfolder/tools/dev
./build -c -p
```

### Locally

Requirements:

- [CMake](https://cmake.org/download/) (>=v3.14)
- Standard C++ toolchain
- Python (>=3.6)

Then use the wrapper [`Makefile`](Makefile) e.g. `make` in the root dir runs the unit tests

## License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

## Contributing

### Issues

If you find a bug or there are some improvements you'd like to see (e.g. more algorithms), please raise a new issue with a clear explanation.

### Contributing to the Software

When contributing to this repository, please first discuss the change you wish to make via an issue or email.
After that feel free to send a pull request.

#### Pull Request Process

- If necessary, please perform documentation updates where appropriate (e.g. README.md, docs and [CHANGELOG.md](CHANGELOG.md)).
- Increase the version numbers and reference the changes appropriately. Note that the versioning scheme used is based on [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
- Wait for approval for merging.

### Seeking Support

If you have a question or need help, feel free to raise an issue explaining it.

Alternatively, email me at `torressa at tutanota.com`.

## Citing

If you'd like to cite this package, please use the following bib format:

```none
@article{torressa2020,
  doi = {10.21105/joss.01655},
  url = {https://doi.org/10.21105/joss.01655},
  year = {2020},
  publisher = {The Open Journal},
  volume = {5},
  number = {49},
  pages = {1655},
  author = {{Torres Sanchez}, David},
  title = {cspy: A Python package with a collection of algorithms for the
    (Resource) Constrained Shortest Path problem},
  journal = {Journal of Open Source Software}
}
```
