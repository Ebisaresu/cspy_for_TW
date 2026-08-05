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
> [Time windows (this fork)](#5-time-windows-this-fork).
>
> This fork is distributed under its own names, so that it can be installed
> alongside the upstream package instead of overwriting it: the distribution
> name is **`cspy-tw`** and the importable package name is **`cspy_tw`**
> (`from cspy_tw import BiDirectional`). Elsewhere in this file, plain `cspy`
> refers to the algorithm library or to the upstream package, never to the
> import name of this fork.
>
> These additions are **not on PyPI**: `pip install cspy` installs the upstream
> package and does not contain them. This fork ships as a wheel attached to a
> [GitHub release](https://github.com/Ebisaresu/cspy_for_TW/releases), and can
> also be installed straight from its repository address or built from source;
> see [Installing](#installing). The badges above are the upstream repository's,
> and do not reflect the state of this fork.

Documentation [here](https://torressa.github.io/cspy/).

The CSP problem was popularised by [Irnich and Desaulniers (2005)](https://www.researchgate.net/publication/227142556_Shortest_Path_Problems_with_Resource_Constraints). It was initially introduced as a subproblem for the bus driver scheduling problem, and has since then widely studied in a variety of different settings including: the vehicle routing problem with time windows (VRPTW), the technician routing and scheduling problem, the capacitated arc-routing problem, on-demand transportation systems, and, airport ground movement; among others.

More generally, in the applied column generation framework, particularly in the scheduling related literature, the CSP problem is commonly employed to generate columns.

Therefore, this library is of interest to the operational research community, students and academics alike, that wish to solve an instance of the CSP problem.

## 1. The problem cspy solves

### 1.1 Informal statement

cspy looks for a **minimum-weight path from a fixed origin to a fixed
destination** in a directed graph whose arcs consume *resources*, subject to
bounds on the accumulated resource values. This is the **resource constrained
shortest path problem**, the problem the paragraphs above call the CSP
problem; the rest of this documentation abbreviates it **RCSP** rather than
CSP, because "CSP" is also the standard abbreviation of the unrelated
*constraint satisfaction problem*. A resource is any quantity that
accumulates along a path and is bounded — elapsed time, load carried, money
spent, or simply the number of arcs used.

Two conventions apply to every graph handed to cspy:

- the origin $o$ must be a vertex literally labelled `"Source"` and the
  destination $d$ a vertex literally labelled `"Sink"`;
- resource $0$ is the **critical resource** and must be monotone and additive
  (Section 2 explains why); throughout this documentation it is an **arc
  counter**, `res_cost[0] = 1` on every arc.

### 1.2 The model, stated once

**Data.** A digraph $(V, A)$ with $V = \{o\} \cup N \cup \{d\}$, where $N$ is
the set of customer vertices; a weight $w_{ij} \in \mathbb{R}$ on every arc
$(i,j) \in A$; a resource index set
$\mathcal{R} = \{0, \dots, n_{\mathrm{res}} - 1\}$ and a consumption
$t^{(r)}_{ij}$ for every arc and every resource; bounds
$q^{\min}_r \le q^{\max}_r$ for every resource.

**Decision variables.** $x_{ij} \in \{0,1\}$, equal to $1$ if and only if the
path uses arc $(i,j)$; $q_r$, the accumulated value of resource $r$.

$$
\min\ z \;=\; \sum_{(i,j) \in A} w_{ij}\, x_{ij}
$$

subject to

$$
\sum_{j\,:\,(o,j) \in A} x_{oj} \;=\; 1,
\qquad
\sum_{i\,:\,(i,d) \in A} x_{id} \;=\; 1,
$$

$$
\sum_{i\,:\,(i,k) \in A} x_{ik} \;=\; \sum_{j\,:\,(k,j) \in A} x_{kj}
\qquad \forall k \in N,
$$

$$
q_r \;=\; \sum_{(i,j) \in A} t^{(r)}_{ij}\, x_{ij},
\qquad
q^{\min}_r \;\le\; q_r \;\le\; q^{\max}_r
\qquad \forall r \in \mathcal{R},
$$

$$
x_{ij} \in \{0,1\} \qquad \forall (i,j) \in A .
$$

The first three lines say that $x$ is the incidence vector of a walk from $o$
to $d$, possibly together with cycles. Setting `elementary=True` adds "every
customer is entered at most once", which removes those cycles and turns the
problem into the **elementary shortest path problem with resource constraints
(ESPPRC)**, NP-hard even when every resource is additive.

Two points of precision, both settled in
[`tsptw_example/FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 2.2.
First, cspy checks the resource bounds *after every extension*, that is at
every vertex of the path and not only at its end; the two readings have the
same feasible set whenever every consumption is nonnegative and
$q^{\min}_r \le 0$, and the exact per-vertex form is stated there. Second,
$w_{ij}$ and $t^{(r)}_{ij}$ are **independent data**: the objective is
$\sum w_{ij} x_{ij}$ and never $\sum t^{(r)}_{ij} x_{ij}$.

### 1.3 Symbol-to-code correspondence

| Symbol | Meaning | Code |
|---|---|---|
| $V$, $A$ | vertex set, arc set | `G.nodes`, `G.edges` of a `networkx.DiGraph` |
| $o$, $d$ | origin, destination | the node labels `"Source"` and `"Sink"` |
| $n_{\mathrm{res}}$ | number of resources | `G.graph["n_res"]` |
| $w_{ij}$ | arc weight (the objective coefficient) | edge attribute `weight` |
| $t^{(r)}_{ij}$ | consumption of resource $r$ on arc $(i,j)$ | edge attribute `res_cost[r]` |
| $q^{\max}_r$ | upper bound on resource $r$ | `max_res[r]` |
| $q^{\min}_r$ | lower bound on resource $r$ | `min_res[r]` |
| $z$ | objective value | `total_cost` |

### 1.4 What `run()` gives back

| Attribute | Symbol | Meaning |
|---|---|---|
| `path` | $P$ | the returned path, as a list of the **original node labels** of `G` |
| `total_cost` | $z$ | the weight of that path, $\sum_{(i,j) \in A(P)} w_{ij}$ |
| `consumed_resources` | $q$ | the resource vector at the end of that path |
| `termination_reason` | — | why the search stopped (this fork; Section 5.8) |

When no complete path was accepted, **cspy returns a degenerate path rather
than raising**: `["Source"]` under `direction="forward"`, `None` under
`direction="both"`, `["Sink"]` under `direction="backward"`. Check the result
before using it.

### 1.5 Where the full treatment is

[`tsptw_example/FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Sections 1 and
2 give the notation, the glossary, the mixed integer program with the resource
variables written per vertex, the equivalent dynamic program, and the
dominance rule. Every symbol used anywhere in this repository's documentation
is defined there **normatively**: where this README or a guide repeats a
definition — as Sections 1.2 and 1.3 above do, so that the quick start can be
read on its own — that repetition is a convenience copy, and
`FORMULATIONS.md` is what settles any disagreement.

## 2. Algorithms

Currently, the exact and metaheuristic algorithms implemented include:

- [x] Bidirectional labeling algorithm with dynamic halfway point (exact) (also monodirectional) [Tilk et al. (2017)](https://www.sciencedirect.com/science/article/pii/S0377221717302035);
- [x] Heuristic Tabu search (metaheuristic);
- [x] Greedy elimination procedure (metaheuristic);
- [x] Greedy Randomised Adaptive Search Procedure (GRASP) (metaheuristic). Adapted from [Ferone et al. (2019)](https://www.tandfonline.com/doi/full/10.1080/10556788.2018.1548015);
- [x] Particle Swarm Optimization with combined Local and Global Expanding Neighborhood Topology (PSOLGENT) (metaheuristic) [Marinakis et al. (2017)](https://www.sciencedirect.com/science/article/pii/S0377221717302357).

Four terms from the first entry, each defined once in
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 1.6. A **labelling
algorithm** is a dynamic programming method that keeps several *labels* — a
label being a partial path together with the weight and the resource vector it
has accumulated — at each vertex, one per non-dominated combination, and
repeatedly extends them along outgoing arcs. A **bidirectional** search
extends labels forward from `"Source"` and backward from `"Sink"` and joins
them (`direction="both"`); a **monodirectional** search runs in one direction
only (`direction="forward"` or `"backward"`). The **halfway point** is the
value of the **critical resource** at which the bidirectional search stops
extending and starts joining, "dynamic" meaning that it is adjusted during the
search rather than fixed in advance. The critical resource is the one resource
(index $0$ by default, `critical_res`) that this cut-off is measured on, which
is why it has to be monotone and additive.

Please see the [docs](https://cspy.readthedocs.io/en/latest/index.html) for individual algorithms Python or C++ API documentation, as well as some toy examples and further details.


- [Bidirectional and monodirectional algorithms](https://torressa.github.io/cspy/python_api/cspy.BiDirectional.html)
- [Heuristic Tabu Search](https://torressa.github.io/cspy/python_api/cspy.Tabu.html)
- [Greedy Elimination Procedure](https://torressa.github.io/cspy/python_api/cspy.GreedyElim.html)
- [GRASP](https://torressa.github.io/cspy/python_api/cspy.GRASP.html)
- [PSOLGENT](https://torressa.github.io/cspy/python_api/cspy.PSOLGENT.html)

## 3. Getting Started

### Prerequisites

Conceptual background and input formatting is discussed in the [docs](https://torressa.github.io/cspy/how_to.html).

Module dependencies are:

- [NetworkX](https://networkx.github.io/documentation/stable/)
- [NumPy](https://docs.scipy.org/doc/numpy/reference/)

Both are installed automatically by `pip`. Note that
[`python/requirements.dev.txt`](python/requirements.dev.txt) contains modules for development purposes.

### Installing

This fork is **not** on the Python Package Index. `pip install cspy-tw` will not
find it, and `pip install cspy` installs the *upstream* package, which is a
different distribution and does not contain the native time windows. Use one of
the three routes below instead.

|     | Route | What the machine needs | When to use it |
|:----|:------|:-----------------------|:---------------|
| (a) | [A prebuilt wheel](#a-a-prebuilt-wheel-from-the-releases-page) | `pip`, nothing else | Normal use |
| (b) | [Installing from the repository address](#b-installing-directly-from-the-repository) | A C++ compiler | No wheel matches your machine |
| (c) | [A source build](#c-a-source-build) | CMake, SWIG, a C++ compiler | Working on the C++ side |

All three install the same thing under the same names: the distribution is
`cspy-tw` and the importable package is `cspy_tw`. Both names differ from the
upstream project on purpose, so that this fork and upstream `cspy` can be
installed side by side in one environment without either overwriting the other.
Write `from cspy_tw import BiDirectional`; `import cspy` keeps meaning the
upstream package, unchanged. Both may also be imported and used in the same
process: this fork links its C++ core into its own extension module and hides
every C++ symbol, so the dynamic loader cannot serve one version's code to the
other's objects.

#### (a) A prebuilt wheel from the releases page

A wheel is a prebuilt binary: it already contains the compiled C++ core, so
nothing is compiled on your machine and no build tools are needed. The
[releases page](https://github.com/Ebisaresu/cspy_for_TW/releases) carries one
wheel per combination below.

| Operating system | Architecture | Interpreter |
|:-----------------|:-------------|:------------|
| Linux | x86-64, AArch64 | CPython 3.9 to 3.13 |
| macOS 11 and later | Apple silicon, Intel | CPython 3.9 to 3.13 |
| Windows | x86-64 | CPython 3.9 to 3.13 |

Only CPython is covered; PyPy and free-threaded builds are not. Copy the address
of the wheel whose interpreter version and platform match yours, and hand it to
`pip`:

```none
python3 -m pip install https://github.com/Ebisaresu/cspy_for_TW/releases/download/<tag>/<wheel file name>
```

A wheel you have already downloaded works the same way:

```none
python3 -m pip install ./<wheel file name>
```

The file names read `cspy_tw-<version>-cp313-cp313-<platform>.whl`, where `cp313`
means CPython 3.13. If `pip` answers that the file `is not a supported wheel on
this platform`, the wheel does not match the interpreter it was given to: check
`python3 --version` and pick another one. If nothing on the page matches your
machine at all, take route (b).

#### (b) Installing directly from the repository

```none
python3 -m pip install git+https://github.com/Ebisaresu/cspy_for_TW.git
```

This compiles the C++ core on your machine, so a **C++ compiler** has to be
present: the Xcode command line tools on macOS, `build-essential` or the
distribution's equivalent on Linux, the Visual Studio build tools on Windows.
Everything else the build needs — CMake, Ninja and SWIG — is declared as a build
dependency in [`pyproject.toml`](pyproject.toml) and is fetched from the Python
Package Index into a temporary environment. Nothing of that is added to the
environment you install into, and neither `setuptools` nor `wheel` has to be
present beforehand, so a freshly created virtual environment is enough. While
configuring, CMake clones [LEMON](https://github.com/MultiFlow/LEMON) and
[spdlog](https://github.com/gabime/spdlog), so **git** has to be on the machine
as well, and the network has to reach more than the package index.

The command took about half a minute on an Apple silicon laptop; on a slower
machine, or one where CMake and Ninja have to be downloaded first, expect a few
minutes. A particular revision can be pinned by appending it to the address, for
example `git+https://github.com/Ebisaresu/cspy_for_TW.git@v1.1.0`.

#### (c) A source build

For working on the C++ side, or for building a wheel to carry elsewhere. Clone
first:

```none
git clone https://github.com/Ebisaresu/cspy_for_TW.git
cd cspy_for_TW
```

From here there are two ways on, and they produce the same wheel.

**Through the build backend**, which is the path route (b) takes, applied to a
working copy instead of a remote address. The requirements are exactly those of
route (b):

```none
python3 -m pip install .
```

**Through CMake directly**, which is the faster loop while editing C++, because
the build tree is kept and the compile is incremental:

```none
cmake -S . -Bbuild -DBUILD_PYTHON=ON
cmake --build build
python3 -m pip install --force-reinstall build/python/dist/cspy_tw-*.whl
```

This route uses the CMake (>=3.14), SWIG and C++ compiler **installed on the
machine** rather than the ones from the package index, so all three have to be
there. It also builds the wheel with `setup.py`, and installs `setuptools` and
`wheel` into the active Python environment at configure time if they are
missing. The rebuild loop, including what has to be rebuilt after a change to
the SWIG interface, is
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md) Appendix B; the rest of
the build system is [Building](#6-building) below.

#### Checking the installation

```console
$ python3 -c "import cspy_tw; print(cspy_tw.__version__)"
1.1.0
```

The upstream package answers `import cspy` and knows nothing about
`time_windows`, so the following also confirms that what got installed is this
fork:

```console
$ python3 -c "import inspect; from cspy_tw import BiDirectional; print('time_windows' in inspect.signature(BiDirectional.__init__).parameters)"
True
```

## 4. Quick start — Instance A

The three quick starts below all solve the same instance, called **Instance A**
throughout this documentation and defined in full in
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 2.7.

### 4.1 The instance

Five vertices $V = \{o, A, B, C, d\}$ — that is `"Source"`, `A`, `B`, `C`,
`"Sink"` — and six arcs. Two resources: $r = 0$ is the arc counter and
$r = 1$ is one generic consumable (elapsed time, fuel, anything that adds up).
There are no windows, no service times and no coverage requirement.

| arc $(i,j)$ | $t^{(0)}_{ij}$ = `res_cost[0]` | $t^{(1)}_{ij}$ = `res_cost[1]` | $w_{ij}$ = `weight` |
|---|---:|---:|---:|
| $(o, A)$ | 1 | 2 | 0 |
| $(A, B)$ | 1 | 0.3 | 0 |
| $(A, C)$ | 1 | 0.1 | 0 |
| $(B, C)$ | 1 | 3 | −10 |
| $(B, d)$ | 1 | 2 | 10 |
| $(C, d)$ | 1 | 10 | 0 |

Bounds: $q^{\max} = (4,\ 20)$ (`max_res = [4, 20]`, so at most four arcs and at
most 20 units of the consumable) and $q^{\min} = (1,\ 0)$
(`min_res = [1, 0]`).

**A warning about `min_res[0]`, since this is the first example a reader
meets.** `max_res` is what it looks like: an upper bound on each resource,
checked after every extension. `min_res` is **not** its mirror image. On the
critical resource (index 0) it is the *floor of the bidirectional
halfway point*, compared against the running value at every extension, so
setting `min_res[0] = 4` here would kill the very first label — whose arc
count is 1 — and return no path at all, rather than restricting the answer to
paths of four arcs. On a non-critical resource a strictly positive lower
bound is not checked during extensions at all, only at the destination. The
value $q^{\min}_0 = 1$ above is harmless only because the first extension
already reaches $q_0 = 1$. The full table of which bound is checked when is
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 4.6; the
recommended setting is $q^{\min} = 0$ on every resource unless you have read
it.

### 4.2 What the answer is, and why

The digraph is acyclic and there are exactly three $o$–$d$ paths:

| path | $q_0$ (arcs) | $q_1$ | $z$ | feasible |
|---|---:|---:|---:|---|
| $o \to A \to B \to d$ | 3 | 4.3 | 10 | yes |
| $o \to A \to C \to d$ | 3 | 12.1 | 0 | yes |
| $o \to A \to B \to C \to d$ | 4 | 15.3 | −10 | yes |

All three are feasible, so the optimum is the cheapest one: $z^{*} = -10$,
attained uniquely by $o \to A \to B \to C \to d$ with $q = (4,\ 15.3)$. It is
the only path that uses the single negative arc $(B, C)$, and it just fits:
its four arcs meet $q^{\max}_0 = 4$ exactly, so that bound is **binding** —
lowering it to 3 would make the optimum $z^{*} = 0$ on $o \to A \to C \to d$.
The bound $q^{\min}_0 = 1$ changes nothing here: the first extension out of
$o$ already has $q_0 = 1$, so no label is ever rejected by it. That is why it
is safe to leave in place, and not because "at least one arc" is a
restriction the three paths above happen to satisfy — see the warning in
Section 4.1 for what `min_res` on the critical resource actually does.

### 4.3 Python

`elementary` is left at its default `False` (the digraph is acyclic, so
forbidding repeated vertices would change nothing) and `direction` at its
default `"both"`.

```python
# Imports
from cspy_tw import BiDirectional
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

Output:

```none
['Source', 'A', 'B', 'C', 'Sink']
-10.0
[4.0, 15.3]
```

which is the path, the value $z^{*}$ and the resource vector $q$ predicted in
Section 4.2.

For more details see the [Python API](https://cspy.readthedocs.io/en/latest/python_api/cspy.BiDirectional.html)

### 4.4 Cpp

The same instance through the C++ API, where vertices are integers:
$0 = o$, $1 = A$, $2 = B$, $3 = C$, $4 = d$ (the third and fourth constructor
arguments are the origin and destination ids). `addEdge(i, j, w, res_cost)`
takes the weight before the consumption array.

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

Two differences from Section 4.3 are worth noticing before comparing outputs.
The snippet declares five arcs and omits $(A, C)$, that is $1 \to 3$; and the
result is queried through `getPath()`, `getTotalCost()` and
`getConsumedResources()` instead of attributes. Dropping $(A, C)$ leaves the
optimum unchanged — running the same five-arc graph through the Python
interface returns `['Source', 'A', 'B', 'C', 'Sink'] -10.0 [4.0, 15.3]`, as
Section 4.2 predicts, because the removed arc lies on a suboptimal path.

### 4.5 C#

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

This snippet is a **variant** of Instance A, not the same run: like the C++ one
it declares five arcs — omitting $(A, C)$, that is $1 \to 3$ — and on top of
that it uses `min_res = [0, 0]` instead of $(1,\ 0)$ and weight $-1$ on the
three arcs where the table of Section 4.1 has $0$.

Its optimum is therefore not the $-10$ of Section 4.2. Dropping $(A, C)$
leaves only two $o$–$d$ paths, and with the modified weights they cost
$-1 - 1 - 10 - 1 = -13$ on $o \to A \to B \to C \to d$ and
$-1 - 1 + 10 = 8$ on $o \to A \to B \to d$, so the variant's optimal value is
$\mathbf{-13}$, attained on the same path as Instance A and with the same
resource vector $q = (4,\ 15.3)$. Transcribing the snippet's five arcs and
its `min_res = [0, 0]` into the Python interface of Section 4.3 and running
it confirms this:

```none
['Source', 'A', 'B', 'C', 'Sink'] -13.0 [4.0, 15.3]
```

The C# code itself is left exactly as upstream wrote it and is not executed
by this documentation's verification, the C# bindings being out of scope for
the build (Section 5.3); it demonstrates the C# API, not Instance A.

### 4.6 Examples

- [`vrpy`](https://github.com/Kuifje02/vrpy) : External vehicle routing framework which uses `cspy` to solve different variants of the vehicle routing problem using column generation. Particularly, see  [`subproblem_cspy.py`](https://github.com/Kuifje02/vrpy/blob/master/vrpy/subproblem_cspy.py).
- [`jpath`](examples/jpath) : Simple example showing the necessary graph adaptations and the use of custom resource extension functions.


## 5. Time windows (this fork)

### 5.1 Scope and licence

Everything in this section is specific to
[`Ebisaresu/cspy_for_TW`](https://github.com/Ebisaresu/cspy_for_TW), and is
released under the same MIT terms as the upstream code it extends (the original
[LICENSE.txt](LICENSE.txt) is kept unchanged). Please report bugs in these
additions on the
[fork's issue tracker](https://github.com/Ebisaresu/cspy_for_TW/issues): the
[Issues](#issues) and [Seeking Support](#seeking-support) sections below are
upstream's and refer to upstream `cspy`.

### 5.2 What this fork adds, as changes to the model

**(a) Per-node resource windows.** Every resource $r$ and every vertex $v$ gain
a **window** $[lb_r(v),\ ub_r(v)]$, the interval within which the value of
resource $r$ must lie when a label arrives at $v$, and a **node consumption**
$c_r(v) \ge 0$, the quantity resource $r$ gains because of $v$. A **time
window** is the special case on the time resource: $[a_v,\ b_v]$ with
$c(v) = s_v$ the service time. The model is (P1) in
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 3; Sections 5.4 to
5.6 below are the working introduction to it. Upstream reaches the same
feasible set only by writing a **resource extension function (REF)** — the
function that maps the resource vector of a label, together with the arc being
traversed, to the resource vector after the extension — in Python and passing
it as `REF_callback`, and even then only in one direction: `direction="both"`
additionally requires hand-written backward and join REFs that agree with the
forward one. This fork supplies all three natively in C++
([`NodeWindowREF`](src/cc/node_window_ref.h)).

**(b) Mandatory visits.** The path must cover a **required set**
$R \subseteq N$: every vertex of $R$ has in-degree exactly $1$. See
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 4 and Section 5.7
below. No resource extension function can express this, because the rule that
has to change is the dominance rule, which lives inside the engine; the only
callback-level workaround is one visit indicator resource per required vertex
plus a visit counter, which lengthens the resource vector accordingly.

**(c) Early stopping with a reported reason.** The search may stop at the first
path strictly better than a known solution, and afterwards says why it stopped.
See [`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 6 and
Section 5.8 below. Upstream stops at cost $\le \theta$ only and reports
nothing, so an instance proven infeasible and a search truncated by
`time_limit` are indistinguishable from their results; both behaviours are
properties of the search loop, not of a resource extension function.

**(d) A repaired `bounds_pruning`.** This one changes no model — it fixes an
existing option that did not work. Upstream, `bounds_pruning=True` never
reached the C++ side (the wrapper forwarded the argument only when it was
`False`), so it was a silent no-op; underneath that, the preprocessing step
passed the two lower-bound directions swapped, so once the option did take
effect it pruned optimal labels. Both are fixed here and checked against
brute-force enumeration on 60 random instances in each of the three search
directions. The option remains `False` by default. See
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 2.6.

### 5.3 Installing this fork

This fork is not published on PyPI. The three ways to install it — a prebuilt
wheel from the releases page, `pip install git+https://...`, and a source build
— are set out under [Installing](#installing) above, together with what each one
requires of the machine. In short, and in decreasing order of convenience:

```none
python3 -m pip install https://github.com/Ebisaresu/cspy_for_TW/releases/download/<tag>/<wheel file name>
python3 -m pip install git+https://github.com/Ebisaresu/cspy_for_TW.git
cmake -S . -Bbuild -DBUILD_PYTHON=ON && cmake --build build && python3 -m pip install build/python/dist/cspy_tw-*.whl
```

Only the third of these needs [CMake](https://cmake.org/download/), a standard
C++ toolchain and [SWIG](https://www.swig.org/) to be installed on the machine;
the last of those is missing from the upstream requirements list under
[Building](#6-building) below. The rebuild procedure, for after a change to the
C++ side, is in [`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md),
Appendix B.

### 5.4 Time windows as a model — Instance B

The quick start of Section 5.5 solves **Instance B**, which is defined in full
in [`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 3.11 (weight
variant B-i; the customers called $1$ and $2$ there are the vertices named `A`
and `B` here).

**Vertices and arcs.** $V = \{o, A, B, d\}$ — that is `"Source"`, `A`, `B`,
`"Sink"` — with six arcs. Two resources: $r_{\mathrm{crit}} = 0$ is the arc
counter, and $r_{\mathrm{time}} = 1$ is time, so $t^{(1)}_{ij} = t_{ij}$ is the
travel time on arc $(i,j)$.

| arc $(i,j)$ | $t_{ij}$ = `res_cost[1]` | $w_{ij}$ = `weight` |
|---|---:|---:|
| $(o, A)$ | 2 | 0 |
| $(o, B)$ | 5 | 0 |
| $(A, B)$ | 3 | −10 |
| $(B, A)$ | 3 | −10 |
| $(A, d)$ | 2 | 0 |
| $(B, d)$ | 2 | 0 |

There is no arc $(o, d)$, no arc into $o$ and no arc out of $d$.

**Vertex data.** $a_v$ and $b_v$ are the earliest and the latest admissible
service start time at $v$, and $s_v$ is the service time. Only `A` and `B`
are listed in the code; $o$ and $d$ take the defaults $(0,\ q^{\max}_1) =
(0,\ 20)$ and $s = 0$.

| vertex | $a_v$ | $b_v$ | $s_v$ |
|---|---:|---:|---:|
| $o$ (`"Source"`) | 0 | 20 | 0 |
| $A$ | 0 | 4 | 1 |
| $B$ | 8 | 12 | 1 |
| $d$ (`"Sink"`) | 0 | 20 | 0 |

**Bounds.** $q^{\max} = (10,\ 20)$, so at most ten arcs and a horizon of
$H = 20$; $q^{\min} = (0,\ 0)$.

**The rule.** Under the `window_wait` policy the service start time propagates
as

$$
T_j \;=\; \max\bigl(a_j,\ T_i + s_i + t_{ij}\bigr),
\qquad \text{the extension being rejected when } T_j > b_j ,
$$

with $T_o = a_o = 0$: a vehicle arriving before $a_j$ waits, and one arriving
after $b_j$ is refused. Waiting is never charged — it changes feasibility
only, by pushing later values up against $b_j$ and $H$ — and the objective is
$\sum w_{ij} x_{ij}$, not $\sum t_{ij} x_{ij}$.

**The four elementary $o$–$d$ paths.**

| path | $T$ at each vertex | verdict | $z$ |
|---|---|---|---:|
| $o \to A \to d$ | $o{:}0,\ A{:}2,\ d{:}5$ | feasible | 0 |
| $o \to B \to d$ | $o{:}0,\ B{:}8,\ d{:}11$ | feasible (waits 3 units at $B$) | 0 |
| $o \to A \to B \to d$ | $o{:}0,\ A{:}2,\ B{:}8,\ d{:}11$ | feasible (waits 2 units at $B$) | −10 |
| $o \to B \to A \to d$ | $o{:}0,\ B{:}8,\ A{:}12$ | **infeasible** | −10 |

`Source -> B -> A -> Sink` is rejected because the label first waits at `B` until
`a_B = 8`, so service at `A` would start at `8 + 1 + 3 = 12 > b_A = 4`. On
`Source -> A -> B -> Sink` the same wait at `B` is feasible and the label reaches
the sink at time `11`.

So the optimum is $z^{*} = -10$ on $o \to A \to B \to d$, unique among the
feasible paths and reached with $q = (3,\ 11)$: three arcs, and time 11 at the
sink. The rejected path $o \to B \to A \to d$ carries the same weight $-10$, so
what decides between the two is the time windows and not the objective. Note
also that travel time and weight rank the paths differently — $o \to A \to d$
has the smallest total travel time and $o \to A \to B \to d$ the smallest
weight — which is why the objective has to be read off $w$ and never off $t$.

### 5.5 Quick start (time windows)

```python
# Imports
from cspy_tw import BiDirectional
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

— the optimal path, $z^{*}$ and $q$ of Section 5.4. Nodes missing from
`time_windows`/`service_times` default to `(0, max_res[time_res])` and `0`
respectively, `time_res` being the index of the time resource (default `1`; see
Section 5.6).

Two requirements are easy to miss: `res[0]` (the critical resource, index `0` by
default) must remain a monotone additive resource, e.g. an edge counter with
`res_cost[0] = 1` everywhere; and `max_res[r]` must be finite for any resource that
carries a window. Native windows cannot be combined with `REF_callback` or
`find_critical_res=True`, and `preprocess=True` becomes a no-op. Only
`direction="forward"` reports the actual service start times in
`consumed_resources`; the full list of caveats is in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md).

### 5.6 General interface

`time_windows`, `service_times` and `time_res` are syntactic sugar for the
general arguments, which apply a window, a node consumption and a propagation
policy to **any** resource:

| Symbol | Meaning | Argument | Notes |
|---|---|---|---|
| $lb_r(v),\ ub_r(v)$ | the **window** of resource $r$ at vertex $v$: the interval its value must lie in on arrival at $v$ | `node_windows={r: {v: (lb, ub)}}` | per resource, per vertex; keyed by the original node labels of `G` |
| $c_r(v) \ge 0$ | the **node consumption**: the quantity resource $r$ gains because of vertex $v$ | `node_consumption={r: {v: c}}` | when it is added depends on the policy, see the table below |
| $p_r$ | the **propagation policy** of resource $r$: how its value moves along an arc, and what makes an extension infeasible | `window_policy={r: "additive"\|"window_wait"\|"window_hard"}` | unspecified resources default to `"additive"` |
| $\varepsilon$ | the numerical tolerance of the window comparisons | `window_eps` | default `1e-9`; used in the window comparisons only, the engine's own bound checks being exact |
| $a_v,\ b_v$ | the **time window** of $v$: earliest and latest admissible service start time | `time_windows={v: (a, b)}` | shorthand for `node_windows[time_res]` under `window_wait` |
| $s_v$ | the **service time** at $v$, i.e. the node consumption of the time resource | `service_times={v: s}` | shorthand for `node_consumption[time_res]` |
| $r_{\mathrm{time}}$ | the index of the time resource | `time_res` | default `1`; must differ from `critical_res` |

Let a label sit at $i$ with resource value $q_r$ and be extended along $(i,j)$;
write $q'_r$ for the value afterwards. The three policies are:

| Policy | $q'_r$ | Rejected when | Use |
|:-------|--------|---------------|-----|
| `additive` (default) | $q_r + t^{(r)}_{ij} + c_r(j)$, the consumption of the **head** added on arrival | the engine's own check $q^{\min}_r \le q'_r \le q^{\max}_r$ fails | Backward compatible (identical to the default REF when $c_r$ is 0). $c_r(v) = -1$ gives a visit indicator, $+1$ a visit counter |
| `window_wait` | $\max\bigl(lb_r(j),\ q_r + c_r(i) + t^{(r)}_{ij}\bigr)$, the consumption of the **tail** added on departure | $q'_r > ub_r(j) + \varepsilon$ | Time-like: early arrivals wait until $lb_r(j)$ |
| `window_hard` | $q_r + c_r(i) + t^{(r)}_{ij}$, tail consumption as above | $q'_r < lb_r(j) - \varepsilon$ or $q'_r > ub_r(j) + \varepsilon$ | Resources where early arrival must be rejected instead of waited out (`direction="forward"` only) |

Time windows are then the special case of `window_wait` on the time resource
with $lb = a_v$, $ub = b_v$ and $c_r(v) = s_v$, which is exactly the recursion
of Section 5.4. Three consequences of this design deserve stating once:

- Under the two window policies the value is clamped up to $lb_r(o)$ at the
  origin, because a label starts with a resource vector of zeros.
- A resource extension function can only reject a label by returning a value
  outside the resource's own bound (a **sentinel**), which is why
  `max_res[r]` has to be finite for every resource carrying a window.
- `window_hard` is the one policy for which the standard dominance rule is
  **not** sound in general: under it a smaller resource value is no longer
  always at least as good, since arriving too early is itself a rejection, so
  the surviving label can be the one with no feasible completion. It is
  restricted to `direction="forward"`, and
  [`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 3.9 gives the
  counterexample and the conditions under which its answer is nevertheless
  right.

### 5.7 Mandatory visits

The model gains one constraint, (C1) of
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 4.1: the in-degree
of every vertex of a required set $R \subseteq N$ is exactly $1$, that is,
every required vertex is visited.

$$
\sum_{i\,:\,(i,k) \in A} x_{ik} \;=\; 1 \qquad \forall k \in R .
$$

`require_all_visits=True` restricts the search to `Source -> Sink` paths that
visit every node of `required_nodes` (default: every node other than `"Source"`
and `"Sink"`; a proper subset is also accepted), so that adding it to the time
windows above solves the traveling salesman problem with time windows (TSPTW)
with a resource vector of length two — an edge counter and time — instead of one
visit indicator resource per customer. The standard dominance rule is unsound
once coverage is required — a cheaper label whose visited set is a proper subset
could prune the only label still able to cover the rest — so the option also
restricts dominance to labels that visit exactly the same required nodes, which
is why it needs `elementary=True` and `direction="forward"` and rejects anything
else with an explanatory error; the soundness proof of that restriction is in
[`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 4.4. Two things to
keep in mind: an exact TSPTW solve
is exponential in the number of customers (on an Apple M1 with 8 GB, well under
a second up to about twelve customers, seconds to minutes at fourteen to
sixteen, impractical beyond about eighteen), and a run cut short by `time_limit`
returns the same degenerate `["Source"]` as a genuinely infeasible instance —
check the `termination_reason` property (see
[Stopping at a target value](#58-stopping-at-a-target-value)) to tell the two
apart. Worked examples, the comparison against the visit indicator encoding and
the remaining caveats are in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md), Section 6.

### 5.8 Stopping at a target value

The upstream `threshold` argument stops the search at the first complete path
of total cost at most the given value; this fork adds `threshold_strict=True`,
which stops only on a strictly smaller cost, so the value of a known incumbent
solution can be passed as the threshold to stop exactly when a true improvement
is found. After `run()`, the new `termination_reason` property reports why the
search stopped — `'completed'`, `'threshold_reached'`, `'time_limit_reached'`
or `'no_feasible_path'` — which in particular distinguishes a proven-infeasible
instance from a search truncated before it found any complete path.

A **maximisation** objective is handled by negating twice. Let
$\mathrm{rew}_{ij} \ge 0$ be a reward on arc $(i,j)$, let
$\mathrm{rew}(P) = \sum_{(i,j) \in A(P)} \mathrm{rew}_{ij}$ be the total
reward of a path $P$, and let $X$ be the reward target being asked for. Store
$w_{ij} = -\mathrm{rew}_{ij}$, so that $z(P) = -\mathrm{rew}(P)$, and
translate the target the same way, since

$$
\mathrm{rew}(P) > X \iff z(P) < -X ;
$$

pass `threshold = -X` with `threshold_strict=True`. The reported
`total_cost` is then the negated objective value, so report
$-\,$`total_cost` to the user
([`FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) Section 6.3). Executed
examples, the exact meaning of each value and the full list of caveats are in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md), Section 7.

### 5.9 Performance

The instance family is the pricing subproblem of a vehicle routing problem with
time windows, that is, the elementary shortest path problem with resource
constraints and time windows (ESPPRC-TW), with $n$ the number of customers.

All runs use `elementary=True`. Two separate effects, which are easy to
conflate and are therefore stated apart.

**Dropping the Python boundary**, comparing a native forward run against an
equivalent Python `REF_callback` forward run, is worth 1.7-1.9x on small
instances (n = 10 to 15), 1.3x at n = 20, and only 1.0-1.1x from n = 30 up,
where the labeling core's own dominance checks have grown to dominate the run
time.

**Unlocking `direction="both"`** is the larger effect. The native REFs supply
validated backward and join functions out of the box, where a Python
`REF_callback` would need hand-written ones that agree with the forward
function. On pricing for the capacitated vehicle routing problem with time
windows (CVRPTW) with a tight critical resource (n = 50 customers, at most 4
customers per route), the native run takes 7.4 s with `direction="forward"`
and 30 ms with `direction="both"`, a factor of **243x**. Measured against the
8.1 s of the *Python* forward run it replaces, the same 30 ms is **267x**;
both figures appear in the literature of this repository, and which baseline
is meant has to be said, since only the second folds in the language boundary
as well.

With a loose bound on the critical resource, `both` is instead 1.7-4.5x
slower than `forward`, so the direction has to be chosen per instance. Full
tables are in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md), Section 9.

### 5.10 Implementation notes

Upstream, time windows have to be written as a Python `REF_callback`, which is
called through the SWIG director — the mechanism that lets a C++ virtual call
dispatch into a Python subclass — on every label extension, and which needs
consistent backward and join REFs of its own before `direction="both"` can be
used. This fork adds a native (C++, non-director) resource extension function,
[`NodeWindowREF`](src/cc/node_window_ref.h), whose virtual calls stay inside
C++. Only the resource extension hooks (`REF_fwd`, `REF_bwd`, `REF_join`) are
implemented: for the window resources there are no changes to the dominance
rules or to the halfway-point logic, and `direction="both"` is supported. The
existing `REF_callback` mechanism and the rest of the API are unchanged.

The [mandatory visits](#57-mandatory-visits) option is the one feature that does
change what the labeling core decides, because the rule it has to change *is*
the dominance rule. Every added code path is guarded by the option, which is
off by default; with it off the engine was checked to produce byte-identical
output to the unmodified build over 3222 solver runs.

The remaining changes to
[`src/cc/bidirectional.cc`](src/cc/bidirectional.cc) — about 155 lines in
total across all of them — are these three, none of which alters the search
on a default-configured run:

- the **early-stopping bookkeeping** of [Section 5.8](#58-stopping-at-a-target-value):
  a `termination_reason_` field, the four places that set it, and the strict
  threshold comparison. It records which exit the existing loop took;
- a pair of defensive **null guards** in `joinLabels()`, which fix an upstream
  segfault reachable with `direction="both"` and a binding `min_res` on a
  non-critical resource, independently of time windows;
- the **`bounds_pruning` repair** of Section 5.2 (d), one line in
  `runPreprocessing` swapping the two lower-bound directions back, plus one
  line in the Python wrapper so the option reaches C++ at all.

The implementation-level vocabulary used here — SWIG directors, ownership,
bit sets, the layout of the labelling core — is defined in
[`NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md), Appendix A.

### 5.11 Further reading

- [`tsptw_example/FORMULATIONS.md`](tsptw_example/FORMULATIONS.md) : the canonical formulations, notation and glossary that the other two guides refer to; every symbol and every term used in this repository is defined there.
- [`tsptw_example/NATIVE_TW_GUIDE.md`](tsptw_example/NATIVE_TW_GUIDE.md) : guide to this native implementation, with the full API reference, REF formulas, rebuild steps, benchmarks and limitations.
- [`tsptw_example/TSPTW_GUIDE.md`](tsptw_example/TSPTW_GUIDE.md) : teaching guide on solving the traveling salesman problem with time windows exactly with a Python REF, and the modelling background (visit indicators, dominance) both interfaces share.
- [`tsptw_example/tsptw_cspy.py`](tsptw_example/tsptw_cspy.py) : runnable TSPTW example.
- [`test/python/tests_native_time_windows.py`](test/python/tests_native_time_windows.py) : regression tests for the native interface.
- [`test/python/tests_termination_reason.py`](test/python/tests_termination_reason.py) : regression tests for `threshold_strict` and `termination_reason`.
- [`test/python/tests_bounds_pruning.py`](test/python/tests_bounds_pruning.py) : regression tests for the repaired `bounds_pruning`, one per bug (option forwarding, and agreement with brute force).


## 6. Building

This section is about the build system itself. To *install* the package, see
[Installing](#installing) — route (c) there is the short form of what follows.

There are two entry points into the same build, and both end in a wheel that
contains the extension module and the shared library it loads:

- **The build backend.** `pip install .` reads
  [`pyproject.toml`](pyproject.toml), which hands the work to
  [scikit-build-core](https://scikit-build-core.readthedocs.io/). That backend
  configures this project's `CMakeLists.txt`, builds it, and packages what the
  CMake install rules stage. CMake, Ninja and SWIG come from the Python Package
  Index, so a C++ compiler and git are all the machine has to supply. This is
  the path a user takes, and the one the wheels on the releases page are built
  through.
- **CMake on its own.** `cmake -S . -Bbuild -DBUILD_PYTHON=ON` followed by
  `cmake --build build` writes the wheel to `build/python/dist/`. This path uses
  the machine's own CMake, SWIG and compiler, keeps its build tree between runs,
  and is what the sections below describe.

The two do not collide: the backend puts its build tree in `build/<wheel tag>/`,
one per interpreter, and skips the `setup.py` step that the plain CMake path
uses.

### Docker

Using docker, docker-compose is the easiest way.

To run the tests first, clone the repository into a path in your machine `~/path/newfolder` by running

```none
git clone https://github.com/Ebisaresu/cspy_for_TW.git ~/path/newfolder
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
- [SWIG](https://www.swig.org/) (>=v4 is what this fork is developed against)
- Python (>=3.9 for this fork; the upstream project states >=3.6)

Then use the wrapper [`Makefile`](Makefile) e.g. `make` in the root dir runs the unit tests

Only the CMake path needs SWIG and CMake to be installed; through the build
backend both arrive from the Python Package Index. The Python test suite is run
from `test/python` with `python3 -m unittest discover -p "tests_*.py"`; it
reports `Ran 162 tests ... FAILED (errors=4, skipped=1)`, the four errors being
a pre-existing incompatibility between the particle swarm algorithm and NumPy 2
that has nothing to do with this fork's additions.

## 7. License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.

## 8. Contributing

### Issues

If you find a bug or there are some improvements you'd like to see (e.g. more algorithms), please raise a new issue with a clear explanation.

### Contributing to the Software

When contributing to this repository, please first discuss the change you wish to make via an issue or email.
After that feel free to send a pull request.

#### Pull Request Process

- If necessary, please perform documentation updates where appropriate (e.g. README.md, docs and [CHANGELOG.md](CHANGELOG.md)).
- Increase the version numbers and reference the changes appropriately. Note that the versioning scheme used is based on [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
- Wait for approval for merging.

### Continuous integration and releases (this fork)

Two workflows, and neither of them runs on a push to a branch.

**[`ci.yml`](.github/workflows/ci.yml)** runs on every pull request, and when
started by hand from the Actions tab. It builds the wheel through the build
backend — the same path a user takes with `pip install git+https://...`, so that
a break in the packaging shows up here rather than in a bug report — installs
it, and runs the Python test suite through
[`.github/scripts/run_tests.py`](.github/scripts/run_tests.py). That script
deselects, by name, the four tests that fail because of the pre-existing
PSOLGENT bug, and fails if any of those four names ever stops existing, so the
exclusion cannot outlive the bug. A second job rejects any workflow that would
publish to a package index.

**[`wheels.yml`](.github/workflows/wheels.yml)** builds the wheels that go on
the releases page, using
[cibuildwheel](https://cibuildwheel.pypa.io/) on five runners (Linux x86-64 and
AArch64, macOS Apple silicon and Intel, Windows x86-64) for CPython 3.9 to 3.13.
A short job reads
[`pyproject.toml`](pyproject.toml) first, so that a one-line mistake there costs
a few seconds rather than half an hour of build time across five runners. Every
wheel is then installed and tested from outside the source tree before it is
kept, which is what catches a bundled shared library the loader cannot find.
There are exactly two ways to start it:

- **Push a version tag.** A tag matching `v*` builds every wheel and attaches
  the lot to the release of that name. If no release by that name exists yet,
  one is created **as a draft**, so nothing becomes publicly visible until a
  human presses publish. To cut version 1.2.0:

  ```none
  # bump project(... VERSION 1.2.0 ...) in CMakeLists.txt first: it is the only
  # place the version is written, and both the wheel metadata and pyproject.toml
  # read it from there
  git tag v1.2.0
  git push origin v1.2.0
  ```

  Then edit the draft release's notes and publish it. Nothing checks that the
  tag and the version in `CMakeLists.txt` agree, so a tag pushed without the
  bump produces wheels carrying the previous version number.

- **Run it by hand** from the Actions tab, choosing "Wheels" and pressing "Run
  workflow". Two inputs, both optional:
  - *build-selector* — a cibuildwheel build selector. Empty builds CPython 3.9
    to 3.13; `cp313-*` builds one interpreter, which is the quick way to check a
    change to the build without spending half an hour.
  - *attach-to-release* — the tag of a release to attach the wheels to. **Leave
    it empty** and the wheels stay as build artifacts of the run and no release
    is touched at all.

Nothing in either workflow uploads to PyPI, to NuGet, or to any other package
index; the sole distribution channel of this fork is a GitHub release. The
upstream workflows that did publish were deleted, and the
`no-package-index-publishing` job of `ci.yml` fails the build if a step that
could publish reappears.

### Seeking Support

If you have a question or need help, feel free to raise an issue explaining it.

Alternatively, email me at `torressa at tutanota.com`.

## 9. Citing

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
