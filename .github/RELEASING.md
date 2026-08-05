# Releasing this fork

This fork distributes wheels as GitHub release assets and nowhere else. It is
not published to the Python Package Index or to NuGet, and nothing in this
repository is allowed to publish there. `.github/scripts/check_no_publishing.py`
enforces that for the repository tree, and
`.github/workflows/no-publishing.yml` runs it on every push to `master`, on
every pull request, and on demand.

## One-off: things a repository file cannot remove

Deleting the publishing workflows was not enough. The following live outside the
repository tree, survive any change to it, and have to be removed by hand, once,
by someone with administrator access. Until then a restored workflow file could
still publish.

1. **Repository secrets.** Settings -> Secrets and variables -> Actions. Delete
   `PYPI_API_KEY`, `NUGET_API_KEY` and `GH_PAGES_TOKEN`. None of the workflows
   that remain read any secret other than the automatic `GITHUB_TOKEN`.
2. **The deployment environment.** Settings -> Environments. Delete the
   environment named `pypi`. The deleted `pypi_release.yml` declared it, which
   is also the shape a trusted publisher is registered against.
3. **A trusted publisher on the index side.** Log in to the Python Package Index
   account and open Your projects -> Publishing, including the *pending*
   publishers list. A pending publisher registered against
   `Ebisaresu/cspy_for_TW` with workflow file `pypi_release.yml` and environment
   `pypi` would let a restored file of that exact name both publish and claim
   the distribution name, with no token involved at all. The name `cspy-tw` is
   currently unclaimed, which is what makes that worth checking. Delete any
   entry that refers to this repository.
4. **Default workflow permissions.** Settings -> Actions -> General -> Workflow
   permissions. Set it to "Read repository contents and packages permissions".
   Every workflow here that needs more asks for it explicitly.

## Before the first tagged release

No leg of `wheels.yml` has ever run: every one of the five builds for the first
time when a tag is pushed, or when the workflow is started by hand. `ci.yml`
covers less than it looks like it does -- Linux and Windows, CPython 3.13, one
architecture each, and through `pip` rather than through cibuildwheel.
The package contains a single compiled file with the C++ core linked into it, so
`auditwheel` and `delocate` have nothing to relocate. `delvewheel` on Windows
does have something to do: the extension imports `MSVCP140.dll` from the Visual
C++ runtime, which is not part of Windows, so the Windows wheel is the one wheel
whose shipped layout is not the layout that was built. Do a dry run first:

1. Actions -> Wheels -> Run workflow. Set **build-selector** to `cp313-*`, leave
   **platforms** at `all`, and leave **attach-to-release** empty. Nothing
   touches a release in this mode; the wheels stay as build artifacts. To
   re-check one platform after a fix, set **platforms** to that platform
   instead of paying for all five again.
2. Download all five artifacts. For each one, in a throwaway virtual
   environment: install it, `import cspy_tw`, run
   `python .github/scripts/run_tests.py`, and check that the package carries its
   own compiled code and asks the operating system for nothing beyond the C++
   runtime (`otool -L` on macOS, `ldd` on Linux, `dumpbin /dependents` on
   Windows).
3. For the Windows wheel, do two more things. Unzip it and confirm it contains
   a vendored copy of the Visual C++ runtime. `delvewheel` renames what it
   vendors, so the entry reads `msvcp140-<hash>.dll` rather than
   `MSVCP140.dll`; match the stem case-insensitively rather than the whole
   name. `delvewheel` puts vendored libraries in a top-level
   `cspy_tw.libs` directory, beside the `cspy_tw` package rather than beside the
   extension module inside it, and patches the package's `__init__.py` to add
   that directory to the search path at import time. A wheel without it depends
   on the user having the Visual C++ redistributable installed. Then install the
   wheel on a Windows machine that has never had Visual Studio on it, and import
   it. Neither a GitHub runner nor a developer machine can stand in for that
   second check, because both have the runtime already.
4. Only then push the version tag.

## Cutting a release

1. Update `VERSION` in the `project()` call in `CMakeLists.txt`. That is the
   single source of truth: `pyproject.toml` reads it, and so does the version
   module inside the package.
2. Commit, then create and push the tag: `git tag v<version> && git push origin
   v<version>`.
3. `wheels.yml` builds the wheels for all five platforms, creates a **draft**
   release for the tag and attaches them. Nothing is publicly visible yet.
4. Check the draft, write the notes, press publish.

Users then install a wheel by its address:

```
pip install https://github.com/Ebisaresu/cspy_for_TW/releases/download/<tag>/<wheel file name>
```

## Pinned dependencies

`CMakeLists.txt` fetches LEMON and spdlog by commit, not by branch name. Two
builds of the same tag therefore produce the same binary, and an upstream force
push cannot silently change what users receive. Moving either pin is a
deliberate edit, and it should be followed by the dry run above.
