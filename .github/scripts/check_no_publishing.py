"""Fail if anything under .github can publish this project to a package index.

This fork is not published to the Python Package Index or to NuGet.  The wheels
are distributed as GitHub release assets and nothing else.  The workflows that
used to publish were removed, but an upstream merge or a well meaning edit could
bring them back, so the ban is checked rather than assumed.

Scope of the scan:

* every file under .github, not only .github/workflows, because a composite
  action under .github/actions can run any command a workflow step can;
* this script itself is excluded by path, since it necessarily contains every
  pattern it looks for;
* physical lines are joined on a trailing backslash before matching, so that
  splitting "twine \\" and "upload dist/*" across two lines does not hide it.

What this cannot see is anything outside the repository: the tokens stored as
repository secrets, the GitHub deployment environment the deleted workflow
declared, and any trusted publisher registered on the package index side.  Those
have to be removed by hand; .github/RELEASING.md lists them.
"""

import re
import sys
from pathlib import Path

GITHUB_DIR = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

# Files worth reading.  Workflows and actions are YAML; a publishing step is
# just as easy to hide in a shell or Python helper that a workflow calls.
SUFFIXES = {".yml", ".yaml", ".sh", ".bash", ".zsh", ".ps1", ".py"}

# Each entry is a human readable reason and the pattern that betrays it.
# The patterns are matched case insensitively against logically joined lines.
FORBIDDEN = [
    # Actions that upload to an index.
    ("publishes to PyPI with the pypa action", r"gh-action-pypi-publish"),
    ("publishes to PyPI with an action", r"pypa/[a-z0-9._-]*pypi[a-z0-9._-]*"),
    # Command line tools that upload to an index.  Every packaging front end in
    # common use has such a command, so name them all rather than assume the
    # next contributor reaches for twine.
    ("publishes to PyPI with twine", r"twine\s+upload"),
    ("publishes to PyPI with flit", r"flit\s+publish"),
    ("publishes to PyPI with uv", r"\buv\s+publish"),
    ("publishes to PyPI with poetry", r"\bpoetry\s+publish"),
    ("publishes to PyPI with hatch", r"\bhatch\s+publish"),
    ("publishes to PyPI with pdm", r"\bpdm\s+publish"),
    ("publishes to PyPI with maturin", r"\bmaturin\s+(upload|publish)"),
    ("publishes to PyPI with cibuildwheel", r"cibuildwheel[^\n]*--?upload"),
    ("publishes with the setuptools upload command", r"setup\.py[^\n]*\bupload\b"),
    # The endpoints themselves.
    ("talks to the PyPI upload endpoint", r"(test\.)?pypi\.org/legacy"),
    ("talks to the PyPI upload endpoint", r"upload\.(test\.)?pypi\.org"),
    ("publishes to NuGet", r"nuget\s+push"),
    ("talks to the NuGet upload endpoint", r"api\.nuget\.org/v3/index\.json"),
    # Credentials.  A token that is read has a reason to be read.
    ("reads a PyPI token", r"PYPI_API_KEY|PYPI_API_TOKEN|PYPI_TOKEN"),
    ("reads a PyPI token", r"TWINE_PASSWORD|TWINE_USERNAME|TWINE_REPOSITORY"),
    ("reads a PyPI token", r"UV_PUBLISH_TOKEN|POETRY_PYPI_TOKEN|POETRY_HTTP_BASIC"),
    ("reads a PyPI token", r"HATCH_INDEX_AUTH|HATCH_INDEX_USER"),
    ("reads a PyPI token", r"PDM_PUBLISH_PASSWORD|PDM_PUBLISH_USERNAME"),
    ("reads a PyPI token", r"MATURIN_PASSWORD|MATURIN_USERNAME"),
    ("reads a NuGet token", r"NUGET_API_KEY|NUGET_TOKEN"),
    # Trusted publishing needs an OpenID Connect token and, in the shape the
    # deleted workflow used, a deployment environment named after the index.
    # Nothing in this repository has a reason for either.
    ("requests an OpenID Connect token", r"id-token:\s*write"),
    ("declares a package index deployment environment", r"name:\s*['\"]?pypi\b"),
    ("declares a package index deployment environment", r"name:\s*['\"]?nuget\b"),
]

# A reusable workflow from another repository is opaque to this scan: the file
# that would do the publishing is not in this repository at all.  Treat calling
# one as a finding on its own.  Local reusable workflows (./.github/...) are
# fine, because they are scanned like everything else.
REUSABLE_WORKFLOW = re.compile(
    r"^\s*uses:\s*['\"]?(?!\./)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+/\.github/workflows/[^\s'\"]+)",
    re.IGNORECASE,
)


def logical_lines(text):
    """Yield (first physical line number, joined line).

    A line ending in a backslash is continued by the next one, which is how a
    shell command can be spread over several lines inside a run: block.
    """
    pending = ""
    start = None
    for number, line in enumerate(text.splitlines(), start=1):
        if start is None:
            start = number
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        yield start, pending + line
        pending = ""
        start = None
    if pending:
        yield start, pending


def files_to_scan():
    for path in sorted(GITHUB_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve() == SELF:
            continue
        if path.suffix.lower() in SUFFIXES:
            yield path


def main() -> int:
    if not GITHUB_DIR.is_dir():
        print(f"No .github directory at {GITHUB_DIR}.", file=sys.stderr)
        return 1

    paths = list(files_to_scan())
    if not paths:
        print(f"Nothing to scan under {GITHUB_DIR}.", file=sys.stderr)
        return 1

    problems = []
    for path in paths:
        relative = path.relative_to(GITHUB_DIR.parent)
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in logical_lines(text):
            for reason, pattern in FORBIDDEN:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    problems.append((relative, number, reason, line.strip()))
            match = REUSABLE_WORKFLOW.search(line)
            if match:
                problems.append(
                    (
                        relative,
                        number,
                        f"calls a reusable workflow from another repository "
                        f"({match.group(1)}), whose contents this check cannot "
                        f"see",
                        line.strip(),
                    )
                )

    if problems:
        print("Something under .github can publish this project to a package")
        print("index. That is not allowed in this fork; the wheels go to a")
        print("GitHub release and nowhere else.")
        print()
        for relative, number, reason, line in problems:
            print(f"  {relative}:{number}: {reason}")
            print(f"    {line[:160]}")
        return 1

    print(f"Scanned {len(paths)} files under {GITHUB_DIR.name}:")
    for path in paths:
        print(f"  {path.relative_to(GITHUB_DIR.parent)}")
    print()
    print("Nothing under .github can publish to a package index.")
    print()
    print("This says nothing about the repository settings. Secrets, the")
    print("deployment environment and any trusted publisher registered on the")
    print("index live outside the repository; see .github/RELEASING.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
