# The Native Time-Window Features of this cspy Fork

## 1. Purpose, audience and scope

This guide documents the three features this fork adds to cspy in C++, and
shows each of them at work on a stated model with stated data:

- **per-node resource windows**, of which time windows are the special case
  (Sections 3 to 5);
- **mandatory visits**, `require_all_visits` (Section 6);
- **early termination**, `threshold_strict` and `termination_reason`
  (Section 7).

It then wires the first of them into a column generation pricing loop
(Section 8), reports the measured cost of each choice (Section 9) and lists
what the implementation cannot do (Section 10). The C++ internals, the
rebuild procedure and the verification record are appendices, because a
reader who only wants to *use* the features does not need them.

**What this guide is not.** It does not state the models: every mixed
integer program, every dynamic program and every soundness argument lives in
[`FORMULATIONS.md`](./FORMULATIONS.md), and this guide links to it rather
than restating it. It does not teach how to write a resource extension
function in Python either; that is [`TSPTW_GUIDE.md`](./TSPTW_GUIDE.md).

**Audience.** Students and researchers who have read `FORMULATIONS.md`
Sections 1 to 3 (notation, the resource constrained shortest path problem,
per-node windows) and want to use this fork. Familiarity with
`TSPTW_GUIDE.md` is helpful but not assumed.

**Acronyms**, spelled out here and used in short form afterwards: RCSP =
resource constrained shortest path problem; ESPPRC = elementary shortest
path problem with resource constraints; ESPPRC-TW = the same with time
windows; TSPTW = traveling salesman problem with time windows; VRPTW =
vehicle routing problem with time windows; CVRPTW = capacitated VRPTW.

### 1.1 Notation used in this guide

The canonical notation table is `FORMULATIONS.md` Section 1, and nothing
here redefines a symbol. The symbols this guide actually uses are repeated
below with the argument that carries each of them, so that the code and the
formulas can be read side by side.

| Symbol | Meaning | Carried by |
|---|---|---|
| $q_r$ | the value of resource $r$ carried by a label; $q'_r$ after an extension | `consumed_resources[r]` after `run()` |
| $q^{\max}_r,\ q^{\min}_r$ | the bounds on resource $r$ | `max_res[r]`, `min_res[r]` |
| $lb_r(v),\ ub_r(v)$ | the **window** of resource $r$ at vertex $v$: the interval the value must lie in on arrival at $v$ | `node_windows[r][v] = (lb, ub)`; C++ `lb_[r][v]`, `ub_[r][v]` |
| $c_r(v) \ge 0$ | the **node consumption** of resource $r$ at $v$ | `node_consumption[r][v]` |
| $p_r$ | the **propagation policy** of resource $r$, one of `additive`, `window_wait`, `window_hard` | `window_policy[r]` (default `"additive"`) |
| $T_v$ | the value of the **time** resource at $v$: the service start time under `window_wait`, the arrival time under `window_hard` | `consumed_resources[time_res]` |
| $a_v,\ b_v,\ s_v$ | the time window and the service time of $v$, i.e. $lb$, $ub$ and $c$ of the time resource | `time_windows[v] = (a, b)`, `service_times[v]` |
| $H$ | the **horizon**: the upper bound on the time resource | `max_res[time_res]` |
| $\hat T_v$ | the **latest** feasible service start time at $v$; used only by the backward search | none |
| $g_r$ | the reversed-axis value of a window resource in a backward label, $g_r = H - \hat T$ | `consumed_resources[r]` under `direction="backward"` |
| $\varepsilon$ | the numerical tolerance of the window comparisons (the engine's own bound checks are exact) | `window_eps` (default `1e-9`) |
| $\Sigma_r$ | the **rejection sentinel** of resource $r$: a value deliberately outside the engine's bound, so the ordinary feasibility test rejects the label | C++ `sentinel_[r]` |
| $R \subseteq N$ | the **required set**: the vertices a feasible path must visit | `required_nodes` (defaults to every vertex other than `"Source"` and `"Sink"`) |

Two further conventions from `FORMULATIONS.md` Section 1 are used
throughout. $o$ and $d$ are the origin and destination vertices, spelled
`"Source"` and `"Sink"` in the code; $N$ is the customer set and $n = |N|$;
$t_{ij}$ is the travel time on arc $(i,j)$ and $w_{ij}$ its objective
weight, and the two are **independent data** — the objective is
$\sum w_{ij} x_{ij}$ and never $\sum t_{ij} x_{ij}$. Resource $0$ is the
critical resource $r_{\mathrm{crit}}$ and resource $1$ is the time resource
$r_{\mathrm{time}}$, unless `critical_res` / `time_res` say otherwise.

## 2. What this fork adds, and why

### 2.1 The three features, as changes to the model

**Per-node resource windows** (`FORMULATIONS.md` Section 3, model (P1))
attach to every resource a propagation policy and, to every vertex, an
admissible interval and a consumption. Time windows are the special case
"policy `window_wait` on the time resource", which is why one implementation
covers both. Upstream cspy has no notion of a per-vertex admissible interval
at all; the only way to express one was to write a resource extension
function — the function that maps a label's resource vector and an arc to
the resource vector after the extension (`FORMULATIONS.md` Section 1.6) — in
Python.

**Mandatory visits** (`FORMULATIONS.md` Section 4, model (P2)) add the
coverage constraint "every vertex of a required set $R$ is visited". With
$R = N$ this turns the elementary shortest path problem into the TSPTW.
Coverage cannot be expressed by a resource extension function, because what
has to change is the **dominance** rule — the rule by which one label
discards another (`FORMULATIONS.md` Section 1.6) — and a resource extension
function has no access to it. It could previously only be encoded in extra
resources, at a cost measured in Section 6.5.

**Early termination** (`FORMULATIONS.md` Section 6) turns the search into a
satisficing procedure: stop at the first complete path meeting a target
value, and report afterwards which of the four possible reasons ended the
search. This changes what is *claimed* about the returned path, not what the
search computes.

### 2.2 Why a Python resource extension function is not enough

In the approach of `TSPTW_GUIDE.md`, the time-window propagation
$T_j = \max(a_j,\ T_i + s_i + t_{ij})$ is written in Python as
`REFCallback.REF_fwd`, and cspy calls it once per label extension,
round-tripping C++ → Python → C++ each time. That is fine at teaching scale.
It is not fine in column generation, where the pricing problem is solved on
**every iteration**: the number of resource extension function calls in a
single `run()` reaches roughly **120,000 at $n = 30$ and 780,000 at
$n = 50$** (Section 9). At the profiling done when this branch was started, a
Python resource extension function invoked across the language boundary cost
about **5.2 µs per call** including its own body; even the pure difference
between an optimised array-based Python implementation and the native one is
**0.9–1.6 µs per call** lost to the boundary (Section 9.4).

This fork therefore implements the resource extension function for node
resource windows as a **pure C++ class, `NodeWindowREF`**, exposed directly
through `BiDirectional`'s constructor arguments. The mechanics of how a C++
class is registered so that its virtual calls never re-enter Python are in
Appendix A.

### 2.3 The two goals

1. **No Python calls inside the labelling loop.** The engine's virtual
   function calls stay entirely inside C++; the regression test
   `test_zero_python_calls_in_labelling_loop` demonstrates this with
   `sys.setprofile`.
2. **First-class support for `direction="both"`.** A consistent Python
   implementation of the backward and join functions is hard to get right
   (`TSPTW_GUIDE.md` discusses why), and upstream even had a segmentation
   fault (Section 10, caveat 10). This fork provides validated backward and
   join formulas in C++ (Section 3.5). For pricing with a tight capacity
   constraint, bidirectional search is **243x** faster than the native
   forward search on the largest instance measured, and **267x** faster than
   the Python forward search it replaces (Section 9.2, columns (b) and (a)
   against column (c)). Which of the two comparisons is meant matters, so
   both are stated wherever the figure appears.

## 3. Per-node resource windows: the model

This section states what the implementation computes. The equivalent mixed
integer program, the proof that subtours are excluded automatically and the
soundness arguments are `FORMULATIONS.md` Section 3.

### 3.1 The three propagation policies

Let a label sit at vertex $i$ with resource value $q_r$, and let it be
extended along the arc $(i,j)$. Write $q'_r$ for the value after the
extension. Every resource carries exactly one policy $p_r$, and unspecified
resources are `additive`, which reproduces the engine's default behaviour
bit for bit.

| Policy $p_r$ | $q'_r$ | The extension is rejected when |
|---|---|---|
| `additive` (default) | $q_r + t^{(r)}_{ij} + c_r(j)$ — the consumption of the **head** is added on arrival | the engine's own check $q^{\min}_r \le q'_r \le q^{\max}_r$ fails |
| `window_wait` | $\max\bigl(lb_r(j),\ q_r + c_r(i) + t^{(r)}_{ij}\bigr)$ — the consumption of the **tail** is added on departure; an early arrival waits | $q'_r > ub_r(j) + \varepsilon$ |
| `window_hard` | $q_r + c_r(i) + t^{(r)}_{ij}$ — as above, but waiting is not allowed | $q'_r < lb_r(j) - \varepsilon$ or $q'_r > ub_r(j) + \varepsilon$ |

**Rejection is expressed by returning the sentinel $\Sigma_r$**, a value
placed deliberately outside $[q^{\min}_r,\ q^{\max}_r]$ so that the engine's
ordinary feasibility test discards the label. A resource extension function
has no other way of saying "reject", and this is why $q^{\max}_r$ must be
finite for every resource carrying a window policy.

Note the two settings of `additive` consumption that matter later: $c_r(v) =
-1$ at a single customer $v$ gives a **visit indicator resource** (a flag
that reads $0$ while $v$ is unvisited and $-1$ afterwards), and $c_r(v) = +1$
at every customer gives a **visit counter**. Both are used in Section 5.3,
example (2).

### 3.2 Time windows as the special case

Setting $p_{r_{\mathrm{time}}} = \texttt{window\_wait}$ with $lb = a_v$,
$ub = b_v$ and $c_r(v) = s_v$ makes the propagated value exactly

$$
T_j = \max\bigl(a_j,\ T_i + s_i + t_{ij}\bigr),
\qquad\text{rejected when } T_j > b_j ,
$$

with $T_v$ the **service start time** at $v$. This is the recursion of
`FORMULATIONS.md` Section 3.2 and the one `TSPTW_GUIDE.md` writes in Python.

**The service-time convention** adds $s_i$ on departure from the tail. This
is the formula that was validated by brute-force cross-checking against 300+
random instances in the proof of concept, and it is the natural reading of a
time window: service may start at $T_j$, and service at $i$ must finish
before the vehicle leaves $i$.

The alternative **D-convention** checks the window on arrival and reports
the departure time $D_v = T_v + s_v$. It is **feasibility-equivalent** for
the same data; only the reported value shifts by $+s_v$. This fork does not
use it, and the distinction matters only when comparing output against
another code.

### 3.3 The Source clamp

A label's initial resource vector is zero. An instance with
$lb_r(o) > 0$ would therefore start below its own window, so for the two
window policies the value is first replaced by

$$
q_r \leftarrow \max\bigl(q_r,\ lb_r(o)\bigr)
\qquad\text{whenever the tail is } o .
$$

The clamp is idempotent, so applying it on every extension out of $o$ is
harmless.

### 3.4 Why the critical resource is fixed to `additive`

The bidirectional search — the search that extends labels forward from $o$
and backward from $d$ and joins them at a halfway point
(`FORMULATIONS.md` Section 1.6) — uses the value of the **critical
resource** to decide where the two halves meet, and therefore assumes that
resource is monotone and additive. This fork enforces the assumption rather
than trusting it: a non-`additive` policy on $r_{\mathrm{crit}}$, or a
non-zero node consumption on it, raises an exception on the C++ side. The
recommended critical resource is an arc counter, `res_cost[0] = 1` on every
arc.

### 3.5 The backward and join functions

These define what `direction="both"` computes, so they are part of the model
and not an implementation detail. The reversal notation is fixed first:
$H = q^{\max}_r$ is the horizon, $\hat T$ is the **latest** feasible service
start time at a vertex, and a backward label carries $g_r = H - \hat T$, the
value on the reversed axis. All three are in the table of Section 1.1. The
formulas below are written for a `window_wait` resource; the critical
resource is always additive.

**`additive` resources under a backward extension.** The table of
Section 3.1 is written head-on-arrival, $q'_r = q_r + t^{(r)}_{ij} + c_r(j)$,
which is the *forward* orientation. A backward label sits at the head $j$ and
extends toward the tail $i$, so the node consumption it picks up is the one
of $i$, the vertex it is arriving at in that orientation:

$$
q'_r \;=\; q_r + t^{(r)}_{ij} + c_r(i)
\qquad \text{(backward extension of an \texttt{additive} resource)} .
$$

Both orientations add the consumption of the vertex being arrived at; the
formulas differ only because "arrived at" means the head going forward and
the tail going backward. This matters as soon as `node_consumption` is
combined with `direction="both"`, and it is why a visit indicator or a visit
counter accumulates the same total in either direction.

**Forward** (tail $i$ → head $j$), exactly the formula of Sections 3.2
and 3.3:

$$T' = \max(T,\ lb_r(o))\ \text{(tail} = o \text{ only)},\qquad
T_j = \max\bigl(lb_r(j),\ T' + c_r(i) + t^{(r)}_{ij}\bigr)$$

with the sentinel returned if $T_j > ub_r(j) + \varepsilon$.

**Backward** (a backward label sits at the head $j$ and extends toward the
tail $i$; the time axis is reversed):

$$g_j = \max\bigl(g,\ H - ub_r(j)\bigr),\qquad
g_i = \max\bigl(g_j + c_r(i) + t^{(r)}_{ij},\ H - ub_r(i)\bigr)$$

with the sentinel returned if $g_i > H - lb_r(i) + \varepsilon$. The clamp
$\max(g,\ H - ub)$ corrects the initial backward label, whose $g$ is $0$,
and is a no-op on every other label. A backward extension can only track an
upper bound — a no-waiting **lower** bound cannot be checked backward — which
is why `window_hard` is restricted to `direction="forward"`.

**Join** (a forward label at tail $i$ meets a backward label at head $j$
across the arc $(i,j)$). Three steps, all three of which the implementation
performs:

$$T'_i = \max\bigl(T_i,\ lb_r(o)\bigr)\ \text{(tail} = o \text{ only)},
\qquad
g_j \leftarrow \max\bigl(g_j,\ H - ub_r(j)\bigr),$$

$$T_j^{\mathrm{start}} = \max\bigl(lb_r(j),\ T'_i + c_r(i) + t^{(r)}_{ij}\bigr),
\qquad \text{returned value} = T_j^{\mathrm{start}} + g_j ,$$

with the sentinel returned instead if $T_j^{\mathrm{start}} > ub_r(j) +
\varepsilon$.

The first clamp is the Source clamp of Section 3.3 again, needed because a
single-arc join $o \to j$ meets a forward label that is still the initial one;
the second is the same correction the backward rule applies to the initial
backward label. The explicit rejection in the last line is redundant in exact
arithmetic — $T_j^{\mathrm{start}} + g_j \le H$ together with
$g_j \ge H - ub_r(j)$ already gives $T_j^{\mathrm{start}} \le ub_r(j)$ — and
is kept because it applies the tolerance $\varepsilon$ on the same side as
the forward and backward rules do.

The joined path is window-feasible **if and only if**
$T_j^{\mathrm{start}} + g_j \le H$, which is exactly what the engine's
$q^{\max}_r$ check evaluates. This is also why the reported value of a
window resource is a feasibility surrogate rather than a schedule under
`direction="both"` (Section 10, caveat 7). The critical resource alone needs
special handling inside the engine; Appendix A.5 explains it.

### 3.6 Dominance soundness, by policy

Dominance discards a label $L_2$ when another label $L_1$ at the same vertex
has no larger weight, no larger value in every resource, and — under
`elementary=True` — an unreachable set contained in $L_2$'s. Whether that is
**sound**, meaning that it never discards a label that could have led to an
optimal solution, depends on the policy.

- **`additive` and `window_wait` are sound.** Both propagation rules are
  non-decreasing in $q_r$, and both reject only from above, so a smaller
  value is always at least as good. `FORMULATIONS.md` Section 3.9.1 gives
  the argument.
- **`window_hard` is not sound in general.** Its rejection test is
  two-sided: arriving *too early* is refused. A smaller value is therefore
  not always at least as good, and the component-wise comparison is no
  longer a valid criterion.

The failure is not hypothetical. On a six-vertex instance in which a vertex
$w$ has the degenerate window $[5, 5]$, four partial paths reach a vertex
$v$ with the same weight and time values $2, 3, 3, 4$; only the label with
the **largest** time, $T_v = 4$, can extend to $w$ and reach the optimum, yet
the other three each dominate it on the component-wise test and one of them
does discard it. cspy then reports `'completed'` while returning a path of
weight 100 on an instance whose optimum is 0. The instance, the enumeration
and the confirmation that dominance is the cause are in `FORMULATIONS.md`
Section 3.9.2.

Use `window_hard` only when the instance is small enough to be checked by
enumeration, or when the answer is being used as a heuristic. Section 5.3,
example (3), is a case where the returned answer *is* optimal — and
Section 5.3 explains why that is a property of the instance, not of the
policy.

### 3.7 The mixed integer program

The mixed integer program equivalent to everything above — the arc-flow
constraints, the big-M time propagation constraints, the smallest valid
big-M constants, and the proof that subtours are excluded without any extra
constraint — is `FORMULATIONS.md` Section 3, model (P1).

## 4. Python API reference

`BiDirectional`'s constructor gained the arguments below. Existing arguments
and existing functionality, including the Python `REF_callback` mechanism,
remain fully backward compatible.

### 4.1 The simple interface: time windows

| Argument | Type / default | Symbol | Meaning |
|---|---|---|---|
| `time_windows` | `{node label: (a_v, b_v)}` / `None` | $a_v,\ b_v$ | Sets `window_wait` on resource `time_res`. Keys are the **original node labels** of `G`, not the internal integer identifiers. Vertices not listed default to $(0,\ \texttt{max\_res[time\_res]})$ |
| `service_times` | `{node label: s_v}` / `None` | $s_v \ge 0$ | Added on departure from the tail. Vertices not listed default to $0$. Only usable together with `time_windows` |
| `time_res` | `int` / `1` | $r_{\mathrm{time}}$ | The resource index `time_windows` applies to. Must differ from the critical resource's index |

### 4.2 The general interface: any resource, any policy

| Argument | Type / default | Symbol | Meaning |
|---|---|---|---|
| `node_windows` | `{r: {node label: (lb, ub)}}` / `None` | $lb_r(v),\ ub_r(v)$ | Per-resource, per-vertex windows |
| `node_consumption` | `{r: {node label: c_v}}` / `None` | $c_r(v)$ | Per-resource, per-vertex consumption; when it is added depends on the policy (Section 3.1) |
| `window_policy` | `{r: 'additive'\|'window_wait'\|'window_hard'}` / `None` | $p_r$ | Resources not listed default to `'additive'` |
| `window_eps` | `float` / `1e-9` | $\varepsilon$ | Tolerance of the window comparisons only |

The simple interface is exactly syntactic sugar for the general one:
`time_windows=TW, service_times=S` is `node_windows={time_res: TW},
node_consumption={time_res: S}, window_policy={time_res: "window_wait"}`.
Section 5.3, example (1), checks that claim at run time.

### 4.3 Validation rules and mutual exclusions

All violations are collected and raised together as a single exception.

- **Mutually exclusive** with `REF_callback` (the Python resource extension
  function mechanism) and with `find_critical_res=True`.
- **`window_hard` requires `direction="forward"`** (Section 3.5).
- **`max_res[r]` must be finite** for any resource carrying a window policy,
  because the rejection sentinel has to exceed it (Section 3.1).
- **Supplying `node_windows[r]` while leaving `window_policy[r]` at
  `additive` is an error**, so that a window can never be silently ignored.
- **The critical resource must stay `additive` with zero node consumption**
  (Section 3.4).
- **`preprocess=True` becomes a no-op**: the `prune_graph` step is always
  skipped when a native or custom resource extension function is in use
  (Section 10, caveat 3).

## 5. Worked examples of the interface

Every example in this section runs on the same four-vertex instance, so that
the effect of each argument can be read off against a single set of tables.

### 5.1 Instance B

Instance B is defined in `FORMULATIONS.md` Section 3.11; its data are
restated here because the code sits next to them. Four vertices
$V = \{o, 1, 2, d\}$ and six arcs. The graph and the time-window data are
identical in the two weight variants **B-i** and **B-ii**; only $w$ differs,
which is the point — the two have the same feasible set and different
optima.

**Arc data.** `res_cost[0] = 1` on every arc (the arc counter),
`res_cost[1]` $= t_{ij}$.

| arc $(i,j)$ | $t_{ij}$ | $w_{ij}$ (B-i) | $w_{ij}$ (B-ii) |
|---|---:|---:|---:|
| $(o, 1)$ | 2 | 0 | 0 |
| $(o, 2)$ | 5 | 0 | 0 |
| $(1, 2)$ | 3 | −10 | 5 |
| $(2, 1)$ | 3 | −10 | 5 |
| $(1, d)$ | 2 | 0 | 1 |
| $(2, d)$ | 2 | 0 | 1 |

There is no arc $(o,d)$, no arc out of $d$ and no arc into $o$.

**Vertex data.** The values for $o$ and $d$ are the wrapper's defaults,
since neither is listed in `time_windows` / `node_windows` or in
`service_times` / `node_consumption`: an unlisted vertex gets the window
$[0,\ q^{\max}_{r_{\mathrm{time}}}] = [0, 20]$ and consumption $0$.

| vertex | $a_v$ | $b_v$ | $s_v$ |
|---|---:|---:|---:|
| $o$ | 0 | 20 | 0 |
| $1$ | 0 | 4 | 1 |
| $2$ | 8 | 12 | 1 |
| $d$ | 0 | 20 | 0 |

**Bounds.** $q^{\max} = (10,\ 20)$, so $H = 20$ and the arc bound is
$q^{\max}_0 = 10$; $q^{\min} = (0,\ 0)$. Example (2) of Section 5.3 adds
three resources and changes these, as its own table records.

**The four elementary $o$–$d$ paths**, with the two time traces:

| path | arcs | $\sum t_{ij}$ | $z$ (B-i) | $z$ (B-ii) | $T$ under `window_wait` | feasible? | $T$ under `window_hard` | feasible? |
|---|---:|---:|---:|---:|---|---|---|---|
| $P_1 = o \to 1 \to d$ | 2 | 4 | 0 | 1 | $o{:}0,\ 1{:}2,\ d{:}5$ | yes | $o{:}0,\ 1{:}2,\ d{:}5$ | yes |
| $P_2 = o \to 2 \to d$ | 2 | 7 | 0 | 1 | $o{:}0,\ 2{:}8,\ d{:}11$ | yes (waits 3 at 2) | $o{:}0,\ 2{:}5$ | **no**: $5 < a_2 = 8$ |
| $P_3 = o \to 1 \to 2 \to d$ | 3 | 7 | −10 | 6 | $o{:}0,\ 1{:}2,\ 2{:}8,\ d{:}11$ | yes (waits 2 at 2) | $o{:}0,\ 1{:}2,\ 2{:}6$ | **no**: $6 < a_2 = 8$ |
| $P_4 = o \to 2 \to 1 \to d$ | 3 | 10 | −10 | 6 | $o{:}0,\ 2{:}8,\ 1{:}12$ | **no**: $12 > b_1 = 4$ | $o{:}0,\ 2{:}5$ | **no**: $5 < a_2 = 8$ |

Two things to read off this table. First, $\sum t$ and $z$ rank the paths
differently in both variants: the objective is $\sum w_{ij} x_{ij}$ and
nothing else. Second, waiting is never charged — $P_2$ waits 3 units and
$P_3$ waits 2, and neither appears in $z$; waiting affects feasibility only,
by pushing later values up against $b_j$ and $H$. The arc bound is not
binding: $3 \le q^{\max}_0 = 10$.

**The optima**, one per configuration used below:

| configuration | used in | feasible set | $z^{*}$ | optimal path(s) | $q$ at $d$ |
|---|---|---|---:|---|---|
| B-i, `window_wait` | Section 5.2 | $P_1, P_2, P_3$ | −10 | $P_3$ (unique) | $(3,\ 11)$ |
| B-ii, `window_wait` | Section 5.3 (1) | $P_1, P_2, P_3$ | 1 | $P_1$ **and** $P_2$ (a tie) | $(2,5)$ resp. $(2,11)$ |
| B-ii, `window_wait` + coverage | Section 5.3 (2) | $P_3$ | 6 | $P_3$ (unique) | $(3,\ 11)$ |
| B-ii, `window_hard` | Section 5.3 (3) | $P_1$ | 1 | $P_1$ (unique) | $(2,\ 5)$ |

**The README quick start is Instance B-i** with the customers named `"A"`
and `"B"` instead of `1` and `2`. It was re-run against this section: both
spellings return the path `Source → A/1 → B/2 → Sink`, `total_cost` −10.0
and `consumed_resources` `[3.0, 11.0]`.

### 5.2 The simple interface (executed code)

**The model.** Instance B-i under `window_wait` on the time resource: find
the minimum-weight elementary $o$–$d$ path subject to $q_0 \le 10$ arcs, the
horizon $H = 20$, and the time window of every vertex, with $T$ propagated by
$T_j = \max(a_j,\ T_i + s_i + t_{ij})$. This is model (P1) of
`FORMULATIONS.md` Section 3.3. By the table of Section 5.1 its optimum is
$P_3$ with $z^{*} = -10$, unique.

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

**How to read this.** Both directions return $P_3$ at $z = -10$, as the
table predicts. The reverse order $P_4$ is rejected because service at
customer 1 would start at $8 + 1 + 3 = 12 > b_1 = 4$; $P_3$ is feasible
because customer 2 waits 2 units until $a_2 = 8$, giving
$T_2 = \max(8,\ 2 + 1 + 3) = 8$ and $T_d = 11$. Note that
`consumed_resources[1]` is the genuine service start time only under
`direction="forward"` (11); under `"both"` it is the join surrogate
$T^{\mathrm{start}} + g$ of Section 3.5 (16), which certifies feasibility
and is not a schedule (Section 10, caveat 7).

### 5.3 The general interface (executed code)

The three examples below solve **three different problems** on the same
instance data. Each is named before its code.

- **(1)** the ESPPRC with time windows: Instance B-ii under `window_wait`,
  model (P1) of `FORMULATIONS.md` Section 3.3, with
  $q^{\max} = (10, 20)$, $q^{\min} = (0,0)$. **Optimum $z^{*} = 1$, attained
  by both $P_1$ and $P_2$** (a tie).
- **(2)** the same **plus the coverage constraint** $\sum_i x_{ik} = 1$ for
  every $k \in \{1, 2\}$, i.e. model (P2) of `FORMULATIONS.md` Section 4,
  here encoded in resources exactly as `FORMULATIONS.md` Section 4.3
  prescribes: two visit indicator resources ($c(1) = -1$ on resource 2,
  $c(2) = -1$ on resource 3, both bounded to $[-1, 0]$) and one visit counter
  (resource 4, $c(v) = +1$ at both customers, $q^{\min}_4 = 2$), so
  $q^{\max} = (10, 20, 0, 0, 10)$ and $q^{\min} = (0, 0, -1, -1, 2)$.
  **Optimum $z^{*} = 6$, attained by $P_3$, unique** — the only path
  covering both customers.
- **(3)** the same as (1) but with the time resource under `window_hard`, so
  that waiting is forbidden: model (P1) with
  $p_{r_{\mathrm{time}}} = \texttt{window\_hard}$, `FORMULATIONS.md`
  Section 3.8. The feasible set collapses to $\{P_1\}$, so
  **$z^{*} = 1$ attained by $P_1$, unique**.

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

# (2) Force full-visit coverage with visit indicators (res[2,3]: 0 -> -1) and
#     a visit counter (res[4]: +1). min_res[4]=2 means "2 customers visited by
#     the time Sink is reached" (enforced only at the final feasibility check).
#     The indicators are required to restrict dominance to matching visit sets
#     (FORMULATIONS.md Section 4.3). Section 6 asks for the same thing with
#     require_all_visits=True and no extra resources; this encoding is kept
#     as the reference implementation that the Section 6 core code is
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

**How to read this.**

**(1)** No coverage is required, so a two-arc path of weight 1 suffices.
Note that **the optimum is not unique**: $P_1$ and $P_2$ both have $z = 1$,
and the returned $P_2$ is a tie-break made by the dominance test and by the
**label heap** — the container of labels generated but not yet extended,
ordered by resource consumption rather than by cost
(`FORMULATIONS.md` Section 1.6) — and not by the model. Returning $P_1$ would
be equally correct;
perturbing $w_{(2,d)}$ from 1 to 1.001 makes cspy return $P_1$, which is how
the tie was confirmed (`FORMULATIONS.md` Section 3.11, caveat 1). The second
run checks that the general interface and the simple interface agree on
path, cost and resource vector.

**(2)** Coverage forces $P_3$, weight 6. The resource vector shows the two
indicators at $-1$ and the counter at $2$, exactly the values
`FORMULATIONS.md` Section 4.3 predicts.

**(3)** Waiting is forbidden, so customer 2 becomes unreachable — every path
arrives before $a_2 = 8$ — and only $P_1$ survives. **This answer is correct
even though `window_hard` dominance is unsound in general** (Section 3.6).
The reason is specific to this instance: under `window_hard` the search
produces exactly three forward labels, one per reachable vertex. Dominance is
only ever tested between two labels sitting at the *same* vertex — that
vertex's **efficient set**, the set of non-dominated labels kept there
(`FORMULATIONS.md` Section 1.6) — and never across vertices, so with one
label per vertex every efficient set is a singleton, no dominance test fires,
and nothing can be wrongly pruned. `FORMULATIONS.md` Section 3.9.3 records
the census that establishes this. Do not read example (3) as evidence that
`window_hard` is safe.

**Example (2) is a reference implementation, not the recommended way of
asking for coverage.** It is kept because it shows the general interface is
expressive enough to reproduce the visit indicator encoding without a Python
resource extension function, and because it is the yardstick the core
implementation of Section 6 is measured against. To actually require
coverage, use `require_all_visits=True` (Section 6): it expresses the same
requirement with no extra resources, it cannot be mis-assembled, and
Section 6.5 shows the two return the same answers while the encoding gets
steadily slower as the number of customers grows.

### 5.4 Advanced: constructing `NodeWindowREF` directly

The C++ object can also be built without going through the wrapper;
`REF_fwd` / `REF_bwd` / `REF_join` are callable from Python, which is what
the unit tests and the equivalence checks use. This is the one place in this
guide where vertices are the **internal integer identifiers** rather than the
original node labels, because the wrapper — which is what normally performs
that translation (Appendix A.3) — is being bypassed.

The two constructor calls take, in order:

| Argument | Meaning |
|---|---|
| `n_vertices` | the number of vertices of the graph, i.e. how long each per-vertex array must be |
| `max_res` | the bound vector $q^{\max}$, wrapped in `DoubleVector`; the rejection sentinel $\Sigma_r$ is derived from it, so each entry carrying a window policy must be finite |
| `source_id`, `sink_id` | the internal integer identifiers of $o$ and $d$ |
| `critical_res` | the index $r_{\mathrm{crit}}$, which this class then holds to the `additive` policy |
| `eps` | the window tolerance $\varepsilon$ |
| `r` | the index of the resource being configured |
| `lb_vec`, `ub_vec` | the windows $lb_r(v)$ and $ub_r(v)$, one entry per vertex, indexed by internal identifier |
| `cons_vec` | the node consumptions $c_r(v)$, likewise one entry per vertex |

A complete, runnable instance: two resources on a three-vertex graph
$o \to 1 \to d$ with internal identifiers $o = 0$, $1 = 1$, $d = 2$, a
horizon $H = 20$, and resource 1 a time resource under `window_wait` whose
only real window is $[8, 12]$ at vertex 1, with service time 1 there.

```python
from cspy.algorithms.pyBiDirectionalCpp import (
    NodeWindowREF, DoubleVector, POLICY_WINDOW_WAIT)

n_vertices, source_id, sink_id, critical_res, eps = 3, 0, 2, 0, 1e-9
max_res = [10.0, 20.0]                       # arc counter, then time
r = 1                                        # configure the time resource
lb_vec = DoubleVector([0.0, 8.0, 0.0])       # lb_r(o), lb_r(1), lb_r(d)
ub_vec = DoubleVector([20.0, 12.0, 20.0])    # ub_r(o), ub_r(1), ub_r(d)
cons_vec = DoubleVector([0.0, 1.0, 0.0])     # s_o, s_1, s_d

ref = NodeWindowREF(n_vertices, DoubleVector(max_res), source_id, sink_id,
                    critical_res, eps)
ref.setResourcePolicy(r, POLICY_WINDOW_WAIT, lb_vec, ub_vec, cons_vec)

# One forward extension o -> 1 along an arc of travel time 5, from the
# initial label (resource vector all zeros): T_1 = max(8, 0 + 0 + 5) = 8.
print(list(ref.REF_fwd(DoubleVector([0.0, 0.0]), source_id, 1,
                       DoubleVector([1.0, 5.0]), [], 0.0)))
```

Output (actual output):

```text
[1.0, 8.0]
```

— one arc consumed, and a service start time of 8 at vertex 1: the vehicle
arrives at 5, waits until $a_1 = 8$, exactly the `window_wait` rule of
Section 3.1.

Invalid input — an out-of-range resource index, $lb > ub$, a non-additive
policy on the critical resource, `max_res=inf` on a resource with a window
policy — raises a C++ `std::invalid_argument`, converted to a Python
`RuntimeError`. Constructing the object this way makes **you** responsible
for keeping it alive for the lifetime of the `BiDirectional` object;
Appendix A.6 explains why.

## 6. Mandatory visits (`require_all_visits`)

### 6.1 The requirement, and why encoding it in resources is clumsy

Nothing in a labelling algorithm asks for a path that *covers* a given set
of vertices. It asks for a shortest path subject to resource bounds, and a
path that skips a customer is normally shorter than one that does not. The
model is (P2) of `FORMULATIONS.md` Section 4: model (P1) together with

$$
\sum_{i\,:\,(i,k) \in A} x_{ik} = 1 \qquad \forall k \in R ,
$$

the required set $R$ being a subset of the customers. With $R = N$ this is
the TSPTW.

Before this option, the only way to impose that constraint was to encode it
in resources, as example (2) of Section 5.3 does and `FORMULATIONS.md`
Section 4.3 sets out. For $n$ customers that means assembling three things
by hand:

1. one **visit indicator resource per customer** — `additive` policy,
   consumption $-1$ at that customer, $q^{\max} = 0$ and $q^{\min} = -1$, so
   the resource reads $0$ while the customer is unvisited and $-1$ once it
   has been visited;
2. one **visit counter resource** — consumption $+1$ at every customer and
   $q^{\min} = n$, which is what actually rejects an incomplete path when
   the destination is reached;
3. a `res_cost` array widened to length $n+3$ on **every** arc of the graph.

Three things are wrong with that.

- **The resource vector grows with the instance.** Dominance compares
  resource vectors component by component, so each comparison costs $n+3$
  floating-point comparisons instead of two, and each label carries
  $8(n+3)$ bytes of resource data instead of 16. Section 6.5 measures the
  result.
- **Every step of the assembly fails silently.** Widening `res_cost` on all
  but one arc, leaving an indicator's $q^{\min}$ at $0$, or putting the
  counter's bound on the wrong index each produce a perfectly well-formed
  run that returns a plausible but wrong answer. Nothing raises, because
  each of these is a legitimate resource constrained shortest path model —
  just not the intended one.
- **The requirement never appears in the model.** "Visit every customer" is
  spread across three sets of numbers, none of which says so.

The indicator resources are not decoration. They are what makes the
dominance rule sound (Section 6.4); dropping them and keeping only the
counter yields a search that reports no solution on instances that have one
(`FORMULATIONS.md` Section 4.3 shows the degenerate output).

`require_all_visits=True` replaces all three steps. The resource vector
stays at the two resources the model actually needs, the critical arc
counter and time.

### 6.2 The two arguments

| Argument | Type / default | Meaning |
|---|---|---|
| `require_all_visits` | `bool` / `False` | When true, only `Source` → `Sink` paths that visit every vertex of `required_nodes` are accepted, and dominance is restricted to match (Section 6.4). Requires `direction='forward'` and `elementary=True` |
| `required_nodes` | iterable of node labels / `None` | The set $R$, given as the **original node labels** of `G`, not the internal integer identifiers. Duplicates are ignored and the order is irrelevant. `None` means every vertex other than `'Source'` and `'Sink'`. Only usable together with `require_all_visits=True` |

`required_nodes` accepts any iterable, including one that can be traversed
only once (a generator expression, `map`, `filter`, `iter(...)`, a
`csv.reader`): the argument is materialised exactly once, during validation,
and that materialised list is what the rest of the constructor uses. An
**empty** required set is rejected rather than quietly accepted, because it
would turn the call back into a plain elementary shortest path solve while
`require_all_visits=True` still reads as though the requirement were in
force. The same applies to a graph whose only vertices are `'Source'` and
`'Sink'`.

### 6.3 Instance C, and the code that solves it

**Instance C** is the six-customer TSPTW of
[`tsptw_cspy.py`](./tsptw_cspy.py), defined in `FORMULATIONS.md`
Section 4.8, whose optimum is known independently by exhaustive search over
all $6! = 720$ permutations. The depot is vertex 0 and is split into $o$ and
$d$; $N = \{1, \dots, 6\}$, $R = N$, and $w_{ij} = t_{ij}$.

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

**Bounds.** $q^{\max} = (7,\ 200)$ — seven arcs for a tour through six
customers, and the horizon $H = b_0 = 200$ — and $q^{\min} = (0,\ 0)$.

**The optimum.** $z^{*} = 33$, attained by the **unique** tour
$0 \to 2 \to 5 \to 4 \to 1 \to 6 \to 3 \to 0$, with $q = (7,\ 66)$. Only 4
of the 720 permutations are feasible at all. The instance was constructed by
seed search so that windows, waiting and service times are all three binding
simultaneously: ignoring the windows the optimal tour costs 29 and is
infeasible here; the optimal tour waits 12 units at customer 4 and arrives at
customer 5 exactly at its deadline $b_5 = 13$; and replacing every service
time by the constant 3 changes the optimal visiting order.

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

**How to read this.** The first tour is the known optimum of Instance C:
cost 33, seven arcs, depot return (service start) time 66 — exactly the
values tabulated above. The second run sets $R = \{2, 5\}$, and since
visiting anyone else only adds travel time it returns the two-customer tour
at cost 16. A **proper subset is a meaningful request, not a degenerate
one**: the listed vertices must be visited and the rest are visited only
when that pays off. The third run leaves `direction` at its default
`'both'` and is refused in the constructor (Section 6.6, restriction 1).

### 6.4 Why the dominance rule has to change

The engine's dominance rule prunes a label when another label at the same
vertex has no larger weight, no larger value in every resource, and (under
`elementary=True`) an unreachable set contained in the other's. That rule is
sound for the ESPPRC, because there **any** elementary completion is
acceptable. It is **not** sound once every required vertex must appear on
the path: a cheap label whose visited set is a proper subset can dominate a
label whose visited set is a superset, and the pruned label may have been
the only one that could still cover the remaining required vertices. The
concrete failure on Instance C is that the search reports the degenerate
`['Source']` on an instance that has a feasible tour.

The added condition is stated once, over the visited sets themselves: **a
label may dominate another only when the two visit exactly the same required
vertices.** Writing $V(L)$ for the set of vertices on the partial path of
$L$,

$$
V(L_1) \cap R \;=\; V(L_2) \cap R .
$$

The **terminal condition** is the other half: an extension into $d$ is
refused unless the label already covers $R$.

*Sketch.* Any completion of $L_2$ that is resource feasible and covers $R$
is also a valid completion of $L_1$ — it stays elementary and resource
feasible for the usual reasons, and it still covers $R$ because whatever it
does not visit lies in $V(L_2) \cap R = V(L_1) \cap R$ — so discarding $L_2$
cannot lose an optimal solution. The terminal condition loses nothing
because an optimal path covers $R$ already at the vertex before $d$.

**The full proof, and the answer to "why equality rather than containment",
are `FORMULATIONS.md` Section 4.4.** That section also records the one
hypothesis the proof borrows: monotonicity of the resource extension
functions, which the engine assumes anyway, so combining
`require_all_visits` with `window_hard` is unsound for the reason of
Section 3.6 and not because of coverage.

### 6.5 Relation to the visit indicator encoding, and what it costs

**The two are the same pruning rule.** In the encoding of Section 5.3,
example (2), "$\le$ on every indicator resource" means
$V(L_1) \supseteq V(L_2)$ — the indicators are decremented, which reverses
the direction. The opposite inclusion comes from the **arc counter**: with
`res_cost[0] = 1` on every arc, the component-wise condition
$q_0(L_1) \le q_0(L_2)$ reads $|V(L_1)| \le |V(L_2)|$ for two labels at the
same vertex, and a superset of no larger size is equal. Together they say the
visited sets coincide. The core condition says the visited sets coincide on
$R$, which given that the labels sit at the same vertex is the same
statement.

It is worth being precise about what does *not* supply the second inclusion:
the elementary containment condition compares the **unreachable** sets, and
an unreachable set strictly contains its label's visited set as soon as one
extension has been rejected, so it does not bound the visited sets on its
own. The arc counter is what closes the argument.

So the two generate and keep the same set of labels; only the representation
differs, from a vector of doubles to $\lceil |R| / 64 \rceil$ machine words.
`FORMULATIONS.md` Section 4.5 states the equivalence precisely. This is why
the encoding is kept as the reference implementation in
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

Both express the same thing, so both should return the same answer. On
Instance C they do:

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

**These timings are not the practical ceiling quoted elsewhere.** The
`require_all_visits` column above reads 0.93 s at $n = 14$, while
restriction 7 of Section 6.6 below, `FORMULATIONS.md` Section 4.7 and the
README all say "seconds to minutes at fourteen to
sixteen". Both are right and they measure different things: the instances
here were generated to compare two encodings, so they are drawn from one
family with relatively wide windows, and four instances per row is a median
over a small sample. The "seconds to minutes" band is the range across
instance families, and tight windows at the same $n$ sit at its upper end.
Read the table above for the **ratio** between the two encodings, which is
what it was built to measure, and not for the absolute difficulty of a
14-customer TSPTW.

### 6.6 Restrictions and caveats

1. **`direction='forward'` only.** `'both'` and `'backward'` are rejected
   with an explanatory exception, from the Python layer and from the C++
   engine. The backward search and the label joining step would each need
   their own coverage argument (the bounds used in `joinLabels`, `getUB`
   and `best_labels` may come from paths that do not cover $R$), and until
   that is worked out the safe answer is to refuse. Since the default is
   `direction='both'`, this exception is the first thing most callers see;
   it names the fix.
2. **`elementary=True` is required.** The soundness argument of
   Section 6.4 uses it, and without it the visited-set bit set would
   silently collapse repeated visits.
3. **The monotonicity assumption is inherited, not introduced.** A custom
   `REF_callback` that is not monotone, or the `window_hard` policy (which
   rejects early arrivals instead of waiting), breaks the assumption that
   $q(L_1) \le q(L_2)$ propagates. That is a pre-existing property of the
   engine's dominance rule, explained in Section 3.6 and proved unsound by
   counterexample in `FORMULATIONS.md` Section 3.9.2;
   `require_all_visits` neither causes nor cures it. A warning is logged
   when the two are combined.
4. **$q^{\min}_r > 0$ on a non-critical resource gives a wrong answer, not
   a weaker bound.** The dominance rule assumes that the feasibility of a
   non-critical resource is decided by its upper bound alone, so a strictly
   positive lower bound on such a resource lets the search discard labels
   that are on the way to a feasible path, and the run then reports the
   degenerate `['Source']` for an instance that does have a solution
   (`FORMULATIONS.md` Section 4.6 states exactly when the lower bound is
   checked). A warning is logged. This applies without `require_all_visits`
   as well, but with `require_all_visits` there is no longer any reason to
   set such a bound at all: coverage is enforced directly and not through a
   counter resource. A lower bound that really is part of the model belongs
   on the critical resource (`critical_res`), where it is handled exactly.
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
   no `Source` → `Sink` path can do that anyway.
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
   `Source` → `Sink` path has been accepted, the result is the degenerate
   `['Source']` with `total_cost` 0.0 — byte for byte what a genuinely
   infeasible instance returns, and note that the 0.0 is a *default*, not a
   path cost, which is why it must never be read as one (Section 8.3 gives
   the check). This is pre-existing engine behaviour, but
   `require_all_visits` makes it much easier to hit, because the first
   accepted path is far deeper in the search than in a plain elementary
   shortest path problem. The returned path alone cannot separate the two
   cases; the `termination_reason` property (Section 7.2) can:
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
as in Appendix B.

## 7. Stopping as soon as a better solution is found

Exact labelling pays for its optimality proof: most of the running time is
spent proving that no better path exists, long after a good one has been
found. When any solution better than a known value is enough — an
**incumbent** to beat inside a branching scheme, or a target value in a
satisficing application — the engine's `threshold` argument stops the search
at the first acceptable complete path. This fork adds a strict variant of
the comparison and, more importantly, an answer to the question the caller
is then left with: *why did the search stop?*

### 7.1 The two arguments, and what they claim

| Argument | Type / default | Meaning |
|---|---|---|
| `threshold` | `float` / `None` | Stop the search as soon as a resource-feasible `Source` → `Sink` path with total cost $\le \theta$ is accepted, and return that path. Upstream argument, unchanged |
| `threshold_strict` | `bool` / `False` | **New in this fork.** When true, the comparison becomes strict: stop only on total cost $< \theta$. Pass the value of a known incumbent as `threshold` to stop only when a strictly better solution is found — with the default $\le$ the incumbent's own value would stop the search immediately, proving nothing. Requires `threshold` to be a number (`None` and `NaN` are rejected); non-`bool` values are rejected |

**What is claimed and what is not.** The returned path satisfies
$z \le \theta$ (respectively $z < \theta$). That is the entire claim. It is
*not* claimed to be optimal, nor even to be the best path found so far: the
label queue is ordered by resource consumption, not by cost, so the returned
path is whichever acceptable path the search reached first. `FORMULATIONS.md`
Section 6.1 states the rule as a modification of the dynamic program. With
`threshold_strict=False` (the default) the behaviour is exactly the upstream
behaviour, bit for bit.

### 7.2 Reading the stop: `termination_reason`

After `run()`, the property `termination_reason` reports why the search
stopped; before `run()` it is `None`.

| Value | Meaning |
|---|---|
| `'completed'` | The search processed every generated label and a `Source` → `Sink` path was found. This certifies optimality **only when the dominance rule is sound** for the resource extensions in use; the documented exception in this fork is the `window_hard` policy (Section 3.6), where an exhausted search may still have pruned the optimum. The value is deliberately not named `'optimal'` |
| `'threshold_reached'` | A `Source` → `Sink` path meeting the threshold was found and the search stopped early; that path is the one returned. It is the **first acceptable path encountered, not necessarily the best found so far**: the label queue is ordered by resource consumption, not by cost |
| `'time_limit_reached'` | `time_limit` expired before the search could finish. A complete path found before the limit (if any) is still returned together with this reason; a degenerate result (Section 10, caveat 8) means the instance status is **unknown**, not proven infeasible |
| `'no_feasible_path'` | The search processed every generated label without finding any resource-feasible `Source` → `Sink` path: the instance is infeasible, under the same dominance-soundness proviso as `'completed'` |

This closes the gap noted in Section 6.6, restriction 8: a genuinely
infeasible instance (`'no_feasible_path'`) and a search truncated before its
first complete path (`'time_limit_reached'` with a degenerate result) both
return the same degenerate path, but are now told apart by the reason.

### 7.3 Threshold and strict threshold on Instance C (executed code)

The instance is Instance C of Section 6.3, with known optimum 33.

```python
"""Stop the six-customer TSPTW solve of Section 6.3 as soon as a tour
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

**How to read this.** Run (1) asked for any tour of cost at most 40 and the
first accepted tour happened to be the optimum — a coincidence of this
instance, not a guarantee. Run (2) is the intended use of
`threshold_strict`: the incumbent value 33 is passed as the threshold, no
strictly better tour exists, so the search runs to exhaustion, reports
`'completed'`, and still returns the best tour it found. Run (3) shows why
the strict variant is needed: with the default $\le$ comparison the
incumbent's own value stops the search at once, which proves nothing about
improvability.

### 7.4 Infeasible, or merely truncated? (executed code)

```python
"""Telling a genuinely infeasible instance apart from a search stopped by
the time limit, on Instance C of Section 6.3."""
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
time_windows = {i: (float(tw_a[i]), float(tw_b[i])) for i in range(1, n + 1)}
service_times = {i: float(service[i]) for i in range(1, n + 1)}

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
Section 6.6, restriction 8 explains why this distinction matters especially
under `require_all_visits`.

### 7.5 Maximisation objectives (executed code)

`BiDirectional` minimises. `FORMULATIONS.md` Section 6.3 proves the
proposition that makes a maximisation objective a special case of it: with
$w_{ij} = -\mathrm{rew}_{ij}$ every path satisfies
$z(P) = -\mathrm{rew}(P)$, hence for any target $X$

$$
\mathrm{rew}(P) > X \iff z(P) < -X ,
\qquad
\mathrm{rew}(P) \ge X \iff z(P) \le -X .
$$

So `threshold=-X` with `threshold_strict=True` stops exactly on a path of
reward strictly above $X$, and `threshold=-X` alone stops on reward at least
$X$. The reported `total_cost` is the **negated** objective value.

**Instance E** (`FORMULATIONS.md` Section 6.4). The digraph has vertices
$o, a, b, c, d$ and eight arcs, each carrying a reward; two resources, both
arc counters with $t^{(r)}_{ij} = 1$, bounds $q^{\max} = (10, 10)$ and
$q^{\min} = (0, 0)$. No windows.

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

The maximum reward is 18.

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

Run (1) stops at the first path whose reward exceeds 12; on this instance
that path happens to be the best one, which the table above lets the reader
check. Run (2) asks for a reward strictly above the optimum 18, so nothing
can stop the search early; it completes, which — under sound dominance —
proves that no better path exists, and the best path found is returned
anyway.

### 7.6 Caveats

1. **The returned path is the first acceptable one, not the best so far.**
   The label queue is ordered by resource consumption, not by cost, so a
   `'threshold_reached'` stop returns whichever acceptable path the search
   reached first. For satisficing ("any solution better than $X$") this is
   exactly right; for "the best solution found within a budget" it is not —
   use `time_limit` and read the returned path as a heuristic solution.
2. **`'completed'` is not spelled `'optimal'` on purpose.** Exhausting the
   label queue certifies optimality only when the dominance rule is sound
   for the resource extensions in use. The documented exception in this
   fork is `window_hard` (Section 3.6); a non-monotone custom
   `REF_callback` would be another. Under the standard `additive` and
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
   of Section 8 already does).
5. **`direction='both'` after a timeout is asymmetric.** The label-joining
   step still runs after a timed-out main loop, so a time-limited `both`
   run may return a complete `Source` → `Sink` path (with
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
`test/python/tests_termination_reason.py`. As with Section 6, the SWIG
interface gained a method, so an out-of-date wheel in the venv shows up as
`AttributeError: getTerminationReason`; rebuild and reinstall as in
Appendix B.

## 8. Wiring into column generation pricing

### 8.1 The model

Column generation solves the linear programming relaxation of the set
partitioning formulation of the VRPTW — one binary variable $\lambda_p$ per
feasible route, one covering constraint per customer — without writing down
its exponentially many columns. At each iteration the **restricted master
problem** (the master linear program over the columns generated so far) is
solved, its dual prices $\pi_j$ are read off, and the **pricing problem**
looks for a route of negative **reduced cost**
$\bar z_p = c_p - \sum_j \alpha_{jp} \pi_j$. Because the route cost is a sum
over arcs and each customer on the route is entered exactly once, that
reduced cost rewrites as a sum over arcs, so **the pricing problem is an
instance of model (P1) on the same digraph with**

$$
w_{ij} \;=\; \bar c_{ij} \;=\; t_{ij} - \pi_j ,
\qquad \pi_d := 0 .
$$

Every arc entering customer $j$ picks up $-\pi_j$. If the minimum reduced
cost is non-negative, no column can improve the restricted master problem
and its optimum is the optimum of the full linear programming relaxation.

The full statement is `FORMULATIONS.md` Section 5, model (P3). One
consequence deserves repeating here because it changes the solver call:
**pricing does not impose coverage**, so every elementary path is feasible,
so Feillet-style dominance is sound as it stands, so **no visit indicator
resources are needed** — the exact converse of Section 6
(`FORMULATIONS.md` Section 5.4).

### 8.2 Instance D

`FORMULATIONS.md` Section 5.7. Four customers and a depot (vertex 0), at
most three customers per route.

**Travel times $t_{ij}$** (symmetric here):

| from \ to | 0 | 1 | 2 | 3 | 4 |
|---|---:|---:|---:|---:|---:|
| **0** | 0 | 8 | 9 | 14 | 12 |
| **1** | 8 | 0 | 5 | 8 | 11 |
| **2** | 9 | 5 | 0 | 6 | 8 |
| **3** | 14 | 8 | 6 | 0 | 7 |
| **4** | 12 | 11 | 8 | 7 | 0 |

**Vertex data.** $s_j = 2$ at every customer; the depot has $s = 0$ and the
window $[0, 100]$.

| vertex | $a_v$ | $b_v$ | $s_v$ |
|---|---:|---:|---:|
| 1 | 5 | 30 | 2 |
| 2 | 10 | 40 | 2 |
| 3 | 15 | 60 | 2 |
| 4 | 20 | 70 | 2 |

**Bounds.** $q^{\max} = (4,\ 100)$ and $q^{\min} = (0,\ 0)$. The arc bound
$q^{\max}_0 = 4$ is the capacity constraint: a route uses one arc out of the
depot, one back into it, and at most two arcs between customers, hence **at
most three customers per route**. $H = 100$.

**The expected run.** Starting from the four single-customer columns,
pricing generates one column per iteration; the linear programming optimum
is $44\tfrac13$, attained by $\lambda = \tfrac13$ on each of the four
three-customer routes $\{2,3,4\}, \{1,2,3\}, \{1,2,4\}, \{1,3,4\}$ of costs
34, 31, 33, 35 — indeed $(34+31+33+35)/3 = 133/3$. The **integer** optimum
is 50, attained by $\{1\}$ together with $\{2,3,4\}$, as exhaustive search
over all partitions confirms.

### 8.3 The executed skeleton

A working skeleton of VRPTW column generation with the native interface. The
restricted master problem is solved here exactly by brute-force basis
enumeration for teaching purposes; production code would take the dual
values from a linear programming solver. The key part is the loop of **dual
prices → `weight` updates**: every arc entering customer $j$ picks up
$-\pi_j$, and the pricing graph is rebuilt from scratch each iteration (the
construction cost is negligible, as Section 9.3 shows).

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
    # degenerate-path check (when infeasible, forward returns ['Source'], cost 0.0 -- Section 10)
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

### 8.4 How to read it

The linear programming optimum 44.33 is reached in 5 iterations, and it
matches the value tabulated in Section 8.2. The solution is **fractional**
(four three-customer routes at $\tfrac13$ each) and strictly smaller than
the integer optimum 50 (routes $\{2,3,4\}$ and $\{1\}$) — the gap is where
**branching** takes over, giving branch and price.

Two practical points:

- **The degenerate-path check is mandatory.** When pricing is infeasible, a
  forward run returns `["Source"]` with `total_cost` 0.0. Reading that 0.0
  as a reduced cost would be interpreted as "no improving column" and would
  terminate column generation early, silently, with a wrong bound
  (Section 10, caveat 8).
- **Choose the direction per instance.** Use `direction='forward'` when the
  critical resource's upper bound is loose, and `'both'` when the capacity
  constraint is tight — the latter can be orders of magnitude faster
  (Section 9.5). This example's bound $q^{\max}_0 = 4$ is tight, but the
  instance is far too small for the difference to matter.

## 9. Measured benchmarks

### 9.1 What was measured

ESPPRC-TW pricing instances, `elementary=True`, on an Apple M1 with 8 GB;
every figure is a median. Four variants are compared:

- **(a)** a Python `REFCallback`, array-based;
- **(a')** the same but reading networkx attributes (the typical
  implementation in `TSPTW_GUIDE.md`);
- **(b)** the native interface, `direction="forward"`;
- **(c)** the native interface, `direction="both"`.

On every row, (a) and (b) match exactly on both path and cost, (a) and (c)
match on cost, and every path has been independently re-verified for
feasibility and cost by simulation. Configurations that took over 60 s were
measured once (the cutoff rule); the footnotes record where that applied.

### 9.2 `run()` time (median, ms)

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

### 9.3 `BiDirectional` construction time (median, ms)

This cost is paid on every iteration of a column generation loop, so it is
reported separately.

| n | (a) Py (including callback-array preparation) | (b) native fwd | (c) native both |
|--:|--:|--:|--:|
| 10 | 0.49 | 0.48 | 0.45 |
| 20 | 1.48 | 1.57 | 1.52 |
| 30 | 3.03 | 3.09 | 3.09 |
| 50 | 7.45 | 7.54 | 7.34 |

Construction time is nearly identical across all variants (the penalty of
id translation and `NodeWindowREF` construction for the native interface is
within measurement noise). At n≥20, `run()` dominates.

### 9.4 Python-boundary overhead per resource extension function call

Measured as $(\text{run}_a - \text{run}_b) / \text{calls}$.

| n | calls | (a)−(b) µs/call | (a')−(b) µs/call | reference: native-side total cost per extension |
|--:|--:|--:|--:|--:|
| 10 | 368 | 0.97 | 1.22 | 1.45 µs |
| 15 | 654 | 0.92 | 1.18 | 1.27 µs |
| 20 | 6,522 | 1.03 | 1.29 | 3.97 µs |
| 30 | 117,804 | 1.24 | 1.57 | 17.3 µs |
| 50 (capacity 5) | 780,438 | 0.94 | 1.25 | 9.48 µs |

### 9.5 How to read this

Eliminating the Python boundary is worth 0.9–1.6 µs/call by itself — a
1.7–1.9x speed-up at small scale, but only 1.0–1.1x at n≥30 — because the
cspy core's dominance computation grows super-linearly per extension (1.4 µs
at n=10 → 17 µs at n=30 → 150 µs at n=40), shrinking the Python boundary's
contribution from ~40% down to <1%. The largest practical payoff is
**`direction='both'`, newly unlocked by this implementation**: for CVRPTW
pricing with a tight capacity constraint on the critical resource (n=50, ≤4
customers/route), 8.13 s → 30 ms = **267x**. Conversely, when the critical
resource's upper bound is loose, both is 1.7–4.5x slower than forward (and
breaks down at n=40), so **choosing between them is essential**.

## 10. Limitations and caveats

1. **Keep `res[0]` (the critical resource) a monotone additive resource**
   (Section 3.4). A positive `res_cost[0]` on every edge (e.g. an arc
   counter) is recommended. `min_res[0]` is the halfway-point floor of the
   bidirectional search, not "a lower bound at the Sink"
   (`FORMULATIONS.md` Section 4.6).
2. **Mutually exclusive**: cannot be combined with `REF_callback` (the
   Python resource extension function mechanism) or `find_critical_res=True`
   (raises in the constructor).
3. **`preprocess=True` is a no-op**: as with `REF_callback`, the
   `prune_graph` preprocessing step is always skipped when native windows
   are used. Do your own pre-reduction if you need it.
4. **`window_hard` is restricted to `direction='forward'`** (backward
   extension can only track an upper bound, Section 3.5). Its dominance is
   also unsound in general (Section 3.6).
5. **`max_res[r]` must be finite for a resource with a window policy** (the
   rejection sentinel must exceed `max_res`; `inf` is rejected in the
   constructor).
6. **`min_res[time_res] = 0` is recommended**. A lower bound on a
   non-critical resource is enforced only at the final check when it is
   strictly positive, and when that lower bound is binding, the engine's
   component-wise dominance can prune away the very label that would have
   satisfied it — leading to a suboptimal solution or a spurious "no
   solution" (pre-existing engine semantics; `FORMULATIONS.md` Section 4.6
   states exactly when the bound is checked). If a binding `min_res` is
   unavoidable, e.g. to force full coverage, pairing it with **visit
   indicator resources** as in Section 5.3, example (2), restricts dominance
   to matching visit sets and restores soundness (a bare counter without
   indicators is unsound). To force full coverage, prefer
   `require_all_visits=True` (Section 6), which needs neither the counter
   nor the indicators.
7. **The window-resource value in `consumed_resources`**: only
   `direction='forward'` gives the actual service start time. `'both'`
   gives the join surrogate $T^{\mathrm{start}} + g$ of Section 3.5, and
   `'backward'` gives $g_r = H - \hat T$ on the reversed axis. If you need
   the actual schedule, use forward, or forward-simulate the returned path
   yourself with the recursion of `FORMULATIONS.md` Section 3.7 (the
   `compute_schedule` approach of `TSPTW_GUIDE.md`).
8. **The degenerate result when infeasible is direction-dependent**:
   `'forward'` gives `['Source']` with `total_cost 0.0`, `'both'` gives
   `path is None`, and `'backward'` gives `['Sink']` (pre-existing engine
   behaviour, not specific to native windows). Always include the
   `infeasible` check of Section 8.3.
9. **Numerical tolerances are asymmetric**: node-window comparisons use
   `window_eps` (default 1e-9), but the engine's `max_res`/`min_res` checks
   are exact. Solutions right at the horizon boundary fall on the safe
   (infeasible) side.
10. **Defensive fix for an upstream bug**: upstream cspy segfaults with
    `direction='both'` plus `min_res > 0` on a time resource
    (`bidirectional.cc joinLabels` null-dereferences the still-unset
    `best_labels[n]` when every label reaching the Sink has died). This
    fork adds null guards to both the forward and backward accesses in
    `joinLabels` (the only two spots in the `bidirectional.cc` diff). After
    the fix, it no longer crashes and instead falls through to the normal
    infeasible handling.
11. **Ownership**: handled automatically when going through the wrapper
    (Appendix A.6). Extracting and using `bidirectional_cpp` directly still
    keeps the resource extension function alive via the keepalive
    attribute, but with the direct construction of Section 5.4 you must hold
    the reference yourself.

---

## Appendix A. C++ implementation internals

Nothing in this appendix is needed to use the features. It documents how
they are built, for readers extending the fork or tracking upstream. The
terms used here are the implementation-only terms of the glossary
(`FORMULATIONS.md` Section 1.6 marks them `[impl]` and points here).

**SWIG** (Simplified Wrapper and Interface Generator) is the tool that
generates cspy's Python and C# bindings from its C++ headers. A **SWIG
director** is the feature that lets a C++ virtual call dispatch into a
Python subclass — which is how a Python resource extension function is
invoked from inside the C++ search loop, and therefore the source of the
per-call cost measured in Section 9.4. A **non-director class** is one
registered without that feature, so its virtual calls stay inside C++ and
cross no language boundary.

### A.1 File layout and class design

- **`src/cc/node_window_ref.h` / `.cc`** (new): `class NodeWindowREF final :
  public REFCallback`. A **non-director** pure C++ class that simply
  inherits the resource extension function base class
  (`src/cc/ref_callback.h`), the engine's officially sanctioned extension
  point. Its members are the per-resource policy `policy_[r]`, the per-node
  data `lb_[r][v]`, `ub_[r][v]`, `cons_[r][v]` (all indexed by internal
  integer identifier), the rejection sentinel
  `sentinel_[r] = max(max_res[r]+1, nextafter(max_res[r], +inf))`, and the
  tolerance `eps_`.
- **`setResourcePolicy(r, policy, lb, ub, cons)`**: unconfigured resources
  default to `additive` with zero data (identical to the engine's default
  additive resource extension function). It validates the input (resource
  index range, policy value, vector length equal to the number of vertices,
  $lb \le ub$, the critical resource being fixed to additive with zero
  consumption, and finiteness of `max_res` for resources with a window
  policy), throwing `std::invalid_argument` on any violation.

### A.2 Registration and the argument guard

**`src/cc/python/bidirectional.i`** registers `NodeWindowREF` with SWIG
without `%feature("director")`, so it never goes through the director
mechanism, and adds a `std::exception` → Python `RuntimeError` conversion.
It also adds an argument guard for the case where `REF_fwd` and friends are
called directly from Python (`checkExtensionArgs`: node-id range and
resource-vector length), so out-of-range access raises an exception instead
of crashing.

### A.3 The wrapper's normalisation path

**`src/python/algorithms/bidirectional.py`**: validates arguments
(`src/python/checking.py check_native_windows`) → normalises the simple and
general interfaces into per-resource specifications → **after**
`_init_graph()` (`convert_node_labels_to_integers`), translates the original
node labels to internal integer identifiers and arrays them → constructs
`NodeWindowREF` and passes it via `setREFCallback`. This ordering is why
every argument in Section 4 is keyed by the original node labels while
Section 5.4 and this appendix speak of integer identifiers.

### A.4 Why the labelling core is left unmodified for window resources

For the node windows themselves, `labelling.cc` / `digraph.cc` are
untouched, and nothing in `bidirectional.cc` is changed on their account.
(This is a statement about the *window* feature only. The fork's total diff
to `bidirectional.cc` is about 155 lines, carrying the mandatory-visit
feature and the early-termination reporting discussed below, plus the two
null guards of Section 10, caveat 10 and the `bounds_pruning` repair of
`FORMULATIONS.md` Section 2.6.) (1) **Backward compatibility**: since only the
resource extension function, the engine's officially sanctioned extension
point, is used, the existing search / dominance / bidirectional logic cannot
change behaviour, and the existing Python test suite passes exactly as
before. (2) **Verifiability**: it is possible to brute-force check that
"native and a Python director resource extension function implementing the
same formulas return **bit-identical** output" (already done, roughly 2600
checks in total, all passing). Touching the core would move the goalposts of
that comparison. (3) **Staying close to upstream**: a smaller diff makes it
easier to track updates to upstream cspy, and easier to turn into a pull
request.

Three changes do reach beyond the resource extension function, and it is
worth separating them. The **early-termination reporting** of Section 7 adds
a `termination_reason_` field and the four places that set it; it records
which exit the existing search loop took and changes no decision. The
**`bounds_pruning` repair** (`FORMULATIONS.md` Section 2.6) fixes two
upstream bugs in an option that is off by default, and restores the behaviour
upstream intended rather than introducing a new one. The third, the
**mandatory-visit feature** of Section 6, is the one deliberate change to
what the search decides, for two reasons that do not apply to the window
resources.
First, a resource extension function cannot express the required change:
the rule that has to change is the **dominance** rule, and a resource
extension function has no access to it. Encoding the visit set in
resources, as Section 5.3 example (2) does, works, but it makes the resource
vector grow with the number of customers, so every dominance comparison
costs one floating-point comparison per customer and every label carries
eight bytes per customer. Second, and this is what makes the exception
acceptable, the core change is provably **the same pruning predicate** as
the resource encoding, only represented as a bit set instead of a vector of
doubles (Section 6.5, `FORMULATIONS.md` Section 4.5). The resource encoding
therefore remains available as a reference implementation, and the two are
compared against each other, and against exhaustive enumeration, in the test
suite. All new code paths sit inside an `if (require_all_visits)` guard, no
existing expression or branch was rewritten, and the resulting binary was
checked to produce byte-identical output to the pre-change build on 3222
solver runs with the feature switched off.

### A.5 The `mergeLabels` fix-up, and why `REF_join` reproduces it

**The critical resource alone needs special handling** in the join step
whose formula is Section 3.5. `labelling.cc mergeLabels` has a fix-up that
silently re-adds `bwd_res_inverted` unless the value returned by `REF_join`
matches `fwd[0] + m + (max_res[0] − bwd[0])` (`m` = the arc's consumption, 1
if it is 0) under a **floating-point equality comparison**.
`NodeWindowREF::REF_join` computes this same expression with **the same
operations in the same combining order** and returns it, matching bit for
bit so that the fix-up never fires.

### A.6 Ownership: keepalive, `__disown__`, and the `REF_callback` reference

`Params` never deletes its `ref_callback` pointer, so **ownership must stay
on the Python side**. The wrapper keeps a reference in `self._window_ref`
and additionally attaches it to the `bidirectional_cpp` proxy itself via a
keepalive attribute (so extracting just the proxy and discarding the
wrapper does not cause a use-after-free). Note this is the **opposite** of
the Python-director `REF_callback`, which transfers ownership to C++ via
`__disown__`. If you construct `NodeWindowREF` yourself as in Section 5.4,
keep the object alive for the lifetime of the `BiDirectional` object (do not
call `__disown__`).

The wrapper also keeps a plain reference to a user-supplied `REF_callback`
in `self._ref_callback`. The C++ side only stores a raw pointer, so
`BiDirectional(..., REF_callback=MyCallback())` with a temporary used to let
the callback be collected before `run()` and crash the interpreter with a
segmentation fault; the reference removes that trap. It does not change what
the search computes.

## Appendix B. Rebuild procedure

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
(`python3 -m unittest discover -p "tests_*.py"` in `test/python/`, **162
tests**) is also expected to pass entirely, the only pre-existing failures
being the 4 PSOLGENT numpy-2.x incompatibilities and one skip; the run
reports `Ran 162 tests ... FAILED (errors=4, skipped=1)`. The three test
files this fork adds account for 85 of the 162: 65 in
`tests_native_time_windows.py`, 18 in `tests_termination_reason.py` and 2 in
`tests_bounds_pruning.py`. `dotnet/` (the C# bindings) is out of scope for
the build.

Note that adding a method to the SWIG interface (as `setRequiredNodes`,
Section 6, and `getTerminationReason`, Section 7, did) makes a rebuild
mandatory: a stale wheel left in the venv surfaces as `AttributeError`, not
as a build error.

## Appendix C. Verification record

**The documentation.** Every code example in this guide was executed with
the Python interpreter of the repository's `.venv`, and every output block
is a verbatim copy of a real run. None is transcribed from memory or edited
for presentation. This is the standing rule for all four documents of this
repository (`FORMULATIONS.md` Section 7).

**The instances.** The tables of Instances B (Section 5.1), C (Section 6.3),
D (Section 8.2) and E (Section 7.5) were produced by exhaustive enumeration
with exact rational arithmetic (`fractions.Fraction`), so no floating-point
rounding enters the expected values: all elementary $o$–$d$ paths of B, D
and E, all $6! = 720$ permutations of C, and all partitions of the customer
set of D into feasible routes. The tie in Instance B under weight variant
B-ii was established by perturbation, and the claim that no dominance test
fires under `window_hard` on Instance B (Section 5.3, example (3)) by a
census of the comparisons actually performed. `FORMULATIONS.md` Section 7
records the full procedure.

**The implementation.** The native resource extension function was compared
bit for bit against an independently written Python director resource
extension function implementing the same formulas — roughly **2600 checks**
in total, all passing — and cross-checked by exact brute force with
`Fraction`. The build with the mandatory-visit feature switched off was
confirmed to produce **byte-identical** output to the pre-change build over
**3222 solver runs**. The `bounds_pruning` repair (`FORMULATIONS.md`
Section 2.6) was checked against brute-force enumeration of every simple
`Source` → `Sink` path on 60 random instances in each of the three search
directions. The permanent regression tests are
`test/python/tests_native_time_windows.py` (65 cases, of which 33 cover the
mandatory visits of Section 6), `test/python/tests_termination_reason.py`
(18 cases covering the stopping features of Section 7) and
`test/python/tests_bounds_pruning.py` (2 cases, one per repaired bug). The
measurements of Sections 6.5 and 9 were taken on an Apple M1 with 8 GB as
described in those sections.

For the primary source of the formulas and caveats, see `docs/ref.rst`.

## References

- S. Irnich and G. Desaulniers: *Shortest Path Problems with Resource
  Constraints*, in G. Desaulniers, J. Desrosiers and M. M. Solomon (eds.),
  *Column Generation*, Springer, 2005, 33–65.
- G. Desaulniers, J. Desrosiers and M. M. Solomon (eds.): *Column
  Generation*, Springer, 2005.
- D. Feillet, P. Dejax, M. Gendreau and C. Gueguen: *An exact algorithm for
  the elementary shortest path problem with resource constraints:
  Application to some vehicle routing problems*, Networks, 44(3), 216–229,
  2004.
- G. Righini and M. Salani: *Symmetry helps: Bounded bi-directional dynamic
  programming for the elementary shortest path problem with resource
  constraints*, Discrete Optimization, 3(3), 255–273, 2006.
- E. Tilk, A.-K. Rothenbächer, T. Gschwind and S. Irnich: *Asymmetry
  matters: Dynamic half-way points in bidirectional labeling for solving
  shortest path problems with resource constraints faster*, European Journal
  of Operational Research, 261(2), 530–539, 2017.
- Y. Dumas, J. Desrosiers, E. Gelinas and M. M. Solomon: *An optimal
  algorithm for the traveling salesman problem with time windows*,
  Operations Research, 43(2), 367–371, 1995.

The full annotated list, with a note on what each reference supplies, is
`FORMULATIONS.md` Section 8.
