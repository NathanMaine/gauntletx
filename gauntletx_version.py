"""The version of this gauntletx checkout.

Single source of truth is the VERSION file at the repo root, read from next
to this module — so copied installs (the NAS container's /app) keep working
without a package install. Bump VERSION and tag the release on the way out;
the UI footer and /api/version show it so you can tell what is running
without opening the box.
"""

import pathlib

# What this file shipped as, used only when the VERSION file is absent
# (e.g. a bare copy of just the .py files). The file, when present, wins.
_FALLBACK = "0.3.3"


def _read():
    try:
        p = pathlib.Path(__file__).resolve().parent / "VERSION"
        v = p.read_text(encoding="utf-8").strip()
        return v or _FALLBACK
    except OSError:
        return _FALLBACK


VERSION = _read()
