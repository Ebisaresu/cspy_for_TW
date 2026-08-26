Two changes worth upgrading for: the labelling core is dramatically faster on
mandatory-visit instances, and NumPy is no longer installed unless you ask for
it. No interface changes; every result is unchanged.

## Installing

Wheels for CPython 3.9 to 3.13 on Linux (x86-64, AArch64), macOS (Intel,
Apple Silicon) and Windows (x64) are attached below. Nothing is compiled and
no build tools are needed:

```
pip install --force-reinstall --no-cache-dir https://github.com/Ebisaresu/cspy_for_TW/releases/download/v1.2.0/cspy_tw-1.2.0-cp310-cp310-win_amd64.whl
```

Substitute `cp39`, `cp311`, `cp312` or `cp313` and the platform to match your
interpreter; `python tools/pick_wheel.py` prints the exact command for the
Python running it. `--force-reinstall` matters when a source build is already
present: `pip` sees a version it already has and otherwise leaves it alone.

On Windows, prefer the wheel to `pip install git+…`: a source build is not put
through `delvewheel`, so the extension resolves `MSVCP140.dll` by name against
whichever copy the process has already loaded, and Anaconda ships its own.

## Faster

The dominance machinery was profiled and rewritten. Measured with
`benchmarks/python/bench_labelling.py`, best of three:

| instance | v1.1.1 | v1.2.0 | factor |
|---|---:|---:|---:|
| TSPTW n=14, `require_all_visits` | 0.31 s | 0.017 s | 18x |
| TSPTW n=16, `require_all_visits` | 4.9 s | 0.080 s | 61x |
| TSPTW n=18, `require_all_visits` | 181 s | 0.42 s | **432x** |
| TSPTW n=20, `require_all_visits` | impractical | 2.3 s | — |
| ESPPRC pricing shape, n=16 | 0.33 s | 0.14 s | 2.3x |

Exact TSPTW is now practical to roughly twenty customers on an ordinary
machine, up from roughly a dozen. Three changes, in decreasing order of
effect:

- **Labels at a vertex are grouped by required-visit mask.** Under
  `require_all_visits` a label can only dominate, be dominated by, or equal a
  label with the same mask, so the quadratic pass at each vertex no longer
  visits the pairs that could not interact. Without the mandatory-visit mode
  every label lands in one group and the pass visits exactly what it always
  visited.
- **`unreachable_nodes` is a sorted vector, not a `std::set`.** The subset
  test inside every elementary dominance check walks two contiguous arrays
  instead of chasing red-black-tree nodes — tree iteration alone was ~30% of a
  pricing-shaped run.
- **`Label` is movable.** A user-declared destructor had been suppressing the
  implicit move operations, so every heap sift and vector reallocation
  deep-copied two vectors and a set per label touched.

Nothing about the answers changed, by construction and by measurement: a sweep
of 120 random instances across all five dominance modes (mandatory visits +
windows, windows only, plain elementary, two-cycle elimination, and
`direction="both"`) produces byte-identical paths, costs and termination
reasons against v1.1.1.

The exponential state space is untouched, and eventually wins: n=25 still does
not finish, and it now runs out of memory rather than time (roughly 9 GB per
minute of search). Set `time_limit` on large instances — it stops the search
cleanly, where exhausting memory does not.

## Lighter

`pip install cspy-tw` now installs NetworkX and nothing else. NumPy arrives
only with a new extra:

```
pip install "cspy-tw[heuristics]"
```

NumPy was never used on the `BiDirectional` code path. Two module-level
imports in `cspy.checking` made it a hard requirement — an `ndarray` check the
labelling algorithm was already exempt from, and a `RandomState` used by a
seeding call that has been commented out for as long as this fork has existed.
Both are now imported where they are used, and the four heuristic algorithms
(`GRASP`, `PSOLGENT`, `Tabu`, `GreedyElim`), which genuinely do need NumPy,
resolve through a module `__getattr__` instead of being imported eagerly.

`from cspy_tw import GRASP`, `cspy_tw.GRASP` and `dir(cspy_tw)` behave exactly
as before. Without NumPy installed, asking for a heuristic raises an
`ImportError` naming the extra rather than a bare "No module named 'numpy'".

This changes what gets **installed**, not what gets **upgraded**. Neither this
fork nor upstream `cspy` pins a version of either dependency, so `pip` has
always accepted an already-installed NetworkX or NumPy and left it alone —
confirmed against NumPy 1.26.4 and 2.2.6, both untouched. The compiled
extension contains no reference to NumPy at all, so there is no ABI coupling
to the 1.x/2.x split either.

## Also in this release

- `test/cc/test_issue89.cc` passed a three-entry `max_res` against
  two-resource edges and a two-entry `min_res`. The stray entry was never
  read; the equal-length check added in v1.1.1 rejects it, which is how it was
  noticed. The C++ suite had not been run since that guard was added.
- Three benchmark drivers under `benchmarks/python/`:
  `bench_labelling.py` (TSPTW and pricing shapes, prints paths so two builds
  can be diffed for equivalence), `bench_beasley.py` (the shipped
  Beasley–Christofides RCSPP set, asserting all 24 costs against the published
  optima), and `bench_tw_scaling.py` (ESPPRC with time windows and no
  mandatory visits).

## Verification

The 188-test Python suite and the 61-test C++ suite both pass, as does the
120-instance equivalence sweep against v1.1.1. Every wheel attached here was
built by continuous integration and had the test suite run against it on its
own platform.
