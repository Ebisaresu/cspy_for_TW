`cspy-tw` is a fork of [`cspy`](https://github.com/torressa/cspy) that adds
native C++ support for time windows to the bidirectional labelling algorithm,
along with two things that are needed to use them: a way to require that every
customer is visited, and a way to stop the search once a solution is good
enough.

This is the first release. It is a separate distribution from upstream `cspy`
and imports under a different name, so the two can be installed side by side.

## Installing

Wheels are attached below for CPython 3.9 to 3.13 on Linux (x86-64 and
AArch64), macOS (Intel and Apple Silicon) and Windows (x64). Nothing has to be
compiled and no build tools are needed — pick the file matching your Python
version and platform:

```
pip install https://github.com/Ebisaresu/cspy_for_TW/releases/download/v1.1.0/cspy_tw-1.1.0-cp313-cp313-win_amd64.whl
```

To build from source instead, which needs a C++ compiler:

```
pip install git+https://github.com/Ebisaresu/cspy_for_TW.git
```

Either way the import name is `cspy_tw`:

```python
from cspy_tw import BiDirectional
```

## What this adds

**Time windows, computed in C++.** Each node can carry a window and a service
time, passed as `time_windows={node: (a, b)}` and `service_times={node: s}`.
Arriving early waits; arriving after the deadline is rejected. Time windows are
the special case of a more general mechanism — a window and a consumption per
node per resource, under one of three policies — so the same machinery covers
resources that are not time. Upstream this has to be written as a Python
callback that the search calls back into on every label extension; here the
propagation stays inside C++, and `direction="both"` works without writing
backward and join functions by hand.

**Requiring every visit.** `require_all_visits=True` restricts the search to
paths that visit every node, which turns the solver into an exact method for
the travelling salesman problem with time windows. This is not just a filter on
the answer: the usual dominance rule discards a label that visited fewer nodes
but is cheaper, which throws away the only label that could still be completed
into a full tour, so the rule is tightened alongside it.

**Stopping early.** `threshold_strict=True` makes the existing `threshold` stop
the search on a solution strictly better than the value given, rather than one
merely as good, so passing the value of a solution you already have stops on a
genuine improvement. `termination_reason` then reports why the search stopped —
`completed`, `threshold_reached`, `time_limit_reached` or `no_feasible_path` —
which also separates a genuinely infeasible instance from a search that was cut
short before it found anything. For a maximisation problem, negate the weights
and the threshold.

**Fixes carried in this release.** `bounds_pruning` could not be switched on
from Python, and pruned optimal solutions when it was. `joinLabels` dereferenced
a label that is never set when no feasible path reaches a vertex, which crashed
`direction="both"` under a binding `min_res`. A `REF_callback` passed as a
temporary was collected while C++ still held a pointer to it.

## A worked example

Two customers, `A` and `B`, reachable from `Source` and both leading to `Sink`.
Travel times are on the arcs, and the weight is what is minimised — in a column
generation subproblem it would be the reduced cost, which is why several of
these are negative.

| arc | travel time | weight |  | node | window | service time |
|---|---:|---:|---|---|---|---:|
| `Source → A` | 2 | −8 |  | `A` | [0, 4] | 1 |
| `Source → B` | 5 | −1 |  | `B` | [8, 12] | 1 |
| `A → B` | 3 | +5 |  | | | |
| `B → A` | 3 | −20 |  | | | |
| `A → Sink` | 2 | 0 |  | | | |
| `B → Sink` | 2 | 0 |  | | | |

`B → A` is by far the cheapest arc, but a label reaching `B` at time 8 arrives
at `A` at 8 + 1 + 3 = 12, past the deadline of 4, so the window rules that route
out. Of what is left, skipping `B` entirely is cheapest, and visiting both costs
more.

```python
import networkx as nx
import numpy as np
from cspy_tw import BiDirectional

ARCS = [("Source", "A", 2, -8.0), ("Source", "B", 5, -1.0),
        ("A", "B", 3, 5.0), ("B", "A", 3, -20.0),
        ("A", "Sink", 2, 0.0), ("B", "Sink", 2, 0.0)]
WINDOWS = {"A": (0.0, 4.0), "B": (8.0, 12.0)}
SERVICE = {"A": 1.0, "B": 1.0}

# res[0] counts arcs, which is the monotone resource the algorithm needs.
# res[1] carries time, and is the one the windows apply to.
G = nx.DiGraph(n_res=2)
for tail, head, travel, weight in ARCS:
    G.add_edge(tail, head, res_cost=np.array([1.0, float(travel)]), weight=weight)

common = dict(direction="forward", elementary=True,
              time_windows=WINDOWS, service_times=SERVICE)

for label, extra in [("cheapest path         ", {}),
                     ("every customer visited", {"require_all_visits": True}),
                     ("stop below -5         ", {"threshold": -5.0,
                                                 "threshold_strict": True})]:
    alg = BiDirectional(G, [10.0, 20.0], [0.0, 0.0], **common, **extra)
    alg.run()
    print(f"{label}: {str(alg.path):38} cost={alg.total_cost:6}  "
          f"{alg.termination_reason}")
```

```
cheapest path         : ['Source', 'A', 'Sink']                cost=  -8.0  completed
every customer visited: ['Source', 'A', 'B', 'Sink']           cost=  -3.0  completed
stop below -5         : ['Source', 'A', 'Sink']                cost=  -8.0  threshold_reached
```

The first two answers are the optima, confirmed by enumerating the four
elementary paths in exact arithmetic. The third stops as soon as it holds
something better than −5 rather than proving optimality; here that happens to
be the optimum, and in general it need not be.

## Documentation

- [`tsptw_example/FORMULATIONS.md`](https://github.com/Ebisaresu/cspy_for_TW/blob/v1.1.0/tsptw_example/FORMULATIONS.md)
  states each problem as a mathematical program — the resource constrained
  shortest path problem, per-node windows, the travelling salesman problem with
  time windows, and the pricing problem of column generation — with the notation
  and the arguments that solve each one.
- [`tsptw_example/NATIVE_TW_GUIDE.md`](https://github.com/Ebisaresu/cspy_for_TW/blob/v1.1.0/tsptw_example/NATIVE_TW_GUIDE.md)
  documents everything above: the API, the formulas the C++ evaluates,
  measurements, a worked column generation loop, and the limitations.
- [`tsptw_example/TSPTW_GUIDE.md`](https://github.com/Ebisaresu/cspy_for_TW/blob/v1.1.0/tsptw_example/TSPTW_GUIDE.md)
  is a teaching guide covering the modelling background — labels, dominance,
  why visit indicators are needed — for readers new to labelling algorithms.

## Notes

`require_all_visits` needs `direction="forward"` and `elementary=True`, and is
refused otherwise. As an exact method it is practical to roughly a dozen
customers on an ordinary machine; the guide gives measured figures.

Every wheel attached here was built by continuous integration and had the test
suite run against it on its own platform.

Upstream `cspy` is by David Torres Sanchez and is distributed under the MIT
License, which this fork keeps unchanged; `LICENSE.txt` and `NOTICE.txt` ship
inside every wheel.
