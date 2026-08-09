"""Print the release wheel that matches the interpreter running this script.

    python tools/pick_wheel.py

"is not a supported wheel on this platform" means pip compared the wheel's
compatibility tag against the interpreter's list and found no overlap. The
message names the wheel but never the interpreter, which is the half you
actually need: the mismatch is usually that the `python` on PATH is not the
version, the architecture, or even the installation you thought it was.

This script reports what the running interpreter accepts, fetches the asset
list from the releases page, and prints the install command for the wheel that
matches -- or says plainly that none does, and why.

Nothing outside the standard library is used, so it runs before cspy_tw is
installed and regardless of what is in the environment.
"""

import json
import sys
import sysconfig
import urllib.error
import urllib.request

RELEASES_API = "https://api.github.com/repos/Ebisaresu/cspy_for_TW/releases"

#: Enough of the wheel tag grammar for the wheels this project publishes:
#: CPython only, one platform per file, no ABI-agnostic builds.


def interpreter_tag():
    """e.g. 'cp310' -- the interpreter this script is running on."""
    return "cp{}{}".format(sys.version_info[0], sys.version_info[1])


def platform_tags():
    """Platform tags this interpreter accepts, most specific first.

    `sysconfig.get_platform()` answers with the platform the interpreter was
    *built* for, in the punctuation-bearing form ('win-amd64',
    'macosx-11.0-arm64', 'linux-x86_64'); wheel filenames use underscores.
    Only the exact-match cases are handled here -- manylinux and the macOS
    version-compatibility rules are pip's job, and this script defers to pip
    for the final word by printing a command rather than installing anything.
    """
    base = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    tags = [base]
    if base.startswith("linux_"):
        arch = base[len("linux_"):]
        # The published Linux wheels are manylinux; accept them for the arch.
        tags.append("manylinux_2_24_" + arch)
        tags.append("manylinux_2_28_" + arch)
    return tags


def fetch_assets():
    request = urllib.request.Request(
        RELEASES_API, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.load(response)
    assets = []
    for release in releases:
        for asset in release.get("assets") or []:
            if asset["name"].endswith(".whl"):
                assets.append((release.get("tag_name"), asset["name"],
                               asset["browser_download_url"]))
    return assets


def main():
    py_tag = interpreter_tag()
    plats = platform_tags()

    print("interpreter :", sys.version.replace("\n", " "))
    print("executable  :", sys.executable)
    print("wheel tag   :", py_tag)
    print("platform    :", sysconfig.get_platform(), "->", ", ".join(plats))
    print("64-bit      :", sys.maxsize > 2 ** 32)
    print()

    if sys.implementation.name != "cpython":
        print("This is {}, not CPython. Only CPython wheels are published;"
              " build from source:".format(sys.implementation.name))
        print("  python -m pip install"
              " git+https://github.com/Ebisaresu/cspy_for_TW.git")
        return 1

    try:
        assets = fetch_assets()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("Could not read the releases page ({}).".format(exc))
        print("Check by hand:"
              " https://github.com/Ebisaresu/cspy_for_TW/releases")
        return 1

    if not assets:
        print("The releases page carries no wheels.")
        return 1

    matches = [
        (tag, name, url)
        for tag, name, url in assets
        if "-{}-".format(py_tag) in name
        and any(name.endswith(p + ".whl") for p in plats)
    ]

    if matches:
        tag, name, url = matches[0]
        print("Matching wheel in {}:".format(tag))
        print("  " + name)
        print()
        print("Install it with:")
        print("  python -m pip install --force-reinstall --no-cache-dir \\")
        print("    " + url)
        print()
        print("--force-reinstall matters: the version number is the same as a"
              " source build's,")
        print("so without it pip leaves the existing installation alone.")
        return 0

    print("No published wheel matches this interpreter.")
    print()
    same_py = sorted({n for _t, n, _u in assets if "-{}-".format(py_tag) in n})
    if same_py:
        print("Wheels for {} exist, but for other platforms:".format(py_tag))
        for name in same_py:
            print("  " + name)
        print()
        print("So the Python version is right and the platform is not. Check"
              " whether this")
        print("interpreter is 32-bit (win32), ARM (win_arm64), or a different"
              " installation")
        print("from the one you meant to use -- the 'executable' line above"
              " says which.")
    else:
        versions = sorted({
            part
            for _t, n, _u in assets
            for part in n.split("-")
            if part.startswith("cp")
        })
        print("No wheel is published for {}. Published for: {}".format(
            py_tag, ", ".join(versions)))
    print()
    print("Either use an interpreter one of the wheels matches, or build from"
          " source:")
    print("  python -m pip install"
          " git+https://github.com/Ebisaresu/cspy_for_TW.git")
    print()
    print("If you believe this interpreter should match, the authoritative"
          " list is:")
    print("  python -m pip debug --verbose")
    print("under 'Compatible tags'. Paste that when reporting the problem.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
