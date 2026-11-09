#!/usr/bin/env python3
"""legend_build.py - build Elite Legend from its sources, for the reference machine.

    python3 tools/legend_build.py [--run] [--shot OUT.png]

Copies `orig/legend/EliteLegend_v1_09_source` to `tmp/legend-build`
(the author's build writes `!bin` and `!log` into the tree, and `orig/`
stays pristine) and runs the author's own sjasmplus 1.07 there under
wine - the 2008 build the sources were written for; a current sjasmplus
is not the same assembler.  The assembly writes `!bin/eliterus.sna`, a
128K snapshot that boots straight into the game, which is what the
reference machine needs; the packed `.trd` (mhmt, trdtool, the Lua
merges) is not made, because nothing the port checks against needs
TR-DOS.

`--run` launches the snapshot in ZEsarUX through `tools/zx_control.py`
(machine Pentagon, headless, remote protocol on port 10000), and
`--shot` takes a screenshot after it has settled.  Drive it further
with `zx_control.py press ...`; the manual's key list is in
`docs/reference-sources.md`.

Legend's numbers are checked against this snapshot the way the 1985
port's were checked against `orig/ELITE.SCL`.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "orig/legend/EliteLegend_v1_09_source"
BUILD = ROOT / "tmp/legend-build"
SNA = BUILD / "!bin/eliterus.sna"


def build():
    if not SRC.exists():
        sys.exit(f"error: {SRC} not found")
    if not shutil.which("wine"):
        sys.exit("error: wine is needed to run the author's sjasmplus.exe")
    BUILD.mkdir(parents=True, exist_ok=True)
    # a fresh copy each time: the sources are the truth, the copy is scratch
    for item in SRC.iterdir():
        dst = BUILD / item.name
        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)
    (BUILD / "!bin").mkdir(exist_ok=True)
    (BUILD / "!log").mkdir(exist_ok=True)
    env = dict(os.environ, WINEDEBUG="-all")
    r = subprocess.run(["wine", "sjasmplus.exe", "--exp=!log/LabelGame.a80",
                        "--lst=!log/log.txt", "Elite.a80"],
                       cwd=BUILD, env=env, capture_output=True, text=True,
                       errors="replace", timeout=600)
    tail = "\n".join(r.stdout.splitlines()[-3:])
    if r.returncode != 0 or "Errors: 0" not in r.stdout:
        sys.exit(f"error: assembly failed\n{r.stdout[-2000:]}")
    if not SNA.exists():
        sys.exit("error: assembled, but no snapshot was written")
    print(tail)
    print(f"wrote {SNA} ({SNA.stat().st_size} bytes)")
    for f in sorted((BUILD / "!bin").glob("*.bin")):
        print(f"  {f.name:14s} {f.stat().st_size:6d}")


def run(shot):
    zx = [sys.executable, str(ROOT / "tools/zx_control.py")]
    subprocess.run(zx + ["stop"], capture_output=True)
    r = subprocess.run(zx + ["launch", "--sna", str(SNA), "--machine", "Pentagon"],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        sys.exit(1)
    if shot:
        time.sleep(6)
        bmp = Path(shot).with_suffix(".bmp")
        subprocess.run(zx + ["screenshot", str(bmp)], check=True, capture_output=True)
        from PIL import Image
        Image.open(bmp).save(shot)
        bmp.unlink()
        print(f"wrote {shot}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--run", action="store_true", help="launch the snapshot in ZEsarUX")
    ap.add_argument("--shot", default=None, help="with --run: screenshot PNG after boot")
    ap.add_argument("--no-build", action="store_true", help="use the snapshot already built")
    args = ap.parse_args(argv)
    if not args.no_build:
        build()
    if args.run:
        run(args.shot)


if __name__ == "__main__":
    main()
