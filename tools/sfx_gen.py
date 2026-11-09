#!/usr/bin/env python3
"""sfx_gen.py - Legend's AY sound effects: extract them to text, and
compile the text into the effects engine's table.

    python3 tools/sfx_gen.py --extract [--out FILE] [--force]
        orig/legend's LibSFX effects -> src/res/legend/sfx.txt
    python3 tools/sfx_gen.py src/res/legend/sfx.txt --out build/sfx.mac
        the text -> the table src/ppu_sfx.mac plays (the build runs this)
    python3 tools/sfx_gen.py --check
        the text compiles back to the original files byte for byte

Legend's library (Library/LibSFX/!LibSFX.sfx.Elite.a80) lists 29
effects over 26 files, .cse and .sfx alike: a word, the loop point's
offset from byte 2, then one record a frame - a flag byte and what it
says follows:

    bit 0   a noise period byte follows
    bit 1   a tone period word follows, HIGH byte first
    bit 2   go back to the loop point after this frame
    bit 3   the effect ends after this frame
    bits 4-7 the volume

The text says the same a frame a line: `v=N` the volume, `t=HHHH` the
tone period, `n=HH` the noise period, `loop` and `end`; an effect is an
`effect NAME FILE` line, `loopat N` (the loop offset, in bytes) and its
frames, and `table` lists the 29 in the order the game numbers them.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "orig/legend/EliteLegend_v1_09_source/Library/LibSFX"
TXT = ROOT / "src/res/legend/sfx.txt"

# !LibSFX.sfx.Elite.a80: the table, then which file each name is
TABLE = ["KeyPressed", "PressOption", "PilotLaser0", "PilotLaser0",
         "PilotLaser2", "PilotLaser2", "PilotLaser5", "PilotLaser5",
         "PilotLaser6", "PilotLaser7", "PilotLaserHit", "EnemyLaserHit",
         "LaunchMissile", "ECMsystem", "SFXoff", "E_Bomb", "GameOver",
         "CaptureDron", "AlienDrone", "PressPause", "CaptureCargo",
         "Refueled", "LaunchDescent", "JumpGate", "Docking", "Launch",
         "HyperJump", "Collision", "DestroyObj"]
FILES = {
    "KeyPressed": "TauCeti/KeyPressed.cse",
    "PressOption": "TauCeti/PressOption.cse",
    "PilotLaser0": "MSX/MSX2_08.sfx", "PilotLaser2": "MSX/MSX2_09.sfx",
    "PilotLaser5": "sfxElite/LaserMilitary.cse",
    "PilotLaser6": "sfxElite/LaserTargon.cse",
    "PilotLaser7": "MSX/MSX8_27.sfx",
    "PilotLaserHit": "sfxElite/PilotLaserHit2.cse",
    "EnemyLaserHit": "sfxElite/EnemyLaserHit2.cse",
    "LaunchMissile": "MSX/MSX2_17.sfx",
    "ECMsystem": "sfxElite/ECMsystem.cse", "SFXoff": "sfxElite/SfxOff.cse",
    "E_Bomb": "sfxElite/E_Bomb2.cse", "GameOver": "MSX/MSX1_16.sfx",
    "CaptureDron": "sfxElite/CaptureDron.cse", "AlienDrone": "MSX/MSXa_12.sfx",
    "PressPause": "sfxElite/PressPause.cse",
    "CaptureCargo": "sfxElite/CaptureCargo2.cse",
    "Refueled": "sfxElite/Refueled.cse",
    "LaunchDescent": "sfxElite/LaunchDescent.cse",
    "JumpGate": "sfxElite/JumpGate.cse", "Docking": "sfxElite/Docking5.cse",
    "Launch": "sfxElite/Launch2.cse", "HyperJump": "sfxElite/HyperJump.cse",
    "Collision": "MSX/MSX2_23.sfx", "DestroyObj": "sfxElite/DestroyObj.cse",
}


def decode(b):
    """A file's bytes -> (loop offset, [frame dicts]), or an error."""
    loop = b[0] | b[1] << 8
    i, frames = 2, []
    while i < len(b):
        c = b[i]
        f = {"v": c >> 4, "loop": bool(c & 4), "end": bool(c & 8)}
        i += 1
        if c & 1:
            f["n"] = b[i]
            i += 1
        if c & 2:
            f["t"] = b[i] << 8 | b[i + 1]
            i += 2
        frames.append(f)
    if i != len(b):
        sys.exit("error: an effect runs past its file")
    return loop, frames


def encode(loop, frames):
    out = bytearray([loop & 255, loop >> 8])
    for f in frames:
        c = f["v"] << 4 | (1 if "n" in f else 0) | (2 if "t" in f else 0) \
            | (4 if f["loop"] else 0) | (8 if f["end"] else 0)
        out.append(c)
        if "n" in f:
            out.append(f["n"])
        if "t" in f:
            out += bytes([f["t"] >> 8, f["t"] & 255])
    return bytes(out)


def frame_text(f):
    s = [f"v={f['v']}"]
    if "t" in f:
        s.append(f"t={f['t']:04X}")
    if "n" in f:
        s.append(f"n={f['n']:02X}")
    if f["loop"]:
        s.append("loop")
    if f["end"]:
        s.append("end")
    return " ".join(s)


def extract():
    lines = ["# Elite Legend's AY sound effects, from orig/legend's LibSFX by",
             "# tools/sfx_gen.py --extract.  A frame a line: v= the volume, t= the",
             "# tone period (hex), n= the noise period (hex), `loop` back to the",
             "# loop point after it, `end` after it.  src/ppu_sfx.mac plays them",
             "# on the first AY chip; the game numbers them by the table.",
             "", "table " + " ".join(TABLE), ""]
    for name, f in FILES.items():
        loop, frames = decode((LIB / f).read_bytes())
        lines += [f"effect {name} {f}", f"loopat {loop}"]
        lines += [frame_text(fr) for fr in frames]
        lines.append("")
    return "\n".join(lines)


def parse(path):
    """-> (table, {name: (file, loop, frames)}), in the file's order."""
    table, effects, cur = None, {}, None
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].split()
        if not line:
            continue
        where = f"{path}:{n}"
        if line[0] == "table":
            table = line[1:]
        elif line[0] == "effect":
            cur = line[1]
            effects[cur] = [line[2] if len(line) > 2 else "", 0, []]
        elif line[0] == "loopat":
            effects[cur][1] = int(line[1])
        else:
            if cur is None:
                sys.exit(f"error: {where}: a frame before any effect")
            f = {"loop": False, "end": False}
            for tok in line:
                if tok in ("loop", "end"):
                    f[tok] = True
                elif tok[:2] == "v=":
                    f["v"] = int(tok[2:])
                elif tok[:2] == "t=":
                    f["t"] = int(tok[2:], 16)
                elif tok[:2] == "n=":
                    f["n"] = int(tok[2:], 16)
                else:
                    sys.exit(f"error: {where}: what is {tok!r}?")
            if not 0 <= f.get("v", -1) <= 15:
                sys.exit(f"error: {where}: every frame needs v=0..15")
            effects[cur][2].append(f)
    if not table:
        sys.exit(f"error: {path}: no table line")
    for t in table:
        if t not in effects:
            sys.exit(f"error: {path}: the table names {t}, which is not here")
    return table, effects


def macro(table, effects, src):
    lines = [f"; Legend's AY effects, from {src} by tools/sfx_gen.py -",
             "; generated, do not edit.  SX_TAB is each effect's offset from",
             "; SX_TAB (position-independent: the engine runs wherever the",
             "; PPU keeps it); an effect is its loop offset word, as bytes,",
             "; then its frames (tools/sfx_gen.py has the format).",
             f"SX_NEFF = {len(table)}.",
             "SX_TAB:"]
    for t in table:
        lines.append(f"\t\t.WORD\tSE.{t}-SX_TAB")
    for name, (f, loop, frames) in effects.items():
        b = encode(loop, frames)
        lines.append(f"SE.{name}:\t\t\t\t; {f}")
        for i in range(0, len(b), 12):
            lines.append("\t\t.BYTE\t" + ",".join(f"{x:o}" for x in b[i:i + 12]))
    lines.append("\t\t.EVEN")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("src", nargs="?", default=str(TXT))
    ap.add_argument("--out")
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.extract:
        out = Path(a.out) if a.out else TXT
        if out.exists() and not a.force:
            sys.exit(f"error: {out} exists (use --force)")
        out.write_text(extract(), encoding="utf-8")
        print(f"wrote {out}")
        return 0
    table, effects = parse(a.src)
    if a.check:
        bad = [n for n, (f, loop, fr) in effects.items()
               if encode(loop, fr) != (LIB / f).read_bytes()]
        if bad or table != TABLE:
            print("differ: " + ", ".join(bad or ["the table"]))
            return 1
        print(f"{len(effects)} effects, {sum(len(encode(l, fr)) for _, l, fr in effects.values())} "
              "bytes: all as Legend has them")
        return 0
    if a.out:
        out = Path(a.out)
        if out.exists() and not a.force:
            sys.exit(f"error: {out} exists (use --force)")
        out.write_text(macro(table, effects, a.src))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
