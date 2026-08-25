# _version.py is generated at build time by CMake from python/version.py.in,
# so that project(... VERSION ...) in CMakeLists.txt is the only place to edit.
from ._version import __version__
from .algorithms.bidirectional import BiDirectional, REFCallback
from .checking import check
from .preprocessing import preprocess_graph

name = "cspy_tw"

#: Names resolved on first access rather than at import, mapped to the module
#: that defines them.
#:
#: These four are the heuristic algorithms, and every one of them needs numpy
#: -- which the labelling algorithm this package exists for does not. Importing
#: them here unconditionally would make numpy a hard requirement of
#: `import cspy_tw`, so it is deferred to whoever actually asks for a
#: heuristic. See the `heuristics` extra in pyproject.toml.
#:
#: PEP 562 module __getattr__, so `from cspy_tw import GRASP`, `cspy_tw.GRASP`
#: and `dir(cspy_tw)` all behave as they did when these were eager imports.
_LAZY_ATTRIBUTES = {
    "Tabu": ".algorithms.tabu",
    "GreedyElim": ".algorithms.greedy_elimination",
    "PSOLGENT": ".algorithms.psolgent",
    "GRASP": ".algorithms.grasp",
}

__all__ = [
    "BiDirectional",
    "REFCallback",
    "Tabu",
    "GreedyElim",
    "PSOLGENT",
    "GRASP",
    "check",
    "preprocess_graph",
    "__version__",
]


def __getattr__(name):
    module_name = _LAZY_ATTRIBUTES.get(name)
    if module_name is None:
        raise AttributeError(
            "module {!r} has no attribute {!r}".format(__name__, name)
        )
    from importlib import import_module

    try:
        module = import_module(module_name, __name__)
    except ImportError as exc:
        # Almost always the optional numpy dependency. Say so, rather than
        # leaving a bare "No module named 'numpy'" for someone who installed
        # this package for its labelling algorithm and never asked for a
        # heuristic.
        raise ImportError(
            "{} needs the optional dependencies of the heuristic algorithms."
            " Install them with: pip install cspy-tw[heuristics]"
            " (original error: {})".format(name, exc)
        ) from exc
    value = getattr(module, name)
    globals()[name] = value  # resolved once; later lookups skip __getattr__
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_ATTRIBUTES))
