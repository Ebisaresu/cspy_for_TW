# cspy-tw

Algorithms for the resource constrained shortest path problem, with native
support for time windows and per-node service times.

This is a fork of [`cspy`](https://github.com/torressa/cspy) by
David Torres Sanchez. It adds time windows and per-node service times to the
C++ core, so that they no longer have to be expressed through a Python
resource extension function callback.

## Installation

This fork is not published on the Python Package Index, so `pip install
cspy-tw` will not find it. There are two ways to install it instead.

**From a prebuilt wheel (no build tools needed).** Pick the wheel that matches
your operating system and Python version from the
[releases page](https://github.com/Ebisaresu/cspy_for_TW/releases) and install
it by its address:

```
pip install https://github.com/Ebisaresu/cspy_for_TW/releases/download/<tag>/<wheel file name>
```

**From source.** This compiles the C++ core:

```
pip install git+https://github.com/Ebisaresu/cspy_for_TW.git
```

It needs three things on the machine: a C++ compiler, `git`, and reachable
network access to `github.com`. CMake, Ninja and SWIG are downloaded
automatically as build dependencies, but the build also clones two C++
libraries, LEMON and spdlog, while configuring, so it cannot run offline or
behind a firewall that blocks GitHub. The build takes a few minutes.

## Usage

The importable package name is `cspy_tw`, not `cspy`:

```python
from cspy_tw import BiDirectional, REFCallback
```

The distribution name (`cspy-tw`) and the import name (`cspy_tw`) both differ
from the upstream project on purpose, so that this fork and the upstream
`cspy` can be installed side by side in the same environment without one
overwriting the other. They can also be imported and used in the same process:
the compiled core of this fork is linked into its own extension module with its
C++ symbols hidden, so the two versions cannot be confused for each other by the
dynamic loader.

## Relationship to the upstream project

This fork is **not** affiliated with, nor endorsed by, the upstream project.
Please report issues with this fork to its own issue tracker, and not to the
upstream one.

- This fork: <https://github.com/Ebisaresu/cspy_for_TW>
- Upstream project: <https://github.com/torressa/cspy>
- Upstream documentation: <https://cspy.readthedocs.io/>

## License

MIT, the same license as the upstream project. The original copyright notice
is preserved in `LICENSE.txt`; see `NOTICE.txt` for the attribution details.
