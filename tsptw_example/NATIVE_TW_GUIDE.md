# cspy Native Time Windows (NodeWindowREF) Guide — Zero-Python-Boundary Pricing

Intended audience: students and researchers who have finished
[`TSPTW_GUIDE.md`](./TSPTW_GUIDE.md) and are moving on to the pricing problem
(ESPPRC-TW) of column generation / Branch-and-Price.
Target code: branch `feature/native-time-windows` (a fork of cspy v1.0.3,
`/Users/azzqi/workspace/cspy`). All notation ($T_i, a_i, b_i, s_i, t_{ij}$,
`res[0]` = critical resource, sentinel, dominance, degenerate path) is shared
with TSPTW_GUIDE.md.

---

## 1. Motivation — the overhead of the Python REF

In the approach used by TSPTW_GUIDE.md, the time-window propagation
$T_j = \max(a_j,\ T_i + s_i + t_{ij})$ is written in Python as
`REFCallback.REF_fwd`, and cspy calls it via the **SWIG director mechanism**,
round-tripping C++ → Python → C++ on every label extension. That is fine at
teaching scale, but in column generation the pricing problem (ESPPRC-TW) is
solved on **every iteration**, and the number of REF calls in a single
`run()` reaches roughly 120,000 for $n=30$ and 780,000 for $n=50$ (measured
in Section 5). At the profiling done when this branch was started, a Python
REF invoked through the director cost about 5.2 µs/call (including the
Python-side body of the REF itself); even the pure difference between an
optimized array-based Python REF and the native implementation is
**0.9–1.6 µs/call** lost to the Python boundary (Section 5).

This branch therefore implements the REF for time windows (and, more
generally, node resource windows) as the **pure C++ class `NodeWindowREF`**,
exposed directly through `BiDirectional`'s constructor arguments. There are
two goals.

1. **Zero Python calls in the labelling loop**: since it is a non-director
   class, the engine's virtual function calls stay entirely inside C++
   (`test_zero_python_calls_in_labelling_loop` demonstrates this with
   `sys.setprofile`).
2. **First-class support for `direction='both'` (bidirectional search)**: a
   consistent Python implementation of `REF_bwd` / `REF_join` is hard to get
   right (TSPTW_GUIDE.md Section 7, caveat 9), and upstream even had a
   segfault bug (Section 8). This branch provides validated backward and
   join formulas in C++. For pricing with a tight capacity constraint there
   are cases **267x** faster than forward (Section 5).

## 2. Design philosophy of the generalization — per-node resource windows

Rather than hard-coding time windows, this is generalized to "a policy per
resource $r$ plus per-node data". Each resource $r$ and node $v$ carries a
window $[lb_r(v),\ ub_r(v)]$ and a consumption $c_r(v)$, and the policy is
chosen from three kinds.

| Policy | Propagation (edge $(i,j)$, pre-extension resource $T$) | Use |
|---|---|---|
| `additive` (default) | $T + t^{(r)}_{ij} + c_r(j)$ — $c_r(j)$ is added **on arrival at head** | Backward compatible: identical to the engine's default additive REF when $c_r \equiv 0$. $c_r(j) = -1$ gives a **visit flag**, $+1$ a visit counter |
| `window_wait` | $\max\bigl(lb_r(j),\ T + c_r(i) + t^{(r)}_{ij}\bigr)$, rejected if this exceeds $ub_r(j)$ — $c_r(i)$ is added **on departure from tail** | **Time-like**. Early arrivals wait until $lb_r(j)$ |
| `window_hard` | Rejected if $T + c_r(i) + t^{(r)}_{ij}$ falls outside $[lb_r(j), ub_r(j)]$ (no waiting) | For resources where a lower-bound violation should also be rejected immediately |

- **Time windows are a special case**: setting `window_wait` on the time
  resource with $lb = a_v$, $ub = b_v$, $c_r(v) = s_v$ makes the propagated
  value exactly the same "**service start time** $T_v$ at node $v$" as in
  TSPTW_GUIDE.md Section 2: $T_j = \max(a_j,\ T_i + s_i + t_{ij})$, rejected
  when $T_j > b_j$.
- **The service-time convention** adds it on departure from the tail (this
  is exactly the formula validated by brute-force cross-checking against
  300+ random instances in the PoC). The alternative "add on arrival at
  head" convention (the D-convention: the window is checked on arrival, and
  the value is the departure time $D_v = T_v + s_v$) is
  **feasibility-equivalent** for the same parameters; only the reported
  value shifts by $+s_v$.
- **Visit flags can also be expressed** (`additive` with $c_r(v) = -1$): the
  dominance-soundness recipe from TSPTW_GUIDE.md Section 4.2 can be written
  entirely with the native interface (worked example (2) in Section 3). This
  also serves as a test case showing the generalization has not degenerated
  into "a time-windows-only feature".
- **`res[0]` (the critical resource) is fixed to `additive`**: the engine's
  bidirectional search assumes the critical resource is monotone
  (docs/ref.rst), so a non-additive policy or node consumption on it raises
  an exception on the C++ side.
- **Handling $a_{\mathrm{Source}} > 0$**: since a label's initial resource is
  always 0 (TSPTW_GUIDE.md Section 7, caveat 1), the REF clamps
  $T \leftarrow \max(T,\ lb_r(\mathrm{Source}))$ before propagating whenever
  `tail == Source`.

## 3. Python API reference

`BiDirectional`'s constructor gained the following arguments. Existing
arguments and existing functionality (including the Python-director
`REF_callback` mechanism) remain fully backward compatible.

| Argument | Type / default | Meaning |
|---|---|---|
| `time_windows` | `{node name: (a_v, b_v)}` / `None` | **Simple interface**. Sets `window_wait` on resource `time_res`. Keys are the **original node names** (not the internal integer IDs). Unspecified nodes default to $(0,\ \texttt{max\_res[time\_res]})$ |
| `service_times` | `{node name: s_v}` / `None` | $s_v \ge 0$, added on departure from tail. Unspecified defaults to 0. Only usable together with `time_windows` |
| `time_res` | `int` / `1` | Resource index used by `time_windows`. Must differ from the critical resource's index |
| `node_windows` | `{res_idx: {node name: (lb, ub)}}` / `None` | **General interface**. Per-resource, per-node windows |
| `node_consumption` | `{res_idx: {node name: c_v}}` / `None` | Per-resource, per-node consumption (the timing of the addition depends on the policy; see the table in Section 2) |
| `window_policy` | `{res_idx: 'additive'\|'window_wait'\|'window_hard'}` / `None` | Unspecified resources default to `'additive'` |
| `window_eps` | `float` / `1e-9` | Numerical tolerance for window comparisons |

Constraints (validated in the constructor; violations are collected and
raised together as one exception): **mutually exclusive** with
`REF_callback` / `find_critical_res=True`. `window_hard` is restricted to
`direction='forward'`. `max_res[r]` **must be finite** for any resource
carrying a window policy. Supplying `node_windows[r]` while
`window_policy[r]` is left at `additive` is an error (this prevents a window
from being silently ignored). `preprocess=True` is a no-op (Section 8).

### 3.1 Minimal example of the simple interface (executed code)

```python
import networkx as nx
import numpy as np
from cspy import BiDirectional

# res[0] = edge-count counter (critical, res_cost[0]=1 on every edge)
# res[1] = time (res_cost[1] = travel time t_ij)
G = nx.DiGraph(n_res=2)
for u, v, t, w in [("Source", 1, 2, 0.0), ("Source", 2, 5, 0.0),  # (tail, head, travel time, weight)
                   (1, 2, 3, -10.0), (2, 1, 3, -10.0),
                   (1, "Sink", 2, 0.0), (2, "Sink", 2, 0.0)]:
    G.add_edge(u, v, res_cost=np.array([1.0, float(t)]), weight=w)

for direction in ("forward", "both"):
    alg = BiDirectional(
        G, max_res=[10.0, 20.0], min_res=[0.0, 0.0],
        direction=direction, elementary=True,
        time_windows={1: (0.0, 4.0), 2: (8.0, 12.0)},  # unspecified nodes default to (0, max_res[time_res])
        service_times={1: 1.0, 2: 1.0},                # unspecified defaults to 0
        time_res=1,                                    # default 1 (must differ from critical)
    )
    alg.run()
    print(f"{direction:8s}:", alg.path, alg.total_cost, alg.consumed_resources)
```

Output (actual output):

```text
forward : ['Source', 1, 2, 'Sink'] -10.0 [3.0, 11.0]
both    : ['Source', 1, 2, 'Sink'] -10.0 [3.0, 16.0]
```

How to read this: the reverse order `Source→2→1` is rejected because arrival
at customer 1 is $8+1+3 = 12 > b_1 = 4$; `Source→1→2` is feasible because
customer 2 waits 2 units until $a_2 = 8$ ($T_2 = \max(8, 2+1+3) = 8$),
reaching the Sink at $T = 11$. Note that `consumed_resources[1]` is the
actual service start time (11) under forward, but **under both it is a
feasibility-check surrogate value** (16) (Section 8, caveat 7).

### 3.2 Example of the general interface (executed code)

```python
import networkx as nx
import numpy as np
from cspy import BiDirectional

def build(n_res):
    G = nx.DiGraph(n_res=n_res)
    for u, v, t, w in [("Source", 1, 2, 0.0), ("Source", 2, 5, 0.0),
                       (1, 2, 3, 5.0), (2, 1, 3, 5.0),
                       (1, "Sink", 2, 1.0), (2, "Sink", 2, 1.0)]:
        G.add_edge(u, v, weight=w,
                   res_cost=np.array([1.0, float(t)] + [0.0] * (n_res - 2)))
    return G

TW = {1: (0.0, 4.0), 2: (8.0, 12.0)}
SERVICE = {1: 1.0, 2: 1.0}

# (1) Time windows via the general interface (equivalent to the simple
#     interface's time_windows/service_times)
alg = BiDirectional(build(2), max_res=[10.0, 20.0], min_res=[0.0, 0.0],
                    direction="forward", elementary=True,
                    node_windows={1: TW},              # {res_idx: {node: (lb, ub)}}
                    node_consumption={1: SERVICE},     # window policies: added on departure from the tail node
                    window_policy={1: "window_wait"})  # default is 'additive'
alg.run()
print("(1) window_wait        :", alg.path, alg.total_cost, alg.consumed_resources)

ref = BiDirectional(build(2), max_res=[10.0, 20.0], min_res=[0.0, 0.0],
                    direction="forward", elementary=True,
                    time_windows=TW, service_times=SERVICE)
ref.run()
print("    == simple interface:", ref.path == alg.path
      and ref.total_cost == alg.total_cost
      and ref.consumed_resources == alg.consumed_resources)

# (2) Force full-visit coverage with visit flags (res[2,3]: 0 -> -1) and a
#     visit counter (res[4]: +1). min_res[4]=2 means "2 customers visited by
#     the time Sink is reached" (enforced only at the final feasibility check).
#     The flags are required to restrict dominance to matching visit sets
#     (TSPTW_GUIDE.md Section 4.2).
alg = BiDirectional(build(5), max_res=[10.0, 20.0, 0.0, 0.0, 10.0],
                    min_res=[0.0, 0.0, -1.0, -1.0, 2.0],
                    direction="forward", elementary=True,
                    node_windows={1: TW},
                    node_consumption={1: SERVICE,
                                      2: {1: -1.0},   # additive: added on arrival at head
                                      3: {2: -1.0},
                                      4: {1: 1.0, 2: 1.0}},
                    window_policy={1: "window_wait"})  # resources 2,3,4 use the default additive policy
alg.run()
print("(2) all visited        :", alg.path, alg.total_cost, alg.consumed_resources)

# (3) window_hard: early arrival at customer 2 (arrival 6 < a=8) cannot wait
#     and is rejected
alg = BiDirectional(build(2), max_res=[10.0, 20.0], min_res=[0.0, 0.0],
                    direction="forward", elementary=True,  # window_hard is forward-only
                    node_windows={1: TW}, node_consumption={1: SERVICE},
                    window_policy={1: "window_hard"})
alg.run()
print("(3) window_hard        :", alg.path, alg.total_cost, alg.consumed_resources)
```

Output (actual output):

```text
(1) window_wait        : ['Source', 2, 'Sink'] 1.0 [2.0, 11.0]
    == simple interface: True
(2) all visited        : ['Source', 1, 2, 'Sink'] 6.0 [3.0, 11.0, -1.0, -1.0, 2.0]
(3) window_hard        : ['Source', 1, 'Sink'] 1.0 [2.0, 5.0]
```

(1) has no enforcement, so the cheap path that skips customer 1 is optimal.
(2) forces full coverage via the flags and counter, so the consumed
resources show flags $-1, -1$ and counter $2$. (3) disallows waiting, so
customer 2 becomes unreachable and only the route through customer 1 is
returned.

### 3.3 Advanced: using NodeWindowREF directly

You can also construct the C++ object directly without going through the
wrapper (`REF_fwd`/`REF_bwd`/`REF_join` are also callable from Python, for
unit tests and equivalence checks). Node indices are **internal integer
IDs**.

```python
from cspy.algorithms.pyBiDirectionalCpp import (
    NodeWindowREF, DoubleVector, POLICY_WINDOW_WAIT)
ref = NodeWindowREF(n_vertices, DoubleVector(max_res), source_id, sink_id,
                    critical_res, eps)
ref.setResourcePolicy(r, POLICY_WINDOW_WAIT, lb_vec, ub_vec, cons_vec)
```

Invalid input (an out-of-range resource index, `lb > ub`, a non-additive
policy on the critical resource, `max_res=inf` on a resource with a window
policy, etc.) raises a C++-side `std::invalid_argument`, converted to a
Python `RuntimeError`.

## 4. Structure of the C++ implementation

### 4.1 File layout and class design

- **`src/cc/node_window_ref.h` / `.cc`** (new): `class NodeWindowREF final :
  public REFCallback`. A **non-director** pure C++ class that simply
  inherits the REF base class (`src/cc/ref_callback.h`), the engine's
  officially sanctioned extension point. Its members are the per-resource
  policy `policy_[r]`, the per-node data `lb_[r][v]`, `ub_[r][v]`,
  `cons_[r][v]` (all indexed by internal integer ID), the rejection sentinel
  `sentinel_[r] = max(max_res[r]+1, nextafter(max_res[r], +inf))`, and the
  tolerance `eps_`.
- **`setResourcePolicy(r, policy, lb, ub, cons)`**: unconfigured resources
  default to `additive` with zero data (identical to the engine's default
  additive REF). It validates the input (resource-index range, policy
  value, vector length equal to the number of vertices, `lb <= ub`, the
  critical resource being fixed to additive with zero consumption, and
  finiteness of `max_res` for resources with a window policy), throwing
  `std::invalid_argument` on any violation.
- **`src/cc/python/bidirectional.i`**: registers `NodeWindowREF` with SWIG
  (without `%feature("director")`, so it never goes through the director
  mechanism), and adds a `std::exception` → Python `RuntimeError`
  conversion. It also adds an argument guard for the case where `REF_fwd`
  etc. are called directly from Python (`checkExtensionArgs`: node-id range
  and resource-vector length), so out-of-range access raises an exception
  instead of crashing.
- **`src/python/algorithms/bidirectional.py`** (the wrapper): validates
  arguments (`src/python/checking.py check_native_windows`) → normalizes the
  simple and general interfaces into per-resource specs → **after**
  `_init_graph()` (`convert_node_labels_to_integers`), translates original
  node names to internal integer IDs and arrays them → constructs
  `NodeWindowREF` and passes it via `setREFCallback`.

### 4.2 Formulas for REF_fwd / REF_bwd / REF_join

Notation for the time reversal: $H = \texttt{max\_res}[r]$ (the horizon),
$g = H - L$ ($L$ = the **latest** service start time at that node). The
following is written for a `window_wait` time resource (the critical
resource is always additive, and `additive` resources follow the table in
Section 2).

**REF_fwd** (forward: tail $i$ → head $j$, exactly the formula validated by
the PoC):

$$T' = \max(T,\ lb_r(\mathrm{Source}))\ \text{(tail = Source only)},\qquad
T_j = \max\bigl(lb_r(j),\ T' + c_r(i) + t^{(r)}_{ij}\bigr)$$

Sentinel if $T_j > ub_r(j) + \varepsilon$ (the engine's `checkFeasibility`
then rejects it via `res > max_res`).

**REF_bwd** (backward: a backward label sits at head $j$ and extends toward
tail $i$; the time axis is reversed):

$$g_j = \max\bigl(g,\ H - ub_r(j)\bigr),\qquad
g_i = \max\bigl(g_j + c_r(i) + t^{(r)}_{ij},\ H - ub_r(i)\bigr)$$

Sentinel if $g_i > H - lb_r(i) + \varepsilon$. The clamp
$\max(g, H - ub)$, needed to correct the initial label ($g = 0$), is
idempotent (a no-op) on non-initial labels. Backward `window_hard` can
only track an upper bound (a no-waiting lower bound cannot be checked
backward) — this is why `window_hard` is restricted to forward.

**REF_join** (joins a forward label @tail $i$ with a backward label @head
$j$ across edge $(i,j)$):

$$T_j^{\mathrm{start}} = \max\bigl(lb_r(j),\ T_i + c_r(i) + t^{(r)}_{ij}\bigr),\qquad
\text{return value} = T_j^{\mathrm{start}} + g_j$$

The joined path is window-feasible $\iff T_j^{\mathrm{start}} + g_j \le H$,
which the engine's `max_res[r]` check evaluates directly. **The critical
resource alone needs special handling**: `labelling.cc mergeLabels` has a
fix-up that silently re-adds `bwd_res_inverted` unless REF_join's return
value matches `fwd[0] + m + (max_res[0] − bwd[0])` (`m` = the edge's
consumption, 1 if it is 0) under a **floating-point equality comparison**.
`NodeWindowREF::REF_join` computes this same expression with **the same
operations in the same combining order** and returns it, matching bit for
bit so the fix-up never fires.

### 4.3 Why the core is left unmodified

`labelling.cc` / `digraph.cc` are untouched, and the diff to
`bidirectional.cc` is only the two null guards described below. (1)
**Backward compatibility**: since only the REF, the engine's officially
sanctioned extension point, is used, the existing search / dominance /
bidirectional logic cannot change behaviour, and the existing Python test
suite passes exactly as before. (2) **Verifiability**: it is possible to
brute-force check that "native and a Python director REF implementing the
same formulas return **bit-identical** output" (already done, roughly 2600
checks in total, all passing). Touching the core would move the goalposts of
that comparison. (3) **Staying close to upstream**: a smaller diff makes it
easier to track updates to upstream cspy, and easier to turn into a PR.

### 4.4 SWIG ownership

`Params` never deletes its `ref_callback` pointer, so **ownership must stay
on the Python side**. The wrapper keeps a reference in `self._window_ref`
and additionally attaches it to the `bidirectional_cpp` proxy itself via a
keepalive attribute (so extracting just the proxy and discarding the
wrapper does not cause a use-after-free). Note this is the **opposite** of
the Python-director `REF_callback`, which transfers ownership to C++ via
`__disown__`. If you construct `NodeWindowREF` yourself as in Section 3.3,
keep the object alive for the lifetime of the `BiDirectional` object (do not
call `__disown__`).

## 5. Benchmark results (measured)

ESPPRC-TW pricing (M1 / 8GB, `elementary=True`, medians). Variants: (a)
Python `REFCallback`, array-based / (a') the same but reading nx attributes
(the typical implementation in TSPTW_GUIDE.md) / (b) native interface,
forward / (c) native interface, `direction='both'`. On every row, (a)==(b)
match exactly on both path and cost, (a)==(c) match on cost, and every path
has been independently re-verified for feasibility and cost by simulation.

### run() time (median, ms)

| n | arcs | REF calls | (a) Py array | (a') Py nx | (b) native fwd | (c) native both | (a)/(b) | (a')/(b) | (a)/(c) |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 10 | 65 | 368 | 0.89 | 0.98 | 0.53 | 0.89 | 1.7x | 1.8x | 1.0x |
| 15 | 136 | 654 | 1.43 | 1.60 | 0.83 | 1.93 | 1.7x | 1.9x | 0.7x |
| 20 | 234 | 6,522 | 32.6 | 34.3 | 25.9 | 116.8 | 1.3x | 1.3x | 0.3x |
| 30 | 500 | 117,804 | 2,184 | 2,223 | 2,038 | 4,039 | 1.07x | 1.09x | 0.5x |
| 40† | 864 | 469,483 | 71,415 | 72,742 | 71,648 | >980,000 (cut off) | 1.00x | 1.02x | — |
| 50‡ (capacity 5) | 1,331 | 780,438 | 8,126 | 8,372 | 7,396 | **30.4** | 1.10x | 1.13x | **267x** |

† For n=40, each configuration took over 60 s, so each was measured once
(the cutoff rule applied). native_both was force-stopped after more than 16
minutes (incomplete).
‡ At n=50 without a capacity limit, even native forward alone failed to
finish in a single run of over 600 s (M1) → shrunk per the rule:
`max_res[0]=5` (at most 4 customers per route, a vehicle-capacity
constraint, the standard setting for CVRPTW pricing). (a)(a')(b) were
measured 3 times, (c) 5 times.

### BiDirectional construction time (median, ms) — occurs every iteration in column generation

| n | (a) Py (including callback-array preparation) | (b) native fwd | (c) native both |
|--:|--:|--:|--:|
| 10 | 0.49 | 0.48 | 0.45 |
| 20 | 1.48 | 1.57 | 1.52 |
| 30 | 3.03 | 3.09 | 3.09 |
| 50 | 7.45 | 7.54 | 7.34 |

Construction time is nearly identical across all variants (the penalty of
id translation and `NodeWindowREF` construction for the native interface is
within measurement noise). At n≥20, `run()` dominates.

### Python-boundary overhead per REF call (measured: (run_a − run_b)/calls)

| n | calls | (a)−(b) µs/call | (a')−(b) µs/call | reference: native-side total cost per extension |
|--:|--:|--:|--:|--:|
| 10 | 368 | 0.97 | 1.22 | 1.45 µs |
| 15 | 654 | 0.92 | 1.18 | 1.27 µs |
| 20 | 6,522 | 1.03 | 1.29 | 3.97 µs |
| 30 | 117,804 | 1.24 | 1.57 | 17.3 µs |
| 50 (capacity 5) | 780,438 | 0.94 | 1.25 | 9.48 µs |

**How to read this**: eliminating the Python boundary is worth 0.9–1.6
µs/call by itself — a 1.7–1.9x speed-up at small scale, but only 1.0–1.1x at
n≥30 — because the cspy core's dominance computation grows super-linearly
per extension (1.4 µs at n=10 → 17 µs at n=30 → 150 µs at n=40), shrinking
the Python boundary's contribution from ~40% down to <1%. The largest
practical payoff is **`direction='both'`, newly unlocked by this
implementation**: for CVRPTW pricing with a tight capacity constraint on the
critical resource (n=50, ≤4 customers/route), 8.13 s → 30 ms = **267x**.
Conversely, when the critical resource's upper bound is loose, both is
1.7–4.5x slower than forward (and breaks down at n=40), so **choosing
between them is essential**.

## 6. Example: wiring into column-generation pricing

A working skeleton of VRPTW column generation, implementing the approach
from TSPTW_GUIDE.md Section 8 (swap in the reduced cost, drop Hamiltonicity
enforcement, no visit flags needed) with the native interface. The
restricted master problem (RMP) is a set-partitioning LP, solved here
exactly by brute-force basis enumeration for teaching purposes (production
code would use an LP solver's dual values). The key part is the **loop of
dual prices → `weight` updates**: every arc entering customer $j$ picks up
$-\pi_j$, and the pricing graph is rebuilt from scratch (the construction
cost is negligible, as shown in Section 5).

```python
# Column generation (VRPTW): RMP = set-partitioning LP (a teaching-scale
# brute-force basis enumeration), pricing = ESPPRC-TW solved via
# BiDirectional with native time windows
from itertools import combinations
import networkx as nx
import numpy as np
from cspy import BiDirectional

N = 4  # depot 0 + customers 1..4, at most 3 customers per route (max_res[0] = 4 edges)
TRAVEL = ((0, 8, 9, 14, 12), (8, 0, 5, 8, 11), (9, 5, 0, 6, 8),
          (14, 8, 6, 0, 7), (12, 11, 8, 7, 0))
TW = {1: (5.0, 30.0), 2: (10.0, 40.0), 3: (15.0, 60.0), 4: (20.0, 70.0)}
SERVICE = {i: 2.0 for i in range(1, N + 1)}

def route_cost(route):  # route = customer visiting order; total travel time out of and back to the depot
    seq = [0] + list(route) + [0]
    return float(sum(TRAVEL[u][v] for u, v in zip(seq[:-1], seq[1:])))

def build_pricing_graph(duals):
    # Reduced-cost graph: subtract pi_j from every arc entering customer j
    # (route reduced cost = c_r - sum pi_j)
    G = nx.DiGraph(n_res=2)
    nodes = ["Source"] + list(range(1, N + 1)) + ["Sink"]
    idx = {"Source": 0, "Sink": 0, **{i: i for i in range(1, N + 1)}}
    for u in nodes:
        for v in nodes:
            if (u == v or v == "Source" or u == "Sink"
                    or (u == "Source" and v == "Sink")):
                continue
            t = float(TRAVEL[idx[u]][idx[v]])
            G.add_edge(u, v, res_cost=np.array([1.0, t]),
                       weight=t - (duals[v] if v != "Sink" else 0.0))
    return G

def solve_rmp(columns, costs):
    # Solve the set-partitioning LP min cx, Ax=1, x>=0 exactly by
    # brute-force basis enumeration (teaching-scale; production code would
    # use an LP solver's dual values). Returns: (objective, x, duals pi)
    A = np.array([[1.0 if i in col else 0.0 for col in columns]
                  for i in range(1, N + 1)])
    c, b, best = np.array(costs), np.ones(N), None
    for basis in combinations(range(len(columns)), N):
        B = A[:, basis]
        if abs(np.linalg.det(B)) < 1e-9:
            continue
        x_b = np.linalg.solve(B, b)
        pi = np.linalg.solve(B.T, c[list(basis)])
        if (x_b < -1e-9).any() or (c - pi @ A < -1e-9).any():
            continue  # keep only bases that are primal feasible and optimal
                      # (every column's reduced cost >= 0)
        obj = float(c[list(basis)] @ x_b)
        if best is None or obj < best[0] - 1e-12:
            x = np.zeros(len(columns))
            x[list(basis)] = x_b
            best = (obj, x, {i: float(pi[i - 1]) for i in range(1, N + 1)})
    return best

columns = [frozenset([i]) for i in range(1, N + 1)]   # initial columns: single-customer routes
costs = [route_cost([i]) for i in range(1, N + 1)]
for it in range(1, 21):
    obj, x, duals = solve_rmp(columns, costs)
    # --- pricing: ESPPRC-TW (native time windows, zero Python calls) ---
    alg = BiDirectional(build_pricing_graph(duals),
                        max_res=[4.0, 100.0], min_res=[0.0, 0.0],
                        direction="forward", elementary=True,
                        time_windows=TW, service_times=SERVICE)
    alg.run()
    path = alg.path
    # degenerate-path check (when infeasible, forward returns ['Source'], cost 0.0 -- Section 8)
    infeasible = (path is None or len(path) <= 1
                  or path[0] != "Source" or path[-1] != "Sink")
    rc = alg.total_cost if not infeasible else 0.0
    print(f"iter {it}: RMP={obj:6.2f}  duals={ {i: round(p, 1) for i, p in duals.items()} }"
          f"  pricing rc={rc:7.3f}  path={path}")
    if infeasible or rc >= -1e-9:
        print("=> no column with negative reduced cost: LP optimal")
        break
    route = tuple(v for v in path if v not in ("Source", "Sink"))
    if frozenset(route) in columns:
        print("=> existing column regenerated (degenerate): stopping")
        break
    columns.append(frozenset(route))
    costs.append(route_cost(route))

print("\nLP value =", round(obj, 4))
for col, cost, xv in zip(columns, costs, x):
    if xv > 1e-9:
        print(f"  x={xv:.3f}  route {sorted(col)}  cost {cost}")
```

Output (actual output):

```text
iter 1: RMP= 86.00  duals={1: 16.0, 2: 18.0, 3: 28.0, 4: 24.0}  pricing rc=-36.000  path=['Source', 2, 3, 4, 'Sink']
iter 2: RMP= 50.00  duals={1: 16.0, 2: 18.0, 3: 28.0, 4: -12.0}  pricing rc=-31.000  path=['Source', 1, 3, 2, 'Sink']
iter 3: RMP= 50.00  duals={1: 16.0, 2: 18.0, 3: -8.0, 4: 24.0}  pricing rc=-25.000  path=['Source', 1, 2, 4, 'Sink']
iter 4: RMP= 50.00  duals={1: 16.0, 2: -18.0, 3: 28.0, 4: 24.0}  pricing rc=-33.000  path=['Source', 1, 3, 4, 'Sink']
iter 5: RMP= 44.33  duals={1: 10.3, 2: 9.3, 3: 11.3, 4: 13.3}  pricing rc=  0.000  path=['Source', 1, 2, 4, 'Sink']
=> no column with negative reduced cost: LP optimal

LP value = 44.3333
  x=0.333  route [2, 3, 4]  cost 34.0
  x=0.333  route [1, 2, 3]  cost 31.0
  x=0.333  route [1, 2, 4]  cost 33.0
  x=0.333  route [1, 3, 4]  cost 35.0
```

Observation: the LP optimum of 44.33 is reached in 5 iterations, but the
solution is fractional (four 3-customer routes at 1/3 each), and it is
strictly smaller than the integer optimum (50: routes {2,3,4} + {1}) → this
is where **branching** (Branch-and-Price) takes over. Because pricing
searches for "any" feasible elementary path, **visit flags are not needed**
(Feillet-style dominance is sound whenever every elementary path is
feasible, TSPTW_GUIDE.md Section 8). Skipping the degenerate-path check
would misread an infeasible `total_cost = 0.0` as "no improving column", so
it must always be included. As in this example, use `direction='forward'`
when the critical resource's upper bound is loose, and `both` when the
capacity constraint is tight — it can be orders of magnitude faster
(Section 5).

## 7. Rebuild procedure

After changing the C++ side (`src/cc/`), rebuild the wheel and reinstall it
into the venv.

```console
$ cd /Users/azzqi/workspace/cspy
$ cmake -S . -Bbuild -DBUILD_PYTHON=ON     # first time only (no-op if already configured)
$ cmake --build build -j2                  # incremental build (keep -j2 on M1 8GB)
$ .venv/bin/pip install --force-reinstall \
    build/python/dist/cspy-1.0.3-cp313-cp313-macosx_26_0_arm64.whl
```

The build automatically runs SWIG wrapper generation → C++ compilation →
`setup.py bdist_wheel`, producing the wheel under `build/python/dist/`.
Verify it with the bundled tests (actual output):

```console
$ cd /Users/azzqi/workspace/cspy/test/python
$ ../../.venv/bin/python3 -m unittest tests_native_time_windows
.node_windows[0][2]: upper bound 12.0 exceeds max_res[0]=10.0; the engine bound is the binding one (value used as given, no clamp).
......................direction='backward' with window resources: reported consumed_resources for window resources are on the reversed time axis (g = max_res[r] - latest start time).
........
----------------------------------------------------------------------
Ran 31 tests in 0.045s

OK
```

(The two warning-log lines in the middle are expected output from test
cases that deliberately trigger a warning.) The existing full suite
(`test/python/`, 77 tests) is also expected to pass entirely (the only
pre-existing failures are the 4 PSOLGENT numpy-2.x incompatibilities).
`dotnet/` (the C# bindings) is out of scope for the build.

## 8. Limitations and caveats

1. **Keep `res[0]` (the critical resource) a monotone additive resource**
   (Section 2). A positive `res_cost[0]` on every edge (e.g. an edge-count
   counter) is recommended. `min_res[0]` is the halfway-point floor of the
   bidirectional search, not "a lower bound at the Sink" (the same trap as
   TSPTW_GUIDE.md Section 3.2).
2. **Mutually exclusive**: cannot be combined with `REF_callback` (Python
   director) or `find_critical_res=True` (raises in the constructor).
3. **`preprocess=True` is a no-op**: as with `REF_callback`, the
   `prune_graph` preprocessing step is always skipped when native windows
   are used. Do your own pre-reduction if you need it.
4. **`window_hard` is restricted to `direction='forward'`** (backward
   extension can only track an upper bound, Section 4.2).
5. **`max_res[r]` must be finite for a resource with a window policy** (the
   rejection sentinel must exceed `max_res`; `inf` is rejected in the
   constructor).
6. **`min_res[time_res] = 0` is recommended**. A lower bound on a
   non-critical resource is enforced only at the final check, and when that
   lower bound is binding, the engine's component-wise dominance can prune
   away the very label that would have satisfied it — leading to a
   suboptimal solution or a spurious "no solution" (pre-existing engine
   semantics). If a binding `min_res` is unavoidable, e.g. to force full
   coverage, pairing it with a **visit-flag resource** as in Section 3.2 (2)
   restricts dominance to matching visit sets and restores soundness (a
   bare counter without flags is unsound).
7. **The window-resource value in `consumed_resources`**: only
   `direction='forward'` gives the actual service start time. `'both'`
   gives a feasibility-check surrogate ($T^{\mathrm{start}} + g$), and
   `'backward'` gives a value on the reversed axis. If you need the actual
   schedule, use forward, or forward-simulate the resulting path yourself
   (the `compute_schedule` approach of TSPTW_GUIDE.md Section 5.4).
8. **The degenerate result when infeasible is direction-dependent**:
   `'forward'` gives `['Source']` with `total_cost 0.0`, `'both'` gives
   `path is None`, and `'backward'` gives `['Sink']` (pre-existing engine
   behaviour, not specific to native windows). Always include the
   `infeasible` check from Section 6.
9. **Numerical tolerances are asymmetric**: node-window comparisons use
   `window_eps` (default 1e-9), but the engine's `max_res`/`min_res` checks
   are exact. Solutions right at the horizon boundary fall on the safe
   (infeasible) side.
10. **Defensive fix for an upstream bug**: upstream cspy segfaults with
    `direction='both'` plus `min_res > 0` on a time resource
    (`bidirectional.cc joinLabels` null-dereferences the still-unset
    `best_labels[n]` when every label reaching the Sink has died). This
    branch adds null guards to both the forward and backward accesses in
    `joinLabels` (the only two spots in the `bidirectional.cc` diff). After
    the fix, it no longer crashes and instead falls through to the normal
    infeasible handling.
11. **Ownership**: handled automatically when going through the wrapper
    (Section 4.4). Extracting and using `bidirectional_cpp` directly still
    keeps the REF alive via the keepalive attribute, but with the direct
    construction of Section 3.3 you must hold the reference yourself.

---

*Implementation verification*: every code example in this guide was actually
executed with the Python at `/Users/azzqi/workspace/cspy/.venv`, and the
output blocks are verbatim copies of real runs. The implementation itself
passes roughly 2600 checks in total, including a bit-identical comparison
against a Python director REF written independently from the PoC-validated
formulas and exact brute-force cross-checking with `Fraction`. The permanent
regression tests are in `test/python/tests_native_time_windows.py`
(31 cases); for the primary source of the formulas and caveats, see
`docs/ref.rst`.
