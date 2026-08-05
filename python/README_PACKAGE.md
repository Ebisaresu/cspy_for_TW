# cspy-tw

Algorithms for the resource constrained shortest path problem, with native
support for time windows and per-node service times.

This is a fork of [`cspy`](https://github.com/torressa/cspy) by
David Torres Sanchez. It adds time windows and per-node service times to the
C++ core, so that they no longer have to be expressed through a Python
resource extension function callback.

## Installation

```
pip install cspy-tw
```

## Usage

The importable package name is `cspy_tw`, not `cspy`:

```python
from cspy_tw import BiDirectional, REFCallback
```

The distribution name (`cspy-tw`) and the import name (`cspy_tw`) both differ
from the upstream project on purpose, so that this fork and the upstream
`cspy` can be installed side by side in the same environment without one
overwriting the other.

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
