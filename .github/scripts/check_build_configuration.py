"""Fail early if pyproject.toml is missing what the wheel workflow relies on.

The wheel workflow spends about half an hour across five runners.  Everything
it needs from pyproject.toml is cheap to check first, so check it first and
say plainly what is wrong instead of letting five build legs discover it.
"""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = ROOT / "pyproject.toml"

# The build runs in an isolated environment created from build-system.requires,
# so a build tool that is not part of the runner image has to be named there.
# SWIG generates the Python bindings and is not guaranteed to exist inside the
# manylinux container, so it has to be requested explicitly.
REQUIRED_BUILD_TOOLS = ["swig"]

# CMake drives the C++ build and is just as necessary, but some backends add it
# to the build environment themselves through get_requires_for_build_wheel, so
# naming it in build-system.requires would be redundant rather than required.
BACKENDS_THAT_SUPPLY_CMAKE = ("scikit_build_core", "scikit-build-core")


def main() -> int:
    if not PYPROJECT.is_file():
        print(f"There is no {PYPROJECT}.")
        print("Without it, pip cannot build this project from a checkout and")
        print("cibuildwheel has nothing to drive.")
        return 1

    with PYPROJECT.open("rb") as handle:
        config = tomllib.load(handle)

    problems = []

    build_system = config.get("build-system", {})
    requires = build_system.get("requires")
    if not requires:
        problems.append("build-system.requires is missing or empty.")
        requires = []
    backend = build_system.get("build-backend")
    if not backend:
        problems.append("build-system.build-backend is missing.")

    lowered = " ".join(requires).lower()
    for tool in REQUIRED_BUILD_TOOLS:
        if tool not in lowered:
            problems.append(
                f"build-system.requires does not mention {tool}. "
                f"The build needs {tool} and the runner images do not all "
                f"ship it, so it has to come from the isolated build "
                f"environment."
            )

    supplies_cmake = backend is not None and backend.startswith(
        BACKENDS_THAT_SUPPLY_CMAKE
    )
    if "cmake" not in lowered and not supplies_cmake:
        problems.append(
            f"build-system.requires does not mention cmake, and the backend "
            f"{backend!r} is not one that is known to add cmake to the build "
            f"environment on its own."
        )

    project = config.get("project", {})
    if not project.get("name"):
        problems.append("project.name is missing.")
    requires_python = project.get("requires-python")
    if not requires_python:
        problems.append(
            "project.requires-python is missing. cibuildwheel uses it to "
            "decide which interpreters are worth building for."
        )

    if problems:
        print("pyproject.toml is not ready for the wheel workflow.")
        print()
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"build-backend: {build_system['build-backend']}")
    print(f"build-system.requires: {', '.join(requires)}")
    print(f"project.name: {project['name']}")
    print(f"project.requires-python: {requires_python}")
    if "cibuildwheel" in config.get("tool", {}):
        print("[tool.cibuildwheel] is present.")
    else:
        print(
            "[tool.cibuildwheel] is absent. That is survivable: the workflow "
            "passes the settings it depends on as environment variables."
        )
    print("The build configuration looks usable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
