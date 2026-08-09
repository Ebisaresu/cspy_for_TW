"""Check that this installation of cspy_tw cannot kill the interpreter.

Run it from a *terminal*, not from a notebook:

    python tools/diagnose_kernel_crash.py

Why a terminal: every check below used to end the process rather than raise.
Jupyter reports that as "The kernel appears to have died. It will restart
automatically." and nothing else -- the message names the notebook, never the
call. Run from a shell, the same crash prints a real diagnosis ("Segmentation
fault", a faulthandler traceback, an access violation) and, because each check
runs in its own subprocess here, the script survives to tell you which one it
was.

Exit status is 0 when every check raised an ordinary Python exception (what a
fixed installation does) and 1 when any of them killed its subprocess (an
installation predating the fixes, or a new crash).
"""

import os
import subprocess
import sys
import textwrap

#: Each entry is (name, what it used to do, source to run in a subprocess).
#: The preamble is prepended to every one.
PREAMBLE = """
import faulthandler
faulthandler.enable()
from networkx import DiGraph
from cspy_tw import BiDirectional, REFCallback

def graph():
    G = DiGraph(directed=True, n_res=2)
    G.add_edge("Source", "A", res_cost=[1, 2], weight=0)
    G.add_edge("Source", "B", res_cost=[1, 2], weight=0)
    G.add_edge("A", "B", res_cost=[1, 2], weight=-10)
    G.add_edge("B", "A", res_cost=[1, 2], weight=-10)
    G.add_edge("A", "Sink", res_cost=[1, 2], weight=0)
    G.add_edge("B", "Sink", res_cost=[1, 2], weight=0)
    return G
"""

CHECKS = [
    (
        "import only",
        "a crash here is the loader, not the algorithm: the wrong C++ runtime,"
        " or an extension built against a different interpreter",
        """
        print("imported cleanly")
        raise SystemExit(0)
        """,
    ),
    (
        "the release notes example",
        "the documented worked example, verbatim",
        """
        import numpy as np, networkx as nx
        ARCS = [("Source", "A", 2, -8.0), ("Source", "B", 5, -1.0),
                ("A", "B", 3, 5.0), ("B", "A", 3, -20.0),
                ("A", "Sink", 2, 0.0), ("B", "Sink", 2, 0.0)]
        WINDOWS = {"A": (0.0, 4.0), "B": (8.0, 12.0)}
        SERVICE = {"A": 1.0, "B": 1.0}
        G = nx.DiGraph(n_res=2)
        for tail, head, travel, weight in ARCS:
            G.add_edge(tail, head,
                       res_cost=np.array([1.0, float(travel)]), weight=weight)
        common = dict(direction="forward", elementary=True,
                      time_windows=WINDOWS, service_times=SERVICE)
        for label, extra in [("cheapest path", {}),
                             ("every customer visited",
                              {"require_all_visits": True}),
                             ("stop below -5",
                              {"threshold": -5.0, "threshold_strict": True})]:
            alg = BiDirectional(G, [10.0, 20.0], [0.0, 0.0], **common, **extra)
            alg.run()
            print(label, alg.path, alg.total_cost, alg.termination_reason)
        raise SystemExit(0)
        """,
    ),
    (
        "import and solve",
        "the happy path; if this one fails, nothing else matters",
        """
        alg = BiDirectional(graph(), [10, 20], [0, 0], direction="forward",
                            elementary=True,
                            time_windows={"A": (0, 4), "B": (8, 12)},
                            service_times={"A": 1, "B": 1})
        alg.run()
        assert alg.path == ["Source", "A", "B", "Sink"], alg.path
        print("solved:", alg.path, alg.total_cost, alg.consumed_resources)
        raise SystemExit(0)
        """,
    ),
    (
        "result read before run()",
        "null dereference on best_label_",
        """
        alg = BiDirectional(graph(), [10, 20], [0, 0])
        alg.path
        """,
    ),
    (
        "total_cost read before run()",
        "null dereference on best_label_",
        """
        alg = BiDirectional(graph(), [10, 20], [0, 0])
        alg.total_cost
        """,
    ),
    (
        "consumed_resources read before run()",
        "null dereference on best_label_",
        """
        alg = BiDirectional(graph(), [10, 20], [0, 0])
        alg.consumed_resources
        """,
    ),
    (
        "check_critical_res() before run()",
        "null dereference on best_label_",
        """
        alg = BiDirectional(graph(), [10, 20], [0, 0])
        alg.check_critical_res()
        """,
    ),
    (
        "run() twice, direction='backward'",
        "null params_ptr and an empty resource vector in processBwdLabel",
        """
        alg = BiDirectional(graph(), [10, 20], [0, 0], direction="backward")
        alg.run()
        alg.run()
        """,
    ),
    (
        "critical_res out of range",
        "out-of-bounds write; the heap corruption surfaces later",
        # This one is checked by asking whether the value is rejected, not by
        # waiting to see whether it crashes. The access is out of bounds, so
        # whether the corrupted heap actually kills the process varies from
        # run to run of the very same input -- a check that waited for the
        # crash would clear a broken installation whenever it got lucky.
        # os._exit skips the traceback the runner would otherwise read as a
        # clean rejection.
        """
        import os
        try:
            BiDirectional(graph(), [10, 20], [0, 0], critical_res=5)
        except Exception as exc:
            print("rejected:", exc)
            raise SystemExit(0)
        os._exit(3)
        """,
    ),
    (
        "REF_callback returning too few resources",
        "the search stops checking the critical resource and never terminates",
        """
        class Short(REFCallback):
            def REF_fwd(self, c, t, h, e, p, w): return [0.0]
            def REF_bwd(self, c, t, h, e, p, w): return [0.0]
            def REF_join(self, f, b, t, h, e):   return [0.0]
        cb = Short()
        alg = BiDirectional(graph(), [10, 20], [0, 0], direction="forward",
                            REF_callback=cb)
        alg.run()
        """,
    ),
    (
        "REF_callback outliving the wrapper that holds it",
        "the director object was collected while C++ held its raw pointer",
        """
        import gc
        class Additive(REFCallback):
            def REF_fwd(self, c, t, h, e, p, w):
                return [c[i] + e[i] for i in range(len(c))]
            def REF_bwd(self, c, t, h, e, p, w):
                return [c[i] + e[i] for i in range(len(c))]
            def REF_join(self, f, b, t, h, e):
                return [f[i] + b[i] + e[i] for i in range(len(f))]
        def build():
            alg = BiDirectional(graph(), [10, 20], [0, 0],
                                direction="forward", REF_callback=Additive())
            return alg.bidirectional_cpp
        cpp = build()
        gc.collect()
        cpp.run()
        print("path:", list(cpp.getPath()))
        raise SystemExit(0)
        """,
    ),
    (
        "empty max_res / min_res",
        "every resource check was skipped, then the engine indexed the empty "
        "bounds",
        """
        G = DiGraph(directed=True, n_res=0)
        G.add_edge("Source", "A", res_cost=[], weight=0)
        G.add_edge("A", "Sink", res_cost=[], weight=0)
        alg = BiDirectional(G, [], [])
        alg.run()
        alg.path
        """,
    ),
    (
        "REF_callback returning no resources",
        "indexing an empty std::vector",
        """
        class Empty(REFCallback):
            def REF_fwd(self, c, t, h, e, p, w): return []
            def REF_bwd(self, c, t, h, e, p, w): return []
            def REF_join(self, f, b, t, h, e):   return []
        cb = Empty()
        alg = BiDirectional(graph(), [10, 20], [0, 0], direction="forward",
                            REF_callback=cb)
        alg.run()
        """,
    ),
]

#: Generous: the point is to separate "raised promptly" from "never returned",
#: not to measure anything.
TIMEOUT_SECONDS = 60


def run_check(source):
    """Run one check in a subprocess. Returns (verdict, detail)."""
    script = PREAMBLE + textwrap.dedent(source)
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "HANG", "did not finish within {}s".format(TIMEOUT_SECONDS)

    if completed.returncode == 0:
        return "OK", (completed.stdout.strip().splitlines() or [""])[-1]
    # A negative return code is a signal on POSIX. On Windows a native crash
    # shows up as a large unsigned status instead, 0xC0000005 (access
    # violation) being the usual one, so neither can be recognised by sign
    # alone; the reliable marker is the absence of a Python traceback.
    if "Traceback (most recent call last)" in completed.stderr:
        last = [l for l in completed.stderr.splitlines() if l.strip()][-1]
        return "OK", last
    if completed.returncode == 3:
        # Reserved by the checks that test for a validation rather than wait
        # for a crash: the bad value was accepted.
        return "CRASH", "the invalid value was accepted, not rejected"
    return "CRASH", "exit status {} with no Python traceback".format(
        completed.returncode
    )


def report_environment():
    """Print what the loader saw, which is where a Windows-only crash lives.

    None of the checks in CHECKS can see this. They exercise the algorithm; a
    crash that happens because the wrong C++ runtime was loaded, or because
    the extension was built against a different interpreter, happens before
    any of them get a say. On Windows this section is usually the one that
    matters.
    """
    import sysconfig

    print("platform   :", sys.platform, "|", os.name)
    print("executable :", sys.executable)
    print("64-bit     :", sys.maxsize > 2 ** 32)
    conda = os.environ.get("CONDA_PREFIX")
    if conda:
        print("conda env  :", conda)

    try:
        import cspy_tw
        from cspy_tw.algorithms import pyBiDirectionalCpp as ext
    except Exception as exc:
        print("extension  : FAILED TO IMPORT:", exc)
        return

    ext_file = getattr(ext, "__file__", None)
    print("package    :", os.path.dirname(cspy_tw.__file__))
    print("version    :", cspy_tw.__version__)

    # The compiled module is the sibling _pyBiDirectionalCpp.<tag>.pyd/.so.
    pkg_dir = os.path.dirname(ext_file) if ext_file else None
    if pkg_dir:
        binaries = [
            f for f in sorted(os.listdir(pkg_dir))
            if f.endswith((".pyd", ".so", ".dylib", ".dll"))
        ]
        for name in binaries:
            full = os.path.join(pkg_dir, name)
            print("binary     : {} ({} bytes)".format(name, os.path.getsize(full)))
        libs = os.path.join(pkg_dir, ".libs")
        if os.path.isdir(libs):
            print("bundled    :", ", ".join(sorted(os.listdir(libs))) or "(empty)")
        elif sys.platform == "win32":
            # delvewheel creates this when it repairs a wheel. A source build
            # (pip install git+..., pip install .) is never repaired, so the
            # extension resolves MSVCP140.dll by name against whatever the
            # process has already loaded -- Anaconda ships its own copy.
            print("bundled    : no .libs directory (source build, not a"
                  " repaired wheel)")

    print("built for  :", sysconfig.get_platform(),
          "| ABI tag", sysconfig.get_config_var("SOABI")
          or sysconfig.get_config_var("EXT_SUFFIX"))
    print()


def main():
    print("python     :", sys.version.replace("\n", " "))
    report_environment()
    try:
        import cspy_tw

        print("cspy_tw    :", cspy_tw.__version__)
        print("            ", os.path.dirname(cspy_tw.__file__))
    except Exception as exc:  # pragma: no cover - the import is the test
        print("cspy_tw    : FAILED TO IMPORT:", exc)
        print()
        print("The package does not import at all. That is a build or")
        print("installation problem, not one of the crashes below.")
        return 1
    print()

    crashed = []
    for name, used_to, source in CHECKS:
        verdict, detail = run_check(source)
        print("[{:5}] {}".format(verdict, name))
        if verdict == "OK":
            print("         {}".format(detail))
        else:
            print("         {}".format(detail))
            print("         used to be: {}".format(used_to))
            crashed.append(name)
        sys.stdout.flush()

    print()
    if crashed:
        print("{} of {} checks killed the interpreter:".format(
            len(crashed), len(CHECKS)))
        for name in crashed:
            print("  - {}".format(name))
        print()
        print("An installation carrying the fixes raises on all of these.")
        print("Reinstall from the current source:")
        print("  python -m pip install --force-reinstall --no-cache-dir \\")
        print("    git+https://github.com/Ebisaresu/cspy_for_TW.git")
        return 1

    print("All {} checks raised an ordinary exception. This installation"
          " cannot".format(len(CHECKS)))
    print("be made to kill the kernel by any of the known routes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
