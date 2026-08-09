A bug-fix release. Nothing is added to the interface and no model behaves
differently; what changes is that a mistake in how the interface is called now
raises a Python exception instead of ending the process.

## Who this is for

If you have ever seen this, in Jupyter or JupyterLab:

> **The Kernel appears to have died. It will restart automatically.**

That message means the interpreter was killed rather than an exception raised,
so there is no traceback and nothing names the call responsible. Eight ways to
provoke it from the documented interface are closed here, along with a ninth
that struck before any of that code ran.

Upgrading is worthwhile even if you have not seen it: several of these were
out-of-bounds *writes*, which corrupt the heap and can be survived. A run that
finishes is not evidence that it did not happen.

## Installing

Wheels for CPython 3.9 to 3.13 on Linux (x86-64, AArch64), macOS (Intel, Apple
Silicon) and Windows (x64) are attached below. Nothing is compiled and no build
tools are needed:

```
pip install --force-reinstall --no-cache-dir https://github.com/Ebisaresu/cspy_for_TW/releases/download/v1.1.1/cspy_tw-1.1.1-cp310-cp310-win_amd64.whl
```

`--force-reinstall` matters when a source build is already present: pip sees a
version it already has and otherwise leaves it alone. Substitute `cp39`,
`cp311`, `cp312` or `cp313`, and the platform, to match your interpreter —
`python tools/pick_wheel.py` prints the exact command for the Python running
it.

**On Windows, prefer the wheel over `pip install git+…`.** A source build is
not put through `delvewheel`, so the extension resolves `MSVCP140.dll` by name
against whichever copy the process has already loaded, and Anaconda ships its
own. The wheels here carry the runtime they were built against inside them and
had the test suite run against them on a Windows runner.

## What was wrong

**Reading a result before `run()`.** `best_label_` is allocated by `init()`,
which `run()` calls, so `path`, `total_cost`, `consumed_resources` and
`check_critical_res()` dereferenced a null pointer until then. In a notebook,
running the cell that prints the answer before the cell that computes it was
enough.

**Calling `run()` twice on one object.** The search containers are not rebuilt
between calls. With `direction="backward"` the second call reached
`processBwdLabel` with a default-constructed label — null `params_ptr`, empty
resource vector — and segfaulted. Re-executing a notebook cell was enough.

**An out-of-range `critical_res`.** It indexes `max_res`, `min_res` and every
label's resource vector, so this was an out-of-bounds write. The process died
at a point that moved between runs of the same input; roughly one run in eight
survived it.

**An empty or mismatched `max_res` / `min_res`.** The validation layer chose
which checks to run by testing the two lists for truthiness, and an empty list
is falsy, so `max_res=[]` skipped every resource check there is and reached the
engine.

**A `REF_callback` returning the wrong number of resources.** The returned
vector is indexed positionally against `max_res`. A short one was the worst
case: the feasibility loop is bounded by the vector's own length, so the
critical resource stopped being checked, the search never terminated, and
labels accumulated until the process was killed — which looks like a hang
followed by a crash, not like a bad return value.

**A `REF_callback` outliving the reference that kept it alive.** The engine
holds the callback as a raw pointer and does not own it, and the only reference
lived on the Python wrapper rather than on the C++ proxy whose lifetime
matters. Extracting `alg.bidirectional_cpp` and dropping `alg` collected the
callback while the labelling loop was still calling it.

**Graph construction.** An unknown node id made `getNodeIdFromUserId`
dereference `vertices.end()` and hand the garbage it read to LEMON; `addNodes`
wrote past `vertices` when given more nodes than the constructor was told
about, and left the source and sink holding indeterminate ids when the graph
carried neither.

**The extension module had no ABI tag.** `swig_add_library` produced a bare
`_pyBiDirectionalCpp.pyd`, and a bare suffix is in importlib's
`EXTENSION_SUFFIXES` for *every* CPython — so a module built against one
version was loaded by another instead of being skipped. On Windows that is
fatal rather than merely wrong: the module links a specific `pythonXY.lib`, so
loading it into a different interpreter pulls a second CPython runtime into the
process, and it dies with an access violation before any of this project's code
runs. The module now carries `EXT_SUFFIX`, which turns the same situation into
an ordinary `ImportError`.

Found while reading the surrounding code: `operator<<` fell off the end of a
value-returning function; `all_resources_positive` was read uninitialised and
assigned per edge rather than accumulated, so the last edge added decided it;
`halfwayCheck` used the three-iterator `std::equal` and read past the end of a
shorter path; `checkCriticalRes` indexed `max_res` by the label's length.

## Behaviour changes

Three things that used to be accepted are now rejected. All three were
previously undefined behaviour, so nothing that was working stops working, but
code that relied on the old silence will now see an exception.

| | Before | Now |
|:--|:--|:--|
| `run()` a second time on one object | degenerate result, meaningless `termination_reason` (documented), or a crash | `RuntimeError` — build a fresh `BiDirectional` |
| `critical_res` outside `[0, len(max_res))` | heap corruption | `Exception` at construction |
| `max_res` / `min_res` empty or of different lengths | out-of-bounds read | `Exception` at construction |

## Two new tools

`tools/diagnose_kernel_crash.py` runs each of the above in its own subprocess,
so it survives the crashes it is looking for and names the one that fired. It
also reports what the loader saw — interpreter, architecture, the extension
module's real filename, whether the wheel was repaired — which is the half of
the picture a crash message never gives you. It exits 0 on an installation
carrying these fixes.

`tools/pick_wheel.py` answers the question `pip` leaves open when it says *"is
not a supported wheel on this platform"*: that message names the wheel but not
the interpreter, and the interpreter is the half that is wrong. It prints what
the running Python accepts and the install command for the wheel that matches.

## How this was checked

Both revisions were built and run side by side. On the previous one,
`diagnose_kernel_crash.py` reports 10 of its 11 checks killing the interpreter;
on this one, none. Alongside that: the 188 tests of the existing suite, 31 new
regression tests in `test/python/tests_no_hard_crash.py`, every runnable
snippet in the documentation, and roughly 1300 randomised small instances.

One caveat worth stating plainly: the verification above ran on Linux. The
Windows-specific layer — the C++ runtime, the loader, the Anaconda environment
— is exercised by continuous integration when it builds and tests each wheel,
but the crash reports that prompted this release have not been reproduced
directly on Windows. If you are still seeing a dead kernel after upgrading,
`tools/diagnose_kernel_crash.py` run from a terminal is the place to start, and
its output is what to attach to an issue.

## Unchanged

`elementary=True` and `require_all_visits=True` retain a number of labels that
grows exponentially with the node count, and the label store is never pruned. A
large instance still exhausts memory, and the operating system still kills the
process for it — which looks exactly like a crash. `time_limit` bounds the
time, not the memory. This is a property of the method, not a defect, and
nothing here changes it.
