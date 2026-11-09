#!/usr/bin/env python3
"""seg_snapshot.py - the exact segments a frozen scene draws, for A/B proofs.

Boots build/elite.dsk, launches, and freezes a scene: a clean sky, the
commander still, and a few hulls poked at seeded random positions and
orientations - some of them over the edges of the view, so the clipper
runs - each with a still mind and no speed, every spare slot a filler
(a drop beyond sixteen bits, as `bench.py --fixed` makes them).  Nothing
then moves, so every frame draws the same segments; the frame on the
screen (SEGOLD, SEGOCNT) is dumped twice, some ticks apart, and the two
must agree or the scene was not frozen.

The output is the list of walk records (src/gfx.mac, three words each)
that start in the space view - the scanner shares the buffer and its
blips blink - one line per segment, per scene.  Two builds that draw the same pixels
write the same file, so a change to the hull pipeline that claims to
change nothing is proved by running this against both and comparing:

    python3 tools/seg_snapshot.py --scenes 12 --out tmp/seg-new.txt
    (in a worktree of the old build)  ... --out tmp/seg-old.txt
    python3 tools/seg_snapshot.py --compare tmp/seg-old.txt tmp/seg-new.txt

A scene where anything moved - a hull nudged aside by another, a still
mind that still turns - is written as skipped, and which scenes those
are depends on how many frames a build fits into the run; so the
comparison is of the scenes frozen in BOTH files.

A station is never used as a station: a slot with a bay spins
(UNIV_STEP), which is motion; its hull is poked as an ordinary ship.
"""

import argparse
import math
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import syms                                        # noqa: E402
import verify_build as vb                          # noqa: E402

Q1 = 16384


def rotation(rng):
    """A random orthonormal matrix, row-major, rounded to Q14."""
    a, b, c = (rng.uniform(-math.pi, math.pi) for _ in range(3))
    ca, sa, cb, sb, cc, sc = (math.cos(a), math.sin(a), math.cos(b),
                              math.sin(b), math.cos(c), math.sin(c))
    m = [ca * cb, ca * sb * sc - sa * cc, ca * sb * cc + sa * sc,
         sa * cb, sa * sb * sc + ca * cc, sa * sb * cc - ca * sc,
         -sb, cb * sc, cb * cc]
    return [round(v * Q1) for v in m]


def scene_script(t, rng, loaded, radius, nships):
    univ, usize, nuniv = (int(t[k], 8) for k in ("UNIV", "U.SIZE", "NUNIV"))

    def field(slot, name, val):
        return vb.poke_at(univ + slot * usize + int(t[name], 8), val)

    out = [vb.poke_at(int(t["PSPEED"], 8), 0), vb.poke_at(int(t["PROLL"], 8), 0),
           vb.poke_at(int(t["PPITCH"], 8), 0)]
    if "STAR_ON" in t:
        out.append(vb.poke_at(int(t["STAR_ON"], 8), 0))
    for slot in range(nuniv):
        out.append(field(slot, "U.TYPE", 0))
    vb.ship_stats("VIPERH")
    placed = []                        # (x, y, z, radius)
    poked = []                         # what each slot must still read
    for slot in range(nships):
        # far enough from the commander and from each other that nothing
        # collides or gives way (CO_SHEER acts inside four hull radii):
        # either would move a hull, and the scene must stand still
        while True:
            ty = rng.choice(loaded)
            r = radius[ty]
            z = rng.randint(max(600, 5 * r), 7000)
            # most of them in view, some across its edges
            x = rng.randint(-z // 2, z // 2) if rng.random() < 0.7 else rng.choice((-1, 1)) * rng.randint(z // 3, z)
            y = rng.randint(-z // 4, z // 4) if rng.random() < 0.7 else rng.choice((-1, 1)) * rng.randint(z // 5, z // 2)
            if all(math.dist((x, y, z), (px, py, pz)) > 5 * (r + pr) for px, py, pz, pr in placed):
                break
        placed.append((x, y, z, r))
        poked.append(None)
        out += [field(slot, "U.TYPE", ty), field(slot, "U.X", x), field(slot, "U.Y", y),
                field(slot, "U.Z", z), field(slot, "U.XH", -1 if x < 0 else 0),
                field(slot, "U.YH", -1 if y < 0 else 0), field(slot, "U.ZH", 0),
                field(slot, "U.FLAGS", 0), field(slot, "U.EXPL", 0), field(slot, "U.SPEED", 0),
                field(slot, "U.TARGET", 0), field(slot, "U.LAUNCH", 0),
                field(slot, "U.ENERGY", 4000), field(slot, "U.BR", 0)]
        mat = rotation(rng)
        for k, v in enumerate(mat):
            out.append(vb.poke_at(univ + slot * usize + int(t["U.MAT"], 8) + 2 * k, v))
        poked[-1] = [ty, x & 0xFFFF, y & 0xFFFF, z, 0] + [m & 0xFFFF for m in mat]
        out += vb.ai_pokes(t, slot, vb._SHIP_KEYS[ty - 1], hyper=False, still=True)
    filler = vb._SHIP_KEYS[int(t["SH_CANISTER"], 8) - 1]
    for slot in range(nships, nuniv):
        out += [field(slot, "U.TYPE", int(t["SH_CANISTER"], 8)), field(slot, "U.X", 0),
                field(slot, "U.Y", 0), field(slot, "U.Z", 0), field(slot, "U.ZH", -2),
                field(slot, "U.FLAGS", int(t["UF_DROP"], 8) | int(t["UF_DERELICT"], 8)),
                field(slot, "U.EXPL", 0), field(slot, "U.SPEED", 0),
                field(slot, "U.TARGET", 0), field(slot, "U.LAUNCH", 0)]
        out += vb.ai_pokes(t, slot, filler, hyper=False, still=True)
    return out, poked


def read_scenes(path):
    """{scene: [record lines]} for every frozen scene in a file."""
    import re
    out, cur = {}, None
    for line in Path(path).read_text().splitlines():
        m = re.match(r"scene (\d+): (\d+) segments", line)
        if m:
            cur = int(m.group(1))
            out[cur] = []
        elif line.startswith(("scene", "#")):
            cur = None
        elif cur is not None:
            out[cur].append(line)
    return out


def compare(old, new):
    a, b = read_scenes(old), read_scenes(new)
    both = sorted(set(a) & set(b))
    differ = [k for k in both if a[k] != b[k]]
    n = sum(len(a[k]) for k in both)
    print(f"{len(both)} scenes frozen in both, {n} segments: "
          + (f"DIFFER in scenes {differ}" if differ else "identical"))
    return 1 if differ or not both else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--compare", nargs=2, metavar=("OLD", "NEW"),
                    help="compare two files this wrote, and nothing else")
    ap.add_argument("--scenes", type=int, default=8)
    ap.add_argument("--ships", type=int, default=5, help="hulls a scene")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    if args.compare:
        return compare(*args.compare)
    if not args.out:
        ap.error("--out is needed to take a snapshot")
    syms.check_fresh()
    t = syms.table()
    reclen = int(t["SEGREC"], 8) if "SEGREC" in t else 6
    maxseg = int(t["MAXSEG"], 8)
    view_end = int(t["VRAM"], 8) + int(t["VIEW_H"], 8) * int(t["SCRWB"], 8)
    tmp = ROOT / "tmp"
    tmp.mkdir(exist_ok=True)

    # which hulls this system has loaded (SHIP_TABLE is filled per system)
    table = tmp / "segsnap-table.bin"
    nships = int(t["NSHIPS"], 8)
    vb.run_emu(list(vb.BOOT) + ["press 107", "run 40",
                                f"dumpcpu {t['SHIP_TABLE']} {2 * nships} {table}", "quit"],
               vb.fresh_disk("segsnap"))
    words = struct.unpack(f"<{nships}H", table.read_bytes()[:2 * nships])
    # a canister is the filler; the rest are the scene's candidates
    loaded = [i + 1 for i, w in enumerate(words) if w and i + 1 != int(t["SH_CANISTER"], 8)]
    import shiplib
    ships = shiplib.read_dir(ROOT / "src/res/legend/ships")
    radius = {ty: shiplib.hull_of(ships[ty - 1], ships).radius for ty in loaded}

    rng = random.Random(args.seed)
    lines = [f"# seg_snapshot seed {args.seed}, {args.scenes} scenes of {args.ships}"]
    bad = 0
    for sc in range(args.scenes):
        pokes, poked = scene_script(t, rng, loaded, radius, args.ships)
        script = list(vb.BOOT) + ["press 107", "run 40"] + pokes
        dumps = []
        # every slot has to read what was poked into it, at both dumps: a
        # hull that moved during the warm-up and then stopped would draw
        # a still frame, but not the frame another build draws
        fields = ["U.TYPE", "U.X", "U.Y", "U.Z", "U.SPEED"]
        mat0 = int(t["U.MAT"], 8)
        watch = []
        for s_ in range(args.ships):
            watch += [f"peekcpu {vb.slot_field(t, s_, f)}" for f in fields]
            base = int(vb.slot_field(t, s_, "U.TYPE"), 8)
            watch += [f"peekcpu {base + mat0 + 2 * k:o}" for k in range(9)]
        for k in range(2):
            script += ["run 60", f"peekcpu {t['SEGOLD']}", f"peekcpu {t['SEGOCNT']}"] + watch
            for name in ("SEGBUF", "SEGBUFB"):
                f = tmp / f"segsnap-{k}-{name}.bin"
                dumps.append(f)
                script.append(f"dumpcpu {t[name]} {reclen * maxseg} {f}")
        script.append("quit")
        v = [int(x, 8) for x in vb.PEEK.findall(vb.run_emu(script, vb.fresh_disk("segsnap")))]
        frames = []
        per = len(fields) + 9
        nw = per * args.ships
        slots = [v[2:2 + nw], v[4 + nw:4 + 2 * nw]]
        v = [v[0], v[1], v[2 + nw], v[3 + nw]]
        moved = [(i, slots[k][per * i:per * i + per], poked[i]) for k in range(2)
                 for i in range(args.ships) if slots[k][per * i:per * i + per] != poked[i]]
        for k in range(2):
            old, cnt = v[2 * k], v[2 * k + 1]
            buf = dumps[2 * k] if old == int(t["SEGBUF"], 8) else dumps[2 * k + 1]
            d = buf.read_bytes()[:reclen * cnt]
            # the space view only: the scanner and the compass share the
            # buffer, and a blip blinks, which is not the hulls moving
            frames.append([r for r in (struct.unpack_from("<3H", d, reclen * i) for i in range(cnt))
                           if r[2] < view_end])
        if frames[0] != frames[1] or moved:
            bad += 1
            print(f"scene {sc}: NOT frozen ({len(frames[0])} then {len(frames[1])} segments)")
            for i, now, was in moved[:4]:     # type, x, y, z, speed, the matrix
                print(f"   slot {i}: poked {[f'{w:o}' for w in was]}, reads {[f'{w:o}' for w in now]}")
            a_, b_ = frames
            for i in range(max(len(a_), len(b_))):
                ra = a_[i] if i < len(a_) else None
                rb = b_[i] if i < len(b_) else None
                if ra != rb:
                    print(f"   {i}: {ra} -> {rb}")
            # (a hull a still mind still turns - the AI's business, which
            # a renderer change does not touch: the scene is skipped, and
            # it is skipped in the other build's file too)
            lines.append(f"scene {sc}: not frozen, skipped")
            continue
        lines.append(f"scene {sc}: {len(frames[1])} segments")
        lines += [" ".join(f"{w:06o}" for w in rec) for rec in frames[1]]
        print(f"scene {sc}: {len(frames[1])} segments")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}: {args.scenes - bad} scenes compared"
          + (f", {bad} skipped as not frozen" if bad else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
