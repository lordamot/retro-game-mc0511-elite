#!/usr/bin/env python3
"""shiplib.py - reader for the ship blueprints in src/res/legend/ships/.

Shared by tools/ships_gen.py (blueprint -> MACRO-11) and
tools/ship_render.py (blueprint -> PNG preview).  See
src/res/legend/ships/README.md for the file format.
"""

import os
import re


# The header fields the original keeps per object, and what each one is
# worth if a blueprint does not name it.  See tools/ships_extract.py for
# where they come from.
STATS = {
    "index": -1,        # the original's own ship-type number
    "class": 2,         # spawn tier, 0..4
    "speed": 20,        # max speed along its own nose
    "energy": 24,       # what it takes to break it up
    "bounty": 0,        # credits for killing it
    "laser": 0,         # its chance of hitting an Elite pilot
    "collide": 40,      # collision distance
    "cargo": 0,         # hold, or what it yields when broken up
    "launch": 0,        # what it can launch
    "dot": 20,          # past this it is drawn as a dot
    "rating": 0,        # combat rating points
    "flags": 0,
    # Elite Legend's header carries five more (tools/legend_ships.py);
    # the 1985 blueprints leave them at zero
    "flags2": 0,
    "laservert": 0,     # the vertex its laser fires from
    "type": 0,          # trader/police/pirate/... and the boardable bit
    "objflags": 0,
    "shipnum": 0,       # its number in the ship yard, for boarding
}


class Ship:
    def __init__(self, key, name="", radius=100, scale=1):
        self.key = key
        self.name = name
        self.radius = radius
        self.scale = scale
        self.vertices = []      # list of (x, y, z)
        self.edges = []         # list of (v0, v1, cull, face1, face2)
        self.normals = []       # list of (x, y, z), one per face
        self.geometry = None    # key of the ship whose hull this borrows
        self.stats = dict(STATS)

    def __getattr__(self, name):
        # Header fields read as attributes: ship.energy, ship.bounty, ...
        if name != "stats" and name in STATS:
            return self.stats[name]
        raise AttributeError(name)

    def __repr__(self):
        return (f"<Ship {self.key} {self.name!r} "
                f"{len(self.vertices)}v {len(self.edges)}e>")


def read_ship(path):
    key = os.path.splitext(os.path.basename(path))[0].upper()
    ship = Ship(key)
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            what = parts[0].lower()
            try:
                if what == "name":
                    ship.name = " ".join(parts[1:])
                elif what == "radius":
                    ship.radius = int(parts[1])
                elif what == "scale":
                    ship.scale = int(parts[1])
                elif what == "vertex":
                    ship.vertices.append(tuple(int(v) for v in parts[1:4]))
                elif what == "edge":
                    # A third field is the original's cull threshold:
                    # 31 = always drawn, less = only from closer in.
                    # The fourth and fifth name the faces it lies on.
                    cull = int(parts[3]) if len(parts) > 3 else 31
                    f1 = int(parts[4]) if len(parts) > 4 else 0
                    f2 = int(parts[5]) if len(parts) > 5 else f1
                    ship.edges.append((int(parts[1]), int(parts[2]),
                                       cull, f1, f2))
                elif what == "normal":
                    ship.normals.append(tuple(int(v) for v in parts[1:4]))
                elif what == "geometry":
                    ship.geometry = parts[1].upper()
                elif what in STATS:
                    ship.stats[what] = int(parts[1])
                else:
                    raise ValueError(f"unknown keyword {what!r}")
            except (IndexError, ValueError) as exc:
                raise SystemExit(f"{path}:{lineno}: {exc}")
    if ship.scale != 1:
        ship.vertices = [tuple(c // ship.scale for c in v)
                         for v in ship.vertices]
    if ship.geometry:
        if ship.vertices or ship.edges or ship.normals:
            raise SystemExit(f"{path}: a ship that borrows geometry from "
                             f"{ship.geometry} may not carry its own")
        return ship
    n = len(ship.vertices)
    nf = len(ship.normals)
    for a, b, _, f1, f2 in ship.edges:
        if not (0 <= a < n and 0 <= b < n):
            raise SystemExit(f"{path}: edge {a}-{b} is out of range "
                             f"(only {n} vertices)")
        if nf and not (f1 < nf and f2 < nf):
            raise SystemExit(f"{path}: edge {a}-{b} names face {f1}/{f2}, "
                             f"but there are only {nf}")
    if not ship.vertices:
        raise SystemExit(f"{path}: no vertices")
    return ship


def read_dir(dirpath):
    """Every blueprint in a directory, in the original's own ship-type
    order when the files carry an `index`, alphabetically otherwise.

    The order matters: it is the order SH_* symbols are numbered in, and
    keeping it the original's means a type number in this port and a type
    number in a disassembly of the original are the same number.
    """
    ships = []
    for name in sorted(os.listdir(dirpath)):
        if name.endswith(".txt") and name != "README.txt":
            ships.append(read_ship(os.path.join(dirpath, name)))
    if all(s.index >= 0 for s in ships):
        ships.sort(key=lambda s: s.index)
        seen = [s.index for s in ships]
        if seen != list(range(len(seen))):
            raise SystemExit(f"{dirpath}: ship indices are {seen}, "
                             f"expected 0..{len(seen) - 1} with no gaps")
    for s in ships:
        if s.geometry and s.geometry not in {t.key for t in ships}:
            raise SystemExit(f"{dirpath}: {s.key} borrows geometry from "
                             f"{s.geometry}, which is not here")
    return ships


# The five spawn tiers the 1985 spawner draws from - CL_* in src/defs.mac.
CL_STATION, CL_DROPS, CL_TRADERS, CL_HEAVIES, CL_FIGHTERS = range(5)

# Elite Legend's type byte: the low three bits are the KIND of object,
# the bits above are flags (8 boardable, 16 missile-proof).
KIND_TRADER, KIND_POLICE, KIND_PIRATE, KIND_HUNTER, KIND_TARGON, \
    KIND_ASTEROID, KIND_MISSILE, KIND_STATIC = range(8)

# Headers the rule below gets wrong, and where they really belong: the
# Targlet is "static" by Legend's type byte because a Targon steers it,
# but it flies and shoots, and the 1985 game sorted it with the fighters.
TIER_BY_KEY = {"TARGLETH": CL_FIGHTERS}


def legend_tier(key, type_, objflags, energy):
    """Compatibility tier used for roster selection and class-based helpers.
    The active flight AI also uses Legend's own role-specific spawn tables.

    By kind: stations and bases are tier 0 with the missile; drops (the
    static objects with bit 7 of the object flags set) and asteroids
    tier 1; traders and police tier 2, which is where the 1985 Viper
    lived; hunters and Targons tier 3; pirates tier 3 or 4 by size, the
    line at 150 energy, which is where the 1985 table drew it (a Cobra
    Mk III pirate at 150 is a heavy, a Krait at 80 a fighter).
    """
    if key.upper() in TIER_BY_KEY:
        return TIER_BY_KEY[key.upper()]
    kind = type_ & 7
    if kind == KIND_STATIC:
        return CL_DROPS if objflags & 0x80 else CL_STATION
    if kind == KIND_MISSILE:
        return CL_STATION
    if kind == KIND_ASTEROID:
        return CL_DROPS
    if kind in (KIND_TRADER, KIND_POLICE):
        return CL_TRADERS
    if kind == KIND_PIRATE:
        return CL_FIGHTERS if energy < 150 else CL_HEAVIES
    return CL_HEAVIES


def hull_of(ship, ships):
    """The ship carrying the geometry `ship` draws with - itself, unless
    it borrows a hull."""
    if not ship.geometry:
        return ship
    return next(t for t in ships if t.key == ship.geometry)
