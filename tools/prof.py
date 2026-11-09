#!/usr/bin/env python3
"""prof.py - rough CPU profile of the running game, by PC sampling.

Boots build/elite.dsk in the headless emulator, lets it settle, then
alternates "run" and "regs" so every sample is the CPU program counter
at one point in time, and reports which routine each sample fell in.
Labels come from build/elite.lst, so `make build` has to have run.

    python3 tools/prof.py [--samples N] [--warmup F] [--step F]

A sample is a slice of wall clock, not an instruction count, so the
percentages say where the time goes, which is the question worth
asking on a machine this size.
"""

import argparse
import re
import subprocess
import sys
from bisect import bisect_right
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LST = ROOT / "build/elite.lst"
DSK = ROOT / "build/elite.dsk"
EMU = ROOT / "bin/ukncbtl/uknc-headless"
ROM = ROOT / "bin/ukncbtl/uknc_rom.bin"

SYM_RE = re.compile(
    r"^\s*\d+\s+([0-7]{6})\s+(?:[0-7]{3,6}'?\s+){0,4}([A-Z][A-Z_0-9.$]*):")
PC_RE = re.compile(r"CPU PC=([0-7]{6})")


def load_symbols():
    syms = []
    for line in LST.read_text(errors="replace").splitlines():
        m = SYM_RE.match(line)
        if m:
            addr = int(m.group(1), 8)
            name = m.group(2)
            if not name.endswith("$"):
                syms.append((addr, name))
    syms.sort()
    # keep the first label at each address
    out, seen = [], set()
    for a, n in syms:
        if a not in seen:
            seen.add(a)
            out.append((a, n))
    return out


def name_of(syms, addrs, pc):
    i = bisect_right(addrs, pc) - 1
    if i < 0:
        return f"<{pc:06o}>"
    return syms[i][1]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--samples", type=int, default=300)
    ap.add_argument("--warmup", type=int, default=340)
    ap.add_argument("--step", type=int, default=1)
    args = ap.parse_args(argv)
    if not LST.exists() or not DSK.exists():
        sys.exit("error: run `make build` first")

    # The boot sequence is verify_build's, imported rather than copied:
    # the two of them drifted apart the moment the title screen and the
    # commander chooser went in, and a profile taken from the docking bay
    # is a hundred per cent VSYNC and says nothing at all.  One more ФИКС
    # after it launches the ship.
    sys.path.insert(0, str(ROOT / "tools"))
    from verify_build import BOOT
    script = list(BOOT) + ["press 107", "run 90"]
    for _ in range(args.samples):
        script += [f"run {args.step}", "regs"]
    script.append("quit")

    r = subprocess.run([str(EMU), "--rom", str(ROM), "--disk", str(DSK)],
                       input="\n".join(script) + "\n",
                       capture_output=True, text=True, timeout=900)
    pcs = [int(m, 8) for m in PC_RE.findall(r.stdout)]
    if not pcs:
        sys.exit("error: no samples (emulator output:\n" + r.stdout[-2000:] + ")")

    syms = load_symbols()
    addrs = [a for a, _ in syms]
    counts = Counter(name_of(syms, addrs, pc) for pc in pcs)
    total = len(pcs)
    print(f"{total} samples")
    for name, n in counts.most_common(20):
        print(f"  {100.0 * n / total:5.1f}%  {n:5d}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
