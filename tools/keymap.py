#!/usr/bin/env python3
"""keymap.py - sweep the УКНЦ keyboard and report what each key sends.

The PPU publishes the raw byte the keyboard delivered into PP_LASTKEY
(see src/ppu.mac).  This holds every scancode in turn, reads back the
make code and then the release code, and prints the pairs - which is how
this port's key table was worked out instead of guessed.

    python3 tools/keymap.py [--from 0] [--to 0177]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import syms                                        # noqa: E402

EMU = ROOT / "bin/ukncbtl/uknc-headless"
ROM = ROOT / "bin/ukncbtl/uknc_rom.bin"
DSK = ROOT / "build/elite.dsk"
PEEK = re.compile(r"peekcpu \d+ = ([0-7]+)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--from", dest="lo", default="0")
    ap.add_argument("--to", dest="hi", default="0177")
    args = ap.parse_args(argv)
    lo, hi = int(args.lo, 8), int(args.hi, 8)

    table = syms.table()
    addr = table.get("PP_LASTKEY")
    if not addr:
        sys.exit("error: PP_LASTKEY not in build/elite.lst - run make build")

    script = ["run 900", "press 030", "run 30", "press 153", "run 400"]
    codes = list(range(lo, hi + 1))
    for c in codes:
        script += [f"keydown {c:o}", "run 2", f"peekcpu {addr}",
                   f"keyup {c:o}", "run 2", f"peekcpu {addr}"]
    script.append("quit")

    r = subprocess.run([str(EMU), "--rom", str(ROM), "--disk", str(DSK)],
                       input="\n".join(script) + "\n",
                       capture_output=True, text=True, timeout=1800)
    vals = [int(v, 8) for v in PEEK.findall(r.stdout)]
    print(f"{'code':>6} {'make':>6} {'release':>8}")
    seen = 0
    for i, c in enumerate(codes):
        if 2 * i + 1 >= len(vals):
            break
        make, rel = vals[2 * i], vals[2 * i + 1]
        if make == 0 and rel == 0:
            continue
        seen += 1
        print(f"{c:6o} {make:6o} {rel:8o}")
    print(f"{seen} codes produced something")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
