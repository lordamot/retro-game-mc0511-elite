#!/usr/bin/env python3
"""ships_gen.py - ship blueprints -> the resident's tables and the hull bank.

Reads src/res/legend/ships/*.txt (see the README.md there) and writes
two things.  The RESIDENT tables, `--out build/ships.mac`:

    NSHIPS       how many blueprints there are
    SH_<KEY>     one type number per blueprint, 1-based, in AdrDataShips
                 order - and the 1985 names (SH_COBRA3, SH_VIPER ...) as
                 aliases of the Legend blueprints that play their part,
                 for the code and the checks that still use them
    SHIP_STATS   the header numbers the rules read, SS_SIZE bytes a type:
                 energy, speed, laser, collide, shipnum (Legend's
                 dShipN, the yard's number for the hull, which a
                 boarding captures; the dot distance is not carried,
                 nothing reads it), cargo, launch, type (Legend's
                 dTypeObj), objflags (dFlgAI) and flags (dFlg_2) as
                 BYTES, then bounty and rating as WORDS -
                 SHIP_STAT in src/space.mac reads a byte below SS_WORDS.
                 The spawn tier (`class`) is not in the record: only
                 the tier lists below are built from it
    SHIP_CLSN / SHIP_CLSP
                 how many types are in each of the five spawn tiers and
                 where that tier's list of type numbers is
    HULL_OFF     where each blueprint's hull is in the bank, as a word
                 offset - a blueprint that borrows a hull has its owner's
    SHIP_TABLE   a word per type: the hull's address in the hull area,
                 or 0 while it is not loaded.  Empty here; src/hull.mac
                 fills it per system
    HULL_BANK_WORDS / HULL_BANK_SECTORS
                 how big the bank is

and the HULL BANK, `--bank build/hulls.bin`: every hull's geometry, one
record after another and word-aligned, in the layout src/ship.mac walks:

    .WORD  <vertex count>, <edge count>, <bounding radius>, <face count>
    .WORD  4x, 4y, 4z          ... one triple per vertex, times four:
                                  VERT_PROJECT's product then lands in the
                                  high word, which saves its shifts
    .BYTE  cull, 2*v0, 2*v1, faces ... one quad per edge: the vertex
                                  indices doubled, a word offset
    .WORD  nx, ny, nz          ... one normal per face

The bank does not live in the resident: tools/build_elite.py writes it to
the disk at HULL_LBA0, HULL_BANK_INIT reads it into the video planes'
spare area at boot, and HULL_SYSTEM copies the hulls a system can show
into HULL_BASE..HULL_END on arrival (src/hull.mac).

Usage:
    python3 tools/ships_gen.py src/res/legend/ships --out build/ships.mac \\
        --bank build/hulls.bin [--force]
"""

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shiplib                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The byte fields of a SHIP_STATS record, in order, then the word fields.
BYTE_FIELDS = ["energy", "speed", "laser", "collide", "shipnum",
               "cargo", "launch", "type", "objflags", "flags"]
WORD_FIELDS = ["bounty", "rating"]

# The 1985 roster's names, and which Legend blueprint plays each part.
# Retained aliases used by resident helpers and regression fixtures.
LEGACY = [
    ("CORIOLIS", "CORIOLISH"), ("MISSILE", "MISSILEH"),
    ("ESCAPEPOD", "ESCAPEPODH"), ("ALLOY", "ALLOYS1H"),
    ("CANISTER", "CARGOHR"), ("SPLINTER", "MINERALSH"),
    ("ASTEROID", "ASTEROIDHA"), ("HERMIT", "ASTEROIDHO"),
    ("VIPER", "VIPERH"), ("COBRA3", "COBRAMK3HT1"),
    ("PYTHON", "PYTHONHT"), ("PYTHONP", "PYTHONHP"),
    ("COBRA3P", "COBRAMK3HP"), ("ASP", "ASPH"),
    ("FERDELANCE", "FERDELANCEH"), ("THARGOID", "TARGONH"),
    ("SIDEWINDER", "SIDEWINDERH"), ("KRAIT", "KRAITH"),
    ("THARGON", "TARGLETH"),
]


def cargo_1985(cargo):
    """Legend's cargo byte in the encoding src/cargo.mac reads.

    Legend marks a drop with a FIXED load by bit 6, with the market index
    below it (an escape pod is #40+3, slaves; alloys #49; minerals #4C),
    and the two mission containers with bit 7.  The 1985 game keeps the
    same fact as "one less than the market index" in the top nibble, and
    the bottom nibble is how many canisters a hull leaves behind.  This
    turns one into the other for the ordinary cargo path. Mission
    containers use a zero ordinary-cargo value and are handled by their
    object type in the mission logic.
    """
    if cargo & 0x80:
        return 0
    if cargo & 0x40:
        return ((cargo & 0x3F) - 1) << 4
    return cargo & 15


def renderer_limits():
    """MAXVERT, MAXEDGE and MAXFACE out of src/ship.mac, so a hull the
    pipeline's buffers cannot hold fails the build instead of the game."""
    text = open(os.path.join(ROOT, "src/ship.mac"), encoding="utf-8").read()
    out = {}
    for name in ("MAXVERT", "MAXEDGE", "MAXFACE"):
        m = re.search(rf"^{name}\s*=\s*(\d+)\.", text, re.M)
        if not m:
            sys.exit(f"error: {name} not found in src/ship.mac")
        out[name] = int(m.group(1))
    return out


def record_bytes(hull):
    """A hull's bank record, exactly as src/ship.mac walks it."""
    out = bytearray()
    out += struct.pack("<4h", len(hull.vertices), len(hull.edges),
                       hull.radius, len(hull.normals))
    for x, y, z in hull.vertices:
        # four times over: SHIP_DRAW rotates them with VERT_PROJECT, whose
        # 32-bit total is then the Q14 answer in its high word (Legend's
        # largest coordinate is 254, so 1016 fits with room to spare)
        out += struct.pack("<3h", 4 * x, 4 * y, 4 * z)
    for a, b, cull, f1, f2 in hull.edges:
        # Cull threshold first: SHIP_DRAW reads it and can skip the edge
        # without touching anything else.  The faces are packed a nibble
        # each, the way the original packs them.  The two vertex indices
        # are DOUBLED - word offsets into the projected-vertex arrays,
        # which a MOVB then reads ready to index with (34 vertices at
        # most, so 66 at most, and the sign extension is harmless).
        faces = (f2 << 4) | f1 if hull.normals else 0
        out += struct.pack("<4B", cull, 2 * a, 2 * b, faces)
    for x, y, z in hull.normals:
        out += struct.pack("<3h", x, y, z)
    if len(out) & 1:
        out += b"\0"
    return bytes(out)


def bank_layout(ships):
    """The bank: every owning hull's record in type order.  Returns the
    bytes and, per blueprint, the word offset of the hull it draws with."""
    bank = bytearray()
    offset = {}
    for s in ships:
        if s.geometry:
            continue
        offset[s.key] = len(bank) // 2
        bank += record_bytes(s)
    per_ship = [offset[shiplib.hull_of(s, ships).key] for s in ships]
    return bytes(bank), per_ship


def emit(ships, out, bank_words, offsets):
    w = out.write
    w("; Generated by tools/ships_gen.py - do not edit.\n")
    w("; Source: src/res/legend/ships/*.txt.  The hulls themselves are in\n")
    w("; build/hulls.bin, on the disk at HULL_LBA0; see src/hull.mac.\n\n")
    w(f"NSHIPS\t= {len(ships)}.\n\n")
    w("; One symbol per blueprint, 1-based, in AdrDataShips order.\n")
    for i, s_ in enumerate(ships):
        w(f"SH_{s_.key.upper()}\t= {i + 1}.\n")
    w("\n; The 1985 roster's names, for the code and the checks that still\n")
    w("; use them: each is the Legend blueprint that plays the part.\n")
    keys = {s.key for s in ships}
    for old, new in LEGACY:
        if new in keys:
            w(f"SH_{old}\t= SH_{new}\n")
    w("\n")

    # ---- the per-type numbers the rules read ----------------------------
    w("; Offsets into a SHIP_STATS record: bytes up to SS_WORDS, words from\n")
    w("; there.  SHIP_STAT (src/space.mac) reads a field by its offset.\n")
    for i, f in enumerate(BYTE_FIELDS):
        w(f"SS_{f.upper()}\t= {i}.\n")
    base = len(BYTE_FIELDS)
    w(f"SS_WORDS\t= {base}.\n")
    for i, f in enumerate(WORD_FIELDS):
        w(f"SS_{f.upper()}\t= {base + i * 2}.\n")
    size = base + 2 * len(WORD_FIELDS)
    w(f"SS_SIZE\t= {size}.\n\n")
    w("SHIP_STATS:\n")
    for s in ships:
        vals = dict(s.stats)
        vals["cargo"] = cargo_1985(vals["cargo"])
        for f in BYTE_FIELDS:
            if not 0 <= vals[f] <= 255:
                sys.exit(f"error: {s.key}: {f} is {vals[f]}, not a byte")
        bytes_ = ", ".join(f"{vals[f]}." for f in BYTE_FIELDS)
        words = ", ".join(f"{vals[f]}." for f in WORD_FIELDS)
        w(f"\t\t.BYTE\t{bytes_}\t; {s.key}\n")
        w(f"\t\t.WORD\t{words}\n")
    w("\n")

    w("SHIP_LVERT:\n")
    w("\t\t.BYTE\t" + ", ".join(f"{s.stats['laservert']}." for s in ships) + "\n\t\t.EVEN\n\n")

    # ---- the five spawn tiers -------------------------------------------
    byclass = {}
    for i, s in enumerate(ships):
        byclass.setdefault(s.stats["class"], []).append((i + 1, s.key))
    nclass = max(byclass) + 1
    w(f"NSHIPCLS\t= {nclass}.\n\n")
    w("SHIP_CLSN:\n")
    for c in range(nclass):
        w(f"\t\t.WORD\t{len(byclass.get(c, []))}.\n")
    w("SHIP_CLSP:\n")
    for c in range(nclass):
        w(f"\t\t.WORD\tSHIPCLS{c}\n")
    for c in range(nclass):
        members = byclass.get(c, [])
        names = " ".join(k for _, k in members) or "(empty)"
        if members:
            w(f"SHIPCLS{c}:\t.BYTE\t"
              + ", ".join(f"{n}." for n, _ in members) + f"\t; {names}\n")
        else:
            w(f"SHIPCLS{c}:\t.BYTE\t0\t; {names}\n")
    w("\t\t.EVEN\n\n")

    # ---- where the hulls are ---------------------------------------------
    w("; Where each blueprint's hull is in the bank, as a word offset from\n")
    w("; HBANK_ADDR; a blueprint that borrows a hull carries its owner's.\n")
    w("HULL_OFF:\n")
    for s, off in zip(ships, offsets):
        note = f"\t; {s.key}" + (f" (borrows {s.geometry})" if s.geometry else "")
        w(f"\t\t.WORD\t{off}.{note}\n")
    sectors = (bank_words * 2 + 511) // 512
    w(f"\nHULL_BANK_WORDS\t= {bank_words}.\n")
    w(f"HULL_BANK_SECTORS = {sectors}.\n")
    largest = max(len(record_bytes(s)) for s in ships if not s.geometry)
    w(f".IIF GT, {largest}.-<HULL_END-HULL_BASE>, .ERROR ; a hull outgrew the CPU working buffer\n")
    w("; the bank has to fit the planes above the screen, a sector at a time\n")
    w(".IIF GT, <HULL_BANK_SECTORS*256.>-HBANK_MAX, .ERROR ; the hull bank "
      "outgrew the planes' spare area\n\n")
    w("; A word per type: its hull's address once loaded, 0 until then.\n")
    w("SHIP_TABLE:\t.BLKW\tNSHIPS\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("srcdir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bank", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    for path in (args.out, args.bank):
        if os.path.exists(path) and not args.force:
            sys.exit(f"error: {path} exists (use --force)")
    ships = shiplib.read_dir(args.srcdir)
    if not ships:
        sys.exit(f"error: no blueprints in {args.srcdir}")
    limits = renderer_limits()
    for s in ships:
        if s.geometry:
            continue
        for what, have, limit in (("vertices", len(s.vertices), "MAXVERT"),
                                  ("edges", len(s.edges), "MAXEDGE"),
                                  ("faces", len(s.normals), "MAXFACE")):
            if have > limits[limit]:
                sys.exit(f"error: {s.key} has {have} {what}, more than "
                         f"{limit} = {limits[limit]} in src/ship.mac")
    bank, offsets = bank_layout(ships)
    with open(args.bank, "wb") as fh:
        fh.write(bank)
    with open(args.out, "w", encoding="utf-8") as fh:
        emit(ships, fh, len(bank) // 2, offsets)
    total_v = sum(len(s.vertices) for s in ships)
    total_e = sum(len(s.edges) for s in ships)
    shared = sum(1 for s in ships if s.geometry)
    hulls = len(ships) - shared
    print(f"-> {args.out}: {len(ships)} blueprints, {total_v} vertices, "
          f"{total_e} edges")
    print(f"   {shared} of them borrow another ship's hull")
    print(f"-> {args.bank}: {hulls} hulls, {len(bank)} bytes, "
          f"{(len(bank) + 511) // 512} sectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
