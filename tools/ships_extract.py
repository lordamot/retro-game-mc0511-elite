#!/usr/bin/env python3
"""ships_extract.py - pull the 3D objects out of orig/ELITE.SCL.

They live in `elitr1`, the 5376-byte block that ends up at 0x5B00 (see
`LOAD_MAP` in elite_re.py for why that address and not the 16384 the
BASIC prints).  Nothing here is guessed at: the original carries its own
table of every object, `AdrDataShips` at 0x6180, and this reads it.

    AdrDataShips: 19 four-byte entries, in ship-type order

        +0   0xC3, a `jp` opcode left over from an older calling
             convention - never executed, only skipped
        +1   the object's blueprint address
        +3   its class, 0..4: the tier the spawner draws from
             (0 station and missile, 1 the small drops, 2 common
             traffic, 3 the heavy hulls, 4 the fighters)

    Blueprint: a 23-byte header, then vertices, edges and normals

        +0   cargo hold / what it yields when broken up
        +1   collision distance
        +2   laser hit chance against an Elite pilot (halved below)
        +3   vertex count
        +4   edge count
        +5   normal count
        +6   max speed
        +7   max energy
        +8   kill bounty, a word
        +10  what it can launch
        +11  geometric size: past this it is drawn as a dot
        +12  offset to the vertices, a word, from the object's own base
        +14  offset to the edges
        +16  offset to the normals
        +18  flags
        +19  unused, +20 unused
        +21  combat rating points, a word

        vertex, 6 bytes: |x|, |y|, |z|, then a byte whose bits 7/6/5 are
             the signs and whose low five bits are a cull distance, then
             two bytes naming up to four faces, a nibble each
        edge,   4 bytes: cull distance, vertex, vertex, face pair
        normal, 4 bytes: |x|, |y|, |z|, signs-and-cull

An edge also names up to two faces, a nibble each, and a face is a
normal: that is the whole of backface culling, and it is why a hull can
be drawn as a wireframe without its far side showing through.  The
Alloys plate is the one object with no normals at all, and the original
treats a zero normal count as "every face always visible".

The cull distance is the useful half of what this port had been throwing
away: 31 means "always draw", anything less means "only from closer than
this".  Eighteen of a Cobra Mk III's 38 edges are panel lines the
original stops drawing as it recedes, and five of them, at a threshold
of 6, are only ever seen at point-blank range.

Three of the nineteen carry a header and nothing else: their offsets
point into another object's tables.  That is how the original gets a
trader and a pirate Cobra out of one hull, and a rock hermit out of the
asteroid.  They are written out here as a `geometry <key>` line rather
than a second copy of the vertices.

    python3 tools/ships_extract.py --out src/res/ships [--force]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elite_re                                   # noqa: E402

HDR = 23
TABLE = 0x6180
NOBJ = 19

# The roster, by the index the original's own table gives each object.
# Identification is the header's numbers against the values every Elite
# uses - a Thargoid is speed 39, energy 240, bounty 500 and launches
# Thargons wherever it appears - backed up by the labels in nzeemin's
# disassembly of this same build (d_ASP, d_Coriolis, d_Krait, ...).
# Nothing here is by silhouette any more.
NAMES = [
    ("coriolis",   "СТАНЦИЯ КОРИОЛИС"),   # 0
    ("missile",    "РАКЕТА"),             # 1
    ("escapepod",  "КАПСУЛА"),            # 2
    ("alloy",      "ПЛАСТИНА"),           # 3
    ("canister",   "КОНТЕЙНЕР"),          # 4
    ("splinter",   "ОБЛОМОК"),            # 5
    ("asteroid",   "АСТЕРОИД"),           # 6
    ("hermit",     "ОТШЕЛЬНИК"),          # 7
    ("viper",      "ВИПЕР"),              # 8
    ("cobra3",     "КОБРА МК3"),          # 9
    ("python",     "ПИТОН"),              # 10
    ("pythonp",    "ПИТОН"),              # 11
    ("cobra3p",    "КОБРА МК3"),          # 12
    ("asp",        "АСП МК2"),            # 13
    ("ferdelance", "ФЕР-ДЕ-ЛАНС"),        # 14
    ("thargoid",   "ТАРГОИД"),            # 15
    ("sidewinder", "СИДЕВАЙНДЕР"),        # 16
    ("krait",      "КРЕЙТ"),              # 17
    ("thargon",    "ТАРГОН"),             # 18
]


def read_table(img):
    """The 19 (blueprint address, class) pairs, in ship-type order."""
    out = []
    for i in range(NOBJ):
        p = TABLE + i * 4
        out.append((img[p + 1] | (img[p + 2] << 8), img[p + 3]))
    return out


def header(img, a):
    """The 23-byte header as a dict, offsets resolved to addresses."""
    def b(k):
        return img[a + k]

    def w(k):
        return img[a + k] | (img[a + k + 1] << 8)

    return dict(
        addr=a, cargo=b(0), collide=b(1), laser=b(2),
        nv=b(3), ne=b(4), nn=b(5), speed=b(6), energy=b(7),
        bounty=w(8), launch=b(10), dot=b(11),
        v0=a + w(12), e0=a + w(14), n0=a + w(16),
        flags=b(18), rating=w(21),
    )


def decode(img, h):
    verts = []
    for k in range(h["nv"]):
        a = h["v0"] + k * 6
        x, y, z, s = img[a], img[a + 1], img[a + 2], img[a + 3]
        verts.append((-x if s & 0x80 else x,
                      -y if s & 0x40 else y,
                      -z if s & 0x20 else z))
    edges = []
    for k in range(h["ne"]):
        e = h["e0"] + k * 4
        faces = img[e + 3]
        edges.append((img[e + 1], img[e + 2], img[e] & 0x1F,
                      faces & 0x0F, faces >> 4))
    normals = []
    for k in range(h["nn"]):
        a = h["n0"] + k * 4
        x, y, z, sn = img[a], img[a + 1], img[a + 2], img[a + 3]
        normals.append((-x if sn & 0x80 else x,
                        -y if sn & 0x40 else y,
                        -z if sn & 0x20 else z))
    n = len(verts)
    for a, b, _, f1, f2 in edges:
        if not (0 <= a < n and 0 <= b < n):
            raise SystemExit(f"0x{h['addr']:04X}: edge {a}-{b} out of range")
        if normals and not (f1 < len(normals) and f2 < len(normals)):
            raise SystemExit(f"0x{h['addr']:04X}: edge names face {f1}/{f2} "
                             f"of {len(normals)}")
    return verts, edges, normals


def write_ship(path, idx, key, name, cls, h, verts, edges, normals, shares):
    """One blueprint as text.  `shares` names the object whose geometry
    this one borrows, or None when it carries its own."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            f"# {name} - extracted from orig/ELITE.SCL by\n"
            f"# tools/ships_extract.py; object {idx} of the original's\n"
            f"# table, blueprint at 0x{h['addr']:04X} of the loaded image.\n"
            f"# Do not edit by hand unless you mean to diverge from the\n"
            f"# original: `make extract` overwrites it.\n")
        fh.write(f"name {name}\n")
        fh.write(f"index {idx}\n")
        fh.write(f"class {cls}\n")
        fh.write(f"speed {h['speed']}\n")
        fh.write(f"energy {h['energy']}\n")
        fh.write(f"bounty {h['bounty']}\n")
        fh.write(f"laser {h['laser']}\n")
        fh.write(f"collide {h['collide']}\n")
        fh.write(f"cargo {h['cargo']}\n")
        fh.write(f"launch {h['launch']}\n")
        fh.write(f"dot {h['dot']}\n")
        fh.write(f"rating {h['rating']}\n")
        fh.write(f"flags {h['flags']}\n")
        if shares:
            fh.write(f"# the header points at {shares}'s tables: one hull,\n"
                     f"# two sets of numbers, exactly as the original does.\n")
            fh.write(f"geometry {shares}\n")
            return
        radius = max(max(abs(c) for c in v) for v in verts)
        fh.write(f"radius {radius}\n")
        for x, y, z in verts:
            fh.write(f"vertex {x:5d} {y:5d} {z:5d}\n")
        for a, b, cull, f1, f2 in edges:
            fh.write(f"edge {a} {b} {cull} {f1} {f2}\n")
        for x, y, z in normals:
            fh.write(f"normal {x:5d} {y:5d} {z:5d}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", default="src/res/ships")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    img = elite_re.load_image()
    table = read_table(img)
    heads = [header(img, a) for a, _ in table]

    # Who owns which geometry.  An object whose vertex offset lands
    # inside another object's tables is borrowing them.
    owner = {}
    for i, h in enumerate(heads):
        owner.setdefault(h["v0"], i)
    for i, h in enumerate(heads):
        if h["v0"] != heads[owner[h["v0"]]]["v0"]:
            raise SystemExit("geometry ownership is not a partition")

    os.makedirs(args.out, exist_ok=True)
    for i, (h, (key, name)) in enumerate(zip(heads, NAMES)):
        own = owner[h["v0"]]
        shares = None if own == i else NAMES[own][0]
        path = os.path.join(args.out, key + ".txt")
        if os.path.exists(path) and not args.force:
            sys.exit(f"error: {path} exists (use --force)")
        verts, edges, normals = decode(img, h)
        write_ship(path, i, key, name, table[i][1], h, verts, edges,
                   normals, shares)
        note = f"shares {shares}" if shares else f"{h['nv']}v {h['ne']}e"
        print(f"  {i:2}  0x{h['addr']:04X}  class {table[i][1]}  "
              f"{key:<11} {note}")
    print(f"{NOBJ} objects extracted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
