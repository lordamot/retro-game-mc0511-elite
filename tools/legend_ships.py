#!/usr/bin/env python3
"""legend_ships.py - Elite Legend's hulls and headers -> src/res/legend/ships/.

    python3 tools/legend_ships.py [--out src/res/legend/ships] [--force]

Reads `INCLUDE/Ships/d_*D.a80` (geometry) and `d_*H.a80` (headers) from
`orig/legend/EliteLegend_v1_09_source`, and `AdrDataShips` in
`INCLUDE/SlotObj.a80` for the object numbering, and writes one blueprint
per HEADER in the format `tools/shiplib.py` reads (see
`src/res/legend/ships/README.md`), plus the Legend header fields that the
1985 format has no place for, and a `class` line - the port's own spawn
tier, worked out from the type byte by `shiplib.legend_tier` so the 1985
spawner can draw from the new roster.  A header that shares a hull with an earlier
one borrows it with `geometry`, the way the 1985 blueprints do for the
two Cobras.

The geometry is Elite's own format - vertex 6 bytes (x, y, z,
signs+distance, two face-pair bytes), edge 4 (distance, v1, v2, faces),
normal 4 (x, y, z, signs+distance) - decoded exactly as
`tools/ships_extract.py` decodes the 1985 disk's.  The header is 24
bytes: cargo, collide, laser, nv, ne, nn, speed, energy, bounty (word),
launch, dot, three offsets (words), flags, flags2, laser vertex, rating
(word), type, objflags, shipnum.

Every number comes out of the source text; nothing is assembled.  `make
verify` checks the resources back against the sources.
"""

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import shiplib                                     # noqa: E402
SRC = ROOT / "orig/legend/EliteLegend_v1_09_source/INCLUDE"
OUT = ROOT / "src/res/legend/ships"

# the Legend-only header fields, in header order after the 1985 ones
EXTRA = ["flags2", "laservert", "type", "objflags", "shipnum"]


def read_source(path):
    """A Legend source file as a list of lines, CP866 decoded, with the
    /* ... */ blocks removed and ; comments stripped."""
    text = path.read_bytes().decode("cp866", errors="replace")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    lines = []
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].rstrip()
        lines.append(line)
    return lines


def number(tok):
    """sjasmplus numbers and the small integer expressions the data uses:
    #hex, %binary, $hex, decimal, with + - * / and brackets (/ is integer
    division there)."""
    t = tok.strip()
    t = re.sub(r"[#$]([0-9A-Fa-f]+)", lambda m: str(int(m.group(1), 16)), t)
    t = re.sub(r"%([01]+)", lambda m: str(int(m.group(1), 2)), t)
    if not re.fullmatch(r"[0-9+\-*/() ]+", t):
        raise ValueError(f"not a number: {tok!r}")
    return int(eval(t.replace("/", "//"), {"__builtins__": {}}, {}))


def split_args(s):
    return [a.strip() for a in s.split(",") if a.strip()]


def parse_data_file(path):
    """d_XxxD.a80 -> {label: {'V': [...], 'E': [...], 'N': [...]}}
    keyed by the hull name (label without its trailing V/E/N)."""
    hulls = {}
    cur = None
    for line in read_source(path):
        if not line:
            continue
        m = re.match(r"^(d_\w+[VEN])\s+equ\s+(d_\w+[VEN])\s*$", line, re.I)
        if m:
            # a section borrowed from another hull: `d_AsteroidBigE equ
            # d_AsteroidE`.  Resolved once every file is read.
            hull, part = m.group(1)[:-1], m.group(1)[-1]
            hulls.setdefault(hull, {"V": [], "E": [], "N": []})
            hulls[hull][part] = ("alias", m.group(2)[:-1], m.group(2)[-1])
            cur = None
            continue
        m = re.match(r"^(\S+)\s*$", line)
        if m and not line.startswith((" ", "\t")):
            label = m.group(1)
            if re.fullmatch(r"d_\w+[VEN]", label):
                cur = (label[:-1], label[-1])
                hulls.setdefault(cur[0], {"V": [], "E": [], "N": []})
            else:
                cur = None
            continue
        m = re.match(r"^\s*(db|DB|defb)\s+(.*)$", line)
        if m and cur:
            vals = [number(t) for t in split_args(m.group(2))]
            hulls[cur[0]][cur[1]].append(vals)
    return hulls


def parse_header_file(path):
    """d_XxxH.a80 -> [(label, [values...], hull_label)] in file order."""
    headers = []
    label = None
    vals = []
    hull = None

    def flush():
        if label and vals:
            headers.append((label, list(vals), hull))

    for line in read_source(path):
        if not line:
            continue
        m = re.match(r"^(d_\w+)\s*$", line)
        if m and not line.startswith((" ", "\t")):
            flush()
            label, vals, hull = m.group(1), [], None
            continue
        m = re.match(r"^\s*(db|dw)\s+(.*)$", line, re.I)
        if m and label is not None:
            kind = m.group(1).lower()
            for tok in split_args(m.group(2)):
                mm = re.fullmatch(r"(d_\w+)[VEN]-(d_\w+)", tok)
                if mm:
                    hull = mm.group(1)
                    vals.append(("off", mm.group(1)))
                    continue
                v = number(tok)
                vals.append(("w" if kind == "dw" else "b", v))
    flush()
    return headers


def decode_geometry(g):
    verts = []
    for v in g["V"]:
        x, y, z, s = v[0], v[1], v[2], v[3]
        verts.append((-x if s & 0x80 else x,
                      -y if s & 0x40 else y,
                      -z if s & 0x20 else z))
    edges = []
    for e in g["E"]:
        faces = e[3]
        edges.append((e[1], e[2], e[0] & 0x1F, faces & 0x0F, faces >> 4))
    normals = []
    for n in g["N"]:
        x, y, z, sn = n[0], n[1], n[2], n[3]
        normals.append((-x if sn & 0x80 else x,
                        -y if sn & 0x40 else y,
                        -z if sn & 0x20 else z))
    return verts, edges, normals


def decode_header(vals):
    """The 24 bytes in order; words are ('w', v), offsets ('off', hull)."""
    flat = []
    for kind, v in vals:
        flat.append((kind, v))
    fields = ["cargo", "collide", "laser", "nv", "ne", "nn", "speed", "energy",
              "bounty", "launch", "dot", "voff", "eoff", "noff", "flags",
              "flags2", "laservert", "rating", "type", "objflags", "shipnum"]
    h = {}
    for name, (kind, v) in zip(fields, flat):
        h[name] = v
    return h


def object_order():
    """AdrDataShips in SlotObj.a80: header label -> object number."""
    order = {}
    lines = read_source(SRC / "SlotObj.a80")
    on = False
    n = 0
    for line in lines:
        if line.strip() == "AdrDataShips":
            on = True
            continue
        if on:
            m = re.match(r"^\s*dw\s+(d_\w+)", line)
            if m:
                order.setdefault(m.group(1), n)
                n += 1
            elif line.strip() and not line.startswith((" ", "\t")):
                break
    return order


def key_of(label):
    return re.sub(r"^d_", "", label).lower()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists() and any(out.glob("*.txt")) and not args.force:
        sys.exit(f"error: {out} has blueprints (use --force)")
    out.mkdir(parents=True, exist_ok=True)

    ships_dir = SRC / "Ships"
    hulls = {}
    for p in sorted(ships_dir.glob("d_*D.a80")):
        hulls.update(parse_data_file(p))
    for hull in hulls.values():                  # resolve the borrowed sections
        for part in "VEN":
            seen = set()
            while isinstance(hull[part], tuple):
                _, other, opart = hull[part]
                if (other, opart) in seen or other not in hulls:
                    sys.exit(f"error: unresolvable alias to {other}{opart}")
                seen.add((other, opart))
                hull[part] = hulls[other][opart]
    headers = []
    for p in sorted(ships_dir.glob("d_*H.a80")):
        headers.extend(parse_header_file(p))
    order = object_order()

    # object numbers: the AdrDataShips ones first, then the rest after
    numbered = sorted((n, lab) for lab, n in order.items())
    known = {lab for _, lab in numbered}
    rest = [lab for lab, _, _ in headers if lab not in known]
    index = {lab: n for n, lab in numbered}
    for i, lab in enumerate(rest):
        index[lab] = len(numbered) + i

    by_label = {lab: (vals, hull) for lab, vals, hull in headers}
    missing = [lab for lab in order if lab not in by_label]
    if missing:
        sys.exit(f"error: AdrDataShips names headers not in any H file: {missing}")

    hull_owner = {}
    written = 0
    for lab in sorted(index, key=lambda l: index[l]):
        vals, hull = by_label[lab]
        h = decode_header(vals)
        if hull is None:
            # a header with no geometry offsets (should not happen)
            sys.exit(f"error: {lab} names no hull")
        if hull not in hulls:
            sys.exit(f"error: {lab} wants hull {hull}, which no D file has")
        g = hulls[hull]
        verts, edges, normals = decode_geometry(g)
        note = ""
        if h["nv"] != len(verts) or h["ne"] != len(edges) or h["nn"] != len(normals):
            # Legend's header counts are what ITS engine iterates; where
            # they disagree with the data (the Adder names 15 normals and
            # has 13) the port draws the data and keeps the note
            note = (f"# NOTE: the header counts {h['nv']}v {h['ne']}e {h['nn']}n, "
                    f"the hull has {len(verts)}v {len(edges)}e {len(normals)}n.")
            print(f"note: {lab}: {note[2:]}", file=sys.stderr)
        key = key_of(lab)
        lines = [f"# {lab} - extracted from orig/legend by tools/legend_ships.py;",
                 f"# object {index[lab]} of AdrDataShips, hull {hull}.",
                 "# `make extract` overwrites it."] + ([note] if note else []) + [
                 f"name {key.upper()}",
                 f"index {index[lab]}",
                 # the port's own spawn tier, derived - see shiplib.legend_tier
                 f"class {shiplib.legend_tier(key, h['type'], h['objflags'], h['energy'])}",
                 f"speed {h['speed']}", f"energy {h['energy']}",
                 f"bounty {h['bounty']}", f"laser {h['laser']}",
                 f"collide {h['collide']}", f"cargo {h['cargo']}",
                 f"launch {h['launch']}", f"dot {h['dot']}",
                 f"rating {h['rating']}", f"flags {h['flags']}"]
        for name in EXTRA:
            lines.append(f"{name} {h.get(name, 0)}")
        if hull in hull_owner:
            lines.append(f"geometry {hull_owner[hull]}")
        else:
            hull_owner[hull] = key.upper()
            radius = max((abs(c) for v in verts for c in v), default=1)
            lines.append(f"radius {radius}")
            for x, y, z in verts:
                lines.append(f"vertex {x:5d} {y:5d} {z:5d}")
            for a, b, cull, f1, f2 in edges:
                lines.append(f"edge {a} {b} {cull} {f1} {f2}")
            for x, y, z in normals:
                lines.append(f"normal {x:4d} {y:4d} {z:4d}")
        (out / f"{key}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
    print(f"{written} blueprints ({len(hull_owner)} hulls, "
          f"{len(numbered)} numbered objects) -> {out}")


if __name__ == "__main__":
    main()
