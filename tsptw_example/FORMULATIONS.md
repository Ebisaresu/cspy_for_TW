# Problem Formulations, Notation and Glossary for the Time-Window Fork of cspy

This document states every model the documentation of this fork refers to,
exactly once, and fixes the notation and terminology that the other documents
use. It contains no API tutorial: each formulation ends with a table saying
which cspy arguments realise it, and the tutorials live in the guides listed
below.

Everything asserted here about the implementation was read off the source of
this repository (`src/cc/node_window_ref.cc`, `src/cc/labelling.cc`,
`src/cc/bidirectional.cc`, `src/cc/params.h`,
`src/python/algorithms/bidirectional.py`), and every number in every instance
table was produced by an exhaustive computation with exact rational
arithmetic and cross-checked against a real solver run. Section 7 records how.

---

## 0. Scope, and how the four documents divide the work

| Document | What it is for |
|---|---|
| **This document** | Normative. The notation, the glossary, the mixed integer programs, the dynamic programs, the soundness arguments, and the definition of every instance used anywhere in the documentation |
| [`../README.md`](../README.md) | Orientation: what the fork adds, how to build it, and the shortest possible working example |
| [`TSPTW_GUIDE.md`](./TSPTW_GUIDE.md) | How to write a resource extension function in Python, using the traveling salesman problem with time windows (TSPTW) as the worked example |
| [`NATIVE_TW_GUIDE.md`](./NATIVE_TW_GUIDE.md) | The native C++ features of the fork — per-node resource windows, mandatory visits, early termination — their API, their measurements and their limitations |

Nothing in the three other documents redefines a symbol or a term. When they
need one they name it and link back here. Terms marked `[impl]` in the
glossary are implementation-only: the glossary gives them a one-line gloss so
that a reader meeting them in the README or in a guide is not stranded, and
the full treatment is in `NATIVE_TW_GUIDE.md` Appendix A.

**Reading order for a newcomer.** This is the order every document of this
set prescribes, and they agree:

1. Section 1 of this document — notation and glossary;
2. Section 2 — the resource constrained shortest path problem, model (P0);
3. the README quick starts — the shortest working code;
4. Sections 3 and 4 here — per-node windows (P1) and mandatory visits (P2);
5. [`TSPTW_GUIDE.md`](./TSPTW_GUIDE.md) — writing a resource extension
   function in Python;
6. [`NATIVE_TW_GUIDE.md`](./NATIVE_TW_GUIDE.md) — the native C++ features.

Section 3 must not be skipped before Section 4: (P2) is defined as (P1) plus
one constraint, and it is stated throughout in the constraint labels and the
vocabulary that Section 3 introduces. Readers who only want the pricing
problem of column generation can go from Section 2 straight to Section 5.

**Numbering convention.** The models are labelled (P0) to (P3); their
constraints are numbered (A*) for (P0), (B*) and (H*) for (P1), (C*) for (P2)
and (D*) for (P3). Instances are labelled A to E and are defined in the
sections that use them.

---

## 1. Notation and terminology

The single rule this document enforces is that a symbol is defined before it
is used and means the same thing everywhere. Sections 1.1 to 1.5 define the
symbols, Section 1.6 defines the words, Section 1.7 lists the collisions that
were resolved deliberately, and Section 1.8 maps every symbol to the cspy
identifier that carries it.

### 1.1 Sets and indices

| Symbol | Meaning |
|---|---|
| $o$ | the origin vertex: the start of every path |
| $d$ | the destination vertex: the end of every path |
| $N$ | the set of customer vertices, that is, every vertex other than $o$ and $d$ |
| $V = \{o\} \cup N \cup \{d\}$ | the vertex set of the search digraph |
| $A \subseteq V \times V$ | the arc set |
| $n = \lvert N \rvert$ | the number of customers |
| $i, j, v, u$ | vertex indices, always elements of $V$ |
| $P = (v_0 = o, v_1, \dots, v_p = d)$ | a path; $A(P)$ is its arc set and $V(P)$ its vertex set |
| $\mathcal{R} = \{0, 1, \dots, n_{\mathrm{res}} - 1\}$ | the resource index set |
| $r$ | a resource index, $r \in \mathcal{R}$ |
| $r_{\mathrm{crit}}$ | the index of the critical resource; $0$ by default |
| $r_{\mathrm{time}}$ | the index of the time resource; $1$ by default |
| $R \subseteq N$ | the **required set**: the vertices a feasible path must visit under (P2) |
| $\sigma = (\sigma_1, \dots, \sigma_n)$ | a permutation of $N$: the customer visiting order of a tour |

$\mathcal{R}$ (calligraphic) and $R$ (roman) are different objects; see
Section 1.7, item 1.

### 1.2 Arc data

| Symbol | Meaning |
|---|---|
| $w_{ij}$, $(i,j) \in A$ | the objective coefficient (the **weight**) of arc $(i,j)$; real-valued, and allowed to be negative |
| $t^{(r)}_{ij}$ | the consumption of resource $r$ on arc $(i,j)$ |
| $t_{ij} := t^{(r_{\mathrm{time}})}_{ij} \ge 0$ | the travel time on arc $(i,j)$ |
| $\bar c_{ij}$ | the reduced-cost arc weight used in pricing, $\bar c_{ij} = t_{ij} - \pi_j$ (Section 5) |

$w_{ij}$ and $t_{ij}$ are **independent data**. The objective is
$\sum w_{ij} x_{ij}$ and never $\sum t_{ij} x_{ij}$; Instance B is built so
that the two rank the paths differently, and in Section 5 the weight is a
reduced cost, which is negative on some arcs while travel times are not.

### 1.3 Per-node window data

| Symbol | Meaning |
|---|---|
| $lb_r(v),\ ub_r(v)$ | the **window** of resource $r$ at vertex $v$: the interval within which the value of resource $r$ must lie on arrival at $v$ |
| $a_v := lb_{r_{\mathrm{time}}}(v)$, $b_v := ub_{r_{\mathrm{time}}}(v)$ | the **time window** of $v$: the earliest and latest admissible service start time |
| $c_r(v) \ge 0$ | the **node consumption** of resource $r$ at $v$ |
| $s_v := c_{r_{\mathrm{time}}}(v)$ | the **service time** at $v$ |
| $p_r \in \{\texttt{additive},\ \texttt{window\_wait},\ \texttt{window\_hard}\}$ | the **propagation policy** of resource $r$ |
| $\varepsilon > 0$ | the numerical tolerance used in window comparisons only |
| $\Sigma_r$ | the **rejection sentinel** of resource $r$ |

The timing of the node consumption depends on the policy: under
`additive` it is added on arrival at the head of the arc, under the two window
policies on departure from the tail. Section 3.2 states all three rules.

The sentinel is
$\Sigma_r = \max\bigl(q^{\max}_r + 1,\ \mathrm{nextafter}(q^{\max}_r, +\infty)\bigr)$
— a value deliberately outside the engine's own bound, so that a resource
extension function can reject a label by returning it (a resource extension
function has no other way of saying "reject"). This is why $q^{\max}_r$ must
be finite for a resource carrying a window policy. Here
$\mathrm{nextafter}(x, +\infty)$ is the C library function returning the
smallest representable floating-point number strictly greater than $x$; the
$\max$ with $q^{\max}_r + 1$ covers the case in which $q^{\max}_r$ is so
large that adding $1$ to it rounds back to $q^{\max}_r$ itself.

### 1.4 Resource values and bounds

| Symbol | Meaning |
|---|---|
| $q = (q_0, \dots, q_{n_{\mathrm{res}}-1})$ | the resource vector carried by a label; $q_r$ before an extension, $q'_r$ after |
| $q^{\max}_r$ | the upper bound on resource $r$, checked at every extension |
| $q^{\min}_r$ | the lower bound on resource $r$; see Section 4.6 for exactly when it is checked |
| $H := q^{\max}_{r_{\mathrm{time}}}$ | the **horizon**: the deadline by which every path must reach $d$ |
| $q^{\max}_0$ | the bound on the arc-count resource when $t^{(0)}_{ij} = 1$ on every arc |
| $T_v$ | the value of the **time** resource when the label sits at $v$ |
| $D_v := T_v + s_v$ | the departure time from $v$ |
| $T^{*}_{v_k}$ | the earliest feasible service start time along a fixed path (Section 3.7) |
| $\hat T_v$ | the latest feasible service start time at $v$, used only by the backward search |
| $g_r$ | the reversed-axis value of a window resource carried by a backward label, $g_r = H - \hat T$ |
| $\rho_{ij}$ | the **resource extension function** of arc $(i,j)$: the map sending the resource vector before the extension to the resource vector after it. Stated for (P0) in Section 2.4; its two window variants are written $\rho^{\mathrm{wait}}_{ij}$ and $\rho^{\mathrm{hard}}_{ij}$ in Section 3.2 |

$T$ denotes the **time** resource only; the value of a generic resource is
$q_r$. Under `window_wait` $T_v$ is the service start time at $v$, under
`window_hard` it is the arrival time at $v$; both readings are only valid for
`direction="forward"` (Section 3.10, note 3).

### 1.5 Decision variables of the mixed integer programs

| Symbol | Meaning |
|---|---|
| $x_{ij} \in \{0,1\}$, $(i,j) \in A$ | $1$ if and only if the path uses arc $(i,j)$ |
| $q_{i,r}$, $i \in V$, $r \in \mathcal{R}$ | the value of resource $r$ at vertex $i$ (Section 2.2) |
| $T_i \ge 0$, $i \in V$ | the service start time at $i$; well defined because each vertex is visited at most once |
| $z$ | the objective value, $z = \sum_{(i,j) \in A} w_{ij} x_{ij}$ |
| $\lambda_p \ge 0$, $p \in \Omega$ | the route (column) variable of the set partitioning master problem (Section 5) |
| $M^-_{ij},\ M^+_{ij}$ | the big-M constants that deactivate a time propagation constraint when $x_{ij} = 0$; written $M^{\pm}_{ijr}$ when the resource has to be named |
| $\bar a_i,\ \bar b_i$ | the range within which $T_i$ can move, used to derive the smallest valid $M^-_{ij}, M^+_{ij}$ |

### 1.6 Glossary

Each entry is one sentence, and this is the normative definition. When a guide
first uses a term it repeats a gloss of at most one clause and links here.
Acronyms are given their full name at first use in every document, not only
here.

**bidirectional search** — a labelling search that extends labels forward from
$o$ and backward from $d$ and joins them at the halfway point
(`direction="both"`).

**binding (constraint or bound)** — a constraint that changes the optimal
value, that is, one whose removal would give a better solution.

**branch and price** — branch and bound in which the linear programming
relaxation at every node is solved by column generation.

**capacitated vehicle routing problem with time windows (CVRPTW)** — the
vehicle routing problem with time windows together with a capacity bound per
route.

**column generation** — a linear programming method that starts from a subset
of the variables and repeatedly adds variables of negative reduced cost found
by solving a pricing problem.

**critical resource** — the one resource, index $r_{\mathrm{crit}} = 0$ by
convention, that must be monotone and additive because the bidirectional
search uses its value to decide where the forward and backward searches meet.

**D-convention** — the alternative reporting convention in which the window is
checked on arrival and the reported value is the departure time
$D_v = T_v + s_v$; it is feasibility-equivalent to the convention used here,
and only the reported value shifts by $+s_v$.

**degenerate path** — the result cspy returns instead of raising when no
complete path was accepted: `["Source"]` under forward search, `None` under
`direction="both"`, `["Sink"]` under backward search.

**dominance** — discarding a label $L_2$ because another label $L_1$ at the
same vertex has no larger weight, no larger value in every resource, and
(under elementary search) an unreachable set contained in $L_2$'s.

**dominance rule** — the precise predicate under which one label is allowed to
discard another.

**bit set** `[impl]` — a set of small integers held as the bits of one or more
machine words, so that membership is one bit test and comparison of two sets
is one bitwise operation; how `require_all_visits` stores a label's visited
set (`NATIVE_TW_GUIDE.md` Appendix A).

**downward closed (feasibility test)** — the property that if a value passes
the test then every smaller value passes it too; equivalently, that the
rejection is one-sided, "too large" and never "too small". It is the
hypothesis that makes a smaller resource value always at least as good, and
hence the hypothesis every dominance soundness argument here rests on
(Sections 2.4, 3.9.1); `window_hard` is the policy that violates it
(Section 3.9.2).

**dual price** — the dual variable of a master problem constraint; $\pi_j$ is
the dual of customer $j$'s covering constraint.

**efficient set (of a vertex)** — the collection of non-dominated labels cspy
keeps at one vertex, written $\Lambda(u, \cdot)$ in Section 2.4. Dominance is
tested only between two labels of the *same* vertex's efficient set, never
across vertices, so a vertex reached by exactly one label can never have a
label discarded.

**elementary path** — a path that visits no vertex more than once.

**elementary shortest path problem with resource constraints (ESPPRC)** — the
resource constrained shortest path problem restricted to elementary paths,
which is NP-hard even when all resource extension functions are additive.

**ESPPRC with time windows (ESPPRC-TW)** — the elementary shortest path
problem with resource constraints in which one resource is time and each
vertex carries a time window constraining the service start time.

**extension** — the operation of stretching a label along one arc and
computing the resource vector of the resulting label.

**feasibility check** — the test $q^{\min} \le q \le q^{\max}$ applied to a
label's resource vector after an extension.

**Feillet-style dominance** — the elementary dominance rule of Feillet et al.
(2004), which adds the unreachable-set containment condition to the usual
comparison on cost and resources.

**halfway point** — the value of the critical resource at which the
bidirectional search stops extending forward and backward labels and starts
joining them.

**Hamiltonian path / Hamiltonicity** — a path that visits every vertex of the
graph exactly once; Hamiltonicity is the requirement that a solution be such a
path.

**horizon** — the upper bound $H = q^{\max}_{r_{\mathrm{time}}}$ on the time
resource, that is, the deadline by which every path must reach $d$.

**incumbent** — the best solution known so far, whose value can be passed as a
threshold to stop the search only on a strict improvement.

**join** — the operation of concatenating a forward label and a backward label
across one arc into a complete path.

**keepalive** `[impl]` — a Python reference deliberately attached to an object
so that the garbage collector cannot free it while C++ still holds a raw
pointer to it (`NATIVE_TW_GUIDE.md` Appendix A.6).

**label** — a partial path from $o$ to some vertex, together with the weight
and the resource vector it has accumulated.

**label heap** — the container of labels the search has generated but not yet
extended, ordered by resource consumption and not by weight. Which of two
equally good labels survives, and in what order paths of equal cost are
found, is decided by this order together with the dominance test; neither is
part of the model, so ties must never be read as a claim of uniqueness.

**labelling algorithm** — a dynamic programming method that keeps several
labels per vertex, one per non-dominated combination of resources, and
repeatedly extends them along outgoing arcs.

**linear programming basis** — a set of variables whose columns form a
nonsingular submatrix, determining one basic solution of the linear program.

**mandatory visits** — the requirement that every vertex of a given required
set appear on the returned path.

**monodirectional search** — a labelling search run in one direction only
(`direction="forward"` or `"backward"`).

**non-director class** `[impl]` — a C++ class exposed to Python without SWIG's
director feature, so that its virtual calls stay inside C++ and cross no
language boundary; `NodeWindowREF` is one (`NATIVE_TW_GUIDE.md` Appendix A).

**monotone (additive) resource** — a resource whose value never decreases
along an extension, so that comparing two labels on it is meaningful.

**node consumption** — the quantity $c_r(v)$ that resource $r$ gains because
of vertex $v$; added on arrival at the head under the additive policy, on
departure from the tail under the window policies.

**node window** — the interval $[lb_r(v),\ ub_r(v)]$ within which the value of
resource $r$ must lie when a label arrives at vertex $v$.

**partial path** — the sequence of vertices a label has already traversed,
passed to a Python resource extension function before the extension is applied
(the head vertex is not included).

**pricing problem** — the subproblem solved at each column generation
iteration to find a column of negative reduced cost, or to prove that none
exists.

**propagation policy** — the choice, made per resource, of how that resource's
value is propagated along an arc and of what makes an extension infeasible:
`additive`, `window_wait` or `window_hard`.

**reduced cost** — the rate at which the master objective would change per
unit of a column entering the basis, $c_p$ minus the sum of the dual prices of
the customers the column covers.

**required set** — the set $R$ of vertices that mandatory visits must cover.

**resource constrained shortest path problem (RCSP)** — the problem of finding
a minimum-weight path from a fixed origin to a fixed destination in a digraph
whose arcs consume resources, subject to bounds on the accumulated resource
values.

**resource extension function (REF)** — the function that maps the resource
vector of a label, together with the arc being traversed, to the resource
vector after the extension.

**restricted master problem (RMP)** — the master linear program restricted to
the columns generated so far.

**satisficing** — accepting any solution that meets a target value rather than
proving optimality.

**sentinel value** — a value deliberately placed outside a resource's bounds
by a resource extension function, so that the ordinary feasibility check
rejects the label.

**service time** — the node consumption of the time resource, added on
departure from the tail.

**set partitioning formulation** — a formulation in which each candidate route
is one binary variable and each customer has one constraint requiring that
exactly one selected route covers it.

**soundness (of a pruning or dominance rule)** — the property that the rule
never discards a label that could have led to an optimal solution.

**subtour** — a cycle that is disjoint from the origin-to-destination path; a
formulation that admits subtours needs extra constraints to exclude them.

**SWIG** `[impl]` — the Simplified Wrapper and Interface Generator, the tool
that generates cspy's Python and C# bindings from its C++ headers. A **SWIG
director** `[impl]` is its feature letting a C++ virtual call dispatch into a
Python subclass, which is how a Python resource extension function is invoked
from inside the C++ search loop, and hence the source of its per-call cost
(`NATIVE_TW_GUIDE.md` Appendix A).

**termination reason** — the property reporting why the search stopped:
`'completed'`, `'threshold_reached'`, `'time_limit_reached'` or
`'no_feasible_path'`.

**time window** — the special case of a window on the time resource under the
`window_wait` policy, giving $T_j = \max(a_j,\ T_i + s_i + t_{ij})$, rejected
when $T_j > b_j$.

**traveling salesman problem with time windows (TSPTW)** — the problem of
finding a minimum-cost tour that starts and ends at the depot, visits every
customer exactly once, and serves each customer within its time window.

**unreachable nodes** — the set of vertices a label can no longer visit, used
by the elementary dominance test; it contains the label's visited set and
grows as extensions are found infeasible.

**vehicle routing problem with time windows (VRPTW)** — the problem of
covering every customer exactly once by a set of vehicle routes out of a
common depot, each route respecting the time windows.

**visit counter resource** — an additive resource with consumption $+1$ at
every customer, whose lower bound rejects, at the destination, any path that
has not visited enough customers.

**visit indicator resource (visit flag)** — an additive resource with
consumption $-1$ at one customer, used so that component-wise resource
comparison forces two labels to have visited the same customers before either
may dominate the other.

### 1.7 Collisions resolved deliberately

These pairs look alike and are not. Each is listed once here so that no other
document has to explain it again.

1. **$\mathcal{R}$ versus $R$.** $\mathcal{R}$ (calligraphic) is the resource
   index set; $R$ (roman) is the required set of Section 4. They are unrelated
   objects.
2. **$z(L)$ versus $c_r(v)$.** The accumulated weight of a label is written
   $z(L)$, not $c(L)$, because $c_r(v)$ already denotes a node consumption.
3. **$\sigma$ versus $\pi$.** A tour permutation is $\sigma$; $\pi_j$ is
   reserved for a dual price.
4. **$L$.** $L$ always denotes a label. The latest start time of the backward
   formulas is $\hat T$, and the arc-count bound is $q^{\max}_0$; neither is
   written $L$.
5. **$T$ versus $q_r$.** $T$ is the time resource only. A generic resource
   value is $q_r$, and the policy definitions of Section 3.2 are stated in
   $q_r$ precisely so that they are not read as being about time.
6. **$V$ versus $V(L)$.** $V$ is the vertex set; $V(L)$ is the visited set of
   the label $L$. The argument disambiguates.
7. **$t_{ij}$ versus $w_{ij}$.** Travel time is a resource consumption, weight
   is the objective coefficient; they are independent data (Section 1.2).
8. **$n$ versus $n_{\mathrm{res}}$.** $n$ is the number of customers,
   $n_{\mathrm{res}}$ the number of resources. Neither is abbreviated to the
   other's letter.
9. **$p$.** Three uses, each in its own section and never in the same
   formula. $p_r$ (with a resource subscript) is the propagation policy of
   Section 1.3; $p$ bare is the index of the last vertex of a path
   $P = (v_0, \dots, v_p)$ in Section 1.1; $p \in \Omega$ is a route, that
   is a column index, in Sections 1.5 and 5. Vertices are **never** named
   $p$ or $q$ anywhere in this documentation, precisely so that these do not
   collide with a vertex.
10. **$q$ versus $q_r$ versus $q^{\max}_r$.** $q$ bare is the whole resource
    vector of a label, $q_r$ its $r$-th component, $q^{\max}_r$ and
    $q^{\min}_r$ that component's bounds. All three are resource quantities;
    none of them ever denotes a vertex.

### 1.8 Master symbol-to-code correspondence table

"Python" is the keyword argument of `cspy.BiDirectional` or the attribute of
the object after `run()`; "C++" is the member of the corresponding class where
one exists.

| Symbol | Python | C++ |
|---|---|---|
| $o$, $d$ | the node labels `"Source"` and `"Sink"` of `G` | `graph_ptr_->source`, `graph_ptr_->sink` |
| $N$ | `G.nodes` minus `{"Source", "Sink"}` | — |
| $V$, $A$ | `G.nodes`, `G.edges` | the internal LEMON digraph |
| $n_{\mathrm{res}}$ | `G.graph["n_res"]` | `Params::n_res` implied by the bound vectors |
| $r_{\mathrm{crit}}$ | `critical_res` (default `0`) | `Params::critical_res` (`src/cc/params.h`) |
| $r_{\mathrm{time}}$ | `time_res` (default `1`) | — (a Python-side convenience only) |
| $R$ | `required_nodes` (defaults to $N$ when `require_all_visits=True`) | `Params::required_bit_by_user_id` |
| $w_{ij}$ | the edge attribute `weight` | `AdjVertex::weight` |
| $t^{(r)}_{ij}$ | the edge attribute `res_cost[r]` | `AdjVertex::resource_consumption[r]` |
| $t_{ij}$ | `res_cost[time_res]` | as above |
| $lb_r(v),\ ub_r(v)$ | `node_windows[r][v] = (lb, ub)` | `NodeWindowREF::lb_[r][v]`, `ub_[r][v]` |
| $a_v,\ b_v$ | `time_windows[v] = (a, b)` | as above, at `r = time_res` |
| $c_r(v)$ | `node_consumption[r][v]` | `NodeWindowREF::cons_[r][v]` |
| $s_v$ | `service_times[v]` | as above, at `r = time_res` |
| $p_r$ | `window_policy[r]` (unspecified resources default to `"additive"`) | `NodeWindowREF::policy_[r]` |
| $\varepsilon$ | `window_eps` (default `1e-9`) | `NodeWindowREF::eps_` |
| $\Sigma_r$ | — | `NodeWindowREF::sentinel_[r]` |
| $q_r$ (final) | `consumed_resources[r]` | `getConsumedResources()` |
| $q_r$ (inside a Python resource extension function) | `cumul_res[r]` before, the $r$-th returned entry after | `Label::resource_consumption[r]` |
| $q^{\max}_r,\ q^{\min}_r$ | `max_res[r]`, `min_res[r]` | `BiDirectional::max_res`, `min_res` |
| $H$ | `max_res[time_res]` | as above |
| $q^{\max}_0$ | `max_res[0]` | as above |
| $T_v$ | `consumed_resources[time_res]` (a service start time only under `direction="forward"`) | as above |
| $g_r$ | `consumed_resources[r]` under `direction="backward"` | as above |
| $z$ | `total_cost` | `getTotalCost()` |
| $P$ | `path` | `getPath()` |
| $\rho_{ij}$ | `REFCallback.REF_fwd` | `NodeWindowREF::REF_fwd` / `REF_bwd` / `REF_join` |
| $z(L)$ | the sixth argument of `REF_fwd` (`accummulated_cost`) | `Label::weight` |
| $V(L)$ | `partial_path` (the fifth argument of `REF_fwd`) | `Label::partial_path`, `Label::required_visited_mask` |
| $\theta$ | `threshold` (with `threshold_strict` selecting `<` instead of `<=`) | `Params::threshold`, `threshold_strict` |
| $\Omega$, $c_p$, $\alpha_{jp}$, $\pi_j$ | the teaching code of Section 5: `columns`, `costs`, `A`, `duals` | — |

---

## 2. (P0) The resource constrained shortest path problem

### 2.1 Data and the digraph

An instance of (P0) consists of

- a digraph $(V, A)$ with a distinguished origin $o$ and destination $d$, and
  $N = V \setminus \{o, d\}$;
- an arc weight $w_{ij} \in \mathbb{R}$ for every $(i,j) \in A$;
- a resource index set $\mathcal{R}$ and an arc consumption $t^{(r)}_{ij}$ for
  every arc and every resource;
- bounds $q^{\min}_r \le q^{\max}_r$ for every resource.

**The Source/Sink convention.** cspy always searches for a path from a vertex
literally labelled `"Source"` to a vertex literally labelled `"Sink"`. A
problem whose natural formulation is a tour out of and back into a single
depot is put in this form by **splitting the depot** into $o$ (the depot at
departure, with no incoming arcs) and $d$ (the depot on return, with no
outgoing arcs). Section 4.2 states the resulting correspondence precisely.

**The critical resource.** Resource $r_{\mathrm{crit}}$ (index $0$ by default)
plays a special role: the bidirectional search uses its value to decide where
the forward and the backward search meet, so it must be monotone and additive.
Throughout this documentation resource $0$ is an **arc counter**,
$t^{(0)}_{ij} = 1$ on every arc, whose bound $q^{\max}_0$ therefore limits the
number of arcs on the path. In the vehicle routing setting that bound is the
vehicle capacity in "customers per route" form.

### 2.2 The mixed integer program

$$
\text{(P0)}\qquad \min\ z = \sum_{(i,j) \in A} w_{ij}\, x_{ij}
$$

subject to

$$
\sum_{j\,:\,(o,j)\in A} x_{oj} = 1
\tag{A1}
$$

$$
\sum_{i\,:\,(i,d)\in A} x_{id} = 1
\tag{A2}
$$

$$
\sum_{i\,:\,(i,k)\in A} x_{ik} \;=\; \sum_{j\,:\,(k,j)\in A} x_{kj}
\qquad \forall k \in N
\tag{A3}
$$

$$
q_{o,r} = 0 \qquad \forall r \in \mathcal{R}
\tag{A4}
$$

$$
q_{i,r} + t^{(r)}_{ij} - M^-_{ijr}\,(1 - x_{ij}) \;\le\; q_{j,r} \;\le\;
q_{i,r} + t^{(r)}_{ij} + M^+_{ijr}\,(1 - x_{ij})
\qquad \forall (i,j) \in A,\ \forall r \in \mathcal{R}
\tag{A5}
$$

$$
q^{\min}_r \;\le\; q_{j,r} \;\le\; q^{\max}_r
\qquad \forall j \in V,\ \forall r \in \mathcal{R}
\tag{A6}
$$

$$
x_{ij} \in \{0,1\},\qquad q_{i,r} \in \mathbb{R}
\tag{A7}
$$

(A1)–(A3) say that $x$ is the incidence vector of a walk from $o$ to $d$ plus
possibly some cycles. (A5) forces $q_{j,r}$ to equal
$q_{i,r} + t^{(r)}_{ij}$ on every used arc and is deactivated on every unused
arc by big enough constants $M^{\pm}_{ijr}$; Section 3.4 derives the smallest
valid ones for the time-window version, and the same derivation applies here
with $s_i = 0$ and $[\bar a_i, \bar b_i] = [q^{\min}_r, q^{\max}_r]$.
(A6) imposes the resource bounds **at every vertex**, which is what the engine
does (it checks feasibility after every extension), not only at $d$.

**Remark (when checking at $d$ alone would be equivalent).** If
$t^{(r)}_{ij} \ge 0$ on every arc then $q_{\cdot,r}$ is non-decreasing along
the path, so the upper bound in (A6) binds only at $d$ and the lower bound is
implied by $q^{\min}_r \le 0$. Under those two hypotheses (A6) may be replaced
by $q^{\min}_r \le q_{d,r} \le q^{\max}_r$ without changing the feasible set.
When they fail, the two formulations genuinely differ, and cspy implements
(A6) with one documented exception stated in Section 4.6.

### 2.3 The elementary variant (ESPPRC)

Adding

$$
\sum_{i\,:\,(i,k)\in A} x_{ik} \;\le\; 1 \qquad \forall k \in N
\tag{A8}
$$

restricts the feasible set to **elementary paths**. Three things change.

1. The cycles that (A1)–(A3) alone would admit are excluded (Section 3.6
   discusses this in detail for the time-window model).
2. The problem becomes NP-hard, even with purely additive resources.
3. The dominance rule of the labelling algorithm gains the unreachable-set
   containment condition of Feillet et al. (2004) (Section 2.4).

Without (A8) the problem is solvable in pseudo-polynomial time but a negative
weight cycle makes it unbounded; cspy warns when `elementary=True` is set on
an instance in which it found no negative cost cycle, since (A8) is then
merely making the search harder.

### 2.4 The dynamic program

A **label** is a tuple $L = (v,\ V(L),\ q(L),\ z(L))$ recording a partial path
from $o$ to $v$, the set of vertices on it, the resource vector it has
accumulated, and the weight it has accumulated. Write
$S := V(L) \cap N$ for the customers it has visited.

**Initial label.**
$L_0 = (o,\ \{o\},\ 0,\ 0)$: cspy always starts a forward label with a
resource vector of zeros, which is why an instance with $a_o > 0$ needs the
Source clamp of Section 3.2.

**Extension.** For an arc $(v,u) \in A$ with $u \notin V(L)$ (under (A8)),

$$
L' = \bigl(u,\ V(L) \cup \{u\},\ \rho_{vu}(q(L)),\ z(L) + w_{vu}\bigr),
$$

where $\rho_{vu}$ is the resource extension function. For (P0) it is additive,
$\rho_{vu}(q)_r = q_r + t^{(r)}_{vu}$; Section 3.2 gives the two window
variants.

**Feasibility.** $L'$ survives if
$q^{\min}_r \le \rho_{vu}(q(L))_r \le q^{\max}_r$ for every $r$ (with the
proviso of Section 4.6 on the lower bounds).

**Dominance.** For two labels $L_1, L_2$ at the same vertex,

$$
L_1 \preceq L_2
\quad:\Longleftrightarrow\quad
z(L_1) \le z(L_2)
\ \wedge\
q(L_1) \le q(L_2)\ \text{component-wise}
\ \wedge\
U(L_1) \subseteq U(L_2),
$$

where $U(L) \supseteq V(L)$ is the label's **unreachable set**: its visited
set together with the vertices whose direct extension from $L$ was found
infeasible. The last conjunct is present only under (A8); it is the condition
of Feillet et al. (2004). When $L_1 \preceq L_2$ and the two labels are not
identical, $L_2$ is discarded. Write $\mathrm{ND}[\cdot]$ for the operator
that discards every dominated element of a set of labels.

**Remark (why $U$ and not $V$).** The identity that makes $U$ usable is:

> if the resource extension functions are monotone and the feasibility test is
> **downward closed** — that is, if whenever a value passes the test every
> smaller value passes it too, so that rejection is only ever "too large" and
> never "too small" — then a vertex whose *direct* extension from $L$ is
> infeasible cannot appear on *any* feasible completion of $L$,

because reaching it later gives resource values that are no smaller. Under
those two hypotheses, $V(Q) \cap U(L) = \emptyset$ for every feasible
completion $Q$ of $L$, which is exactly what the soundness proofs of
Sections 3.9.1 and 4.4 need. Section 3.9.2 exhibits what goes wrong when the
second hypothesis fails.

**Recursion.** Let $\Lambda(u, S)$ be the set of non-dominated labels sitting
at $u$ with customer set $S$. Then $\Lambda(o, \emptyset) = \{L_0\}$ and

$$
\Lambda(u, S) \;=\; \mathrm{ND}\Bigl[\;\bigcup_{v\,:\,(v,u)\in A}
\bigl\{\ \text{the extension of } L \text{ along } (v,u)
\ \big|\ L \in \Lambda\bigl(v,\ S \setminus \{u\}\bigr),
\ \text{the extension is feasible} \bigr\}\Bigr],
$$

with $S \setminus \{u\}$ read as $S$ when $u \in \{o, d\}$. The optimal value
is

$$
z^{*} \;=\; \min\bigl\{\ z(L)\ \big|\ L \in \Lambda(d, S),\ S \subseteq N\ \bigr\}.
$$

**Why the arc count need not be part of the state.** When
$t^{(0)}_{ij} = 1$ on every arc, every label in $\Lambda(u, S)$ has the same
arc count, namely $q_0 = \lvert S \rvert + \mathbf{1}[u = d]$: a label at a
customer has already counted that customer in $S$, a label at $d$ has one arc
more than customers, and a label at $o$ has $q_0 = \lvert S \rvert = 0$. The
indicator is necessary — writing $\lvert S \rvert + 1$ would be wrong at every
customer vertex.

### 2.5 Equivalence of the two formulations

**Proposition.** Let $\mathcal{P}$ be the set of elementary $o$–$d$ paths and,
for $P \in \mathcal{P}$, let $q^P$ be the resource vector obtained by applying
$\rho$ along $P$. Then

$$
\min_{x \text{ feasible for (P0)+(A8)}} \sum_{(i,j)\in A} w_{ij} x_{ij}
\;=\;
\min\Bigl\{\ \textstyle\sum_{(i,j) \in A(P)} w_{ij}
\ \Big|\ P \in \mathcal{P},\ q^P \text{ satisfies the bounds at every prefix}\Bigr\},
$$

and the right-hand side equals the value $z^{*}$ of Section 2.4 **with
$\mathrm{ND}$ replaced by the identity**.

*Proof sketch.* An $x$ satisfying (A1)–(A3) and (A8) decomposes into an
elementary $o$–$d$ path together with cycles that are vertex-disjoint from it
and from each other; Section 3.6 shows that (A4)–(A6) exclude those cycles
whenever some resource has strictly positive consumption on every arc, which
is the case here because resource $0$ is the arc counter. So the $x$ feasible
for (P0)+(A8) are exactly the incidence vectors of elementary $o$–$d$ paths.
For such an $x$, (A4)–(A5) determine $q_{\cdot,r}$ uniquely along the path,
and that determined value is the one $\rho$ produces; (A6) is then exactly the
prefix feasibility condition. The objective coincides term by term, and the
unpruned recursion of Section 2.4 enumerates exactly the feasible prefixes.
$\square$

This proposition **does not use dominance**. Whether the pruned search — the
one cspy actually runs — also attains $z^{*}$ is a separate question, and its
answer is: yes, provided the dominance rule is sound. Section 3.9 shows that
soundness holds for `additive` and `window_wait` resources and **fails** for
`window_hard`.

### 2.6 Solving (P0) with cspy

| Symbol / requirement | Argument | Notes |
|---|---|---|
| $(V, A)$ | `G` | a `networkx.DiGraph` containing nodes named `"Source"` and `"Sink"` |
| $n_{\mathrm{res}}$ | `G.graph["n_res"]` | the length every `res_cost` array must have |
| $w_{ij}$ | edge attribute `weight` | required on every edge |
| $t^{(r)}_{ij}$ | edge attribute `res_cost` | an array of length `n_res`, required on every edge |
| $q^{\max}_r$, $q^{\min}_r$ | `max_res`, `min_res` | positional arguments 2 and 3 |
| (A8) | `elementary=True` | default `False` |
| $r_{\mathrm{crit}}$ | `critical_res` | default `0`; `find_critical_res=True` picks it automatically and cannot be combined with any resource extension function |
| the search direction | `direction` | `"both"` (default), `"forward"` or `"backward"` |

Results: `path` (a list of the original node labels), `total_cost` ($z$),
`consumed_resources` (the vector $q$ at the end of the path), and
`termination_reason` (Section 6.2). **When no complete path was accepted, cspy
returns a degenerate path rather than raising** — see the glossary entry, and
check the result before using it.

**Two further pruning mechanisms, both off by default.** The bidirectional
halfway-point cut-off applies only when `direction="both"`, so a forward or
backward search explores everything dominance does not discard. And
`bounds_pruning=True` adds a cut on the weight: a partial path is discarded
when its accumulated weight plus a **lower bound on the weight of any
completion** already exceeds the best known complete path. The bound used is
the shortest-path distance in the weights alone, ignoring all resources.

**This fork repairs `bounds_pruning`.** Upstream the option did not work, for
two reasons, the first hiding the second.

1. The Python wrapper forwarded the option to C++ only when it was `False`,
   so `bounds_pruning=True` was a **silent no-op**: the argument was accepted
   and nothing changed.
2. Underneath, `runPreprocessing` passed the two lower-bound directions
   swapped. The forward search needs the cost-to-go *to the sink* in order to
   complete a forward partial path, and received the distance *from the
   source* instead (and symmetrically for the backward search). With bug 1
   fixed and bug 2 still present, the cut removes optimal labels: on the
   random instance recorded in the fix, the run returned 11 against the true
   optimum 9.

Both are fixed here (`src/python/algorithms/bidirectional.py` and
`src/cc/bidirectional.cc`), and the result was checked against brute-force
enumeration of every simple $o$–$d$ path on 60 random instances in each of
the three directions: with the fixes, `bounds_pruning=True` and
`bounds_pruning=False` return the exact optimum everywhere. The regression
test is `test/python/tests_bounds_pruning.py`, which fails on either bug
alone. The option is still `False` by default, its Python docstring still
carries upstream's "experimental" note, and every soundness statement in this
document is stated for the default setting.

### 2.7 Instance A

This is the instance of the README quick start. Five vertices, six arcs, two
resources: an arc counter and one generic additive resource.

**Arc data.**

| arc $(i,j)$ | $t^{(0)}_{ij}$ | $t^{(1)}_{ij}$ | $w_{ij}$ |
|---|---:|---:|---:|
| $(o, A)$ | 1 | 2 | 0 |
| $(A, B)$ | 1 | 0.3 | 0 |
| $(A, C)$ | 1 | 0.1 | 0 |
| $(B, C)$ | 1 | 3 | −10 |
| $(B, d)$ | 1 | 2 | 10 |
| $(C, d)$ | 1 | 10 | 0 |

**Bounds.** $q^{\max} = (4,\ 20)$, $q^{\min} = (1,\ 0)$. There are no windows,
no service times and no coverage requirement; every resource is `additive`.

**All $o$–$d$ paths.** The digraph is acyclic and there are exactly three.

| path | $q_0$ (arcs) | $q_1$ | $z$ | feasible |
|---|---:|---:|---:|---|
| $o \to A \to B \to d$ | 3 | 4.3 | 10 | yes |
| $o \to A \to C \to d$ | 3 | 12.1 | 0 | yes |
| $o \to A \to B \to C \to d$ | 4 | 15.3 | −10 | yes |

**Optimum.** $z^{*} = -10$, attained uniquely by
$o \to A \to B \to C \to d$ with $q = (4,\ 15.3)$. It is optimal because it is
the only path using the single negative arc $(B,C)$, and it stays feasible:
its four arcs meet $q^{\max}_0 = 4$ exactly, so the arc bound is **binding**.
Lowering $q^{\max}_0$ to 3 would make the optimum $z^{*} = 0$ on
$o \to A \to C \to d$. All three paths satisfy $q_0 \ge q^{\min}_0 = 1$, so
that bound is not binding.

cspy returns exactly this (`.venv/bin/python3`, `direction="both"`, which is
the default, and `elementary` left at its default `False` — the digraph is
acyclic, so (A8) would change nothing):

```text
['Source', 'A', 'B', 'C', 'Sink'] -10.0 [4.0, 15.3]
```

---

## 3. (P1) Per-node resource windows

### 3.1 The generalisation

(P1) extends (P0) by attaching to every resource $r$

- a **propagation policy** $p_r$, and
- for every vertex $v$, a **window** $[lb_r(v),\ ub_r(v)]$ and a **node
  consumption** $c_r(v) \ge 0$.

Time windows are the special case
$p_{r_{\mathrm{time}}} = \texttt{window\_wait}$,
$lb_{r_{\mathrm{time}}}(v) = a_v$, $ub_{r_{\mathrm{time}}}(v) = b_v$,
$c_{r_{\mathrm{time}}}(v) = s_v$. The critical resource is **required** to
keep the `additive` policy with $c_{r_{\mathrm{crit}}} \equiv 0$, because the
bidirectional search assumes it is monotone; anything else is rejected in the
constructor.

Vertices not mentioned in `node_windows` receive the default window
$[0,\ q^{\max}_r]$, and vertices not mentioned in `node_consumption` receive
$c_r(v) = 0$. In particular $o$ and $d$ get $[a_o, b_o] = [a_d, b_d] = [0, H]$
and $s_o = s_d = 0$ unless they are listed explicitly.

### 3.2 The three policies as resource extension functions

Let the label sit at $i$ with resource value $q_r$, and let the extension be
along $(i,j)$. Write $q'_r$ for the value after the extension. For the two
window policies, $q_r$ is first replaced by $\max(q_r,\ lb_r(o))$ **when
$i = o$** (the Source clamp: a label's initial resource vector is zero, so
without this an instance with $lb_r(o) > 0$ would start below its own window).

| Policy | $q'_r$ | The extension is rejected when |
|---|---|---|
| `additive` | $q_r + t^{(r)}_{ij} + c_r(j)$ | the engine's own check $q^{\min}_r \le q'_r \le q^{\max}_r$ fails |
| `window_wait` | $\rho^{\mathrm{wait}}_{ij}(q_r) = \max\bigl(lb_r(j),\ q_r + c_r(i) + t^{(r)}_{ij}\bigr)$ | $q'_r > ub_r(j) + \varepsilon$ |
| `window_hard` | $\rho^{\mathrm{hard}}_{ij}(q_r) = q_r + c_r(i) + t^{(r)}_{ij}$ | $q'_r < lb_r(j) - \varepsilon$ or $q'_r > ub_r(j) + \varepsilon$ |

Three points deserve emphasis.

- **Where the node consumption is added differs by policy.** Under `additive`
  it is $c_r(j)$, the consumption of the **head**, added on arrival; under the
  window policies it is $c_r(i)$, the consumption of the **tail**, added on
  departure. The window policies are stated this way because the natural
  reading of a time window is "service may start at $T_j$", and service at $i$
  must finish before the vehicle leaves $i$.
- **Rejection is expressed by returning the sentinel $\Sigma_r$**, which the
  engine's ordinary check $q'_r \le q^{\max}_r$ then rejects. A resource
  extension function has no other way to say "reject".
- **The tolerances are asymmetric.** The window comparisons carry
  $\varepsilon$; the engine's comparisons against $q^{\max}_r$ and
  $q^{\min}_r$ are exact. A solution sitting exactly on the horizon therefore
  falls on the infeasible side.

Under `window_wait` on the time resource this is exactly

$$
T_j = \max\bigl(a_j,\ T_i + s_i + t_{ij}\bigr),
\qquad \text{rejected when } T_j > b_j,
$$

with $T_v$ the **service start time** at $v$. Under `window_hard` it is
$T_j = T_i + s_i + t_{ij}$, rejected unless $a_j \le T_j \le b_j$, with $T_v$
the **arrival time** at $v$: early arrival is refused instead of waited out.

An alternative convention, the **D-convention**, checks the window on arrival
and reports the departure time $D_v = T_v + s_v$. It is feasibility-equivalent
for the same data; only the reported value shifts by $+s_v$. This fork does
not use it, and the distinction matters only when comparing against another
code's output.

### 3.3 The mixed integer program of a `window_wait` resource

Written for the time resource; the same constraints with $q$, $lb_r$, $ub_r$,
$c_r$ in place of $T$, $a$, $b$, $s$ formulate any `window_wait` resource.
Resource $0$ is the arc counter.

$$
\text{(P1)}\qquad \min\ z = \sum_{(i,j) \in A} w_{ij}\, x_{ij}
$$

subject to

$$
\sum_{j\,:\,(o,j)\in A} x_{oj} = 1
\tag{B1}
$$

$$
\sum_{i\,:\,(i,d)\in A} x_{id} = 1
\tag{B2}
$$

$$
\sum_{i\,:\,(i,k)\in A} x_{ik} \;=\; \sum_{j\,:\,(k,j)\in A} x_{kj} \;\le\; 1
\qquad \forall k \in N
\tag{B3}
$$

$$
T_o = a_o
\tag{B4}
$$

$$
T_j \;\ge\; T_i + s_i + t_{ij} \;-\; M^-_{ij}\,(1 - x_{ij})
\qquad \forall (i,j) \in A
\tag{B5}
$$

$$
a_j \;\le\; T_j \;\le\; \min\{b_j,\ H\}
\qquad \forall j \in V
\tag{B6}
$$

$$
\sum_{(i,j) \in A} x_{ij} \;\le\; q^{\max}_0
\tag{B7}
$$

$$
x_{ij} \in \{0,1\},\qquad T_i \ge 0 .
\tag{B8}
$$

The equality in (B3) is flow conservation and the $\le 1$ is (A8), elementarity.
(B4) fixes the departure time from the origin; (B5) is the linearisation of
$T_j = \max(a_j,\ T_i + s_i + t_{ij})$, whose $\max$ is expressed jointly with
the lower bound $a_j \le T_j$ of (B6); (B7) is the arc-count bound
$q_{d,0} \le q^{\max}_0$ written out, using $t^{(0)}_{ij} = 1$.

The other resources, if any, are governed by (A4)–(A6) of Section 2.2
unchanged.

### 3.4 The big-M constants

(B5) must be inactive when $x_{ij} = 0$. Let $[\bar a_i,\ \bar b_i]$ be the
range within which $T_i$ can move. Under (B4) and (B6),

$$
\bar a_i = a_i \quad (\forall i \in V),
\qquad
\bar b_o = a_o,
\qquad
\bar b_i = \min\{b_i,\ H\} \quad (i \ne o).
$$

**Proposition.** The choice

$$
M^-_{ij} \;=\; \max\bigl\{0,\ \bar b_i + s_i + t_{ij} - \bar a_j\bigr\}
$$

is valid, and it is the smallest valid constant of this form.

*Proof.* Validity: when $x_{ij} = 0$ the right-hand side of (B5) is at most

$$
\bar b_i + s_i + t_{ij} - M^-_{ij}
= \min\bigl\{\bar b_i + s_i + t_{ij},\ \bar a_j\bigr\}
\le \bar a_j \le T_j ,
$$

so (B5) is implied by (B6) and constrains nothing. Minimality: any
$M < \bar b_i + s_i + t_{ij} - \bar a_j$ leaves the pair
$(T_i, T_j) = (\bar b_i, \bar a_j)$, which (B6) admits, violating (B5) with
$x_{ij} = 0$; and $M^-_{ij} \ge 0$ is needed because (B5) with $x_{ij} = 1$
must stay meaningful. $\square$

Using $b_i$ instead of $\min\{b_i, H\}$ keeps validity but loses minimality on
instances where some $b_i > H$. A coarse uniform alternative is

$$
M \;=\; H + \max_{(i,j) \in A}\,(s_i + t_{ij}),
$$

valid because $\bar b_i \le H$ and $\bar a_j \ge 0$. On Instance B it equals
$20 + 5 = 25$, against per-arc values between 0 and 16 (Section 3.11).

A constant $M^-_{ij} = 0$ is not an error: it says that
$T_i + s_i + t_{ij} \le a_j \le T_j$ holds whatever $x$ does, so there is
nothing to deactivate.

### 3.5 Imposing (B6) everywhere versus on visited vertices only

(B6) is written $\forall j \in V$, so it constrains $T_j$ even at vertices the
path does not visit. Usually this changes nothing:

> **If every window is non-empty, that is $a_j \le \min\{b_j, H\}$ for every
> $j \in V$, then imposing (B6) on all vertices and imposing it only on
> visited vertices give the same set of feasible $x$.**

The reason is the choice of $M^-_{ij}$: on an unused arc (B5) is vacuous, so
an unvisited $j$ has $T_j$ constrained by (B6) alone and can always be given a
value in the non-empty interval $[a_j,\ \min\{b_j, H\}]$.

There is one case where the two differ. **If some vertex has an empty window**
($a_j > \min\{b_j, H\}$), the all-vertices form makes the whole mixed integer
program infeasible even when a feasible path avoiding that vertex exists —
and cspy does return that path. The exactly equivalent restatement is

$$
a_j \sum_{i\,:\,(i,j)\in A} x_{ij} \;\le\; T_j \;\le\;
\min\{b_j,\ H\}\, \sum_{i\,:\,(i,j)\in A} x_{ij}
\qquad \forall j \in N,
$$

with (B4) covering $o$ and (B2) covering $d$. Note that this changes the range
of $T_j$ for $j \in N$ to $[0,\ \min\{b_j,H\}]$, so the big-M constants of
Section 3.4 must be recomputed with $\bar a_j = 0$ for $j \in N$. Every
instance in this documentation has non-empty windows, so the simpler (B6) is
used throughout.

### 3.6 Subtours are excluded automatically

(B1)–(B3) alone do **not** exclude subtours, and it is worth being precise
about what does. An $x$ satisfying (B1)–(B3) decomposes into one elementary
$o$–$d$ path plus a (possibly empty) collection of cycles; the $\le 1$ of (B3)
forces those cycles to be vertex-disjoint from the path and from each other,
but it does not forbid them. A cycle on vertices the path never touches
satisfies (B1)–(B3) perfectly well.

What kills them is the **time propagation**. Suppose every arc of a cycle $C$
carries $x_{ij} = 1$. Then (B5) has its big-M term switched off on all of
them, so $T_j \ge T_i + s_i + t_{ij}$ around the whole cycle. Summing over
$C$, the $T$ terms telescope away and

$$
0 \;\ge\; \sum_{(i,j) \in C} (s_i + t_{ij}) ,
$$

which is a contradiction as soon as $s_i + t_{ij} > 0$ on at least one arc of
$C$ and $\ge 0$ on the others. Every instance in this documentation has
$t_{ij} > 0$ on every arc.

**Proposition.** Let $r$ be a resource governed by the propagation
constraints (A4)–(A6) with $t^{(r)}_{ij} > 0$ on every arc. Then no feasible
$x$ contains a cycle.

*Proof.* On a cycle all of whose arcs have $x_{ij} = 1$, (A5) forces
$q_{j,r} = q_{i,r} + t^{(r)}_{ij}$ on every arc; summing around the cycle the
$q$ terms telescope and give $0 = \sum_C t^{(r)}_{ij} > 0$. $\square$

**Which resource supplies the hypothesis differs between the two models, and
the difference matters.**

- In **(P0)** every resource is governed by (A4)–(A6), so the arc counter
  $t^{(0)}_{ij} = 1$ used throughout this documentation supplies it
  immediately.
- In **(P1)** resource $0$ is *not* governed by (A4)–(A6): Section 3.3
  replaces them by the single cardinality bound (B7),
  $\sum_{(i,j)} x_{ij} \le q^{\max}_0$, which a disjoint cycle can satisfy
  whenever the arc budget is slack — and it usually is, Instance B having
  $q^{\max}_0 = 10$ against a three-arc optimum. In (P1) cycle exclusion
  therefore rests **entirely on (B5)**, and hence on
  $s_i + t_{ij} > 0$ on every arc of the cycle, exactly as the telescoping
  argument above derives. Every instance in this documentation has
  $t_{ij} > 0$ on every arc, so the hypothesis holds; an instance with a
  zero-travel-time, zero-service-time cycle would need it restored, either by
  putting resource $0$ back under (A4)–(A6) or by adding subtour elimination
  constraints explicitly.

Under that hypothesis **no Miller–Tucker–Zemlin constraints are needed** —
the classical auxiliary-variable subtour elimination constraints
$u_i - u_j + \lvert V \rvert x_{ij} \le \lvert V \rvert - 1$, which introduce
one continuous variable $u_i$ per vertex to forbid cycles. The time
propagation already does their work, with $T$ playing the role of $u$.

Note that this argument does not use the $\le 1$ of (B3), so it survives
dropping (A8) to obtain the non-elementary relaxation.

### 3.7 $T$ is not unique, and what cspy reports

(B5) and (B6) only bound $T$ from below along the path — a vehicle may always
wait longer than it has to. So a feasible $x$ admits many feasible $T$. Three
observations settle what this does and does not affect.

**Feasibility depends only on the earliest start times.** For a fixed path
$P = (v_0 = o, v_1, \dots, v_p = d)$ define

$$
T^{*}_{v_0} = a_o,
\qquad
T^{*}_{v_k} = \max\bigl(a_{v_k},\ T^{*}_{v_{k-1}} + s_{v_{k-1}} + t_{v_{k-1} v_k}\bigr).
$$

$T^{*}$ is the component-wise minimum of the set of $T$ satisfying (B4)–(B6)
along $P$; hence that set is non-empty **if and only if**
$T^{*}_{v_k} \le \min\{b_{v_k}, H\}$ for every $k$. Waiting longer can only
hurt.

**The objective is unaffected**, because $z$ does not involve $T$.

**cspy reports $T^{*}$.** Under `direction="forward"` with a `window_wait`
time resource, `consumed_resources[time_res]` is exactly $T^{*}_d$, since the
resource extension function computes the recursion above step by step. To
reproduce that number from the mixed integer program one must minimise
$\sum_{i \in V} T_i$ lexicographically **after** minimising $z$; minimising
$z$ alone leaves $T$ undetermined.

### 3.8 `window_hard`: no waiting

Under `window_hard` the value is the arrival time and an early arrival is
rejected. Replace (B5) by the pair

$$
T_j \;\ge\; T_i + s_i + t_{ij} \;-\; M^-_{ij}\,(1 - x_{ij})
\qquad \forall (i,j) \in A
\tag{H1}
$$

$$
T_j \;\le\; T_i + s_i + t_{ij} \;+\; M^+_{ij}\,(1 - x_{ij})
\qquad \forall (i,j) \in A
\tag{H2}
$$

and keep (B1)–(B4), (B6)–(B8). $M^-_{ij}$ is as in Section 3.4, and

$$
M^+_{ij} \;=\; \max\bigl\{0,\ \bar b_j - \bar a_i - s_i - t_{ij}\bigr\}
$$

is valid and smallest of its form, by the mirror image of the proof in
Section 3.4: when $x_{ij} = 0$,

$$
T_i + s_i + t_{ij} + M^+_{ij}
\ \ge\ \bar a_i + s_i + t_{ij} + M^+_{ij}
= \max\bigl\{\bar a_i + s_i + t_{ij},\ \bar b_j\bigr\}
\ \ge\ \bar b_j \ \ge\ T_j .
$$

(H1)+(H2) pin $T$ down uniquely along the path, so the lower bound
$a_j \le T_j$ of (B6), which under `window_wait` merely permitted waiting, now
becomes a genuine **no-early-arrival constraint** at every visit. That is what
"no waiting" means as a mixed integer program.

**(B4) is essential here.** If $T_o$ were a free variable, a path could be
made feasible by leaving the origin late. On Instance B, releasing (B4) would
let the solver depart at time 3 and arrive at customer 2 at
$3 + 0 + 5 = 8 = a_2$, making $o \to 2$ feasible — which contradicts what cspy
does, since a forward label starts with a resource vector of zeros and the
Source clamp only raises it to $\max(0, a_o) = 0$.

`window_hard` is restricted to `direction="forward"`. A backward label can
only propagate an upper bound on the value (Section 3.10, note 3), so it
cannot certify a no-waiting lower bound; the constructor refuses the
combination rather than returning a wrong answer.

### 3.9 Soundness of dominance, by policy

Recall (Section 2.5) that the equivalence between the mixed integer program
and the dynamic program does not use dominance. Whether the **pruned** search
attains the same value is exactly the question of whether the dominance rule
is sound, and the answer depends on the policy.

#### 3.9.1 `additive` and `window_wait`: sound

Two properties suffice.

1. **Monotonicity.** $\rho^{\mathrm{wait}}_{ij}$ is non-decreasing in $q_r$
   (a composition of $\max$ and addition), as is the additive rule.
2. **Downward closedness of the feasible set.** The rejection test is
   one-sided, $q'_r > ub_r(j) + \varepsilon$ (and $q'_r > q^{\max}_r$). So if
   an extension is feasible from some value, it is feasible from every smaller
   value.

Let $L_1 \preceq L_2$ and let $Q$ be any feasible completion of $L_2$ to $d$.
By 1 and 2, $Q$ is feasible from $L_1$ as well and yields resource values no
larger at every vertex; $Q$ stays elementary because the remark of Section 2.4
gives $V(Q) \cap U(L_2) = \emptyset$ and $V(L_1) \subseteq U(L_1) \subseteq
U(L_2)$, so $Q$ avoids everything $L_1$ has already used; and weights are
additive, so $z(L_1) + z(Q) \le z(L_2) + z(Q)$. Discarding $L_2$ therefore
cannot lose an optimal solution. This is the standard soundness argument for
the elementary shortest path problem with resource constraints, and cspy's
containment condition $U(L_1) \subseteq U(L_2)$ is the standard Feillet-style
strengthening of it.

#### 3.9.2 `window_hard`: **not** sound in general

Monotonicity still holds — $\rho^{\mathrm{hard}}_{ij}$ is plain addition — but
**downward closedness fails**, because the rejection test is two-sided:
arriving too early is refused. So "a smaller $q_r$ is at least as good" is
false, and the component-wise comparison on a `window_hard` resource is not a
valid dominance criterion.

**A counterexample on which cspy actually returns a suboptimal path.** Six
vertices, nine arcs, two resources (arc counter and time, the latter under
`window_hard`), all service times zero, $q^{\max} = (10, 20)$,
$q^{\min} = (0,0)$, `elementary=True`, `direction="forward"`.

The four customer vertices are named $u_1, u_2, y, \bar y$. They are named
that way and not $p, q, v, w$ because $p_r$ is a propagation policy, $q$ is
the resource vector, $v$ is the generic vertex index and $w_{ij}$ is the arc
weight (Section 1.7); the vertex names here must collide with none of them.
In the executed code they are the node labels `"u1"`, `"u2"`, `"y"`,
`"ybar"`.

| arc | $t_{ij}$ | $w_{ij}$ |
|---|---:|---:|
| $(o, u_1)$ | 1 | 0 |
| $(o, u_2)$ | 2 | 0 |
| $(u_1, u_2)$ | 1 | 0 |
| $(u_2, u_1)$ | 1 | 0 |
| $(u_1, y)$ | 1 | 0 |
| $(u_2, y)$ | 1 | 0 |
| $(y, \bar y)$ | 1 | 0 |
| $(y, d)$ | 1 | 100 |
| $(\bar y, d)$ | 1 | 0 |

| vertex | $o$ | $u_1$ | $u_2$ | $y$ | $\bar y$ | $d$ |
|---|---|---|---|---|---|---|
| window | $[0,20]$ | $[0,20]$ | $[0,20]$ | $[0,20]$ | $\mathbf{[5,5]}$ | $[0,20]$ |

The single degenerate window $[5,5]$ at $\bar y$ is what makes the instance
work: $\bar y$ can be served at time 5 and at no other time, so the *only*
way to the cheap arc $(\bar y, d)$ is to arrive at $y$ at exactly time 4.

Exhaustive enumeration of the feasible elementary $o$–$d$ paths:

| path | $T$ along the path | $z$ |
|---|---|---:|
| $o \to u_2 \to u_1 \to y \to \bar y \to d$ | 0, 2, 3, 4, 5, 6 | **0** |
| $o \to u_1 \to u_2 \to y \to d$ | 0, 1, 2, 3, 4 | 100 |
| $o \to u_1 \to y \to d$ | 0, 1, 2, 3 | 100 |
| $o \to u_2 \to u_1 \to y \to d$ | 0, 2, 3, 4, 5 | 100 |
| $o \to u_2 \to y \to d$ | 0, 2, 3, 4 | 100 |

so $z^{*} = 0$. What cspy returns:

```text
['Source', 'u2', 'y', 'Sink'] 100.0 [3.0, 4.0] completed
```

The mechanism is exactly the failure of downward closedness. Four partial
paths reach $y$:

| partial path | $z$ | resource vector $(\text{arcs},\ T_y)$ | $V(L)$ | can extend to $\bar y$? |
|---|---:|---|---|---|
| $o \to u_1 \to y$ | 0 | $(2,\ 2)$ | $\{o, u_1, y\}$ | no ($T_{\bar y} = 3 \ne 5$) |
| $o \to u_2 \to y$ | 0 | $(2,\ 3)$ | $\{o, u_2, y\}$ | no ($T_{\bar y} = 4 \ne 5$) |
| $o \to u_1 \to u_2 \to y$ | 0 | $(3,\ 3)$ | $\{o, u_1, u_2, y\}$ | no ($T_{\bar y} = 4 \ne 5$) |
| $o \to u_2 \to u_1 \to y$ | 0 | $(3,\ 4)$ | $\{o, u_2, u_1, y\}$ | **yes** |

Only the last one — the one with the **largest** time value — can reach
$\bar y$ and hence the optimum. Yet all four have the same weight, and the
first three have both a smaller resource vector component-wise and a visited
set contained in the last's, so the rule of Section 2.4 permits them to
discard it. The run above shows that one of them does; the search then
completes and reports `'completed'`, which is why that value is deliberately
**not** spelled `'optimal'`.

That dominance really is the culprit can be confirmed by blocking it and
changing nothing else: add two `additive` visit indicator resources, one for
$u_1$ and one for $u_2$ (Section 4.3). They do not change the feasible set —
under `elementary=True` their bounds $[-1, 0]$ are automatically satisfied —
but they make labels with different visited sets incomparable. The same
instance then returns the enumerated optimum.

```text
plain                               : ['Source', 'u2', 'y', 'Sink'] 100.0 [3.0, 4.0]
dominance blocked by visit indicators: ['Source', 'u2', 'u1', 'y', 'ybar', 'Sink'] 0.0 [5.0, 6.0, -1.0, -1.0]
```

This is the only worked instance in this document whose outputs are not also
produced by a file in the repository, so the driver that produced both output
blocks above is given in full. It builds the nine arcs and the four windows of
the tables directly and needs nothing else; the first block above is the
`plain` run of its first half with `termination_reason` appended.

```python
"""Section 3.9.2: window_hard dominance is not sound."""
import networkx as nx
import numpy as np
from cspy_tw import BiDirectional

ARCS = [("Source", "u1", 1, 0), ("Source", "u2", 2, 0), ("u1", "u2", 1, 0),
        ("u2", "u1", 1, 0), ("u1", "y", 1, 0), ("u2", "y", 1, 0),
        ("y", "ybar", 1, 0), ("y", "Sink", 1, 100), ("ybar", "Sink", 1, 0)]
WINDOWS = {"u1": (0.0, 20.0), "u2": (0.0, 20.0), "y": (0.0, 20.0),
           "ybar": (5.0, 5.0)}


def build(n_res):
    G = nx.DiGraph(n_res=n_res)
    for (i, j, t, w) in ARCS:
        G.add_edge(i, j, weight=float(w),
                   res_cost=np.array([1.0, float(t)] + [0.0] * (n_res - 2)))
    return G


# plain: two resources, the arc counter and time under window_hard
plain = BiDirectional(build(2), [10.0, 20.0], [0.0, 0.0], direction="forward",
                      elementary=True, node_windows={1: WINDOWS},
                      window_policy={1: "window_hard"})
plain.run()

# dominance blocked: one additive visit indicator resource for u1, one for u2
blocked = BiDirectional(build(4), [10.0, 20.0, 0.0, 0.0],
                        [0.0, 0.0, -1.0, -1.0], direction="forward",
                        elementary=True, node_windows={1: WINDOWS},
                        node_consumption={2: {"u1": -1.0}, 3: {"u2": -1.0}},
                        window_policy={1: "window_hard"})
blocked.run()

print("plain                               :", plain.path, plain.total_cost,
      plain.consumed_resources)
print("dominance blocked by visit indicators:", blocked.path,
      blocked.total_cost, blocked.consumed_resources)
print("termination_reason of the plain run :", plain.termination_reason)
```

which prints the second block above followed by

```text
termination_reason of the plain run : completed
```

The indicators are not a fix for `window_hard` in general — they only prevent
comparisons between labels with different visited sets, and two labels with
the *same* visited set and different arrival times remain wrongly comparable.
There is no resource encoding that repairs a policy whose feasible set is not
downward closed.

#### 3.9.3 When a `window_hard` answer is nevertheless right

Example (3) of `NATIVE_TW_GUIDE.md` Section 5.3 uses `window_hard` and returns
the correct optimum. The reason is not the argument of Section 3.9.1 — it is
that **no dominance test ever fires on that instance**. Under `window_hard`,
Instance B produces exactly three forward labels, at $o$, at customer 1 and at
$d$, one per vertex. Dominance is tested only between two labels sitting at
the *same* vertex — that vertex's **efficient set**, the collection of
non-dominated labels kept there, written $\Lambda(u, \cdot)$ in Section 2.4 —
and never across vertices. With one label per vertex every efficient set is a
singleton, so no comparison ever takes place, and the optimum is determined by
the four-path enumeration of Section 3.11 alone.

That is a property of the instance, not of the policy. Use `window_hard` only
when either the instance is small enough to be checked by enumeration, or the
answer is being used as a heuristic.

### 3.10 Solving (P1) with cspy

**Simple interface** (time windows only):

| Symbol | Argument | Notes |
|---|---|---|
| $a_v,\ b_v$ | `time_windows={v: (a, b)}` | keyed by the **original** node labels of `G`; unlisted vertices default to $(0,\ q^{\max}_{r_{\mathrm{time}}})$ |
| $s_v$ | `service_times={v: s}` | unlisted vertices default to 0; only usable together with `time_windows` |
| $r_{\mathrm{time}}$ | `time_res` | default `1`; must differ from `critical_res` |

**General interface** (any resource, any policy):

| Symbol | Argument | Notes |
|---|---|---|
| $lb_r(v),\ ub_r(v)$ | `node_windows={r: {v: (lb, ub)}}` | per resource, per vertex |
| $c_r(v)$ | `node_consumption={r: {v: c}}` | the timing of the addition depends on $p_r$ (Section 3.2) |
| $p_r$ | `window_policy={r: "additive"}`, `{r: "window_wait"}` or `{r: "window_hard"}` | unspecified resources default to `"additive"` |
| $\varepsilon$ | `window_eps` | default `1e-9` |

Preconditions checked in the constructor, all reported together as one
exception: mutually exclusive with `REF_callback` and with
`find_critical_res=True`; `window_hard` requires `direction="forward"`;
$q^{\max}_r$ must be **finite** for any resource carrying a window policy (the
sentinel must exceed it); supplying `node_windows[r]` while leaving
`window_policy[r]` at `additive` is an error, so that a window can never be
silently ignored. `preprocess=True` becomes a no-op.

Three notes on reading the results.

1. `consumed_resources[r]` for a window resource is $T^{*}_d$, the earliest
   feasible value at the destination, **only under
   `direction="forward"`**. Under `"both"` it is the join surrogate
   $T^{\mathrm{start}} + g$ used for the feasibility test, and under
   `"backward"` it is $g_r = H - \hat T$ on the reversed axis.
2. To get the schedule of a returned path, forward-simulate the path with the
   recursion of Section 3.7 rather than reading it out of the solver.
3. `min_res[time_res] = 0` is the recommended setting; a strictly positive
   lower bound on a non-critical resource interacts badly with dominance
   (Section 4.6).

### 3.11 Instance B

Four vertices, six arcs. This instance is used by the README time-window quick
start (weight variant **B-i**) and by `NATIVE_TW_GUIDE.md` Section 5.3 (weight
variant **B-ii**). The graph and the time-window data are identical in both;
only $w$ differs, which is the point: the two variants have different optima
while having identical feasible sets.

**Arc data.**

| arc $(i,j)$ | $t_{ij}$ | $w_{ij}$ (B-i) | $w_{ij}$ (B-ii) |
|---|---:|---:|---:|
| $(o, 1)$ | 2 | 0 | 0 |
| $(o, 2)$ | 5 | 0 | 0 |
| $(1, 2)$ | 3 | −10 | 5 |
| $(2, 1)$ | 3 | −10 | 5 |
| $(1, d)$ | 2 | 0 | 1 |
| $(2, d)$ | 2 | 0 | 1 |

There is no arc $(o,d)$, no arc out of $d$ and no arc into $o$.

**Vertex data.** (The values for $o$ and $d$ are the defaults, since neither is
listed in `node_windows` or `node_consumption`.)

| vertex | $a_v$ | $b_v$ | $s_v$ |
|---|---:|---:|---:|
| $o$ | 0 | 20 | 0 |
| $1$ | 0 | 4 | 1 |
| $2$ | 8 | 12 | 1 |
| $d$ | 0 | 20 | 0 |

**Bounds.** $q^{\max} = (10,\ 20)$, so $H = 20$ and $q^{\max}_0 = 10$;
$q^{\min} = (0,\ 0)$. Configuration (2) below adds resources and changes these.

**The four elementary $o$–$d$ paths.**

| path | arcs | $\sum t_{ij}$ | $z$ (B-i) | $z$ (B-ii) |
|---|---:|---:|---:|---:|
| $P_1 = o \to 1 \to d$ | 2 | 4 | 0 | 1 |
| $P_2 = o \to 2 \to d$ | 2 | 7 | 0 | 1 |
| $P_3 = o \to 1 \to 2 \to d$ | 3 | 7 | −10 | 6 |
| $P_4 = o \to 2 \to 1 \to d$ | 3 | 10 | −10 | 6 |

Note that $\sum t$ and $z$ rank the paths differently in both variants; the
objective is $\sum w_{ij} x_{ij}$ and nothing else. (B7) is not binding:
$3 \le q^{\max}_0 = 10$.

**Time traces.** Under `window_wait`, $T^{*}$ of Section 3.7:

| path | $T^{*}$ | verdict |
|---|---|---|
| $P_1$ | $o{:}0,\ 1{:}2,\ d{:}5$ | feasible |
| $P_2$ | $o{:}0,\ 2{:}8,\ d{:}11$ | feasible (waits 3 units at customer 2) |
| $P_3$ | $o{:}0,\ 1{:}2,\ 2{:}8,\ d{:}11$ | feasible (waits 2 units at customer 2) |
| $P_4$ | $o{:}0,\ 2{:}8,\ 1{:}12$ | **infeasible**: $12 > b_1 = 4$ |

Under `window_hard`, $T_j = T_i + s_i + t_{ij}$ with $a_j \le T_j$ required:

| path | $T$ | verdict |
|---|---|---|
| $P_1$ | $o{:}0,\ 1{:}2,\ d{:}5$ | feasible |
| $P_2$ | $o{:}0,\ 2{:}5$ | **infeasible**: $5 < a_2 = 8$, and waiting is not allowed |
| $P_3$ | $o{:}0,\ 1{:}2,\ 2{:}6$ | **infeasible**: $6 < a_2 = 8$ |
| $P_4$ | $o{:}0,\ 2{:}5$ | **infeasible**: $5 < a_2 = 8$ |

Waiting is never charged: $P_2$ waits 3 units and $P_3$ waits 2, and neither
appears in $z$. Waiting affects feasibility only, by pushing later values up
against $b_j$ and $H$.

**Big-M constants** (Sections 3.4 and 3.8), with $\bar a_i = a_i$,
$\bar b_o = a_o = 0$ and $\bar b_i = \min\{b_i, H\} = b_i$ otherwise:

| arc $(i,j)$ | $\bar b_i$ | $s_i$ | $t_{ij}$ | $\bar a_j$ | $M^-_{ij}$ | $\bar b_j$ | $\bar a_i$ | $M^+_{ij}$ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| $(o,1)$ | 0 | 0 | 2 | 0 | 2 | 4 | 0 | 2 |
| $(o,2)$ | 0 | 0 | 5 | 8 | 0 | 12 | 0 | 7 |
| $(1,2)$ | 4 | 1 | 3 | 8 | 0 | 12 | 0 | 8 |
| $(2,1)$ | 12 | 1 | 3 | 0 | 16 | 4 | 8 | 0 |
| $(1,d)$ | 4 | 1 | 2 | 0 | 7 | 20 | 0 | 17 |
| $(2,d)$ | 12 | 1 | 2 | 0 | 15 | 20 | 8 | 9 |

The coarse uniform alternative is $M = 20 + 5 = 25$. The deactivation
conditions $\bar b_i + s_i + t_{ij} - M^-_{ij} \le \bar a_j$ and
$\bar a_i + s_i + t_{ij} + M^+_{ij} \ge \bar b_j$ were verified on all six
arcs.

**The four configurations and their optima.**

| configuration | feasible set | $z^{*}$ | optimal path(s) | $q$ at $d$ |
|---|---|---:|---|---|
| B-i, `window_wait` | $P_1, P_2, P_3$ | −10 | $P_3$ (unique) | $(3,\ 11)$ |
| B-ii (1), `window_wait` | $P_1, P_2, P_3$ | 1 | $P_1$ **and** $P_2$ (tie) | $(2,5)$ resp. $(2,11)$ |
| B-ii (2), `window_wait` + coverage | $P_3$ | 6 | $P_3$ (unique) | $(3,\ 11)$ |
| B-ii (3), `window_hard` | $P_1$ | 1 | $P_1$ (unique) | $(2,\ 5)$ |

and the corresponding cspy runs:

```text
B-i,   window_wait          : ['Source', 1, 2, 'Sink'] -10.0 [3.0, 11.0]
B-ii (1), window_wait       : ['Source', 2, 'Sink'] 1.0 [2.0, 11.0]
B-ii (2), indicator encoding: ['Source', 1, 2, 'Sink'] 6.0 [3.0, 11.0, -1.0, -1.0, 2.0]
B-ii (2), require_all_visits: ['Source', 1, 2, 'Sink'] 6.0 [3.0, 11.0]
B-ii (3), window_hard       : ['Source', 1, 'Sink'] 1.0 [2.0, 5.0]
```

Configuration (2) is shown twice: with the visit indicator encoding of
Section 4.3, and with `require_all_visits=True` of Section 4.4. They agree on
path and cost, and differ only in the resource vector, which is what
Section 4.5 says they should do.

**Two caveats that must travel with this instance.**

1. **The optimum of B-ii (1) is not unique.** $P_1$ and $P_2$ both have
   $z = 1$. cspy returns $P_2$; returning $P_1$ would be equally correct, and
   which one survives depends on tie-breaking in the dominance test and in the
   **label heap** — the container of generated-but-not-yet-extended labels,
   which is ordered by resource consumption and not by weight — and not on the
   model. A sentence such as "the cheap path that skips
   customer 1 is optimal" must be read as "without a coverage requirement a
   two-arc path of cost 1 suffices", not as a uniqueness claim. Perturbing
   $w_{(2,d)}$ from 1 to 1.001 makes cspy return $P_1$; perturbing
   $w_{(1,d)}$ instead makes it return $P_2$ — which is how the tie was
   confirmed.
2. **The `window_hard` result of B-ii (3) is correct for the reason given in
   Section 3.9.3**, namely that no dominance test fires, and not because
   dominance is sound under that policy. It is not.

---

## 4. (P2) Requiring all visits: the traveling salesman problem with time windows

### 4.1 The coverage constraint

(P2) is (P1) together with

$$
\sum_{i\,:\,(i,k)\in A} x_{ik} \;=\; 1 \qquad \forall k \in R
\tag{C1}
$$

for a given **required set** $R \subseteq N$: the in-degree of every required
vertex is exactly 1, that is, every required vertex is visited. Vertices in
$N \setminus R$ keep the $\le 1$ of (B3) and are visited only when doing so
pays off. With $R = N$ this turns the resource constrained shortest path
problem into the traveling salesman problem with time windows.

Nothing else changes: the objective, the time propagation, the windows and the
arc bound are exactly as in Section 3.3.

### 4.2 TSPTW proper, and the correspondence with (P2)

The traveling salesman problem with time windows is naturally stated over a
depot $0$ and customers $1, \dots, n$ as: find a permutation
$\sigma = (\sigma_1, \dots, \sigma_n)$ of the customers minimising

$$
\sum_{k=0}^{n} t_{\sigma_k \sigma_{k+1}},
\qquad \sigma_0 = \sigma_{n+1} = 0,
$$

subject to $T_{\sigma_k} = \max\bigl(a_{\sigma_k},\ T_{\sigma_{k-1}} +
s_{\sigma_{k-1}} + t_{\sigma_{k-1} \sigma_k}\bigr) \le b_{\sigma_k}$ with
$T_{\sigma_0} = 0$.

**Proposition (the depot split is exact).** Split the depot into $o$ and $d$
with $a_o = 0$, $[a_d, b_d] = [0, H]$, $s_o = s_d = 0$, an arc $(o, k)$ of
travel time $t_{0k}$ and an arc $(k, d)$ of travel time $t_{k0}$ for every
customer $k$, and set $w_{ij} = t_{ij}$ on every arc, $R = N$,
$q^{\max}_0 = n + 1$. Then the map
$\sigma \mapsto (o, \sigma_1, \dots, \sigma_n, d)$ is a bijection between the
tours feasible for the traveling salesman problem with time windows and the
paths feasible for (P2), and it preserves the objective value.

*Proof.* The map is clearly injective and its image is exactly the set of
elementary $o$–$d$ paths visiting every customer, which by (C1) with $R = N$,
(B3) and (A8) is the feasible set of (P2) (the arc count of such a path is
$n+1$, so (B7) is tight but satisfied). The time recursion is the same
recursion, with $T_o = a_o = 0$ matching $T_{\sigma_0} = 0$, and the objective
is $\sum_{(i,j) \in A(P)} w_{ij} = \sum_{k=0}^{n} t_{\sigma_k \sigma_{k+1}}$
because $w = t$. $\square$

Choosing $w_{ij} \ne t_{ij}$ gives the same feasible set with a different
objective — for instance a "minimise total distance while respecting a time
schedule" model. The reduction does not depend on $w = t$.

### 4.3 Encoding coverage in resources

(C1) can be imposed without touching the engine, using two kinds of extra
`additive` resources. This is what `TSPTW_GUIDE.md` does and what example (2)
of `NATIVE_TW_GUIDE.md` Section 5.3 does.

- **One visit indicator resource per required vertex $k$**: consumption
  $c_r(k) = -1$ and $c_r(v) = 0$ elsewhere, with bounds
  $q^{\max}_r = 0$, $q^{\min}_r = -1$. Its value at the end of a path is
  $-\sum_i x_{ik}$.
- **One visit counter resource**: consumption $+1$ at every required vertex,
  with $q^{\min}_r = \lvert R \rvert$. Its value at the end of a path is
  $\sum_{k \in R} \sum_i x_{ik}$.

What each bound actually imposes:

| resource | what $q^{\max}_r$ says | what $q^{\min}_r$ says |
|---|---|---|
| indicator for $k$ | $-\sum_i x_{ik} \le 0$ — vacuous | $-\sum_i x_{ik} \ge -1$, that is, $k$ is visited at most once |
| counter | $\sum_k \sum_i x_{ik} \le q^{\max}_r$ — non-binding if set to $\lvert R \rvert$ or more | $\sum_{k \in R} \sum_i x_{ik} \ge \lvert R \rvert$ |

**Only the counter's lower bound changes the model.** Its value at $d$ is
$\sum_{k \in R} \sum_i x_{ik}$, a sum of $\lvert R \rvert$ terms each of which
is at most 1 by (A8); requiring the sum to be at least $\lvert R \rvert$
therefore forces every term to equal 1, which is (C1). The indicator resources
are **redundant as constraints** — under `elementary=True` their bounds are
automatically satisfied — and exist for one purpose only: to **restrict
dominance**. Since cspy's dominance requires $q(L_1) \le q(L_2)$ component-wise
and the indicators are decremented on visit, requiring it on the indicators
forces

$$
V(L_1) \cap N \;\supseteq\; V(L_2) \cap N .
$$

The reverse inclusion comes from the **arc counter**, not from the
unreachable sets. Because $t^{(0)}_{ij} = 1$ on every arc, the component-wise
condition $q_0(L_1) \le q_0(L_2)$ is $\lvert V(L_1) \rvert \le
\lvert V(L_2) \rvert$ for two labels at the same vertex (Section 2.4, "why the
arc count need not be part of the state"), and a superset of no larger
cardinality is equal. The two together pin the visited sets to coincide.

It is worth being explicit that the elementary condition
$U(L_1) \subseteq U(L_2)$ would **not** do this job. $U$ is the *unreachable*
set, which contains $V$ but grows beyond it as soon as one extension has been
found infeasible, so containment of the unreachable sets says nothing about
containment of the visited sets in general. The arc counter is what supplies
the missing direction.

**Dropping the indicators is not a weaker model, it is a wrong answer.** On
Instance B configuration (2), keeping only the counter with
$q^{\min} = (0,0,2)$ gives

```text
counter without indicators  : ['Source'] 0.0 [0.0, 0.0, 0.0]
```

— the degenerate path, on an instance whose optimum $P_3$ exists and costs 6.
The reason is Section 4.6: a strictly positive lower bound on a non-critical
resource is only checked at the terminal check, so the labels that would have
satisfied it are pruned by dominance long before that check is reached. The
direction of the indicator matters too: $0 \to +1$ instead of $0 \to -1$ flips
the containment and leaves exactly the domination-by-a-subset case one is
trying to remove.

### 4.4 Encoding coverage in the engine

`require_all_visits=True` asks the engine for the same thing directly. Two
changes are made, both inside an `if (require_all_visits)` guard.

**The dominance condition.** A label may dominate another only when the two
visit **exactly the same required vertices**:

$$
V(L_1) \cap R \;=\; V(L_2) \cap R .
\tag{C2}
$$

*Soundness.* Suppose $L_1$ and $L_2$ sit at the same vertex and satisfy
(i) $z(L_1) \le z(L_2)$, (ii) $q(L_1) \le q(L_2)$ component-wise,
(iii) $U(L_1) \subseteq U(L_2)$ (the existing elementary condition), and
(iv) (C2). Let $Q$ be any completion of $L_2$ to $d$ that is resource feasible
and covers $R$. Then $Q$ is a valid completion of $L_1$: it stays elementary
because the remark of Section 2.4 gives $V(Q) \cap U(L_2) = \emptyset$ while
$V(L_1) \subseteq U(L_1) \subseteq U(L_2)$; it stays resource feasible because the resource extension functions
are monotone, so $q(L_1) \le q(L_2)$ propagates along $Q$; and it still covers
$R$, because any $k \in R$ not on $Q$ lies in
$V(L_2) \cap R = V(L_1) \cap R$ by (C2). Finally
$z(L_1) + z(Q) \le z(L_2) + z(Q)$. So discarding $L_2$ cannot lose an optimal
solution. $\square$

*Why equality rather than containment.* The coverage step of the proof needs
only the one inclusion $V(L_2) \cap R \subseteq V(L_1)$; imposing equality
asks for the reverse inclusion as well and is therefore, in principle,
stricter. Three reasons to impose it anyway. It is what the indicator
encoding of Section 4.3 imposes, so the two are the same rule and can be
checked against each other. Whenever the arc counter is present — and it is,
being the critical resource — condition (ii) supplies
$\lvert V(L_1) \rvert \le \lvert V(L_2) \rvert$, which turns the one
inclusion into equality by itself, so nothing extra is being demanded in
practice. And equality reduces to a single comparison of two bit sets, where
containment would need two.

The one thing that does **not** supply the reverse inclusion is condition
(iii): $U$ is the unreachable set, which strictly contains $V$ as soon as an
extension has been rejected, so $U(L_1) \subseteq U(L_2)$ does not imply
$V(L_1) \subseteq V(L_2)$.

**The terminal condition.** An extension into $d$ is refused unless the label
already covers $R$. This loses nothing: an optimal path covers $R$ at the
vertex before $d$, and every refused label would have produced a path that
does not cover $R$. Under `direction="forward"` the search is complete, since
the halfway-point cut-off fires only for `direction="both"`, so global
optimality follows.

The soundness proof uses monotonicity of the resource extension functions,
which the engine assumes anyway. It is therefore inherited, not introduced:
combining `require_all_visits` with `window_hard`, or with a non-monotone
custom resource extension function, is unsound for the reason of Section 3.9.2
and not because of coverage. The implementation logs a warning when the two
are combined.

### 4.5 The two encodings are the same pruning rule

Write the two predicates side by side. Both prune $L_2$ only when
$z(L_1) \le z(L_2)$, $q(L_1) \le q(L_2)$ on the base resources, and (iii)
$U(L_1) \subseteq U(L_2)$. On top of that:

- the **indicator encoding** adds "$\le$ on every indicator resource", which,
  because the indicators are decremented on visit and so reverse the
  direction, is $V(L_1) \cap R \;\supseteq\; V(L_2) \cap R$;
- **`require_all_visits`** adds (C2), $V(L_1) \cap R = V(L_2) \cap R$.

So (C2) is the conjunction of the indicator condition with its reverse
inclusion. That reverse inclusion is supplied by the **arc counter**, which
is part of condition (ii) in both encodings: with $t^{(0)}_{ij} = 1$ on every
arc, $q_0(L_1) \le q_0(L_2)$ reads
$\lvert V(L_1) \rvert \le \lvert V(L_2) \rvert$ for two labels at the same
vertex, and a superset of no larger cardinality is equal. (Condition (iii) is
*not* what supplies it: $U \supseteq V$ strictly once an extension has been
rejected.) (C2) is therefore **never weaker** than the indicator condition,
so it is sound wherever the indicator encoding is, and in practice the two
keep the same labels: on the 20 randomly
generated instances of `NATIVE_TW_GUIDE.md` Section 6.5 they returned the same
cost on all 20 and the same tour on 19, the one remaining pair being two
alternative optima of equal cost.

What differs is representation and cost:

| | indicator encoding | `require_all_visits=True` |
|---|---|---|
| coverage requested by | $q^{\min}_r = \lvert R \rvert$ on a counter resource | the `require_all_visits` / `required_nodes` arguments |
| dominance restricted by | one indicator resource per required vertex, compared as part of the component-wise test | one bit set per label, compared once |
| visited set stored as | $\lvert R \rvert$ doubles, $0$ or $-1$ | $\lceil \lvert R \rvert / 64 \rceil$ machine words |
| incomplete paths rejected | at the terminal feasibility check, through $q^{\min}$ | when the extension into $d$ is attempted |
| resource vector length | $n + 3$ | 2 |
| membership test | floating-point comparison | exact bit operation |
| assembling it wrongly | silently returns a different answer | rejected in the constructor |

`NATIVE_TW_GUIDE.md` Section 6.5 reports the measured consequence: the same
answers, with the indicator encoding 1.6x slower at $n = 6$ growing to 5.5x at
$n = 14$, exactly the $O(\lvert R \rvert)$ versus $O(1)$ per-comparison cost
the table predicts.

### 4.6 When the lower bound of a non-critical resource is actually checked

This is the one place where the implementation does not impose (A6) verbatim,
and it is the reason a bare counter resource is unsound. From
`Label::checkFeasibility` (`src/cc/labelling.cc`):

- **The upper bound $q^{\max}_r$ is checked at every extension, for every
  resource, unconditionally.**
- The lower bound $q^{\min}_r$ is checked only when
  $r = r_{\mathrm{crit}}$, or the check is not "soft", or the check is soft
  and $q^{\min}_r \le 0$.

Extensions perform a soft check; the terminal check performed when a label
reaching $d$ is recorded is not soft. So:

| resource | at each extension | at the terminal check |
|---|---|---|
| the critical resource | checked | checked |
| non-critical with $q^{\min}_r \le 0$ | checked | checked |
| non-critical with $q^{\min}_r > 0$ | **not checked** | checked |

A visit counter has $q^{\min}_r = \lvert R \rvert > 0$ and therefore falls in
the third row: its bound has no effect until the destination is reached, by
which time dominance has already discarded the labels that could have met it.
Adding the visit indicators fixes this precisely because their bound is
$-1 \le 0$ and their presence in the resource vector blocks the offending
dominance comparisons. The statement "a lower bound on a non-critical resource
only bites at the end" is correct **only when that bound is strictly
positive**.

Note also that $q^{\min}_{r_{\mathrm{crit}}}$ is not a "lower bound at the
destination" at all: the bidirectional search uses it as the floor of the
halfway point and raises it monotonically as the search proceeds, and it is
compared at every extension. Setting it to $n+1$ in the hope of forcing a
Hamiltonian path kills the very first label, whose arc count is 1
(`TSPTW_GUIDE.md` Section 3.2, approach (a)).

### 4.7 Solving (P2) with cspy

| Symbol / requirement | Argument | Notes |
|---|---|---|
| (C1) | `require_all_visits=True` | default `False` |
| $R$ | `required_nodes` | an iterable of the **original** node labels; `None` means every vertex other than `"Source"` and `"Sink"`; a proper subset is a meaningful request; an empty set is rejected; the iterable is materialised exactly once |
| precondition | `elementary=True` | the soundness proof of Section 4.4 uses it |
| precondition | `direction="forward"` | the backward search and the join step would each need their own coverage argument; `"both"` and `"backward"` are refused with an explanatory exception |

The reference alternative — useful when a required-visit-like condition has to
be expressed that the option does not cover — is the indicator recipe of
Section 4.3: for each $k \in R$ one `additive` resource with $c_r(k) = -1$,
$q^{\max}_r = 0$, $q^{\min}_r = -1$, plus one counter with $c_r(k) = +1$ for
all $k \in R$ and $q^{\min}_r = \lvert R \rvert$, and `res_cost` widened to
length $n + 3$ on **every** arc. Both parts are needed; neither alone is
correct.

Two practical facts. An exact solve is exponential in $\lvert R \rvert$: on an
Apple M1 with 8 GB, randomly generated instances take well under a second up
to about twelve customers, seconds to minutes at fourteen to sixteen, and are
impractical beyond about eighteen. Those figures are a range over instance
families and not a single curve — the four instances measured at $n = 14$ in
`NATIVE_TW_GUIDE.md` Section 6.5 have a median of 0.93 s, at the fast end of
the "seconds to minutes" band, because they were generated with wide windows;
tight windows at the same $n$ are what reach minutes. And a run cut short by `time_limit` returns
the same degenerate path as a genuinely infeasible instance, which only
`termination_reason` (Section 6.2) can tell apart.

### 4.8 Instance C

The six-customer traveling salesman problem with time windows of
[`tsptw_cspy.py`](./tsptw_cspy.py), used by both guides. The depot is vertex 0
and is split into $o$ and $d$; $N = \{1, \dots, 6\}$, $R = N$,
$q^{\max} = (7,\ 200)$, $q^{\min} = (0,\ 0)$, $w_{ij} = t_{ij}$.

**Travel times $t_{ij}$** (asymmetric; row $i$, column $j$):

| from \ to | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **0** | 0 | 11 | 8 | 5 | 8 | 5 | 7 |
| **1** | 9 | 0 | 7 | 12 | 3 | 11 | 7 |
| **2** | 8 | 12 | 0 | 4 | 8 | 3 | 11 |
| **3** | 3 | 4 | 10 | 0 | 8 | 3 | 8 |
| **4** | 10 | 3 | 3 | 6 | 0 | 8 | 4 |
| **5** | 5 | 8 | 5 | 12 | 4 | 0 | 10 |
| **6** | 8 | 4 | 7 | 5 | 12 | 4 | 0 |

**Vertex data.**

| vertex | $a_v$ | $b_v$ | $s_v$ |
|---|---:|---:|---:|
| 0 (the depot, i.e. $o$ and $d$) | 0 | 200 | 0 |
| 1 | 39 | 59 | 6 |
| 2 | 2 | 18 | 2 |
| 3 | 38 | 60 | 4 |
| 4 | 32 | 57 | 5 |
| 5 | 2 | 13 | 3 |
| 6 | 42 | 60 | 1 |

$H = b_0 = 200$.

**How it was constructed.** The travel times, windows and service times were
chosen by seed search followed by exhaustive evaluation of all $6! = 720$
permutations, so that windows, waiting and service times are **all three
binding simultaneously**. Only 4 of the 720 permutations are feasible.

**The optimum.** $z^{*} = 33$, attained by the unique tour
$0 \to 2 \to 5 \to 4 \to 1 \to 6 \to 3 \to 0$, that is
$P = (o, 2, 5, 4, 1, 6, 3, d)$, with $q = (7,\ 66)$: seven arcs, and a depot
return at time 66. Its schedule, from the recursion of Section 3.7:

| vertex | window | $s_v$ | arrival | wait | $T^{*}_v$ | $D_v$ |
|---|---|---:|---:|---:|---:|---:|
| $o$ | $[0, 200]$ | 0 | 0 | 0 | 0 | 0 |
| 2 | $[2, 18]$ | 2 | 8 | 0 | 8 | 10 |
| 5 | $[2, 13]$ | 3 | 13 | 0 | 13 | 16 |
| 4 | $[32, 57]$ | 5 | 20 | 12 | 32 | 37 |
| 1 | $[39, 59]$ | 6 | 40 | 0 | 40 | 46 |
| 6 | $[42, 60]$ | 1 | 53 | 0 | 53 | 54 |
| 3 | $[38, 60]$ | 4 | 59 | 0 | 59 | 63 |
| $d$ | $[0, 200]$ | 0 | 66 | 0 | 66 | 66 |

**Why the three features are binding.**

- **Windows.** Ignoring them, the optimal tour is
  $0 \to 6 \to 1 \to 4 \to 2 \to 3 \to 5 \to 0$ with cost 29; it is infeasible
  under the windows. The gap $33 - 29 = 4$ is caused by the windows alone.
- **Waiting.** The optimal tour arrives at customer 4 at time 20 and waits 12
  units until $a_4 = 32$. It also arrives at customer 5 exactly at its
  deadline $b_5 = 13$, so that window is tight.
- **Service times.** Replacing every service time by the constant 3 changes
  the optimal visiting order (to $0 \to 5 \to 2 \to 3 \to 1 \to 4 \to 6 \to 0$,
  also of cost 33), and the original order becomes infeasible.

cspy with `require_all_visits=True` returns exactly this:

```text
['Source', 2, 5, 4, 1, 6, 3, 'Sink'] 33.0 [7.0, 66.0] completed
```

---

## 5. (P3) The pricing problem of column generation

### 5.1 The master problem

Let $\Omega$ be the set of feasible **routes**: elementary $o$–$d$ paths that
respect the time windows and the capacity bound, each corresponding to one
vehicle's itinerary out of and back into the depot. For $p \in \Omega$ let
$c_p$ be its cost and $\alpha_{jp} \in \{0,1\}$ indicate whether it visits
customer $j$. The set partitioning formulation of the vehicle routing problem
with time windows is

$$
\min \sum_{p \in \Omega} c_p\, \lambda_p
\qquad \text{s.t.} \qquad
\sum_{p \in \Omega} \alpha_{jp}\, \lambda_p = 1 \ \ \forall j \in N,
\qquad \lambda_p \in \{0,1\} .
\tag{D1}
$$

$\Omega$ is exponentially large, which is why the linear programming
relaxation is solved by column generation instead of being written down.

### 5.2 The restricted master problem and reduced costs

Let $\Omega' \subseteq \Omega$ be the columns generated so far. The
**restricted master problem** is (D1) over $\Omega'$ with
$\lambda_p \ge 0$ replacing integrality. Let $\pi_j$ be the dual price of
customer $j$'s covering constraint at an optimal basis of that linear program.
The **reduced cost** of a column $p \in \Omega$ is

$$
\bar z_p \;=\; c_p \;-\; \sum_{j \in N} \alpha_{jp}\, \pi_j .
\tag{D2}
$$

### 5.3 The pricing subproblem

$$
\text{(P3)}\qquad \min_{p \in \Omega} \ \bar z_p
\tag{D3}
$$

Because $c_p = \sum_{(i,j) \in A(p)} t_{ij}$ and each customer $j$ on the
route is entered exactly once, (D2) rewrites as a sum over arcs,

$$
\bar z_p \;=\; \sum_{(i,j) \in A(p)} \bigl(t_{ij} - \pi_j\bigr),
\qquad \pi_d := 0 ,
$$

so **(P3) is an instance of (P1) on the same digraph with**

$$
w_{ij} \;=\; \bar c_{ij} \;=\; t_{ij} - \pi_j .
$$

Every arc entering customer $j$ picks up $-\pi_j$; arcs entering $d$ pick up
nothing. This is the single sentence that makes the whole documentation's
insistence on separating $w_{ij}$ from $t_{ij}$ (Section 1.2) worth the
trouble: in pricing they are different by construction, and $w_{ij}$ is
routinely negative.

**Stopping rule.** If $\min_p \bar z_p \ge 0$, no column can improve the
restricted master problem, so its optimum is the optimum of the full linear
programming relaxation of (D1). Otherwise the minimising route is added to
$\Omega'$ and the process repeats. This proves optimality of the linear
program, not of (D1) — see Section 5.7.

### 5.4 Why coverage is *not* imposed in pricing

Pricing asks for *some* route of negative reduced cost. It does not ask for a
route covering anything. Consequently:

- (C1) is absent, so **every elementary path is feasible** for (P3) as long as
  it respects the windows and the capacity;
- therefore the hypothesis of Section 3.9.1 holds and Feillet-style dominance
  is sound as it stands;
- therefore **no visit indicator resources are needed**, and dropping them
  makes the search both correct and faster.

This is the exact converse of Section 4.3, and it is why the same solver call
is set up so differently in Sections 4 and 5.

### 5.5 Capacity as a resource, and why the direction matters

A capacity limit "at most $k$ customers per route" is $q^{\max}_0 = k + 1$ on
the arc counter; a limit on a load quantity is another `additive` resource
with the load as arc or node consumption. Putting it on the **critical**
resource is what makes `direction="both"` pay: the bidirectional search meets
in the middle of the critical resource's range, so a tight bound on it halves
the depth each side must reach and prunes the joins aggressively.
`NATIVE_TW_GUIDE.md` Section 9.2 measures this on a 50-customer pricing
instance with at most 4 customers per route: 7.4 s for the native forward
search against 30 ms for the native bidirectional one, a factor of 243. (The
243x compares the two native runs, columns (b) and (c) of that table. The
larger figure of 267x quoted elsewhere is column (a) against column (c), the
*Python* forward search against the native bidirectional one, and so folds
in the cost of the language boundary as well; both are correct, and which one
is meant has to be said.) The same section also measures the opposite: with a
loose critical bound, `"both"` is 1.7x to 4.5x **slower**. The direction has
to be chosen per instance, not once.

### 5.6 Solving (P3) with cspy

| Requirement | How |
|---|---|
| $w_{ij} = t_{ij} - \pi_j$ | rebuild the arc weights from the current duals at every iteration; the graph construction cost is negligible against `run()` from about 20 customers up |
| windows | `time_windows` / `service_times` as in Section 3.10 |
| capacity | `max_res[0]` (arc counter) or a further `additive` resource |
| elementarity | `elementary=True` |
| coverage | **not** requested; leave `require_all_visits` at `False` |
| direction | `"forward"` when the critical bound is loose, `"both"` when it is tight (Section 5.5) |
| a fresh object per iteration | `run()` is single-shot per `BiDirectional` object |

**The degenerate-path check is mandatory.** When pricing is infeasible, a
forward run returns `["Source"]` with `total_cost` 0.0. Reading that 0.0 as a
reduced cost would be interpreted as "no improving column" and would terminate
column generation early, silently, with a wrong bound. Test the returned path
before using the cost:

```text
infeasible = (path is None or len(path) <= 1
              or path[0] != "Source" or path[-1] != "Sink")
```

### 5.7 Instance D

Four customers and a depot, at most three customers per route.

**Travel times $t_{ij}$** (symmetric here; vertex 0 is the depot):

| from \ to | 0 | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|---:|
| **0** | 0 | 8 | 9 | 14 | 12 |
| **1** | 8 | 0 | 5 | 8 | 11 |
| **2** | 9 | 5 | 0 | 6 | 8 |
| **3** | 14 | 8 | 6 | 0 | 7 |
| **4** | 12 | 11 | 8 | 7 | 0 |

**Vertex data.** $s_j = 2$ for every customer; the depot has $s = 0$ and the
window $[0, 100]$.

| vertex | $a_v$ | $b_v$ |
|---|---:|---:|
| 1 | 5 | 30 |
| 2 | 10 | 40 |
| 3 | 15 | 60 |
| 4 | 20 | 70 |

**Bounds.** $q^{\max} = (4,\ 100)$, $q^{\min} = (0,\ 0)$: four arcs, hence at
most three customers per route. $H = 100$.

**The cheapest feasible route per customer subset** (exhaustive over all
orders; this is the data (D1) is written over, restricted to subsets of size
at most three):

| subset | cost | order |
|---|---:|---|
| $\{1\}$ | 16 | (1) |
| $\{2\}$ | 18 | (2) |
| $\{3\}$ | 28 | (3) |
| $\{4\}$ | 24 | (4) |
| $\{1,2\}$ | 22 | (1, 2) |
| $\{1,3\}$ | 30 | (1, 3) |
| $\{1,4\}$ | 31 | (1, 4) |
| $\{2,3\}$ | 29 | (2, 3) |
| $\{2,4\}$ | 29 | (2, 4) |
| $\{3,4\}$ | 33 | (3, 4) |
| $\{1,2,3\}$ | 31 | (1, 3, 2) |
| $\{1,2,4\}$ | 33 | (1, 2, 4) |
| $\{1,3,4\}$ | 35 | (1, 3, 4) |
| $\{2,3,4\}$ | 34 | (2, 3, 4) |

**The column generation run.** Starting from the four single-customer columns,
pricing generates one column per iteration:

| iteration | restricted master value | duals $(\pi_1,\pi_2,\pi_3,\pi_4)$, rounded | $\min \bar z_p$ | column found |
|---:|---:|---|---:|---|
| 1 | 86.00 | (16, 18, 28, 24) | −36 | $\{2,3,4\}$, cost 34 |
| 2 | 50.00 | (16, 18, 28, −12) | −31 | $\{1,2,3\}$, cost 31 |
| 3 | 50.00 | (16, 18, −8, 24) | −25 | $\{1,2,4\}$, cost 33 |
| 4 | 50.00 | (16, −18, 28, 24) | −33 | $\{1,3,4\}$, cost 35 |
| 5 | 44.33 | (10.3, 9.3, 11.3, 13.3) | 0 | none: the linear program is optimal |

**A caveat on reproducing this table.** Iterations 2, 3 and 4 all have
restricted master value 50: the restricted master problem is **degenerate**
there, so its optimal dual vector is not unique and the three lines above
report the duals of one particular optimal basis. A different linear
programming solver, or a different pivoting rule, will report different duals
on those rows and may generate the same three columns in a different order.
The final value $133/3$ and the set of columns generated are not affected. The
figures above match the executed run in `NATIVE_TW_GUIDE.md` Section 8.3
exactly, which is the run they were read from.

**The linear programming optimum is fractional**: $44\tfrac{1}{3}$, attained
by $\lambda = \tfrac13$ on each of the four three-customer routes
$\{2,3,4\}, \{1,2,3\}, \{1,2,4\}, \{1,3,4\}$ — indeed
$(34 + 31 + 33 + 35)/3 = 133/3 = 44.33\ldots$

**The integer optimum is 50**, attained by $\{1\}$ together with $\{2,3,4\}$
($16 + 34$), as an exhaustive search over all partitions of $\{1,2,3,4\}$ into
feasible routes confirms. The gap $50 - 44.33$ is where **branching** enters:
branch and price solves (D1) by branch and bound with column generation at
every node.

---

## 6. Early termination and the objective sign convention

### 6.1 `threshold` and `threshold_strict` as a stopping rule

Let $\theta$ be the threshold. The rule modifies the dynamic program of
Section 2.4 by stopping as soon as a resource-feasible $o$–$d$ label $L$ with

$$
z(L) \le \theta
\qquad\text{(or } z(L) < \theta \text{ when \texttt{threshold\_strict=True})}
$$

is accepted, and returning the path of that $L$.

**What is claimed and what is not.** The returned path satisfies the
inequality above. That is the entire claim. It is *not* claimed to be optimal,
nor even to be the best path found so far: the label queue is ordered by
resource consumption, not by cost, so the returned path is whichever
acceptable path the search reached first. For satisficing this is exactly
right; for "the best solution within a budget" it is not, and `time_limit`
with the returned path read as a heuristic is the right tool instead.

The strict variant exists because passing the value of a known **incumbent**
as $\theta$ under the default $\le$ comparison would stop the search on the
incumbent's own value, proving nothing. With `threshold_strict=True` the
search stops exactly when a strictly better solution appears, and otherwise
runs to exhaustion and proves that none exists. With
`threshold_strict=False` the behaviour is bit for bit the upstream behaviour.

### 6.2 `termination_reason`

Four statements about the search, each with its proviso:

| value | statement |
|---|---|
| `'completed'` | every generated label was processed and an $o$–$d$ path was found. This certifies optimality **only if the dominance rule is sound for the resource extensions in use**; the documented exception in this fork is `window_hard` (Section 3.9.2), where an exhausted search may still have pruned the optimum. This is why the value is not named `'optimal'` |
| `'threshold_reached'` | a path meeting $\theta$ was found and the search stopped early; that path is the one returned, and it is the first acceptable path encountered, not the best (Section 6.1) |
| `'time_limit_reached'` | `time_limit` expired first. Any complete path found earlier is still returned; a degenerate result means the instance status is **unknown**, not proven infeasible |
| `'no_feasible_path'` | every generated label was processed and no resource-feasible $o$–$d$ path was found: the instance is infeasible, under the same soundness proviso as `'completed'` |

The last two are the reason the property exists: a genuinely infeasible
instance and a search truncated before its first complete path return
**byte-identical** degenerate results, and only the reason separates them.
Before `run()` the property is `None`. The time limit is checked before the
threshold within each iteration, so a run in which both hold reports
`'time_limit_reached'` — conservative, in that the reason never overstates how
far the search got.

### 6.3 Maximisation objectives

`BiDirectional` minimises. Let $\mathrm{rew}_{ij} \ge 0$ be a reward per arc
and set $w_{ij} = -\mathrm{rew}_{ij}$.

**Proposition.** For every path $P$, $z(P) = -\mathrm{rew}(P)$ where
$\mathrm{rew}(P) = \sum_{(i,j) \in A(P)} \mathrm{rew}_{ij}$. Hence for any
target $X$,

$$
\mathrm{rew}(P) > X \iff z(P) < -X,
\qquad
\mathrm{rew}(P) \ge X \iff z(P) \le -X .
$$

*Proof.* Immediate from $z(P) = \sum_{(i,j) \in A(P)} w_{ij} =
-\sum_{(i,j) \in A(P)} \mathrm{rew}_{ij}$ and multiplying the inequality by
$-1$. $\square$

So `threshold = -X` together with `threshold_strict=True` stops exactly on a
path of reward strictly above $X$, and `threshold = -X` alone stops on reward
at least $X$. The reported `total_cost` is the **negated** objective value:
report $-\,$`total_cost` to the user.

### 6.4 Instance E

Five vertices — $o$, $a$, $b$, $c$, $d$, so $N = \{a, b, c\}$ — and eight
arcs, one reward per arc; two resources, both arc counters with
$t^{(r)}_{ij} = 1$, bounds $q^{\max} = (10, 10)$, $q^{\min} = (0,0)$. No
windows.

| arc | reward $\mathrm{rew}_{ij}$ | $w_{ij}$ |
|---|---:|---:|
| $(o, a)$ | 5 | −5 |
| $(o, b)$ | 3 | −3 |
| $(a, b)$ | 4 | −4 |
| $(a, c)$ | 2 | −2 |
| $(b, c)$ | 6 | −6 |
| $(b, d)$ | 1 | −1 |
| $(a, d)$ | 1 | −1 |
| $(c, d)$ | 3 | −3 |

All six $o$–$d$ paths, by decreasing reward:

| path | arcs | reward | $z$ |
|---|---:|---:|---:|
| $o \to a \to b \to c \to d$ | 4 | **18** | −18 |
| $o \to b \to c \to d$ | 3 | 12 | −12 |
| $o \to a \to c \to d$ | 3 | 10 | −10 |
| $o \to a \to b \to d$ | 3 | 10 | −10 |
| $o \to a \to d$ | 2 | 6 | −6 |
| $o \to b \to d$ | 2 | 4 | −4 |

The maximum reward is 18. Asking for reward $> 12$ (`threshold=-12.0`,
`threshold_strict=True`) stops at the first acceptable path, which on this
instance happens to be the best one; asking for reward $> 18$
(`threshold=-18.0`) can never be met, so the search runs to exhaustion,
reports `'completed'`, and still returns the best path it found:

```text
reward > 12 : threshold_reached | path ['Source', 'a', 'b', 'c', 'Sink'] | reward 18.0
reward > 18 : completed | path ['Source', 'a', 'b', 'c', 'Sink'] | reward 18.0
```

---

## 7. Verification record

**How the models in this document were checked.**

- Every instance table was produced by exhaustive enumeration with
  `fractions.Fraction`, so no floating-point rounding enters the expected
  values: all $o$–$d$ elementary paths of Instances A, B, D, E and the
  Section 3.9.2 counterexample, all $6! = 720$ permutations of Instance C, and
  all partitions of the customer set of Instance D into feasible routes.
- The mixed integer program of Section 3.3 was checked directly against the
  dynamic program by enumerating every $0/1$ assignment of $x$ and deciding
  the feasibility of the resulting system in $T$ exactly. Once $x$ is fixed,
  every remaining constraint has the shape $T_j - T_i \ge \text{const}$ or
  $T_j \le \text{const}$; such a system is called a **difference constraint
  system**, and it is feasible if and only if a certain derived digraph — one
  vertex per variable, one arc per constraint — contains no negative-weight
  cycle. **Bellman–Ford** is the classical shortest-path algorithm that
  detects exactly that, so feasibility is decided in polynomial time without
  a linear programming solver and without floating point. The feasible sets
  matched as sets in every configuration.
- The big-M tables were recomputed from the definitions of Sections 3.4 and
  3.8 and the two deactivation inequalities were verified on every arc.
- The claim of Section 3.5 was checked by comparing the $x$-feasible sets of
  the all-vertices and visited-vertices-only forms of (B6).
- The claim of Section 3.6 was checked by enumerating the $x$ satisfying
  (B1)–(B3) and (B7) — none contains a cycle — and, after dropping the
  $\le 1$, by confirming that each remaining cycle-carrying $x$ has an
  infeasible $T$ subsystem.
- The tie in Instance B-ii configuration (1) was established by perturbation:
  raising $w_{(2,d)}$ to 1.001 makes cspy return $P_1$, raising $w_{(1,d)}$
  instead makes it return $P_2$.
- A census of which dominance comparisons actually fire established the claim
  of Section 3.9.3 (none fire under `window_hard` on Instance B). The
  counterexample of Section 3.9.2 was constructed so that one does; the
  suboptimal answer was reproduced against a real solver run, and dominance
  was confirmed to be its cause by re-solving the identical instance with
  visit indicator resources added to block the offending comparison, which
  recovers the enumerated optimum.

**How the implementation was checked.** The native resource extension function
was compared bit for bit against an independently written Python resource
extension function implementing the same formulas, roughly 2600 checks in
total; the build with the mandatory-visit feature switched off was confirmed
to produce byte-identical output to the pre-change build over 3222 solver
runs; and the `bounds_pruning` repair of Section 2.6 was checked against
brute-force enumeration of every simple $o$–$d$ path on 60 random instances
in each of the three search directions. The permanent regression tests are
`test/python/tests_native_time_windows.py` (65 cases, 33 of them covering
mandatory visits), `test/python/tests_termination_reason.py` (18 cases) and
`test/python/tests_bounds_pruning.py` (2 cases, one per repaired bug).

**The standing rule for this repository's documentation.** Every printed
output block in any of the four documents is a verbatim copy of a real run
made with the repository's `.venv`. None is transcribed from memory or edited
for presentation.

---

## 8. References

- S. Irnich and G. Desaulniers: *Shortest Path Problems with Resource
  Constraints*, in G. Desaulniers, J. Desrosiers and M. M. Solomon (eds.),
  *Column Generation*, Springer, 2005, 33–65. (the survey of the resource
  constrained shortest path problem and of resource extension functions)
- G. Desaulniers, J. Desrosiers and M. M. Solomon (eds.): *Column Generation*,
  Springer, 2005. (the standard reference on column generation, branch and
  price and pricing problems)
- D. Feillet, P. Dejax, M. Gendreau and C. Gueguen: *An exact algorithm for
  the elementary shortest path problem with resource constraints: Application
  to some vehicle routing problems*, Networks, 44(3), 216–229, 2004. (the
  unreachable-set containment condition of elementary dominance)
- G. Righini and M. Salani: *Symmetry helps: Bounded bi-directional dynamic
  programming for the elementary shortest path problem with resource
  constraints*, Discrete Optimization, 3(3), 255–273, 2006. (the basis of
  cspy's bidirectional labelling)
- E. Tilk, A.-K. Rothenbächer, T. Gschwind and S. Irnich: *Asymmetry matters:
  Dynamic half-way points in bidirectional labeling for solving shortest path
  problems with resource constraints faster*, European Journal of Operational
  Research, 261(2), 530–539, 2017. (the dynamic halfway point cspy
  implements)
- Y. Dumas, J. Desrosiers, E. Gelinas and M. M. Solomon: *An optimal algorithm
  for the traveling salesman problem with time windows*, Operations Research,
  43(2), 367–371, 1995. (an exact dynamic programming algorithm for the
  traveling salesman problem with time windows)
- D. Torres Sanchez: *cspy: A Python package with a collection of algorithms
  for the (Resource) Constrained Shortest Path problem*, Journal of Open
  Source Software, 5(49), 1655, 2020.
- cspy upstream repository: <https://github.com/torressa/cspy>; documentation:
  <https://torressa.github.io/cspy/>.
