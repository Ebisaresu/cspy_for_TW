# cspy Native Time Windows (NodeWindowREF) Guide — Zero-Python-Boundary Pricing

Intended audience: students and researchers who have finished
[`TSPTW_GUIDE.md`](./TSPTW_GUIDE.md) and are moving on to the pricing problem
(ESPPRC-TW) of column generation / Branch-and-Price.
Target code: this fork of cspy v1.0.3. All notation ($T_i, a_i, b_i, s_i, t_{ij}$,
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
#     (TSPTW_GUIDE.md Section 4.2). Section 9 asks for the same thing with
#     require_all_visits=True and no extra resources; this encoding is kept
#     as the reference implementation that the Section 9 core code is
#     checked against.
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

Example (2) is kept in this guide as a **reference implementation, not as
the recommended way of asking for full coverage**. It shows that the general
interface is expressive enough to reproduce the visit indicator encoding of
`TSPTW_GUIDE.md` Section 4.2 without a Python resource extension function,
and it is the yardstick the core implementation is measured against. To
actually require coverage, use `require_all_visits=True` (Section 9): it
expresses the same requirement with no extra resources, it cannot be
mis-assembled, and Section 9.4 shows the two return the same answers while
the encoding gets steadily slower as the number of customers grows.

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

### 4.3 Why the core is left unmodified for the window resources

For the node windows themselves, `labelling.cc` / `digraph.cc` are
untouched, and the diff to `bidirectional.cc` is only the two null guards
described below. (1) **Backward compatibility**: since only the REF, the
engine's officially sanctioned extension point, is used, the existing search
/ dominance / bidirectional logic cannot change behaviour, and the existing
Python test suite passes exactly as before. (2) **Verifiability**: it is
possible to brute-force check that "native and a Python director REF
implementing the same formulas return **bit-identical** output" (already
done, roughly 2600 checks in total, all passing). Touching the core would
move the goalposts of that comparison. (3) **Staying close to upstream**: a
smaller diff makes it easier to track updates to upstream cspy, and easier
to turn into a PR.

The mandatory-visit feature of Section 9 is the one deliberate exception to
this rule, for two reasons that do not apply to the window resources.
First, a resource extension function cannot express the required change:
the rule that has to change is the **dominance** rule, and a resource
extension function has no access to it. Encoding the visit set in
resources, as Section 3.2 example (2) does, works, but it makes the
resource vector grow with the number of customers, so every dominance
comparison costs one floating-point comparison per customer and every label
carries eight bytes per customer. Second, and this is what makes the
exception acceptable, the core change is provably **the same pruning
predicate** as the resource encoding, only represented as a bit set instead
of a vector of doubles (Section 9.4). The resource encoding therefore
remains available as a reference implementation, and the two are compared
against each other, and against exhaustive enumeration, in the test suite.
All new code paths sit inside an `if (require_all_visits)` guard, no
existing expression or branch was rewritten, and the resulting binary was
checked to produce byte-identical output to the pre-change build on 3222
solver runs with the feature switched off.

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

The wrapper also keeps a plain reference to a user supplied `REF_callback`
in `self._ref_callback`. The C++ side only stores a raw pointer, so
`BiDirectional(..., REF_callback=MyCallback())` with a temporary used to let
the callback be collected before `run()` and crash the interpreter with a
segmentation fault; the reference removes that trap. It does not change what
the search computes.

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
$ cd <repository root>
$ cmake -S . -Bbuild -DBUILD_PYTHON=ON     # first time only (no-op if already configured)
$ cmake --build build -j2                  # incremental build (keep -j2 on M1 8GB)
$ .venv/bin/pip install --force-reinstall \
    build/python/dist/cspy-1.0.3-cp313-cp313-macosx_26_0_arm64.whl
```

The build automatically runs SWIG wrapper generation → C++ compilation →
`setup.py bdist_wheel`, producing the wheel under `build/python/dist/`.
Verify it with the bundled tests (actual output):

```console
$ cd test/python
$ ../../.venv/bin/python3 -m unittest tests_native_time_windows
.node_windows[0][2]: upper bound 12.0 exceeds max_res[0]=10.0; the engine bound is the binding one (value used as given, no clamp).
.......................direction='backward' with window resources: reported consumed_resources for window resources are on the reversed time axis (g = max_res[r] - latest start time).
........No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
.No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
.No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
.....No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
......No negative cost cycle has been found and elementary set to true.
Consider setting elementary to false.
....................
----------------------------------------------------------------------
Ran 65 tests in 0.141s

OK
```

(The warning-log lines in the middle are expected output from test cases
that deliberately trigger a warning.) The full suite
(`python3 -m unittest discover -p "tests_*.py"` in `test/python/`, 142
tests) is also expected to pass entirely, the only pre-existing failures
being the 4 PSOLGENT numpy-2.x incompatibilities and one skip.
`dotnet/` (the C# bindings) is out of scope for the build.

Note that adding a method to the SWIG interface (as
`setRequiredNodes`, Section 9, did) makes a rebuild mandatory: a stale
wheel left in the venv surfaces as `AttributeError`, not as a build error.

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
   bare counter without flags is unsound). To force full coverage, prefer
   `require_all_visits=True` (Section 9), which needs neither the counter
   nor the flags.
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

## 9. Mandatory visits (`require_all_visits`)

### 9.1 The problem: coverage used to be assembled by hand

Nothing in a labelling algorithm asks for a path that *covers* a given set
of nodes. It asks for a shortest path subject to resource bounds, and a path
that skips a customer is normally shorter than one that does not. Before
this option, the only way to force coverage was to encode it in resources,
the way example (2) of Section 3.2 does and `TSPTW_GUIDE.md` Sections 3.2
and 4.2 explain at length. For $n$ customers that means assembling three
things by hand:

1. one **visit indicator resource per customer** — `additive` policy,
   consumption $-1$ at that customer, `max_res` $=0$ and `min_res` $=-1$, so
   the resource reads $0$ while the customer is unvisited and $-1$ once it
   has been visited;
2. one **visit counter resource** — consumption $+1$ at every customer and
   `min_res` $= n$, which is what actually rejects an incomplete path when
   the sink is reached;
3. a `res_cost` array widened to length $n+3$ on **every edge** of the
   graph.

Three things are wrong with that.

- **The resource vector grows with the instance.** Dominance compares
  resource vectors component by component, so each comparison costs $n+3$
  floating-point comparisons instead of two, and each label carries
  $8(n+3)$ bytes of resource data instead of 16. Section 9.4 measures the
  result.
- **Every step of the assembly fails silently.** Widening `res_cost` on all
  but one edge, leaving an indicator's `min_res` at $0$, or putting the
  counter's bound on the wrong index each produce a perfectly well-formed
  run that returns a plausible but wrong answer. Nothing raises, because
  each of these is a legitimate resource-constrained shortest path model —
  just not the intended one.
- **The requirement never appears in the model.** "Visit every customer" is
  spread across three sets of numbers, none of which says so.

The indicator resources are not decoration. They are what makes the
dominance rule sound (Section 9.3); dropping them and keeping only the
counter yields a search that reports no solution on instances that have one.

`require_all_visits=True` replaces all three steps. The resource vector
stays at the two resources the model actually needs, the critical edge-count
resource and time.

### 9.2 Using `require_all_visits` (executed code)

| Argument | Type / default | Meaning |
|---|---|---|
| `require_all_visits` | `bool` / `False` | When true, only `Source` -> `Sink` paths that visit every node of `required_nodes` are accepted, and dominance is restricted to match (Section 9.3). Requires `direction='forward'` and `elementary=True` |
| `required_nodes` | iterable of node labels / `None` | The nodes that must be visited, given as the **original node labels** of `G` (not the internal integer identifiers). Duplicates are ignored and the order is irrelevant. `None` means every node other than `'Source'` and `'Sink'`. Only usable together with `require_all_visits=True` |

The instance below is the six-customer TSPTW of
[`tsptw_cspy.py`](./tsptw_cspy.py), whose optimum is known independently by
exhaustive search.

```python
"""Solve a six-customer TSPTW with cspy, using two resources only."""
import networkx as nx
import numpy as np
from cspy import BiDirectional

n = 6
travel = ((0, 11, 8, 5, 8, 5, 7), (9, 0, 7, 12, 3, 11, 7), (8, 12, 0, 4, 8, 3, 11),
          (3, 4, 10, 0, 8, 3, 8), (10, 3, 3, 6, 0, 8, 4), (5, 8, 5, 12, 4, 0, 10),
          (8, 4, 7, 5, 12, 4, 0))
tw_a = (0, 39, 2, 38, 32, 2, 42)
tw_b = (200, 59, 18, 60, 57, 13, 60)
service = (0, 6, 2, 4, 5, 3, 1)
horizon = tw_b[0]

# res[0] = edge counter (critical, monotone), res[1] = time. Nothing else.
G = nx.DiGraph(n_res=2)
for i in range(1, n + 1):
    G.add_edge("Source", i, res_cost=np.array([1.0, float(travel[0][i])]),
               weight=float(travel[0][i]))
    G.add_edge(i, "Sink", res_cost=np.array([1.0, float(travel[i][0])]),
               weight=float(travel[i][0]))
    for j in range(1, n + 1):
        if i != j:
            G.add_edge(i, j, res_cost=np.array([1.0, float(travel[i][j])]),
                       weight=float(travel[i][j]))

time_windows = {i: (float(tw_a[i]), float(tw_b[i])) for i in range(1, n + 1)}
service_times = {i: float(service[i]) for i in range(1, n + 1)}

alg = BiDirectional(
    G,
    [float(n + 1), float(horizon)],   # max_res
    [0.0, 0.0],                       # min_res
    direction="forward",              # required by require_all_visits
    elementary=True,                  # required by require_all_visits
    time_windows=time_windows,
    service_times=service_times,
    require_all_visits=True,          # <-- the new option
    # required_nodes defaults to every node other than "Source" and "Sink"
)
alg.run()
print("tour              :", " -> ".join(str(v) for v in alg.path))
print("total travel time :", alg.total_cost)
print("edges, return time:", alg.consumed_resources)

# A proper subset may be required instead: nodes 2 and 5 are mandatory, the
# other customers are visited only when doing so pays off.
alg2 = BiDirectional(
    G, [float(n + 1), float(horizon)], [0.0, 0.0],
    direction="forward", elementary=True,
    time_windows=time_windows, service_times=service_times,
    require_all_visits=True,
    required_nodes=[2, 5],
)
alg2.run()
print("subset tour       :", " -> ".join(str(v) for v in alg2.path))
print("subset cost       :", alg2.total_cost)

# An unsupported search direction is refused with an actionable message.
try:
    BiDirectional(G, [float(n + 1), float(horizon)], [0.0, 0.0],
                  elementary=True, require_all_visits=True)   # direction='both'
except Exception as error:
    print("guard             :", error)
```

Output (actual output):

```text
tour              : Source -> 2 -> 5 -> 4 -> 1 -> 6 -> 3 -> Sink
total travel time : 33.0
edges, return time: [7.0, 66.0]
subset tour       : Source -> 2 -> 5 -> Sink
subset cost       : 16.0
guard             : require_all_visits=True requires direction='forward' (got 'both'). The backward search and the label joining step cannot yet certify that all required nodes are visited; pass direction='forward'.
```

How to read this. The first tour is the known TSPTW optimum of the instance:
cost 33, seven edges, depot return (service start) time 66. Note that the
time-window-free optimal tour of the same instance costs 29 and is
infeasible here, so the windows are binding. The second run requires only
customers 2 and 5, and since visiting anyone else only adds travel time it
returns the two-customer tour at cost 16 — a **proper subset** is a
meaningful request, not a degenerate one: the listed nodes must be visited
and the rest are visited only when that pays off. The third run leaves
`direction` at its default `'both'` and is refused in the constructor
(Section 9.5, restriction 1).

`required_nodes` accepts any iterable, including one that can be traversed
only once (a generator expression, `map`, `filter`, `iter(...)`, a
`csv.reader`): the argument is materialised exactly once, during validation,
and that materialised list is what the rest of the constructor uses. An
**empty** required set is rejected rather than quietly accepted, because it
would turn the call back into a plain elementary shortest path solve while
`require_all_visits=True` still reads as though the requirement were in
force. The same applies to a graph whose only nodes are `'Source'` and
`'Sink'`.

### 9.3 Why the dominance rule has to change

The engine's dominance rule prunes a label when another label at the same
node has no larger cost, no larger value in every resource, and (under
`elementary=True`) a visited set contained in the other's. That rule is
sound for the elementary shortest path problem with resource constraints,
because there any elementary completion is acceptable. It is **not** sound
once every required node must appear on the path: a cheap label whose
visited set is a proper subset can dominate a label whose visited set is a
superset, and the pruned label may have been the only one that could still
cover the remaining required nodes. The concrete failure on this instance is
documented in `TSPTW_GUIDE.md` Section 4.2: the search reports the
degenerate `['Source']` on an instance that has a feasible tour.

The added condition is stated once, over the visited sets themselves: a
label may only dominate another label when the two visit **exactly the same
required nodes**. Write $V(L)$ for the set of nodes on the partial path of
$L$ and $R$ for the required set; the condition is $V(L_1) \cap R = V(L_2)
\cap R$.

*Soundness.* Suppose $L_1$ and $L_2$ sit at the same node and satisfy
(i) $c(L_1) \le c(L_2)$, (ii) $r(L_1) \le r(L_2)$ component-wise,
(iii) $V(L_1) \subseteq V(L_2)$ (the existing containment condition) and
(iv) $V(L_1) \cap R = V(L_2) \cap R$ (the new condition). Let $Q$ be any
completion of $L_2$ to the sink that is resource feasible and covers $R$.
Then $Q$ is also a valid completion of $L_1$: it stays elementary because
$Q \cap V(L_2) = \emptyset$ and $V(L_1) \subseteq V(L_2)$; it stays
resource feasible because the resource extension functions are monotone, so
$r(L_1) \le r(L_2)$ propagates along $Q$; and it still covers $R$, because
any $x \in R$ not on $Q$ lies in $V(L_2) \cap R = V(L_1) \cap R$. Finally
$c(L_1) + c(Q) \le c(L_2) + c(Q)$. So discarding $L_2$ cannot lose an
optimal solution.

*Why equality rather than containment.* What the coverage argument actually
needs is only $V(L_2) \cap R \subseteq V(L_1)$; the opposite inclusion
already follows from the existing condition (iii). Imposing equality is
therefore never more aggressive than the minimal condition, it reduces to a
single comparison of two bit sets, and it coincides exactly with what the
visit indicator encoding imposes.

The terminal condition is the other half: an extension into the sink is
refused unless the label already covers $R$. This loses nothing, because
the optimal path covers $R$ at the node before the sink, and every refused
label would have produced a path that does not cover $R$. With
`direction='forward'` the search is complete (the halfway-point cut-off in
`checkBounds` only fires for `direction='both'`), so global optimality
follows directly.

### 9.4 Relation to the visit indicator encoding, and what it costs

**The two are the same pruning rule.** In the encoding of Section 3.2 (2),
"every resource $\le$" over the indicator resources means $V(L_1) \supseteq
V(L_2)$ (the indicators are decremented, which reverses the direction), and
the containment condition (iii) means $V(L_1) \subseteq V(L_2)$; together
they say the visited sets coincide. The core condition says the visited
sets coincide on $R$, which under (iii) is the same statement. So the two
generate and keep the same set of labels; only the representation differs,
from a vector of doubles to $\lceil |R| / 64 \rceil$ machine words. This is
why the encoding is kept as the reference implementation in
`test/python/tests_native_time_windows.py`.

The correspondence, term by term:

| | Visit indicator encoding | `require_all_visits=True` |
|---|---|---|
| Coverage is requested by | `min_res[counter] = n` on a counter resource | the `require_all_visits` / `required_nodes` arguments |
| Dominance is restricted by | one indicator resource per required node, compared as part of the component-wise resource test | one bit set per label, compared once |
| Visited set is represented as | $n$ `double` values, $0$ or $-1$ | $\lceil \|R\| / 64 \rceil$ machine words, one bit per required node |
| Incomplete paths are rejected | at the final feasibility check, through `min_res` | when the extension into the sink is attempted |
| Resource vector length | $n + 3$ | 2 |
| Resource data per label | $8(n+3)$ bytes | 16 bytes, plus an inline 64-bit word for up to 64 required nodes (no allocation) |
| Set membership test | floating-point comparison | exact bit operation |
| Assembling it wrongly | silently returns a different answer | rejected in the constructor |

Both express the same thing, so both should return the same answer. On the
six-customer instance of Section 9.2 they do:

```python
"""The visit indicator encoding and require_all_visits, side by side, on the
six-customer TSPTW instance of tsptw_cspy.py."""
import networkx as nx
import numpy as np
from cspy import BiDirectional

n = 6
travel = ((0, 11, 8, 5, 8, 5, 7), (9, 0, 7, 12, 3, 11, 7), (8, 12, 0, 4, 8, 3, 11),
          (3, 4, 10, 0, 8, 3, 8), (10, 3, 3, 6, 0, 8, 4), (5, 8, 5, 12, 4, 0, 10),
          (8, 4, 7, 5, 12, 4, 0))
tw_a = (0, 39, 2, 38, 32, 2, 42)
tw_b = (200, 59, 18, 60, 57, 13, 60)
service = (0, 6, 2, 4, 5, 3, 1)
horizon = float(tw_b[0])
time_windows = {i: (float(tw_a[i]), float(tw_b[i])) for i in range(1, n + 1)}
service_times = {i: float(service[i]) for i in range(1, n + 1)}


def build(n_res):
    G = nx.DiGraph(n_res=n_res)

    def rc(t):
        return np.array([1.0, float(t)] + [0.0] * (n_res - 2))

    for i in range(1, n + 1):
        G.add_edge("Source", i, res_cost=rc(travel[0][i]), weight=float(travel[0][i]))
        G.add_edge(i, "Sink", res_cost=rc(travel[i][0]), weight=float(travel[i][0]))
        for j in range(1, n + 1):
            if i != j:
                G.add_edge(i, j, res_cost=rc(travel[i][j]), weight=float(travel[i][j]))
    return G


# (a) Visit indicator encoding: res[2..7] are the per-customer indicators
#     (consumption -1, bounded to [-1, 0]), res[8] is the visit counter
#     (consumption +1, min_res 6). Resource vector length n + 3 = 9.
n_res = n + 3
consumption = {1: service_times}
for i in range(1, n + 1):
    consumption[1 + i] = {i: -1.0}
consumption[n + 2] = {i: 1.0 for i in range(1, n + 1)}
indicator = BiDirectional(
    build(n_res),
    [float(n + 1), horizon] + [0.0] * n + [float(n)],
    [0.0, 0.0] + [-1.0] * n + [float(n)],
    direction="forward", elementary=True,
    node_windows={1: time_windows}, node_consumption=consumption,
    window_policy={1: "window_wait"},
)
indicator.run()

# (b) require_all_visits: resource vector length 2.
native = BiDirectional(
    build(2), [float(n + 1), horizon], [0.0, 0.0],
    direction="forward", elementary=True,
    time_windows=time_windows, service_times=service_times,
    require_all_visits=True,
)
native.run()

for name, alg, count in (("indicator encoding", indicator, n_res),
                         ("require_all_visits", native, 2)):
    tour = " -> ".join(str(v) for v in alg.path)
    print(f"{name} : {count} resources, cost {alg.total_cost}, tour {tour}")
print("identical answer   :",
      indicator.path == native.path
      and indicator.total_cost == native.total_cost)
```

Output (actual output):

```text
indicator encoding : 9 resources, cost 33.0, tour Source -> 2 -> 5 -> 4 -> 1 -> 6 -> 3 -> Sink
require_all_visits : 2 resources, cost 33.0, tour Source -> 2 -> 5 -> 4 -> 1 -> 6 -> 3 -> Sink
identical answer   : True
```

**What the representation costs.** The search tree is the same size either
way — the same labels are generated and the same labels are kept — so the
difference is entirely the per-comparison and per-label cost of carrying the
visited set as $n$ resources rather than as a bit set. Measured on randomly
generated TSPTW instances (Apple M1, 8 GB), four instances per row, each
figure the median over those instances of the best of three repetitions of
"construct the `BiDirectional` object and call `run()`":

| customers $n$ | resources, indicator encoding | resources, `require_all_visits` | indicator encoding | `require_all_visits` | ratio |
|--:|--:|--:|--:|--:|--:|
| 6 | 9 | 2 | 0.0011 s | 0.0007 s | 1.6x |
| 8 | 11 | 2 | 0.0040 s | 0.0022 s | 1.8x |
| 10 | 13 | 2 | 0.0222 s | 0.0084 s | 2.6x |
| 12 | 15 | 2 | 0.289 s | 0.076 s | 3.8x |
| 14 | 17 | 2 | 5.10 s | 0.93 s | 5.5x |

The ratio grows with $n$ exactly as the model predicts: the indicator
encoding pays $O(n)$ per dominance comparison while the bit set pays $O(1)$
for any $n \le 64$, and the number of comparisons itself grows quickly. At
$n = 6$ and $n = 8$ the totals are small enough that graph construction —
also larger for the indicator encoding, whose `res_cost` arrays are
$n+3$ wide — is a visible part of the measurement; from $n = 10$ on,
`run()` dominates.

Across all 20 instances the two encodings returned **the same cost**. They
returned the same tour on 19 of them; on the remaining one ($n = 12$) they
returned two different tours of equal cost 355.0. That is an alternative
optimum, not a disagreement: neither encoding specifies how ties between
equal-cost labels are broken.

### 9.5 Restrictions and caveats

1. **`direction='forward'` only.** `'both'` and `'backward'` are rejected
   with an explanatory exception, from the Python layer and from the C++
   engine. The backward search and the label joining step would each need
   their own coverage argument (the bounds used in `joinLabels`, `getUB`
   and `best_labels` may come from paths that do not cover $R$), and until
   that is worked out the safe answer is to refuse. Since the default is
   `direction='both'`, this exception is the first thing most callers see;
   it names the fix.
2. **`elementary=True` is required.** The soundness argument above uses it,
   and without it the visited-set bit set would silently collapse repeated
   visits.
3. **The monotonicity assumption is inherited, not introduced.** A custom
   `REF_callback` that is not monotone, or the `window_hard` policy (which
   rejects early arrivals instead of waiting), breaks the assumption that
   $r(L_1) \le r(L_2)$ propagates. That is a pre-existing property of the
   engine's dominance rule; `require_all_visits` neither causes nor cures
   it. A warning is logged when the two are combined.
4. **`min_res[r] > 0` on a non-critical resource gives a wrong answer, not
   a weaker bound.** The dominance rule assumes that the feasibility of a
   non-critical resource is decided by its upper bound alone, so a strictly
   positive lower bound on such a resource lets the search discard labels
   that are on the way to a feasible path, and the run then reports the
   degenerate `['Source']` for an instance that does have a solution. A
   warning is logged. This is a property of the standard dominance rule and
   applies without `require_all_visits` as well, but with
   `require_all_visits` there is no longer any reason to set such a bound at
   all: coverage is enforced directly and not through a counter resource.
   A lower bound that really is part of the model belongs on the critical
   resource (`critical_res`), where it is handled exactly.
5. **A required node that is not in the graph is rejected, not searched
   for.** Every entry of `required_nodes` is checked against `G` in the
   constructor, and an entry that is not a node of `G` is reported through
   the same collected-exception mechanism as the other argument errors
   (`required_nodes entry 99 is not a node of G`). A node that disappears
   between that check and the translation to internal identifiers — which
   `preprocess=True` could in principle do — is caught separately and
   raises a `KeyError` naming the node and pointing at `preprocess`.
6. **Sink out-edges.** The terminal condition refuses every extension into
   the sink from a label that does not yet cover $R$, so a path that passes
   *through* the sink and continues would be cut. Under `elementary=True`
   no `Source` -> `Sink` path can do that anyway.
7. **Cost, and the practical size limit.** Making dominance stricter keeps
   more labels; the label count is exponential in $|R|$ in the worst case.
   This is the intrinsic difficulty of TSPTW and is the same for the visit
   indicator encoding — what changes is the memory per label and the cost
   of each comparison, not the size of the search tree. On a machine of the
   class this fork is developed on (Apple M1, 8 GB), exact solves of
   randomly generated instances run in well under a second up to roughly
   twelve customers, take seconds to minutes around fourteen to sixteen,
   and become impractical beyond about eighteen. Treat that as the exact
   ceiling and use a heuristic or a decomposition above it.
8. **A truncated search returns the same path as an infeasible instance.**
   When `time_limit` (or `threshold`) stops the search before any complete
   `Source` -> `Sink` path has been accepted, the result is the degenerate
   `['Source']` with `total_cost` unset — byte for byte what a genuinely
   infeasible instance returns. This is pre-existing engine behaviour, but
   `require_all_visits` makes it much easier to hit, because the first
   accepted path is far deeper in the search than in a plain elementary
   shortest path problem. The returned path alone cannot separate the two
   cases; the `termination_reason` property (Section 10) can:
   `'no_feasible_path'` is a proof of infeasibility, while
   `'time_limit_reached'` with a degenerate result means the status is
   unknown. Check it whenever `time_limit` is set.
9. **C++ callers**: `BiDirectional::setRequiredNodes` must be called after
   `addNodes`, takes user ids, rejects the source and the sink, and rejects
   an empty required set. The bit index table is a hash map keyed by user
   id, so its memory is proportional to the number of required nodes and
   not to the largest user id; sparse user id spaces such as
   `{0, 1, 10^9}` cost nothing extra. (The Python layer always passes a
   contiguous `0..n-1` anyway.)
10. **The C# bindings** (`src/cc/dotnet/bidirectional.i`) were not extended;
    `setRequiredNodes` is exposed to Python only.

Because the SWIG interface gained a method, an out-of-date wheel in the
venv shows up as `AttributeError: setRequiredNodes`. Rebuild and reinstall
as in Section 7.

## 10. Stopping as soon as a better solution is found

Exact labelling pays for its optimality proof: most of the running time is
spent proving that no better path exists, long after a good one has been
found. When any solution better than a known value is enough — an incumbent
to beat inside a branching scheme, or a target value in a satisficing
application — the engine's `threshold` argument stops the search at the
first acceptable complete path. This fork adds a strict variant of the
comparison and, more importantly, an answer to the question the caller is
then left with: *why did the search stop?*

| Argument | Type / default | Meaning |
|---|---|---|
| `threshold` | `float` / `None` | Stop the search as soon as a resource-feasible `Source` -> `Sink` path with total cost `<= threshold` is accepted, and return that path. Upstream argument, unchanged |
| `threshold_strict` | `bool` / `False` | **New in this fork.** When true, the comparison becomes strict: stop only on total cost `< threshold`. Pass the value of a known incumbent solution as `threshold` to stop only when a strictly better solution is found — with the default `<=` the incumbent's own value would stop the search immediately, proving nothing. Requires `threshold` to be a number (`None` and `NaN` are rejected); non-`bool` values are rejected |

With `threshold_strict=False` (the default) the behaviour is exactly the
upstream behaviour, bit for bit.

### 10.1 Reading the stop: `termination_reason`

After `run()`, the property `termination_reason` reports why the search
stopped (before `run()` it is `None`):

| Value | Meaning |
|---|---|
| `'completed'` | The search processed every generated label and a `Source` -> `Sink` path was found. This certifies optimality **only when the dominance rule is sound** for the resource extensions in use; the documented exception in this fork is the `window_hard` policy (Section 9.5, restriction 3), where an exhausted search may still have pruned the optimum. The value is deliberately not named `'optimal'` |
| `'threshold_reached'` | A `Source` -> `Sink` path meeting the threshold was found and the search stopped early; that path is the one returned. It is the **first acceptable path encountered, not necessarily the best found so far**: the label queue is ordered by resource consumption, not by cost |
| `'time_limit_reached'` | `time_limit` expired before the search could finish. A complete path found before the limit (if any) is still returned together with this reason; a degenerate result (Section 8, caveat 8) means the instance status is **unknown**, not proven infeasible |
| `'no_feasible_path'` | The search processed every generated label without finding any resource-feasible `Source` -> `Sink` path: the instance is infeasible, under the same dominance-soundness proviso as `'completed'` |

This closes the gap noted in Section 9.5, restriction 8: a genuinely
infeasible instance (`'no_feasible_path'`) and a search truncated before
its first complete path (`'time_limit_reached'` with a degenerate result)
both return the same degenerate path, but are now told apart by the reason.

### 10.2 Threshold and strict threshold on the six-customer TSPTW (executed code)

The instance is the one of Section 9.2, with known optimum 33.

```python
"""Stop the six-customer TSPTW solve of Section 9.2 as soon as a tour
below a target cost is found, and read the reason the search stopped."""
import networkx as nx
import numpy as np
from cspy import BiDirectional

n = 6
travel = ((0, 11, 8, 5, 8, 5, 7), (9, 0, 7, 12, 3, 11, 7), (8, 12, 0, 4, 8, 3, 11),
          (3, 4, 10, 0, 8, 3, 8), (10, 3, 3, 6, 0, 8, 4), (5, 8, 5, 12, 4, 0, 10),
          (8, 4, 7, 5, 12, 4, 0))
tw_a = (0, 39, 2, 38, 32, 2, 42)
tw_b = (200, 59, 18, 60, 57, 13, 60)
service = (0, 6, 2, 4, 5, 3, 1)
horizon = float(tw_b[0])

G = nx.DiGraph(n_res=2)
for i in range(1, n + 1):
    G.add_edge("Source", i, res_cost=np.array([1.0, float(travel[0][i])]),
               weight=float(travel[0][i]))
    G.add_edge(i, "Sink", res_cost=np.array([1.0, float(travel[i][0])]),
               weight=float(travel[i][0]))
    for j in range(1, n + 1):
        if i != j:
            G.add_edge(i, j, res_cost=np.array([1.0, float(travel[i][j])]),
                       weight=float(travel[i][j]))

time_windows = {i: (float(tw_a[i]), float(tw_b[i])) for i in range(1, n + 1)}
service_times = {i: float(service[i]) for i in range(1, n + 1)}
common = dict(direction="forward", elementary=True,
              time_windows=time_windows, service_times=service_times,
              require_all_visits=True)

# (1) Satisficing: accept the first complete tour of cost <= 40.
alg = BiDirectional(G, [float(n + 1), horizon], [0.0, 0.0],
                    threshold=40.0, **common)
print("(1) before run     :", alg.termination_reason)
alg.run()
print("(1) threshold 40   :", alg.termination_reason, "| cost", alg.total_cost,
      "| tour", " -> ".join(str(v) for v in alg.path))

# (2) Improving on a known solution: the optimum of this instance is 33.
#     threshold_strict=True asks for a tour strictly below 33; none exists,
#     so the search runs to exhaustion and proves it.
alg = BiDirectional(G, [float(n + 1), horizon], [0.0, 0.0],
                    threshold=33.0, threshold_strict=True, **common)
alg.run()
print("(2) strict below 33:", alg.termination_reason, "| cost", alg.total_cost)

# (3) Same target without threshold_strict: cost <= 33 is acceptable, so the
#     optimal tour itself stops the search.
alg = BiDirectional(G, [float(n + 1), horizon], [0.0, 0.0],
                    threshold=33.0, **common)
alg.run()
print("(3) at most 33     :", alg.termination_reason, "| cost", alg.total_cost)
```

Output (actual output):

```text
(1) before run     : None
(1) threshold 40   : threshold_reached | cost 33.0 | tour Source -> 2 -> 5 -> 4 -> 1 -> 6 -> 3 -> Sink
(2) strict below 33: completed | cost 33.0
(3) at most 33     : threshold_reached | cost 33.0
```

How to read this. Run (1) asked for any tour of cost at most 40 and the
first accepted tour happened to be the optimum — a coincidence of this
instance, not a guarantee. Run (2) is the intended use of
`threshold_strict`: the incumbent value 33 is passed as the threshold, no
strictly better tour exists, so the search runs to exhaustion, reports
`'completed'`, and still returns the best tour it found. Run (3) shows why
the strict variant is needed: with the default `<=` comparison the
incumbent's own value stops the search at once, which proves nothing about
improvability.

### 10.3 Infeasible or merely truncated? (executed code)

```python
"""Telling a genuinely infeasible instance apart from a search stopped by
the time limit, on the six-customer TSPTW instance of Section 9.2."""
# ... same graph construction as in Section 10.2 ...
common = dict(direction="forward", elementary=True,
              service_times=service_times, require_all_visits=True)

# (1) Genuinely infeasible: a horizon of 50 is too short for any full tour
#     (the optimal tour returns to the depot at time 66). The search runs to
#     exhaustion and proves it.
alg = BiDirectional(G, [float(n + 1), 50.0], [0.0, 0.0],
                    time_windows={i: (float(tw_a[i]), min(float(tw_b[i]), 50.0))
                                  for i in range(1, n + 1)}, **common)
alg.run()
print("(1) horizon 50 :", alg.termination_reason, "| path", alg.path)

# (2) Feasible but stopped immediately by the time limit: the same
#     degenerate path, but the reason says the status is unknown.
alg = BiDirectional(G, [float(n + 1), 200.0], [0.0, 0.0],
                    time_windows=time_windows, time_limit=0.0, **common)
alg.run()
print("(2) time limit :", alg.termination_reason, "| path", alg.path)
```

Output (actual output):

```text
(1) horizon 50 : no_feasible_path | path ['Source']
(2) time limit : time_limit_reached | path ['Source']
```

The returned path is identical in both runs; only `termination_reason`
separates "there is no tour" from "the search never got far enough to say".
Section 9.5, restriction 8 explains why this distinction matters especially
under `require_all_visits`.

### 10.4 Maximisation objectives (executed code)

`BiDirectional` minimises. To stop as soon as a solution **better than a
given value for a maximisation objective** is found, negate every edge
weight and negate the target: a path with original objective value $> X$ is
a path with total (negated) cost $< -X$, so pass `threshold=-X` together
with `threshold_strict=True` (or `threshold=-X` alone for original
objective value $\ge X$). The returned `total_cost` is the negated
objective value of the returned path.

```python
"""Use threshold for a maximisation objective: negate the edge weights and
the target value, and ask for a strictly smaller (negated) cost."""
import networkx as nx
import numpy as np
from cspy import BiDirectional

# Each edge carries a reward; the goal is a path whose total reward is
# larger than a given target. BiDirectional minimises, so store
# weight = -reward and translate "reward > 12" into "cost < -12".
G = nx.DiGraph(n_res=2)
edges = [("Source", "a", 5), ("Source", "b", 3), ("a", "b", 4), ("a", "c", 2),
         ("b", "c", 6), ("c", "Sink", 3), ("b", "Sink", 1), ("a", "Sink", 1)]
for (u, v, reward) in edges:
    G.add_edge(u, v, res_cost=np.array([1.0, 1.0]), weight=float(-reward))

# (1) Stop as soon as a path with total reward > 12 is found.
alg = BiDirectional(G, [10.0, 10.0], [0.0, 0.0], direction="forward",
                    threshold=-12.0, threshold_strict=True)
alg.run()
print("(1) reward > 12 :", alg.termination_reason,
      "| path", alg.path, "| reward", -alg.total_cost)

# (2) An unreachable target: no path has total reward > 18, so the search
#     runs to exhaustion, proves it, and still returns the best path found.
alg = BiDirectional(G, [10.0, 10.0], [0.0, 0.0], direction="forward",
                    threshold=-18.0, threshold_strict=True)
alg.run()
print("(2) reward > 18 :", alg.termination_reason,
      "| path", alg.path, "| reward", -alg.total_cost)
```

Output (actual output):

```text
(1) reward > 12 : threshold_reached | path ['Source', 'a', 'b', 'c', 'Sink'] | reward 18.0
(2) reward > 18 : completed | path ['Source', 'a', 'b', 'c', 'Sink'] | reward 18.0
```

Run (1) stops at the first path whose reward exceeds 12 (here 18). Run (2)
asks for a reward strictly above the optimum 18, so nothing can stop the
search early; it completes, which — under sound dominance — proves that no
better path exists, and the best path found is returned anyway.

### 10.5 Caveats

1. **The returned path is the first acceptable one, not the best so far.**
   The label queue is ordered by resource consumption, not by cost, so a
   `'threshold_reached'` stop returns whichever acceptable path the search
   reached first. For satisficing ("any solution better than X") this is
   exactly right; for "the best solution found within a budget" it is not —
   use `time_limit` and read the returned path as a heuristic solution.
2. **`'completed'` is not spelled `'optimal'` on purpose.** Exhausting the
   label queue certifies optimality only when the dominance rule is sound
   for the resource extensions in use. The documented exception in this
   fork is `window_hard` (Section 9.5, restriction 3); a non-monotone
   custom `REF_callback` would be another. Under the standard additive and
   `window_wait` resources, `'completed'` does mean the returned path is
   optimal.
3. **The time limit takes precedence over the threshold.** Both conditions
   are checked once per iteration of the main loop, time limit first, so a
   run in which both hold at the same iteration reports
   `'time_limit_reached'`. For the same reason a search whose final
   iteration coincides with the limit expiring may report
   `'time_limit_reached'` instead of `'completed'` — conservative, in that
   the reason never overstates how far the search got.
4. **`run()` is single-shot per object.** The internal search state is not
   rebuilt between calls, so a second `run()` on the same object returns a
   degenerate result and its `termination_reason` is meaningless. Build a
   fresh `BiDirectional` object for every solve (the column generation loop
   of Section 6 already does).
5. **`direction='both'` after a timeout is asymmetric.** The label-joining
   step still runs after a timed-out main loop, so a time-limited `both`
   run may return a complete `Source` -> `Sink` path (with
   `'time_limit_reached'`) where `'forward'` or `'backward'` would return
   the degenerate result. Pre-existing engine behaviour; the reason
   reporting does not change it.
6. **Argument validation.** `threshold_strict=True` without a usable
   threshold is rejected in the constructor, with the other collected
   argument errors: `threshold=None` and `threshold=float('nan')` both
   raise `threshold_strict=True requires threshold to be a number` (a `NaN`
   threshold is ignored by the algorithm, so accepting it would silently
   disable the requested strictness), and a non-`bool` value raises
   `threshold_strict must be a bool, got int`.

The C++ side records the reason in an enumeration
(`TerminationReason` in `src/cc/bidirectional.h`, read through
`getTerminationReason()`); the recording is write-only — no search branch
reads it — so default behaviour is unchanged. The regression tests are in
`test/python/tests_termination_reason.py`. As with Section 9, the SWIG
interface gained a method, so an out-of-date wheel in the venv shows up as
`AttributeError: getTerminationReason`; rebuild and reinstall as in
Section 7.

---

*Implementation verification*: every code example in this guide was actually
executed with the Python of the repository's `.venv`, and the output blocks
are verbatim copies of real runs. The implementation itself passes roughly
2600 checks in total, including a bit-identical comparison against a Python
director REF written independently from the PoC-validated formulas and exact
brute-force cross-checking with `Fraction`. The permanent regression tests
are in `test/python/tests_native_time_windows.py` (65 cases, of which 33
cover the mandatory visits of Section 9) and
`test/python/tests_termination_reason.py` (18 cases covering the stopping
features of Section 10); for the primary source of the formulas and
caveats, see `docs/ref.rst`.
