"""Benchmark harness for the labelling core.

Usage:  python benchmarks/python/bench_labelling.py [reps] [name-filter]

Fixed seeds; prints one JSON line per instance: name, best-of-`reps` wall
time, cost, and the path itself. The path is printed so that two builds can
be diffed for behavioural equivalence, not just compared for speed: a
performance change that alters any result is a bug, whatever the speedup.

The numbers in README section 5.9 come from this script (reps=3, taking the
larger tsptw sizes from a single rep). Instance sizes are chosen so the whole
default set finishes in well under a minute on the optimised build; the
tsptw_25/tsptw_30 entries are deliberately beyond the practical frontier and
are only reached with a name filter.

Instance families:
  tsptw_N   : TSPTW via require_all_visits, windows built around a random
              feasible seed tour with +-slack, so every instance is feasible
              and the windows genuinely prune. The headline use case.
  price_N   : elementary RCSPP with negative weights on a dense digraph --
              the shape of a column-generation pricing subproblem.
  join_N    : direction="both" without windows (exercises the merge phase).
"""
import json, math, random, sys, time

from networkx import DiGraph
from cspy_tw import BiDirectional

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ONLY = sys.argv[2] if len(sys.argv) > 2 else ""


def tsptw(n, seed, slack):
    rng = random.Random(seed)
    pts = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n + 1)]
    def d(i, j):
        return round(math.dist(pts[i], pts[j]), 2)
    cust = list(range(1, n + 1))
    tour = cust[:]
    rng.shuffle(tour)
    svc = {c: round(rng.uniform(0.5, 2.0), 2) for c in cust}
    # arrival times along the seed tour
    t, arr = 0.0, {}
    prev = 0
    for c in tour:
        t += d(prev, c)
        arr[c] = t
        t += svc[c]
        prev = c
    H = round(t + d(prev, 0) + 4 * slack + 10, 2)
    tw = {"c%d" % c: (max(0.0, round(arr[c] - slack, 2)),
                      round(arr[c] + slack, 2)) for c in cust}
    st = {"c%d" % c: svc[c] for c in cust}
    G = DiGraph(directed=True, n_res=2)
    def name(i):
        return "Source" if i == 0 else "c%d" % i
    for i in [0] + cust:
        for j in cust:
            if i != j:
                G.add_edge(name(i), "c%d" % j, res_cost=[1.0, d(i, j)],
                           weight=d(i, j))
        if i != 0:
            G.add_edge(name(i), "Sink", res_cost=[1.0, d(i, 0)],
                       weight=d(i, 0))
    kw = dict(direction="forward", elementary=True, time_windows=tw,
              service_times=st, require_all_visits=True)
    return G, [float(n + 2), H], [0.0, 0.0], kw


def pricing(n, seed, density=0.5):
    rng = random.Random(seed)
    nodes = ["n%d" % i for i in range(n)]
    G = DiGraph(directed=True, n_res=2)
    for i, u in enumerate(nodes):
        G.add_edge("Source", u, res_cost=[1, 1], weight=round(rng.uniform(-5, 5), 2))
        G.add_edge(u, "Sink", res_cost=[1, 1], weight=round(rng.uniform(-5, 5), 2))
        for j, v in enumerate(nodes):
            if i != j and rng.random() < density:
                G.add_edge(u, v, res_cost=[1, 1], weight=round(rng.uniform(-4, 2), 2))
    return G, [12.0, 12.0], [0.0, 0.0], dict(direction="forward", elementary=True)


def join(n, seed, density=0.5):
    G, mx, mn, _ = pricing(n, seed, density)
    return G, mx, mn, dict(direction="both", elementary=True)


INSTANCES = []
for n, slack in [(12, 6.0), (14, 5.0), (16, 5.0), (18, 3.0), (20, 3.0),
                 (25, 3.0), (30, 3.0), (18, 5.0), (20, 5.0)]:
    INSTANCES.append(("tsptw_%d_s%g" % (n, slack), tsptw(n, 42 + n, slack)))
for n, cap in [(14, 6.0), (16, 6.0)]:
    G, mx, mn, kw = pricing(n, 7 + n)
    mx[0] = mx[1] = cap
    INSTANCES.append(("price_%d" % n, (G, mx, mn, kw)))
G, mx, mn, kw = join(14, 99)
mx[0] = mx[1] = 6.0
INSTANCES.append(("join_14", (G, mx, mn, kw)))

#: Beyond the practical frontier (the state space is exponential in n);
#: only run when named explicitly, so the default run stays under a minute.
EXPLICIT_ONLY = ("tsptw_25", "tsptw_30")

for label, (G, mx, mn, kw) in INSTANCES:
    if ONLY and ONLY not in label:
        continue
    if not ONLY and label.startswith(EXPLICIT_ONLY):
        continue
    best, result = None, None
    for _ in range(REPS):
        alg = BiDirectional(G, mx, mn, **kw)
        t0 = time.perf_counter()
        alg.run()
        dt = time.perf_counter() - t0
        if best is None or dt < best:
            best = dt
        result = (alg.path, alg.total_cost, alg.termination_reason)
    print(json.dumps({"name": label, "sec": round(best, 4),
                      "cost": result[1], "reason": result[2],
                      "path": result[0]}))
    sys.stdout.flush()
