#!/usr/bin/env python3
"""bench.py - frames a second, against a scene that does not vary.

Timing a live game is misleading: what is in the sky depends on the
random generator, the generator is stepped by the frame loop, and the
frame loop is what is being measured - so a change that makes the game
faster also changes the sky it is drawing, and the two effects cannot be
told apart.  Worse, the loop waits for vsync, so a one-second sample can
only ever report 50/N frames: 12.5, 10, 8.3, 7.1 and nothing between.

This pokes a FIXED scene into the universe - a world, a station and two
hulls at fixed distances, nothing moving - and counts frames over a long
window.  Two runs of the same build give the same number, and two builds
can be compared.

    python3 tools/bench.py [--ticks 400]

A tick is one emulator SystemFrame. The runner's timing command reports
its core's frame rate: current emubase uses 50 Hz, older builds used 25.
Do not compare tick counts across core revisions without this conversion.
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
Q1 = 16384                     # 1.0 in the Q14 the matrices use

# type, x, y, z - the sky every run draws.  A world, the station a
# little way off, a Cobra Mk III and a Viper: between them a disc with
# its meridians, a big hull with its docking slot, and two ordinary
# ships, which is what an ordinary frame has in it.
SCENE = [
    ("SH_CORIOLIS", 0, 0, 20000, "planet"),
    ("SH_CORIOLIS", -8000, 0, 16000, "sun"),
    ("SH_CORIOLIS", 0, 0, 4000, "station"),
    ("SH_COBRA3", 400, 120, 1800, ""),
    ("SH_VIPER", -500, -80, 1400, ""),
]
FLAGS = {"planet": 8, "sun": 16, "station": 2}      # UF_PLANET/SUN/STATION


def poke(addr, val):
    v = val & 0xFFFF
    return f"pokecpu {addr:o} {v & 0xFF:o} {(v >> 8) & 0xFF:o}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--draw-frames", type=int, default=0,
                    help="time this many rendering-only frames (50 Hz interrupts)")
    ap.add_argument("--no-stars", action="store_true", help="disable stars for an ablation run")
    ap.add_argument("--ticks", type=int, default=400,
                    help="a tick is one emulator SystemFrame; duration is "
                         "reported by the installed runner")
    ap.add_argument("--sparse", action="store_true",
                    help="use only the five scene objects; leave spare slots empty and disable traffic")
    ap.add_argument("--no-bodies", action="store_true",
                    help="leave the world and the sun out of the sky, to "
                         "see what the two of them are worth")
    ap.add_argument("--turning", action="store_true",
                    help="fly AND turn: roll and pitch are held on, which "
                         "makes UNIV_STEP turn every ship's matrix as well "
                         "as its position.  This is the worst case the game "
                         "actually has, and --moving cannot see it - flying "
                         "straight rolls nothing")
    ap.add_argument("--fixed", action="store_true",
                    help="fill every spare slot with a canister far behind "
                         "the commander, so TRAFFIC_STEP has no room to add "
                         "anything and two builds draw the SAME sky.  Use it "
                         "to compare builds: without it a faster build gets "
                         "more frames, rolls more dice, and is measured on a "
                         "different scene")
    ap.add_argument("--peek", action="append", default=[], metavar="SYMBOL",
                    help="also read this word before and after the run "
                         "and print the difference (repeatable).  RING_STALL "
                         "says how often the CPU found the PPU's ring full; "
                         "PPB_BUSY is the ticks the PPU spent drawing, "
                         "against --ticks")
    ap.add_argument("--moving", action="store_true",
                    help="fly at cruising speed instead of holding still: "
                         "the bodies are then redrawn every frame, which is "
                         "the expensive half of the game and the half a "
                         "still scene cannot see.  The scene is put back "
                         "where it started every hundred ticks so the "
                         "commander never arrives at it")
    ap.add_argument("--shot", metavar="PNG",
                    help="also take a screenshot at the end of the run: "
                         "a figure that moves for no reason is often a "
                         "scene that changed, and this shows it")
    args = ap.parse_args(argv)
    if args.sparse:
        args.fixed = True
    syms.check_fresh()
    t = syms.table()
    for name in ("UNIV", "U.SIZE", "NUNIV", "FLY_TICK", "PSPEED",
                 "PROLL", "PPITCH"):
        if name not in t:
            sys.exit(f"error: {name} not in build/elite.lst - run make build")
    univ = int(t["UNIV"], 8)
    usize = int(t["U.SIZE"], 8)
    nuniv = int(t["NUNIV"], 8)

    def field(slot, name, val):
        return poke(univ + slot * usize + int(t[name], 8), val)

    from verify_build import BOOT, fresh_disk
    script = ["timing"] + list(BOOT) + ["press 107", "run 60"]
    for slot in range(nuniv):                       # a clean sky first
        script.append(field(slot, "U.TYPE", 0))
    scene = [row for row in SCENE
             if not (args.no_bodies and row[4] in ("planet", "sun"))]
    for slot, (kind, x, y, z, tag) in enumerate(scene):
        script += [field(slot, "U.TYPE", int(t[kind], 8)),
                   field(slot, "U.X", x), field(slot, "U.Y", y),
                   field(slot, "U.Z", z),
                   field(slot, "U.FLAGS", FLAGS.get(tag, 0)),
                   field(slot, "U.EXPL", 0), field(slot, "U.SPEED", 0),
                   field(slot, "U.TARGET", 0), field(slot, "U.LAUNCH", 0),
                   field(slot, "U.ENERGY", 4000),
                   field(slot, "U.BR", 0)]           # the body buffer forgets
        for k in range(9):                           # an identity orientation
            script.append(poke(univ + slot * usize + int(t["U.MAT"], 8) + 2 * k,
                               Q1 if k in (0, 4, 8) else 0))
        if not tag:
            # and a mind of its own that sits still: a poked slot keeps its
            # last tenant's AI byte, which the random state at arrival
            # decides - and that moves with every disk read the boot makes
            # or saves.  Until 2026-09-25 the Cobra could inherit a mind
            # that flew it off at the 100th tick, and a build that only
            # shifted the random state read 23-46% faster than it was
            import verify_build
            verify_build.ship_stats("VIPERH")
            key = verify_build._SHIP_KEYS[int(t[kind], 8) - 1]
            script += verify_build.ai_pokes(t, slot, key, hyper=False, still=True)
    if args.fixed:
        # TRAFFIC_STEP keeps TR_ROOM slots back and adds nothing when
        # they are all that is left; with none free at all it never adds.
        # A canister is nobody's and has no AI, and BEYOND SIXTEEN BITS
        # behind (U.ZH = -2, poked after the widening below) it is
        # outside U_NEAR, so nothing - not the collision pairs, not the
        # scanner - spends a frame on it: the bench measures the scene
        # and nothing else.  They used to sit at -30000, inside sixteen
        # bits, where every pair test ran on them; that this cost
        # nothing was because BODY_SWEEP's 16-bit subtraction against
        # the world 20000 ahead overflowed and blew every one of them up
        # on the first frame (fixed 2026-09-10).  The figures before
        # then were "the scene alone" by accident; these are on purpose.
        for slot in range(len(scene), nuniv):
            script += [field(slot, "U.TYPE", int(t["SH_CANISTER"], 8)),
                       field(slot, "U.X", 0), field(slot, "U.Y", 0),
                       field(slot, "U.Z", 0),
                       # a drop, as a canister is: past sixteen bits the
                       # AI deletes anything that is not a bay or a drop
                       # (AI_STEP), and with flags of 0 every filler was
                       # gone on the first frame from 2026-09-24 until
                       # 2026-09-26 - the station and the traffic filled
                       # the room by the random state's lights
                       field(slot, "U.FLAGS", int(t["UF_DROP"], 8) | int(t["UF_DERELICT"], 8)),
                       field(slot, "U.EXPL", 0), field(slot, "U.SPEED", 0),
                       field(slot, "U.TARGET", 0), field(slot, "U.LAUNCH", 0),
                       field(slot, "U.ENERGY", 4000),
                       field(slot, "U.BR", 0)]
            for k in range(9):
                script.append(poke(univ + slot * usize + int(t["U.MAT"], 8)
                                   + 2 * k, Q1 if k in (0, 4, 8) else 0))
            # and a mind that keeps it there: a poked slot keeps its last
            # tenant's AI byte, and a filler that inherited a hyperspace
            # exit was gone in eight frames - every one of them, on some
            # boots - and the station launched traders into the room.
            # Which boots depended on the random state at arrival, so a
            # build that only grew the resident a sector read 16% slower
            # standing still (2026-09-26)
            import verify_build
            verify_build.ship_stats("VIPERH")
            key = verify_build._SHIP_KEYS[int(t["SH_CANISTER"], 8) - 1]
            script += verify_build.ai_pokes(t, slot, key, hyper=False, still=True)
            script.append(field(slot, "U.ZH", -2))   # past U_NEAR, after the
                                                      # widening's own high word
    # Nothing in the scene is hostile and nothing carries anything to
    # launch, so no dice are rolled and the run is the same every time,
    # moving or not.
    #
    # A moving run puts the scene back where it started every RESET_EVERY
    # ticks.  Without that the commander simply arrives: at speed 16 he
    # covers the four thousand units to the station in about 250 frames,
    # flies into it and dies, and the frame counter stops - so every
    # window longer than about 1200 ticks reported the same 248 frames
    # whatever the build was doing, and the figure looked like a frame
    # rate while really being the distance to the station divided by the
    # speed.  Between resets the projections move exactly as they do in
    # flight, which is what the moving run is for.
    RESET_EVERY = 100
    moving = args.moving or args.turning
    speed = 16 if moving else 0
    for name in args.peek:
        if name not in t:
            sys.exit(f"error: {name} not in build/elite.lst")
    if args.sparse:
        script += [field(slot, "U.TYPE", 0) for slot in range(len(scene), nuniv)]
        script += [poke(int(t["WITCH"], 8), 1)]  # stop ambient traffic
        # A bay can launch even with no ambient traffic. Keep its hull,
        # spin and collision flags, but give it nobody to run the bay.
        for slot, (_, _, _, _, tag) in enumerate(scene):
            if tag == "station":
                script += [field(slot, "U.FLAGS", FLAGS[tag] | int(t["UF_DERELICT"], 8))]

    roster_reads = []
    expected_types = [int(t[kind], 8) for kind, _, _, _, _ in scene]
    expected_types += [0 if args.sparse else int(t["SH_CANISTER"], 8)] * (nuniv - len(scene))

    def check_roster():
        if args.fixed:
            # Record result positions, not addresses: --peek may itself
            # request a symbol at a slot's address.
            roster_reads.append(sum(line.startswith("peekcpu ") for line in script))
            script.extend(f"peekcpu {univ + slot*usize + int(t['U.TYPE'], 8):o}"
                          for slot in range(nuniv))
    script += [poke(int(t["PSPEED"], 8), speed), "run 20",
               f"peekcpu {t['FLY_TICK']}"]
    script += [f"peekcpu {t[name]}" for name in args.peek]
    if args.no_stars:
        script += [poke(int(t["STAR_ON"], 8), 0)]
    if args.draw_frames:
        if not 1 <= args.draw_frames <= 1000:
            sys.exit("error: --draw-frames must be 1..1000")
        script = script[:script.index(f"peekcpu {t['FLY_TICK']}")]
        if args.no_stars:
            script += [poke(int(t["STAR_ON"], 8), 0)]
        if args.turning:
            # Keep the requested rates through the main loop's final
            # controls pass before the drawing-only hook is entered.
            script += [poke(int(t["OPTIONS"], 8), int(t["OPT_STEADY"],8) | int(t["OPT_SOUND"],8)),
                       poke(int(t["PROLL"], 8), 8), poke(int(t["PPITCH"], 8), 4)]
        script += [poke(int(t["HARN_MOVE"], 8), int(moving)),
                   poke(int(t["HARN_GO"], 8), args.draw_frames),
                   f"run {args.draw_frames * 25 + 100}",
                   f"peekcpu {t['HARN_GO']}", f"peekcpu {t['HARN_TICKS']}"]
    elif moving:
        left = args.ticks
        while left > 0:
            step = min(RESET_EVERY, left)
            if args.turning:
                # roll and pitch spring back to centre a notch a frame, so
                # they are held down rather than set once
                for _ in range(step // 10):
                    script += ["run 10", poke(int(t["PROLL"], 8), 8),
                               poke(int(t["PPITCH"], 8), 4)]
            else:
                script += [f"run {step}"]
            check_roster()
            for slot, (kind, x, y, z, tag) in enumerate(scene):
                script += [field(slot, "U.X", x), field(slot, "U.Y", y),
                           field(slot, "U.Z", z)]
            if args.fixed:
                for slot in range(len(scene), nuniv):
                    script += [field(slot, "U.Z", 0), field(slot, "U.ZH", -2)]
            left -= step
    else:
        script += [f"run {args.ticks}"]
        check_roster()
    if not args.draw_frames:
        script += [f"peekcpu {t['FLY_TICK']}"]
        script += [f"peekcpu {t[name]}" for name in args.peek]
    if args.shot:
        script += [f"screenshot {Path(args.shot).with_suffix('.bmp').resolve()}"]
    script += ["quit"]

    from verify_build import widen_positions
    script = widen_positions(script)       # the high words of the positions
    r = subprocess.run([str(EMU), "--rom", str(ROM),
                        "--disk", str(fresh_disk("bench"))],
                       input="\n".join(script) + "\n",
                       capture_output=True, text=True, timeout=900)
    if r.returncode:
        sys.exit(f"error: emulator exited {r.returncode}: {r.stderr[-1000:]}")
    timing = re.search(r"timing: (\d+) frames/sec", r.stdout)
    if not timing or int(timing[1]) <= 0:
        sys.exit("error: emulator did not report timing; rebuild the headless toolchain")
    tick_rate = int(timing[1])
    if args.shot:
        from PIL import Image
        bmp = Path(args.shot).with_suffix(".bmp").resolve()
        Image.open(bmp).save(args.shot)
        bmp.unlink()
    vals = [int(v, 8) for v in PEEK.findall(r.stdout)]
    for start in reversed(roster_reads):
        actual = vals[start:start + nuniv]
        if actual != expected_types:
            sys.exit(f"error: benchmark roster changed: expected {expected_types}, got {actual}")
        del vals[start:start + nuniv]
    if len(vals) < 2:
        sys.exit("error: no answer from the emulator")
    if args.draw_frames:
        if len(vals) != 2 or vals[0] or not vals[1]:
            sys.exit(f"error: incomplete drawing benchmark: {vals}")
        print(f"{args.draw_frames} drawing frames in {vals[1]} interrupts "
              f"= {args.draw_frames * 50 / vals[1]:.3f} fps; "
              f"{vals[1] * 20 / args.draw_frames:.3f} ms/frame")
        return 0
    n = 1 + len(args.peek)                          # words read each time
    frames = vals[n] - vals[0]
    print(f"{frames} frames in {args.ticks} ticks "
          f"at {tick_rate} Hz = {frames * tick_rate / args.ticks:.2f} fps")
    for i, name in enumerate(args.peek):            # each as a delta over
        before, after = vals[1 + i], vals[n + 1 + i]  # the same window
        print(f"{name}: {(after - before) & 0xFFFF} over the run "
              f"(was {before}, now {after})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
