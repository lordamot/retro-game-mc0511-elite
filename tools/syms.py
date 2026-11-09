#!/usr/bin/env python3
"""syms.py - resolve label addresses from build/elite.lst.

    python3 tools/syms.py SCREEN KEYS KEYS_EDGE U.SIZE

Prints "NAME octal" per line.  A label is only recognised where it is
the first token of the source text, so a name mentioned in a comment
never passes for one.  Direct assignments (`U.SIZE = 64`) are resolved
too, so a tool can read the shape of a record rather than hard-coding
it and going quietly wrong the day it changes.
"""
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

LST = Path(__file__).resolve().parent.parent / "build/elite.lst"
SYM_RE = re.compile(
    r"^\s*\d+\s+([0-7]{6})\s+(?:[0-7]{3,6}'?\s+){0,4}([A-Z][A-Z_0-9.$]*):")
# A direct assignment lists its value in the same column a label's address
# would occupy, with the name and an "=" as the source text.
DEF_RE = re.compile(
    r"^\s*\d+\s+([0-7]{6})\s+([A-Z][A-Z_0-9.$]*)\s*=\s")


# A label alone on its line: the listing prints the line number, then
# the label, and no address - that is on the next line that has one.
BARE_RE = re.compile(r"^\s*\d+\s+([A-Z][A-Z_0-9.$]*):")
ADDR_RE = re.compile(r"^\s*\d+\s+([0-7]{6})\s")


def check_fresh(quiet=False):
    """Refuse to work against a build older than the sources.

    A failed `make build` leaves the previous disk and the previous
    listing in place, and everything downstream then reads real
    addresses out of the wrong image: the game appears to run while
    every peek comes back as nonsense.  That has cost two long debugging
    sessions, so the tools check rather than trust.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lst = os.path.join(root, "build", "elite.lst")
    dsk = os.path.join(root, "build", "elite.dsk")
    if not os.path.exists(lst) or not os.path.exists(dsk):
        raise SystemExit("error: no build - run `make build`")
    built = min(os.path.getmtime(lst), os.path.getmtime(dsk))
    newer = []
    for sub in ("src", "src/res"):
        d = os.path.join(root, sub)
        for name in os.listdir(d):
            f = os.path.join(d, name)
            if os.path.isfile(f) and os.path.getmtime(f) > built:
                newer.append(os.path.join(sub, name))
    if newer:
        raise SystemExit("error: the build is older than "
                         + ", ".join(sorted(newer)[:4])
                         + " - run `make build` (and read what it says)")
    if not quiet:
        pass
    return True


def table(overlays=True):
    """Labels and direct assignments, name -> value as an octal string.

    The overlays' listings (build/ovl_*.lst) are read after the
    resident's: their addresses are only meaningful while that overlay
    is in the window, which a check that peeks at one has to know."""
    out = {}
    if overlays:
        for lst in sorted(LST.parent.glob("ovl_*.lst")):
            for name, value in _read(lst).items():
                out.setdefault(name, value)
    for name, value in _read(LST).items():
        out[name] = value
    return out


def _read(path):
    stat = path.stat()
    return _read_version(path, stat.st_mtime_ns, stat.st_size).copy()


@lru_cache(maxsize=64)
def _read_version(path, mtime_ns, size):
    # A verify run asks for the same labels thousands of times.  Reparse
    # only when the listing changes; never cache across a rebuild by name.
    out = {}
    pending = []            # labels on lines of their own, which the
                            # listing prints with no address: they take
                            # the next line's
    for line in path.read_text(errors="replace").splitlines():
        m = SYM_RE.match(line) or DEF_RE.match(line)
        if m:
            for name in pending:
                out.setdefault(name, m.group(1))
            pending = []
            out.setdefault(m.group(2), m.group(1))
            continue
        m = BARE_RE.match(line)
        if m:
            pending.append(m.group(1))
            continue
        m = ADDR_RE.match(line)
        if re.search(r"\.(?:IF|IIF|IFF|ENDC)|\.\.\.V", line):
            continue
        if m and pending:
            for name in pending:
                out.setdefault(name, m.group(1))
            pending = []
    return out


def val(name):
    """One symbol as an int, or KeyError."""
    return int(table()[name], 8)


if __name__ == "__main__":
    t = table()
    for name in sys.argv[1:]:
        print(f"{name} {t.get(name, '?')}")
