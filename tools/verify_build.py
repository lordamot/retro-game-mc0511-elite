#!/usr/bin/env python3
"""verify_build.py - the checks behind `make verify`.

Four things are checked, all of them cheap and all of them things that
have actually broken during this port:

  1. the resources round-trip - re-extracting the commodity table and
     the planet vocabulary from orig/ELITE.SCL, and every Legend resource
     from orig/legend, reproduces what is in src/res, so a regenerated
     resource never silently drifts;
  2. the galaxy generator agrees with Elite - the port's own Python
     model of it puts Lave at index 7 of galaxy 1 with the canonical
     economy, government, tech level and radius;
  3. the disk builds and boots, reaching the flight loop;
  4. the running game agrees with the model - the system data the
     emulator reports for Lave matches what the generator predicts.

    python3 tools/verify_build.py [--skip-emu]
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import elite_re                                    # noqa: E402
import shiplib                                     # noqa: E402
import syms                                        # noqa: E402

EMU = ROOT / "bin/ukncbtl/uknc-headless"
ROM = ROOT / "bin/ukncbtl/uknc_rom.bin"
DSK = ROOT / "tmp/verify-shared.dsk"
PEEK = re.compile(r"peekcpu \d+ = ([0-7]+)")

FAILS = []
CHECK_COUNT = 0

# Firmware boot ends at the welcome page. Keep explicit boundaries so tests
# of the logo, chooser and native relaunch do not depend on list offsets.
POWER_ON = ["run 900", "press 030", "run 30", "press 153", "run 1600"]
SPLASH_KEYS = ["press 153", "run 150", "press 153", "run 300"]
TITLE_BOOT = POWER_ON + SPLASH_KEYS
CHOOSE_KEYS = ["press 107", "run 700"]
COMMANDER_KEYS = ["press 030", "run 250", "press 153", "run 350"]
BOOT = TITLE_BOOT + CHOOSE_KEYS + COMMANDER_KEYS


def check(name, ok, detail=""):
    global CHECK_COUNT
    CHECK_COUNT += 1
    print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


# ---------------------------------------------------------------- 1 ----

def check_resources():
    print("resources round-trip")
    # The ship blueprints were the 1985 disk's until 2026-09-10; they are
    # Elite Legend's now (check_legend_resources), and the 1985 ones are
    # on main.  What is still the disk's: the commodity table and the
    # words a world is described with.
    img = elite_re.load_image()
    goods_txt = ROOT / "src/res/market/goods.txt"
    if not goods_txt.exists():
        # the commodity table is Elite Legend's too since 2026-09-10 (late);
        # the 1985 one is on main
        rows = []
        print("  the 1985 commodity table is not in the tree: skipped")
    else:
        goods = goods_txt.read_text(encoding="utf-8")
        rows = [l.split() for l in goods.splitlines()
                if l.strip() and not l.startswith("#")]
        check("17 commodities", len(rows) == 17, f"{len(rows)}")
    if len(rows) == 17:
        ok = True
        for i, row in enumerate(rows):
            a = 0x701B + i * 4
            if int(row[1]) != img[a] or int(row[3]) != img[a + 2]:
                ok = False
        check("commodity table matches the original", ok)

    # The words a world is described with, checked back against the
    # image they came out of: every stem in planet.txt must still be at
    # the address it claims, or the file has drifted from the disk.
    import planet_extract
    words = []              # not `rows`: that one is the commodity table
    for raw in (ROOT / "src/res/text/planet.txt").read_text(
            encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip("\n")
        if line.strip():
            parts = line.split("\t")
            parts += [""] * (4 - len(parts))       # the harmless colour is
            words.append(parts[:4])                # an empty word, and stays one
    wrong = []
    for group, addr, stem, _shown in words:
        if planet_extract.decode(img, int(addr, 16)) != stem:
            wrong.append((group, addr, stem,
                          planet_extract.decode(img, int(addr, 16))))
    check("the planet vocabulary is still the original's", not wrong,
          f"{len(words)} words" if not wrong else f"{wrong[:2]}")
    groups = {}
    for group, _a, _st, _sh in words:
        groups[group] = groups.get(group, 0) + 1
    check("and the species table has Elite's own shape",
          [groups.get(g) for g in ("size", "colour", "trait", "kind")]
          == [3, 6, 6, 8],
          f"{groups}")

# --------------------------------------------------------------- 1b ----

def check_legend_resources():
    """src/res/legend is what the extractors write from
    orig/legend today: run them into a scratch directory and compare
    byte for byte, then spot-check numbers Legend is known by."""
    print("legend resources round-trip")
    src = ROOT / "orig/legend/EliteLegend_v1_09_source"
    if not src.exists():
        check("orig/legend is here", False)
        return
    have = ROOT / "src/res/legend"
    (ROOT / "tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as td:
        td = Path(td)
        runs = [("legend_ships.py", td / "ships", []), ("legend_tables.py", td, []),
                ("legend_text.py", td / "text", []),
                # phase 6's pictures (2026-09-25): the title's logo and the
                # scanner dishes, extracted the same way
                ("logo_gen.py", td / "logo.txt", ["--extract", str(src / "GFX/logoscr_release.scr")]),
                ("scanner_gen.py", td / "scanners.txt", ["--extract", str(src / "Cocpits/Scaner")]),
                # and the sound effects (2026-09-26)
                ("sfx_gen.py", td / "sfx.txt", ["--extract"])]
        ok = True
        for tool, out, extra in runs:
            r = subprocess.run([sys.executable, f"tools/{tool}", "--out", str(out),
                                "--force"] + extra, cwd=ROOT, capture_output=True, text=True)
            check(f"{tool} runs", r.returncode == 0,
                  "" if r.returncode == 0 else r.stderr.strip()[-120:])
            ok = ok and r.returncode == 0
        if ok:
            fresh = {p.relative_to(td): p.read_bytes() for p in td.rglob("*.txt")}
            kept = {p.relative_to(have): p.read_bytes() for p in have.rglob("*.txt")}
            check("the same files", set(fresh) == set(kept),
                  f"{sorted(str(p) for p in set(fresh) ^ set(kept))[:4]}")
            differ = [str(p) for p in fresh if p in kept and fresh[p] != kept[p]]
            check("and the same bytes in them", not differ, f"{differ[:4]}")
    ships = shiplib.read_dir(have / "ships")
    check("69 blueprints, 64 of them in AdrDataShips",
          len(ships) == 69 and sum(1 for x in ships if x.index < 64) == 64,
          f"{len(ships)}")
    byk = {x.key: x for x in ships}
    cob = byk.get("COBRAMK3HT1")
    check("Cobra Mk III is 28 vertices and 38 edges, as in 1985",
          cob is not None and len(cob.vertices) == 28 and len(cob.edges) == 38,
          cob and f"{len(cob.vertices)}v {len(cob.edges)}e")
    pir = byk.get("COBRAMK3HP")
    check("its pirate borrows the hull and pays 175",
          pir is not None and pir.geometry == "COBRAMK3HT1" and pir.bounty == 175,
          pir and f"{pir.geometry} {pir.bounty}")
    goods = [l for l in (have / "market/goods.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    check("38 commodities, food first at 19", len(goods) == 38
          and goods[0].split()[1:3] == ["FOOD", "19"], f"{len(goods)}")
    cat = [l for l in (have / "catalog.txt").read_text(encoding="utf-8").splitlines()
           if l.strip() and not l.startswith("#")]
    check("20 ships in the yard, the Cobra Mk III at 1 500 000",
          len(cat) == 20 and any("Cobra MK-3" in l and " 1500000 " in l for l in cat),
          f"{len(cat)}")
    eq = [l for l in (have / "equip.txt").read_text(encoding="utf-8").splitlines()
          if l.strip() and not l.startswith("#")]
    check("49 equipment rows, the naval laser mission-gated",
          len(eq) == 49 and any("priceLaser5" in l and " 16 " in l for l in eq), f"{len(eq)}")
    seed = (have / "galaxy.txt").read_text(encoding="utf-8").splitlines()[-1].split()[1:7]
    check("the galaxy seed is 1985's 4A 5A 48 02 53 B7",
          seed == ["74", "90", "72", "2", "83", "183"], " ".join(seed))
    msgs = sum(1 for p in (have / "text").glob("*.txt")
               for l in p.read_text(encoding="utf-8").splitlines()
               if "|" in l and not l.startswith("#"))
    check("769 Russian messages", msgs == 769, f"{msgs}")


# ---------------------------------------------------------------- 2 ----

def galaxy_model(index, galaxy=0):
    """The port's model of Elite's generator; src/galaxy.mac implements
    the same steps.  GALAXY is Legend's number, 0 Lave's (legend_seed)."""
    s = legend_seed(galaxy)

    def tweak(t):
        return [t[1], t[2], (t[0] + t[1] + t[2]) & 0xFFFF]

    for _ in range(index + 1):
        govt = (s[1] >> 3) & 7
        econ = (s[0] >> 8) & 7
        if govt <= 1:
            econ |= 2
        tech = ((s[1] >> 8) & 3) + (econ ^ 7) + (govt >> 1) + (1 if govt & 1 else 0)
        pop = 4 * tech + econ + govt + 1
        x = (s[1] >> 8) & 0xFF
        y = (s[0] >> 8) & 0xFF
        radius = 256 * (((s[2] >> 8) & 15) + 11) + x
        for _ in range(4):
            s = tweak(s)
    return dict(econ=econ, govt=govt, tech=tech, pop=pop, radius=radius, x=x, y=y)


def sys_distance(a, b):
    """SYS_DISTANCE between systems A and B of galaxy 1, in tenths of a
    light year: the chart's y is at half scale, the sum of squares is
    quartered before the root and the root scaled back by eight."""
    import math
    dx = abs(a["x"] - b["x"])
    dy = abs(a["y"] - b["y"]) >> 1
    return 8 * math.isqrt((dx * dx + dy * dy) >> 2)


def check_galaxy():
    print("galaxy generator")
    lave = galaxy_model(7)
    # Lave, galaxy 1 system 7, as every Elite has it
    check("Lave is rich agricultural", lave["econ"] == 5, str(lave["econ"]))
    check("Lave is a dictatorship", lave["govt"] == 3, str(lave["govt"]))
    # Elite shows tech level as the raw value plus one, and Lave's is 5
    check("Lave tech level 5", lave["tech"] + 1 == 5, str(lave["tech"] + 1))
    check("Lave radius 4116 km", lave["radius"] == 4116, str(lave["radius"]))
    return lave


# ------------------------------------------------------------- 3, 4 ----

PRISTINE = ROOT / "tmp" / "verify-pristine.dsk"
BUILT = ROOT / "build" / "elite.raw"           # written by the build, never by a check


def keep_pristine():
    """Reconstruct disposable RT-11 volumes from the built manifest.

    Native docking saves and monitor swapping write to the mounted disk.
    Rebuilding from manifest inputs prevents prior test commanders or
    swap state from leaking into later fixtures.
    """
    PRISTINE.parent.mkdir(exist_ok=True)
    for out in (DSK, PRISTINE):
        r = subprocess.run([sys.executable, str(ROOT / "tools/dsk_build.py"),
                            str(ROOT / "build/manifest.json"), str(out), "--force"],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"error: laying the disk out again failed:\n{r.stdout}{r.stderr}")


def fresh_disk(name):
    """A fresh private copy; pass the returned path explicitly across reboots."""
    import shutil
    if not PRISTINE.exists() or PRISTINE.stat().st_mtime < BUILT.stat().st_mtime:
        keep_pristine()
    out = ROOT / "tmp" / f"verify-{name}.dsk"
    shutil.copyfile(PRISTINE, out)
    return out


def widen_positions(script):
    """Every poke of a slot's U.X/U.Y/U.Z gets its high word poked too.

    Positions are 32-bit since 2026-09-10, the low word at U.X/U.Y/U.Z
    and the high one at U.XH/U.YH/U.ZH; a check that pokes a 16-bit
    position must sign-extend it, or the slot is left with a high word
    from whatever was there before and the game treats the ship as
    being 65536 units off.  Doing it here, once, keeps every check's
    poke as it was written.
    """
    t = syms.table()
    if "U.XH" not in t:
        return script
    univ = int(t["UNIV"], 8)
    usize = int(t["U.SIZE"], 8)
    nuniv = int(t["NUNIV"], 8)
    pairs = {}
    for slot in range(nuniv):
        base = univ + slot * usize
        for lo, hi in (("U.X", "U.XH"), ("U.Y", "U.YH"), ("U.Z", "U.ZH")):
            pairs[base + int(t[lo], 8)] = base + int(t[hi], 8)
    out = []
    for line in script:
        out.append(line)
        m = re.match(r"^pokecpu ([0-7]+) ([0-7]+) ([0-7]+)$", line)
        if m and int(m.group(1), 8) in pairs:
            hi = 0o377 if int(m.group(3), 8) & 0x80 else 0
            out.append(f"pokecpu {pairs[int(m.group(1), 8)]:o} {hi:o} {hi:o}")
    return out


def ui_ready(t=None, frames=28):
    """Wait for main-loop passes after a nonmodal screen/file operation.

    RT-11 directory calls may swap the USR. A fixed old raw-disk delay can
    expire while the menu is still drawing, consuming the next scripted key.
    The default also clears SCREEN_KEYS' 25-frame STOP lockout. Modal
    name/mission prompts use their explicit waits instead.
    """
    t = t or syms.table()
    return f"runrel {t['FLY_TICK']} {frames} 1200"


def mission_ready(t):
    """Stop at the mission overlay's key loop after its text has been drawn."""
    return [f"waitcpu {t['OVL_CUR']} {t['OVL_MISSION']} 1200",
            f"runpc {t['MO_KEY']} 1200"]


def run_emu(script, disk=None, *, palette=None):
    script = widen_positions(script)
    if disk is None:
        disk = fresh_disk("shared")
    r = subprocess.run([str(EMU), "--rom", str(ROM),
                        "--disk", str(disk)] +
                       (["--palette", palette] if palette else []),
                       input="\n".join(script) + "\n",
                       capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise RuntimeError(f"emulator exited {r.returncode}: {r.stderr}\n{r.stdout[-2000:]}")
    expected = sum(line.startswith("peekcpu ") for line in script)
    if len(PEEK.findall(r.stdout)) != expected:
        raise RuntimeError(f"emulator answered {len(PEEK.findall(r.stdout))} of {expected} peeks\n"
                           f"{r.stderr}\n{r.stdout[-2000:]}")
    expected_ppu = sum(line.startswith("peekw ") for line in script)
    answered_ppu = len(re.findall(r"peekw \d+ [0-7]+ = [0-7]+", r.stdout))
    if answered_ppu != expected_ppu:
        raise RuntimeError(f"emulator answered {answered_ppu} of {expected_ppu} plane peeks\n"
                           f"{r.stderr}\n{r.stdout[-2000:]}")
    return r.stdout


def check_emulator(lave):
    print("boot and run")
    if not DSK.exists():
        check("disk exists", False, "run make build")
        return
    table = syms.table()
    need = ["SYS_ECON", "SYS_GOVT", "SYS_TECH", "SYS_RADIUS", "FLY_TICK",
            "SCREEN"]
    missing = [n for n in need if n not in table]
    if missing:
        check("symbols found", False, f"missing {missing}")
        return
    boot = list(BOOT)
    # launch before timing: docked, nothing is drawn and the loop spins
    # far faster than it ever does in flight
    # Fifty ticks is one second of emulated time, and the tick count is
    # deterministic - it does not care what the host is doing.  This
    # used to sample twenty-five and call the answer "frames in one
    # second", which quietly halved every figure it ever printed.
    script = boot + ["press 107", "run 60",
                     f"peekcpu {table['FLY_TICK']}", "run 50",
                     f"peekcpu {table['FLY_TICK']}",
                     "press 004", "run 40",
                     "press 004", "run 40",
                     f"peekcpu {table['SYS_ECON']}",
                     f"peekcpu {table['SYS_GOVT']}",
                     f"peekcpu {table['SYS_TECH']}",
                     f"peekcpu {table['SYS_RADIUS']}", "quit"]
    vals = [int(v, 8) for v in PEEK.findall(run_emu(script))]
    if len(vals) < 6:
        check("emulator answered", False, f"{len(vals)} peeks")
        return
    t0, t1 = vals[0], vals[1]
    check("the flight loop runs", t1 > t0, f"{t1 - t0} frames in one second")
    check("frame rate is playable", t1 - t0 >= 5, f"{t1 - t0} fps in flight")
    econ, govt, tech, radius = vals[2:6]
    check("running game: Lave economy", econ == lave["econ"], str(econ))
    check("running game: Lave government", govt == lave["govt"], str(govt))
    check("running game: Lave tech", tech == lave["tech"], str(tech))
    check("running game: Lave radius", radius == lave["radius"], str(radius))


def check_combat_and_sound():
    """Fly, hold the trigger, and see that something dies and is heard."""
    print("combat and sound")
    table = syms.table()
    need = ["KILLS", "PLASTEMP", "PSHIELD_F", "PENERGY", "NUNIV", "UNIV",
            "U.SIZE", "U.TYPE", "U.FLAGS", "U.TARGET", "U.EXPL", "U.SPEED",
            "U.ENERGY", "U.X", "U.Y", "U.Z", "SH_KRAIT", "UF_HOSTILE"]
    if any(n not in table for n in need):
        check("combat symbols found", False)
        return
    boot = list(BOOT)
    wav = ROOT / "tmp" / "verify-combat.wav"
    wav.parent.mkdir(exist_ok=True)
    # launch first: the game now starts in the station, where ФИКС is
    # the launch key rather than the trigger
    # The trigger is held long enough for a real hull to break up: ships
    # now carry the original's own energy (a Viper has 140, not the flat
    # 24 this port used to give everything), so a burst that used to be
    # plenty no longer is.
    # And a target of its own, dead ahead, with the traffic cleared: what
    # is under test is that the laser kills, not what Lave puts in front
    # of it - see clear_traffic.
    target = [poke_at(int(slot_field(table, 5, n), 8), v) for n, v in [
        ("U.TYPE", int(table["SH_KRAIT"], 8)), ("U.FLAGS", 0), ("U.EXPL", 0),
        ("U.TARGET", 0), ("U.X", 0), ("U.Y", 0), ("U.Z", 900), ("U.SPEED", 0),
        ("U.ENERGY", 100)]]
    target += mind(table, 5, "KRAITH", still=True)
    script = boot + ["press 107", "run 40"] + clear_traffic(table) + target + [
                     "wavstart", "keydown 107", "run 200",
                     f"peekcpu {table['PLASTEMP']}",
                     f"peekcpu {table['KILLS']}",
                     f"peekcpu {table['PSHIELD_F']}",
                     "keyup 107", "run 10", f"wavstop {wav}", "quit"]
    out = run_emu(script)
    vals = [int(v, 8) for v in PEEK.findall(out)]
    if len(vals) < 3:
        check("combat answered", False, f"{len(vals)} peeks")
        return
    heat, kills, shield = vals
    check("the laser heats up", heat > 0, str(heat))
    check("something was shot down", kills > 0, f"{kills} kills")
    # Whether the enemy gets a shot in is checked separately, with the
    # trigger held OFF: firing tends to destroy the hostile before it
    # has had its turn, which made this flap between runs.
    # A hostile of its own, dead ahead and inside AI_FIRE_Z.  Lave's own
    # traffic no longer means harm - a government of 3 sends traders,
    # and only 2 or under sends anyone hostile - and a hostile now only
    # shoots from in front, in range and on the line of fire.  So the
    # check has to put one where it can shoot rather than hope one turns
    # up: what is under test is that the enemy shoots back, not that
    # Lave is dangerous.
    last = int(table["NUNIV"], 8) - 1

    def attacker(field, val):
        return poke_at(int(slot_field(table, last, field), 8), val)

    incoming = [attacker("U.TYPE", int(table["SH_KRAIT"], 8)),
                attacker("U.FLAGS", int(table["UF_HOSTILE"], 8)),
                attacker("U.TARGET", 0), attacker("U.EXPL", 0),
                attacker("U.SPEED", 0), attacker("U.ENERGY", 4000),
                attacker("U.X", 0), attacker("U.Y", 0),
                attacker("U.Z", 1200)]
    incoming += mind(table, last, "KRAITH", facing=True)     # facing him, and with a mind
    # and no station: near one a Krait is shy of the commander (F2_SHY,
    # DirectObject) and turns away on its reaction frames, which is
    # Legend's rule and no way to test a shot
    incoming.append(poke_at(int(slot_field(table, 2, "U.TYPE"), 8), 0))
    # The shield is read every twenty ticks, not once at the end: a hit
    # of seven is thirty-five off the shield and the shield is back to
    # full thirty-five interrupts later, so one read at the end only saw
    # a hit that landed in the last seventeen ticks - and whether one
    # did is the hostile's random jink, which changed with the build.
    # and Lave's traffic cleared: a pirate with a canister in the sky goes
    # and collects it before it bothers with you (SetNewTargetObj's list),
    # and the Krait flew off after the arrival drop at 12000
    script = boot + ["press 107", "run 40"] + clear_traffic(table) + incoming
    for _ in range(10):
        script += ["run 20", f"peekcpu {table['PSHIELD_F']}", f"peekcpu {table['PENERGY']}"]
    script.append("quit")
    v2 = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v2) >= 2:
        full = int(table["ENERGY_MAX"], 8)
        low = min(v2)
        check("the enemy shoots back", low < full,
              f"shield down to {min(v2[0::2])}, energy to {min(v2[1::2])}")

    if wav.exists():
        r = subprocess.run([sys.executable, "tools/wav_analyze.py", str(wav)],
                           cwd=ROOT, capture_output=True, text=True)
        m = re.search(r"(\d+)/(\d+) active", r.stdout)
        active = int(m.group(1)) if m else 0
        check("the AY module is heard", active > 5,
              f"{active} active windows")
    else:
        check("audio captured", False)


def check_hyperspace():
    """Jump to a system three rows up the chart and check the fuel bill."""
    print("hyperspace")
    table = syms.table()
    need = ["PFUEL", "SYS_INDEX", "SCREEN", "P_JUMPS"]
    if any(n not in table for n in need):
        check("hyperspace symbols found", False)
        return
    script = BOOT + [
              "press 004", ui_ready(),
              "press 154", ui_ready(frames=1), "press 154", ui_ready(frames=1),
              "press 154", ui_ready(frames=1),
              # Arrival reads several overlays; observe the next main-loop pass.
              "press 107", ui_ready(frames=1),
              f"peekcpu {table['PFUEL']}",
              f"peekcpu {table['SYS_INDEX']}",
              f"peekcpu {table['SCREEN']}",
              f"peekcpu {table['P_JUMPS']}", "quit"]
    vals = [int(v, 8) for v in PEEK.findall(run_emu(script))]
    if len(vals) < 4:
        check("hyperspace answered", False)
        return
    fuel, index, screen, jumps = vals
    check("fuel was spent", fuel < 70, f"{fuel} tenths left")
    check("arrived somewhere else", index != 7, f"system {index}")
    check("back in the cockpit", screen == 0, str(screen))
    check("and the record counts the jump", jumps == 1, f"{jumps} jumps")

    # the bill is the distance, and the trip takes its time: the fuel
    # squared over ten, tenths of an hour on the clock (HYPER_JUMP,
    # CalcTravelTime); a tank short of the distance refuses the jump
    t = table
    cost = sys_distance(galaxy_model(7), galaxy_model(index))
    clock = [peek_byte(t, k) for k in ("P_DAY", "P_HOUR", "P_MIN")]
    def minutes(w):                   # Legend's clock: 50-minute hours, 30-hour days
        d, h, m = (byte_of(t, k, x) for k, x in zip(("P_DAY", "P_HOUR", "P_MIN"), w))
        return (d * 30 + h) * 50 + m
    jump = ["press 004", ui_ready()] + ["press 154", ui_ready(frames=1)] * 3 + ["press 107", ui_ready(frames=1)]
    v = [int(x, 8) for x in PEEK.findall(run_emu(BOOT + clock + jump + clock + [
        f"peekcpu {t['PFUEL']}", "quit"], fresh_disk("hyperspace")))]
    if len(v) == 7:
        check("the fuel bill is the distance", v[6] == 70 - cost, f"{70 - v[6]} spent, {cost} away")
        # five minutes a tenth of an hour; the flight's own seconds may
        # carry one minute more over the chart and the tunnel
        took, want = minutes(v[3:6]) - minutes(v[0:3]), cost * cost // 10 * 5
        check("and the trip takes the fuel squared over ten, in tenths of an hour",
              want <= took <= want + 1, f"{took} minutes, {want} due")
    else:
        check("the clock answered", False, f"{len(v)} peeks")
    v = [int(x, 8) for x in PEEK.findall(run_emu(BOOT + [poke_at(int(table["PFUEL"], 8), cost - 1)] + jump + [
        f"peekcpu {table['PFUEL']}", f"peekcpu {table['SYS_INDEX']}", f"peekcpu {table['P_JUMPS']}",
        "quit"], fresh_disk("hyperspace")))]
    check("a tank short of the distance refuses the jump",
          v == [cost - 1, 7, 0], f"fuel, system, jumps {v}")


def check_station_and_trade():
    """Start docked, launch, outfit, and use the galactic drive."""
    print("station, outfitting and the galactic drive")
    t = syms.table()
    need = ["DOCKED", "PSPEED", "PMISSILES", "CASH_L", "SCREEN",
            "P_GALDRIVE", "GALNUM", "SYS_INDEX"]
    if any(n not in t for n in need):
        check("station symbols found", False)
        return
    boot = list(BOOT)

    # docked at the start, and ФИКС launches
    script = boot + [f"peekcpu {t['DOCKED']}", "press 107", "run 40",
                     f"peekcpu {t['DOCKED']}", f"peekcpu {t['PSPEED']}",
                     "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 3:
        check("starts docked", v[0] == 1, str(v[0]))
        check("ФИКС launches", v[1] == 0, str(v[1]))
        check("launches under way", v[2] > 0, f"speed {v[2]}")

    # the outfitter sells a missile: the top row with the tanks full,
    # and ФИКС buys it (Legend's list; check_equip goes through the rest)
    script = boot + ["press 004", ui_ready(t)] * 5 + \
        [f"peekcpu {t['SCREEN']}",
         "press 107", "run 35",
         f"peekcpu {t['PMISSILES']}", f"peekcpu {t['CASH_L']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 3:
        check("the outfitter opens", v[0] == 5, f"screen {v[0]}")
        check("a missile is bought", v[1] == 4, f"{v[1]} aboard")
        check("and paid for", v[2] == 700, f"{v[2]} tenths left")

    # the galactic drive, poked in because 500 Cr is a long grind
    script = boot + [poke_dev(t, "P_GALDRIVE"), "press 004", ui_ready(t),
                     "press 107", "run 90",
                     f"peekcpu {t['GALNUM']}", f"peekcpu {t['SYS_INDEX']}",
                     peek_dev(t, "P_GALDRIVE"), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 3:
        # GALNUM is Legend's PilotNumGalaxy now, 0..47
        check("the galactic drive moves galaxy", v[0] == 1, f"galaxy {v[0]}")
        check("and lands somewhere new", v[1] != 7, f"system {v[1]}")
        check("and is used up", not dev_fitted(t, "P_GALDRIVE", v[2]),
              f"{v[2]:o}")


def check_dockcomp():
    """Fit a docking computer, launch, shut the throttle, and be flown in."""
    print("docking computer")
    t = syms.table()
    need = ["P_DOCKCOMP", "DC_ON", "DOCKED", "PSPEED"]
    if any(n not in t for n in need):
        check("docking computer symbols found", False)
        return
    boot = list(BOOT)
    disk = fresh_disk("dockcomp")                    # docking writes a
    script = boot + [poke_dev(t, "P_DOCKCOMP"),     # commander to the disk
                     "press 107", "run 50",
                     f"peekcpu {t['DC_ON']}"]        # not engaged at speed
    for _ in range(4):
        script += ["press 166", "run 20"]            # throttle round to zero
    script += [f"peekcpu {t['DC_ON']}", "run 700",
               f"peekcpu {t['DOCKED']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, disk))]
    if len(v) < 3:
        check("docking computer answered", False)
        return
    check("it leaves you alone at speed", v[0] == 0, str(v[0]))
    check("a shut throttle engages it", v[1] == 1, str(v[1]))
    check("and it flies you in", v[2] == 1, f"docked {v[2]}")


def check_missiles():
    """Launch, lock onto a ship with space, fire, and see it hit."""
    print("missiles")
    t = syms.table()
    need = ["MISS_LOCK", "PMISSILES", "KILLS", "UNIV", "U.SIZE", "U.TYPE",
            "U.FLAGS", "U.EXPL", "U.TARGET", "U.X", "U.Y", "U.Z",
            "SH_SIDEWINDER"]
    if any(n not in t for n in need):
        check("missile symbols found", False)
        return
    # A target of its own, parked dead ahead: the traffic at Lave now
    # flees when it is hurt and gets shot at by the station's Vipers, so
    # a check that waits for whatever happens to be in front of it is
    # checking the wrong thing.
    script = BOOT + [
              "press 107", "run 90"] + clear_traffic(t) + [
              poke_at(int(slot_field(t, 5, "U.TYPE"), 8),
                      int(t["SH_SIDEWINDER"], 8)),
              poke_at(int(slot_field(t, 5, "U.FLAGS"), 8), 0),
              poke_at(int(slot_field(t, 5, "U.EXPL"), 8), 0),
              poke_at(int(slot_field(t, 5, "U.TARGET"), 8), 0),
              poke_at(int(slot_field(t, 5, "U.X"), 8), 0),
              poke_at(int(slot_field(t, 5, "U.Y"), 8), 0),
              poke_at(int(slot_field(t, 5, "U.Z"), 8), 1200),
              poke_at(int(slot_field(t, 5, "U.SPEED"), 8), 0),
              poke_at(int(slot_field(t, 5, "U.ENERGY"), 8), 70)] + mind(t, 5, "SIDEWINDERH", still=True) + [   # a Sidewinder's:
              "run 20",                              # a missile is 160, not a kill
              "press 113", "run 30", f"peekcpu {t['MISS_LOCK']}",
              "press 113", "run 30", f"peekcpu {t['PMISSILES']}",
              "run 400", f"peekcpu {t['KILLS']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 3:
        check("missiles answered", False)
        return
    check("space locks onto a ship", v[0] != 0, f"slot {v[0]}")
    check("and launching spends one", v[1] == 2, f"{v[1]} left")
    check("and the missile kills", v[2] > 0, f"{v[2]} kills")


def check_culling():
    """The port must draw the edges the model says it should, and no more.

    Backface culling and the per-edge distance thresholds live in
    src/ship.mac; this reruns the same decisions in Python against the
    universe the running game actually has, and compares the count with
    the segment buffer.  The exact number cannot be asserted - the
    sample is not frame-aligned, and the scanner adds a segment per ship
    after the ships are drawn - but the gap between culled and unculled
    is wide enough that losing the culling could not hide in it.
    """
    print("backface culling")
    t = syms.table()
    need = ("UNIV", "U.SIZE", "U.FLAGS", "NUNIV", "SEGPREV")
    if any(n not in t for n in need):
        check("culling symbols found", False)
        return
    usize = int(t["U.SIZE"], 8)
    nuniv = int(t["NUNIV"], 8)
    uflags = int(t["U.FLAGS"], 8)
    dump = ROOT / "tmp" / "verify-cull.bin"
    dump.parent.mkdir(exist_ok=True)
    script = BOOT + [
              "press 107", "run 300",
              f"dumpcpu {t['UNIV']} {usize * nuniv} {dump}",
              f"peekcpu {t['SEGPREV']}", "quit"]
    out = run_emu(script)
    vals = [int(v, 8) for v in PEEK.findall(out)]
    if not dump.exists() or not vals:
        check("the universe was dumped", False)
        return
    segcnt = vals[-1]

    import struct
    d = dump.read_bytes()

    def word(off):
        v = struct.unpack_from("<H", d, off)[0]
        return v - 65536 if v >= 32768 else v

    ships = shiplib.read_dir(ROOT / "src/res/legend/ships")
    u_z, u_mat, u_expl = 6, 0o10, 0o46
    culled = uncelled = nships = 0
    for i in range(nuniv):
        a = i * usize
        ty = word(a)
        if ty == 0:
            continue
        if word(a + u_expl):
            culled += 8         # a wreck is eight sparks in a ring, drawn
            uncelled += 8       # by EXPL_DRAW instead of by its blueprint
            continue
        if word(a + uflags) & (8 | 16):     # a world, drawn from its own buffer
            continue
        x, y, z = word(a + 2), word(a + 4), word(a + u_z)
        if z <= 0:
            continue
        nships += 1
        hull = shiplib.hull_of(ships[ty - 1], ships)
        if hull.radius * 384.0 / z < 7:     # far enough to be a dot
            culled += 1
            uncelled += 1
            continue
        if word(a + uflags) & 2 and z < 5000:
            culled += 4         # the station's docking slot: four segments
            uncelled += 4       # the blueprint does not carry
        m = [word(a + u_mat + 2 * k) for k in range(9)]
        q = 16384.0
        # the hull's centre rotated into model space, which is what the
        # face test dots the stored normals against
        px = (m[0] * x + m[3] * y + m[6] * z) / q
        py = (m[1] * x + m[4] * y + m[7] * z) / q
        pz = (m[2] * x + m[5] * y + m[8] * z) / q
        vis = ([nx * px + ny * py + nz * pz < 0
                for nx, ny, nz in hull.normals] if hull.normals else None)
        behind = set()
        for k, (vx, vy, vz) in enumerate(hull.vertices):
            if (m[6] * vx + m[7] * vy + m[8] * vz) / q + z < 24:
                behind.add(k)
        dist = min(31, z >> 8)
        # Where each vertex lands on the screen, the way src/math3d.mac's
        # PROJECT puts it there: the 5/3 aspect is folded into the focal
        # length for x, and a quotient that will not fit in sixteen bits
        # is dropped, which is what the BVS in PROJECT does.
        def screen(vx, vy, vz):
            cx = x + (m[0] * vx + m[1] * vy + m[2] * vz) / q
            cy = y + (m[3] * vx + m[4] * vy + m[5] * vz) / q
            cz = z + (m[6] * vx + m[7] * vy + m[8] * vz) / q
            if cz < 24:
                return None
            sx, sy = cx * 640.0 / cz, cy * 384.0 / cz
            if abs(sx) > 32767 or abs(sy) > 32767:
                return None
            return 320 + sx, 100 - sy

        pts = [screen(*v) for v in hull.vertices]

        for e0, e1, cull, f1, f2 in hull.edges:
            if e0 in behind or e1 in behind:
                continue
            if cull < dist:
                continue
            # A segment with both ends off the same side of the view is
            # thrown away by CLIP_LINE before it reaches the buffer.  The
            # model has to do the same or it counts edges that were never
            # drawn: three police Vipers closing to 600 units fill the
            # screen, and most of what they are made of is outside it.
            a0, a1 = pts[e0], pts[e1]
            if a0 is None or a1 is None:
                continue
            if ((a0[0] < 0 and a1[0] < 0) or (a0[0] > 639 and a1[0] > 639)
                    or (a0[1] < 0 and a1[1] < 0)
                    or (a0[1] > 199 and a1[1] > 199)):
                continue
            uncelled += 1
            if vis is not None and not (vis[f1] or vis[f2]):
                continue
            culled += 1

    check("the game has ships to draw", nships > 0, f"{nships}")
    # The scanner adds up to one segment per ship after the hulls go in,
    # and the dump is a frame ahead of the count.
    # The slack covers what the model cannot know about: the station's
    # docking slot is four segments the blueprints do not carry, the
    # compass dot is one more, a ship may be a frame further along than
    # the dump, and one that has just begun to explode is drawn by
    # EXPL_DRAW instead.
    # The scanner adds up to THREE segments a ship since 2026-09-10: the
    # blip's two rows and the stalk.
    slack = 12
    scanner = 3 * nships
    check("segments match the culled model",
          culled - slack <= segcnt <= culled + scanner + slack,
          f"model {culled}, buffer {segcnt}, "
          f"scanner adds <= {scanner}, slack {slack}")
    check("and are well short of drawing every edge",
          segcnt - scanner < uncelled * 3 // 4,
          f"buffer {segcnt} less the scanner's {scanner}, "
          f"every edge would be {uncelled}")



def check_worlds():
    """A world kills you at its surface, and nowhere else.

    The planet's radius is 3000 and the test used to be a 900-unit box
    around its centre, so it could be flown a long way in - and, off the
    axis, straight through - before anything happened.  Two trials pin
    the shape down: just inside the surface must be fatal, and the same
    distance out on a diagonal must not be.
    """
    print("worlds have a surface")
    t = syms.table()
    if any(n not in t for n in ("UNIV", "DOCKED", "U.SIZE")):
        check("world symbols found", False)
        return
    univ = int(t["UNIV"], 8)

    def poke(off, val):
        v = val & 0xFFFF
        return f"pokecpu {univ + off:o} {v & 0xFF:o} {(v >> 8) & 0xFF:o}"

    def dead_at(x, y, z, expect_dead=False):
        # slot 0 is the planet; move it onto the commander and see.  The
        # commander is HELD STILL: he launches at speed 16, and at that
        # speed the diagonal trial below flew him from 3394 away to
        # 2400 abeam - inside the surface - within the 200 ticks, in
        # every build.  The trial used to pass only because the death
        # came late enough that the title was not up yet when the keys
        # below were pressed, and a build a second faster in that scene
        # (a world filling the view, its rim now drawn whole) failed it.
        script = BOOT + [
                  "press 107", ui_ready(t, frames=2),
                  poke_at(int(t["PSPEED"], 8), 0),
                  poke(2, x), poke(4, y), poke(6, z)]
        script += ([f"waitcpu {t['OVL_CUR']} {t['OVL_TITLE']} 1200",
                    f"runrel {t['TI_TICK']} 2 1200"] if expect_dead else [ui_ready(t, frames=40)])
        script += [
                  # Dying holds the message, then starts the title. Observe
                  # that directly: this collision test does not also need
                  # to drive the RT-11 commander lookup/name dialog.
                  f"peekcpu {t['OVL_CUR']}", f"peekcpu {t['TI_TICK']}", "quit"]
        vals = [int(v, 8) for v in PEEK.findall(run_emu(script))]
        return len(vals) == 2 and vals[0] == int(t['OVL_TITLE'],8) and vals[1] > 0

    check("inside the surface is fatal", dead_at(0, 0, 2600, expect_dead=True),
          "planet 2600 away, radius 3000")

    # and so is a ship that flies into one: the planet is parked at a
    # known distance and a Sidewinder put inside it
    script = BOOT + ["press 107", ui_ready(t, frames=2),
                     poke(2, 0), poke(4, 0), poke(6, 9000),
                     poke_at(int(slot_field(t, 5, "U.TYPE"), 8),
                             int(t["SH_SIDEWINDER"], 8)),
                     poke_at(int(slot_field(t, 5, "U.FLAGS"), 8), 0),
                     poke_at(int(slot_field(t, 5, "U.EXPL"), 8), 0),
                     poke_at(int(slot_field(t, 5, "U.X"), 8), 0),
                     poke_at(int(slot_field(t, 5, "U.Y"), 8), 0),
                     poke_at(int(slot_field(t, 5, "U.Z"), 8), 9000)] + mind(t, 5, "SIDEWINDERH", still=True) + [
                     "run 30",
                     f"peekcpu {slot_field(t, 5, 'U.EXPL')}",
                     f"peekcpu {slot_field(t, 5, 'U.TYPE')}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("worlds")))]
    if len(v) >= 2:
        check("and a ship that flies into a world stops being one",
              v[0] != 0 or v[1] == 0,
              f"explosion {v[0]}, type {v[1]}")
    check("and passing it by is not", not dead_at(2400, 0, 2400),
          "planet 3394 away on the diagonal")


def check_witchspace():
    """A misjump leaves you nowhere, with company."""
    print("witchspace")
    t = syms.table()
    if any(n not in t for n in ("WITCH", "UNIV", "U.SIZE", "U.FLAGS",
                                "NUNIV")):
        check("witchspace symbols found", False)
        return
    dump = ROOT / "tmp" / "verify-univ.bin"
    dump.parent.mkdir(exist_ok=True)
    # Read the slot's shape out of the build rather than hard-coding it:
    # U.SIZE has changed once already, and a stale stride here reads
    # neighbouring words and reports nonsense instead of failing loudly.
    usize = int(t["U.SIZE"], 8)
    uflags = int(t["U.FLAGS"], 8)
    nuniv = int(t["NUNIV"], 8)
    script = BOOT + [
              f"pokecpu {t['WITCH']} 1 0", "press 107", ui_ready(t, frames=2),
              f"dumpcpu {t['UNIV']} {usize * nuniv} {dump}", "quit"]
    run_emu(script)
    if not dump.exists():
        check("the universe was dumped", False)
        return
    import struct
    d = dump.read_bytes()
    hostile = worlds = 0
    for i in range(nuniv):
        a = i * usize
        if a + usize > len(d):
            break
        if struct.unpack_from("<H", d, a)[0] == 0:
            continue
        f = struct.unpack_from("<H", d, a + uflags)[0]
        if f & 1:
            hostile += 1
        if f & (2 | 8 | 16):        # station, planet or sun
            worlds += 1
    check("witchspace is hostile", hostile >= 2, f"{hostile} hunters")
    check("and empty of everything else", worlds == 0,
          f"{worlds} bodies")

    # Legend's jump (JumpToPlanet): the travel time goes on the clock,
    # and the Targons intercept one jump in WI_ODDS of 256 - forced
    # here - leaving the ship halfway between the two systems with
    # three to five Targons, each with an ECM, and nothing else
    need = ["WI_ODDS", "HOME_X", "HOME_Y", "P_TIME", "SH_TARGONH", "SH_TARGON6H", "U.AI3", "F3_ECM", "U.TYPE"]
    if any(n not in t for n in need):
        check("interception symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    clock = [f"peekcpu {a['P_TIME'] + 2:o}", f"peekcpu {a['P_TIME'] + 4:o}"]
    jump = ["press 004", ui_ready(t)] + ["press 154", ui_ready(t, frames=1)] * 3 + ["press 107", ui_ready(t, frames=1)]
    lave, there = galaxy_model(7), galaxy_model(55)
    d = sys_distance(there, lave)
    minutes = (d * d // 10) * 5

    def elapsed(v):
        before, after = (v[0] & 0xFF) * 30 * 50 + (v[0] >> 8) * 50 + (v[1] & 0xFF), \
            (v[2] & 0xFF) * 30 * 50 + (v[2] >> 8) * 50 + (v[3] & 0xFF)
        return after - before

    # the interception ruled out: this jump is the one that arrives
    script = list(BOOT) + [poke_at(a["WI_ODDS"], 0)] + clock + jump + clock + \
        [f"peekcpu {t['WITCH']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 5:
        check("a jump puts its travel time on the clock, five minutes a tenth of an hour",
              minutes <= elapsed(v) <= minutes + 1 and v[4] == 0,
              f"{d} tenths: {elapsed(v)} minutes against {minutes}, witchspace {v[4]}")
    script = list(BOOT) + [poke_at(a["WI_ODDS"], 256)] + jump + \
        [f"peekcpu {t['WITCH']}", f"peekcpu {t['HOME_X']}", f"peekcpu {t['HOME_Y']}",
         f"dumpcpu {t['UNIV']} {usize * nuniv} {dump}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 3 and dump.exists():
        d_ = dump.read_bytes()
        targons = bodies = ecm = angry = 0
        for i in range(nuniv):
            base = i * usize
            ty = struct.unpack_from("<H", d_, base)[0]
            if ty == 0:
                continue
            f = struct.unpack_from("<H", d_, base + uflags)[0]
            if f & (2 | 8 | 16):
                bodies += 1
            if ty in (a["SH_TARGONH"], a["SH_TARGON6H"]):
                targons += 1
                angry += 1 if f & 1 else 0
                ecm += 1 if struct.unpack_from("<H", d_, base + a["U.AI3"])[0] & a["F3_ECM"] else 0
        check("the Targons' interception leaves the ship halfway between the systems",
              v[0] == 1 and v[1] == (lave["x"] + there["x"]) // 2 and v[2] == (lave["y"] + there["y"]) // 2,
              f"witchspace {v[0]}, home ({v[1]},{v[2]}) against ({(lave['x'] + there['x']) // 2},{(lave['y'] + there['y']) // 2})")
        check("with three to five hostile Targons, each with an ECM, and nothing else",
              3 <= targons <= 5 and angry == targons and ecm == targons and bodies == 0,
              f"{targons} Targons, {angry} hostile, {ecm} with an ECM, {bodies} bodies")
    script = list(BOOT) + [poke_at(a["WI_ODDS"], 0)] + jump + [f"peekcpu {t['WITCH']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if v:
        check("and at no odds a jump is never intercepted", v[0] == 0, f"witchspace {v[0]}")


def univ_dump(script_tail, extra=(), name="verify-cargo.bin"):
    """Run a flight script and read the whole universe back.

    Returns (types, flags) per slot, so a check can say what is in the
    sky without knowing the record's shape.
    """
    import struct
    t = syms.table()
    usize = int(t["U.SIZE"], 8)
    nuniv = int(t["NUNIV"], 8)
    uflags = int(t["U.FLAGS"], 8)
    dump = ROOT / "tmp" / name
    dump.parent.mkdir(exist_ok=True)
    if dump.exists():
        dump.unlink()
    script = list(BOOT)
    script += list(extra)
    script += list(script_tail)
    script += [f"dumpcpu {t['UNIV']} {usize * nuniv} {dump}", "quit"]
    out = run_emu(script)
    if not dump.exists():
        return None, None, out
    d = dump.read_bytes()
    types = [struct.unpack_from("<H", d, i * usize)[0] for i in range(nuniv)]
    flags = [struct.unpack_from("<H", d, i * usize + uflags)[0]
             for i in range(nuniv)]
    return types, flags, out


def check_cargo():
    """A wreck leaves cargo, and the scoop takes it aboard.

    The traffic ship is poked into a Cobra Mk III - three canisters in
    the original's own table - and parked dead ahead, disarmed and dead
    in the water, so the run tests the cargo and not the flying.
    Everything after the trigger is the game's own doing: the wreck
    leaves canisters, they hang where it died, and the commander flies
    into them.
    """
    print("cargo")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "U.TYPE", "U.X", "U.Y", "U.Z", "U.SPEED",
            "U.ENERGY", "U.FLAGS", "P_FUELSCOOPS", "CARGO", "NGOODS", "KILLS",
            "SH_COBRA3"]
    if any(n not in t for n in need):
        check("cargo symbols found", False)
        return
    usize = int(t["U.SIZE"], 8)
    ngoods = int(t["NGOODS"], 8)
    traffic = int(t["UNIV"], 8) + 4 * usize     # SPAWN_LOCALS fills the slots
                                                # in order: world, sun,
                                                # station, drop, then whoever
                                                # is flying about

    def field(name, val):
        v = val & 0xFFFF
        a = traffic + int(t[name], 8)
        return f"pokecpu {a:o} {v & 0xFF:o} {(v >> 8) & 0xFF:o}"

    def run(scoop):
        dump = ROOT / "tmp" / "verify-hold.bin"
        dump.parent.mkdir(exist_ok=True)
        if dump.exists():
            dump.unlink()
        # the traffic cleared first: the laser takes the lowest slot under
        # the sight, and whatever Lave had put in front of the Cobra took
        # the shots on one boot in two
        script = BOOT + [
                  "press 107", "run 40"] + clear_traffic(t) + [
                  field("U.TYPE", int(t["SH_COBRA3"], 8)),
                  # one shot's worth: a hurt Cobra lets a canister go in
                  # its critical band, and the canister, a lower slot under
                  # the sight, took every shot after it
                  field("U.ENERGY", 14), field("U.FLAGS", 0),
                  field("U.SPEED", 0), field("U.X", 0), field("U.Y", 0),
                  field("U.Z", 700)] + mind(t, 4, "COBRAMK3HT1", still=True)
        if scoop:
            script += [poke_dev(t, "P_FUELSCOOPS")]
        script += ["keydown 107", "run 60", "keyup 107", "run 500",
                   f"peekcpu {t['KILLS']}",
                   f"dumpcpu {t['CARGO']} {ngoods * 2} {dump}", "quit"]
        out = run_emu(script)
        vals = [int(v, 8) for v in PEEK.findall(out)]
        if not dump.exists() or not vals:
            return None, None
        import struct
        d = dump.read_bytes()
        held = sum(struct.unpack_from("<H", d, 2 * i)[0] for i in range(ngoods))
        return vals[0], held

    kills, held = run(scoop=True)
    if kills is None:
        check("the cargo run answered", False)
        return
    check("the Cobra was shot down", kills > 0, f"{kills} kills")
    check("its cargo was scooped up", held > 0, f"{held} in the hold")

    kills, held = run(scoop=False)
    if kills is None:
        check("the second cargo run answered", False)
        return
    check("and without a scoop nothing is taken aboard", held == 0,
          f"{held} in the hold")


def check_sun():
    """The scoop's other half: fuel off a star, and a cabin that heats.

    The sun is slot 1 of the universe SPAWN_LOCALS builds; it is moved
    to 4000 units dead ahead, which is inside the corona the gauge reads
    and well outside the range that ends the ship.
    """
    print("the sun")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "U.X", "U.Y", "U.Z", "PCABTEMP", "PFUEL",
            "P_FUELSCOOPS"]
    if any(n not in t for n in need):
        check("sun symbols found", False)
        return
    sun = int(t["UNIV"], 8) + 1 * int(t["U.SIZE"], 8)

    def field(name, val):
        v = val & 0xFFFF
        a = sun + int(t[name], 8)
        return f"pokecpu {a:o} {v & 0xFF:o} {(v >> 8) & 0xFF:o}"

    def run(scoop):
        script = BOOT + ["press 107", "run 40",
                         field("U.X", 0), field("U.Y", 0), field("U.Z", 4000),
                         f"pokecpu {t['PFUEL']} 24 0"]      # 20 tenths left
        if scoop:
            script += [poke_dev(t, "P_FUELSCOOPS")]
        script += ["run 120", f"peekcpu {t['PCABTEMP']}",
                   f"peekcpu {t['PFUEL']}", "quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
        return v if len(v) >= 2 else [None, None]

    temp, fuel = run(scoop=True)
    if temp is None:
        check("the sun run answered", False)
        return
    check("the cabin heats near a star", temp > 30, f"{temp} on the gauge")
    check("and a fuel scoop fills the tanks", fuel > 20, f"{fuel} tenths")
    temp, fuel = run(scoop=False)
    if temp is not None:
        check("without one, nothing is scooped", fuel == 20, f"{fuel} tenths")


def check_escorts():
    """What a ship launches: a hermit's rock lets fighters go when it is
    hurt (ReactionObject's launch band, SHIP_LAUNCH), and an angry station
    scrambles Vipers."""
    print("escorts")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "U.TYPE", "U.FLAGS", "U.LAUNCH", "NUNIV", "SH_ASTEROIDHO",
            "SH_SIDEWINDERH", "SH_ADDERH", "SH_VIPERH", "PENERGY", "PSHIELD_F", "WITCH", "UF_POLICE"]
    if any(n not in t for n in need):
        check("escort symbols found", False, f"missing {[n for n in need if n not in t]}")
        return
    a = {n: int(t[n], 8) for n in need}
    alive = [poke_at(a["PENERGY"], 255), poke_at(a["PSHIELD_F"], 255), poke_at(int(t["PSPEED"], 8), 0)]
    quiet = clear_traffic(t) + [poke_at(a["WITCH"], 1)]
    # A hermit's rock (Legend's Asteroid1, a manned rock whose header
    # launches two of a Sidewinder, a Krait and an Adder) dead ahead at
    # forty per cent of its energy: under half, every reaction it
    # launches one, half the time.  Nothing is shot at: what is under
    # test is the launch, and the fighters come out beside the rock
    # rather than under the sight.
    nest = ship_pokes(t, 5, "ASTEROIDHO", z=1500, energy=72, hyper=False) + \
        [poke_at(int(slot_field(t, 5, "U.LAUNCH"), 8), 2)]
    # the rock's hull knits a unit a reaction and passes half in four, so
    # its energy is held under half through the run, not poked once; and
    # the station is taken out of the sky, whose Vipers shot the fighters
    # down as they came out on one boot in two.  A fighter seen at any
    # sample counts: where the fighters are at the end is the fight's
    hurt = [poke_at(int(slot_field(t, 5, "U.ENERGY"), 8), 72)]
    nuniv = int(t["NUNIV"], 8)
    look = [f"peekcpu {slot_field(t, k, 'U.TYPE')}" for k in range(nuniv)]
    script = list(BOOT) + ["press 107", "run 40"] + quiet + nest + \
        [poke_at(int(slot_field(t, 2, "U.TYPE"), 8), 0)] + (alive + hurt + ["run 25"] + look) * 8 + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 8 * nuniv:
        check("the nest run answered", False)
        return
    seen = [sum(1 for ty in v[i:i + nuniv] if a["SH_SIDEWINDERH"] <= ty <= a["SH_ADDERH"])
            for i in range(0, 8 * nuniv, nuniv)]
    fighters, types = max(seen), v[-nuniv:]
    check("a hurt hermit's rock lets its fighters go", fighters > 0,
          f"{fighters} fighters, slots {types}")
    # The station, angry (UF_HOSTILE on its slot, which is what a shot at
    # a trader on its doorstep does to it), launches Vipers: one reaction
    # in four has a roll under 36.  The commander is kept alive and the
    # Vipers, hostile as they come, are what the law looks like.
    angry = [poke_at(int(slot_field(t, 2, "U.FLAGS"), 8), int(t["UF_STATION"], 8) | 1)]
    script = ["press 107", "run 40"] + quiet + angry
    for _ in range(6):
        script += alive + ["run 60"]
    types, flags, _out = univ_dump([], script, "verify-law.bin")
    if types is None:
        check("the station run answered", False)
        return
    vipers = sum(1 for ty, fl in zip(types, flags) if ty == a["SH_VIPERH"] and fl & a["UF_POLICE"])
    check("an angry station scrambles Vipers", vipers > 0, f"{vipers} Vipers, slots {types}")


def signed(v):
    """A peeked word as the CPU means it."""
    return v - 65536 if v >= 32768 else v


def poke_at(addr, val):
    """One pokecpu command: a word, low byte then high, in octal."""
    v = val & 0xFFFF
    return f"pokecpu {addr:o} {v & 0xFF:o} {(v >> 8) & 0xFF:o}"


# A device in the commander's record (src/pilot.mac) is one byte in
# Legend's packing: bit 7 set means not fitted.  pokecpu writes bytes, so
# a device is poked on its own; peekcpu reads the word at the even
# address, so a peeked device is the byte on its side of that word.
DEV_NONE = 0x80


def poke_dev(t, name, fitted=True):
    """Fit (or unfit) the device byte NAME in the record."""
    return f"pokecpu {int(t[name], 8):o} {0 if fitted else DEV_NONE:o}"


def peek_dev(t, name):
    """The peekcpu command that reads the word holding device NAME."""
    return f"peekcpu {int(t[name], 8) & ~1:o}"


def dev_fitted(t, name, word):
    """Whether the device NAME is fitted, given peek_dev's word."""
    b = (word >> 8) if int(t[name], 8) & 1 else word
    return not (b & DEV_NONE)


def clear_traffic(t):
    """Pokes that empty every slot but the world, the sun and the station.

    A check that parks a target dead ahead is testing the guns or the
    lock, not Lave's traffic - and the traffic crowds a parked ship
    aside (CO_SHEER gives way inside four hull radii), which moved the
    target out of the sight on the first build that ran faster.
    """
    return [poke_at(int(slot_field(t, s, "U.TYPE"), 8), 0)
            for s in range(3, int(t["NUNIV"], 8))]


_SHIPS = None
_SHIP_KEYS = None


def ship_stats(key):
    """The header numbers of one blueprint, by its KEY (src/res/legend/ships)."""
    global _SHIPS, _SHIP_KEYS
    if _SHIPS is None:
        ships = shiplib.read_dir(ROOT / "src/res/legend/ships")
        _SHIPS = {s.key.upper(): s.stats for s in ships}
        _SHIP_KEYS = [s.key.upper() for s in ships]       # type n is index n-1
    return _SHIPS[key.upper()]


def ai_pokes(t, slot, key, frame=1, counter=24, hyper=True, still=False):
    """Pokes that give a slot Legend's mind for the blueprint KEY, the way
    UNIV_ADD's SLOT_MIND would (src/ai.mac): its kind and flag bytes in
    U.KIND, its AI byte and counter in U.AI, no turn left in U.TURN, its
    faith and throttle in U.AI3, nothing to launch and no container in
    U.LAUNCH.  A check that pokes a ship into a slot has to poke these
    too: the last tenant's mind is still in the slot, and a Krait that
    inherits a wreck's counter or a Viper's frame does the wrong thing.
    """
    st = ship_stats(key)
    ai = st["objflags"]
    if not ai & 4:                    # the frame, unless the header fixes it
        ai = (ai & ~3) | frame
    ai &= ~4                          # born with the station near: not poked
    if not hyper:                     # a check that wants it to stay
        ai &= ~int(t["AI_HYPER"], 8)
    if still:                         # ... and to sit there: no targets,
        ai &= ~(int(t["AI_HYPER"], 8) | int(t["AI_ATTACK"], 8))   # no counter
    return [poke_at(int(slot_field(t, slot, "U.AI"), 8), ((counter & 0xFF) << 8) | (ai & 0xFF)),
            poke_at(int(slot_field(t, slot, "U.KIND"), 8), ((st["flags"] & 0xFF) << 8) | (st["type"] & 0xFF)),
            poke_at(int(slot_field(t, slot, "U.TURN"), 8), 0),
            poke_at(int(slot_field(t, slot, "U.AI3"), 8), 0x7E),
            poke_at(int(slot_field(t, slot, "U.LAUNCH"), 8), 0)]


def mind(t, slot, what, facing=False, hyper=True, still=False):
    """ai_pokes for WHAT (a blueprint key, or a type number as the checks
    hold them) plus an orientation - the identity, or turned about to
    face the commander - and, for a drop, the flags a drop carries.  A
    poked slot's matrix is whatever its last tenant left, which may be
    nothing at all; a ship steers by it, so it has to be a rotation."""
    if isinstance(what, int):
        ship_stats("VIPERH")
        what = _SHIP_KEYS[what - 1]
    st = ship_stats(what)
    mat = [16384, 0, 0, 0, 16384, 0, 0, 0, 16384]
    if facing:
        mat[0] = mat[8] = -16384
    out = ai_pokes(t, slot, what, hyper=hyper, still=still)
    out += [poke_at(int(slot_field(t, slot, "U.MAT"), 8) + 2 * i, m) for i, m in enumerate(mat)]
    # and the high words of the position: the checks that call this put
    # their ships at positive coordinates, and a stale high word puts a
    # ship beyond sixteen bits, where the AI leaves it alone
    out += [poke_at(int(slot_field(t, slot, h), 8), 0) for h in ("U.XH", "U.YH", "U.ZH")]
    if st["type"] & 7 == 7 and st["objflags"] & 0x80 and what.upper() != "TARGLETH":
        out.append(poke_at(int(slot_field(t, slot, "U.FLAGS"), 8),
                           int(t["UF_DROP"], 8) | int(t["UF_DERELICT"], 8)))
    return out


def ship_pokes(t, slot, key, x=0, y=0, z=1200, hostile=True, energy=None, speed=0, hyper=True,
               facing=False, still=False, **more):
    """A whole ship in a slot: the type by KEY, its position (32-bit, the
    high words by the sign), its flags - hostile or not, and what the
    header gives it: UF_POD for a capsule, UF_POLICE for the police -
    and Legend's mind (ai_pokes).  MORE overrides any field by name."""
    st = ship_stats(key)
    flags = 1 if hostile else 0
    if st["flags"] & 0x80:
        flags |= int(t["UF_POD"], 8)
    if st["type"] & 7 == 1:
        flags |= int(t["UF_POLICE"], 8)
    fields = {"U.TYPE": int(t["SH_" + key.upper()], 8), "U.FLAGS": flags,
              "U.EXPL": 0, "U.TARGET": 0, "U.MOTHER": 0, "U.SPEED": speed,
              "U.ENERGY": st["energy"] if energy is None else energy,
              "U.X": x, "U.Y": y, "U.Z": z,
              "U.XH": -1 if x < 0 else 0, "U.YH": -1 if y < 0 else 0, "U.ZH": -1 if z < 0 else 0}
    fields.update(more)
    out = [poke_at(int(slot_field(t, slot, k), 8), v) for k, v in fields.items()]
    return out + mind(t, slot, key, facing=facing, hyper=hyper, still=still)


def slot_field(t, slot, name):
    """Address of one field of one universe slot, as OCTAL digits.

    The emulator's peekcpu and dumpcpu read their addresses as octal and
    stop the script dead on anything else, so an address computed here
    has to be formatted before it goes anywhere near one - a decimal
    8564 is not a number it will take.
    """
    a = int(t["UNIV"], 8) + slot * int(t["U.SIZE"], 8) + int(t[name], 8)
    return f"{a:o}"


def check_docking():
    """What the slot lets in (src/dock.mac, eObjMove's docking): a level
    slot taken slowly docks; an angry station shoots what flies into its
    slot, which is death; too fast, or on the injectors, the ship is
    shoved back out to the station's distance and takes the bump - twice
    the speed and BUMP_HIT - on the front shield."""
    print("docking: what the slot lets in")
    t = syms.table()
    need = ["DOCKED", "PSPEED", "PROLL", "PSHIELD_F", "OVL_CUR", "OVL_TITLE", "TI_TICK",
            "STATION_Z", "UF_STATION", "UF_HOSTILE", "BUMP_HIT", "P_INJECTORS"]
    if any(n not in t for n in need):
        check("docking symbols found", False, f"missing {[n for n in need if n not in t]}")
        return
    a = {n: int(t[n], 8) for n in need}
    run = lambda sc: [int(x, 8) for x in PEEK.findall(run_emu(sc + ["quit"], fresh_disk("docking")))]
    fly = list(BOOT) + ["press 107", "run 100"] + clear_traffic(t)
    # the station dead ahead in its own slot, square on and still, the
    # commander not rolling; SPEED his throttle
    def park(speed=0, flags=None, z=600):
        out = [poke_at(a["PSPEED"], speed), poke_at(a["PROLL"], 0), poke_at(a["PSHIELD_F"], 160)]
        for f, v_ in (("U.X", 0), ("U.Y", 0), ("U.Z", z), ("U.SPEED", 0)):
            out.append(poke_at(int(slot_field(t, 2, f), 8), v_))
        out += [poke_at(int(slot_field(t, 2, "U.MAT"), 8) + 2 * k, 16384 if k in (0, 4, 8) else 0)
                for k in range(9)]
        if flags is not None:
            out.append(poke_at(int(slot_field(t, 2, "U.FLAGS"), 8), flags))
        return out
    shoved = [f"peekcpu {t['DOCKED']}", f"peekcpu {slot_field(t, 2, 'U.Z')}", f"peekcpu {t['PSHIELD_F']}"]

    v = run(fly + park() + ["run 150", f"peekcpu {t['DOCKED']}"])
    check("a level slot taken slowly docks", v == [1], f"docked {v}")

    # (the title is overlay 0, which is also what an unset word reads, so
    # its frame counter has to be seen running as well)
    v = run(fly + park(flags=a["UF_STATION"] | a["UF_HOSTILE"]) + ["run 300", f"peekcpu {t['OVL_CUR']}",
            f"peekcpu {t['DOCKED']}", f"peekcpu {t['TI_TICK']}", "run 20", f"peekcpu {t['TI_TICK']}"])
    check("an angry station's slot is death: the title again",
          len(v) == 4 and v[0] == a["OVL_TITLE"] and v[1] == 0 and v[3] > v[2],
          f"overlay {v[:1]}, docked {v[1:2]}, title frames {v[2:]}")

    v = run(fly + park(speed=20) + [ui_ready(t, frames=2)] + shoved)
    check("too fast: shoved back out, and the bump taken on the front shield",
          len(v) == 3 and v[0] == 0 and v[1] > a["STATION_Z"] - 200 and v[2] <= 160 - (2 * 20 + a["BUMP_HIT"]),
          f"docked {v[:1]}, station at {v[1:2]}, shield {v[2:3]}")

    # the injectors run only while something locks the J-drive: the
    # station held just outside the slot's box first, then brought in
    v = run(fly + [poke_dev(t, "P_INJECTORS")] + park(z=2000) + ["run 2", "keydown 075", "run 3"] +
            park() + [ui_ready(t, frames=2)] + shoved + ["keyup 075"])
    # (once shoved out the station no longer locks the drive, which may
    # then carry the ship back toward it: "far" is all that is asked)
    check("on the injectors: too fast as well, and the bump taken",
          len(v) == 3 and v[0] == 0 and v[1] > 2000 and v[2] < 160,
          f"docked {v[:1]}, station at {v[1:2]}, shield {v[2:3]}")


def check_views():
    """The commander can look four ways, and the sky changes when he does.

    Right after a launch the station and the world are dead ahead and
    nothing at all is behind, so the segment buffer says which way the
    view is pointing without anything having to be poked.
    """
    print("views")
    t = syms.table()
    if any(n not in t for n in ("VIEW_DIR", "SEGPREV", "PENERGY",
                                "PSHIELD_F")):
        check("view symbols found", False)
        return
    # The banks are refilled between presses.  Looking anywhere but
    # forward draws almost nothing, so the game runs several times as
    # many frames per emulated tick, and the AI shoots per frame: four
    # presses at Lave is enough for the traffic to finish the commander
    # off in the middle of the check, and a dead commander sits in
    # PLAYER_DEAD's three-second hold with the key doing nothing.  What
    # is under test here is the key, not how long he lives.
    alive = [poke_at(int(t["PENERGY"], 8), 255),
             poke_at(int(t["PSHIELD_F"], 8), 255)]
    seen = []
    for presses in range(5):
        script = BOOT + ["press 107", "run 150"]
        for _ in range(presses):
            script += alive + ["press 030", "run 40"]
        script += ["run 60", f"peekcpu {t['VIEW_DIR']}",
                   f"peekcpu {t['SEGPREV']}", "quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
        seen.append(tuple(v[:2]) if len(v) >= 2 else (None, None))
    dirs = [d for d, _ in seen]
    check("the view key goes round the four views", dirs == [0, 1, 2, 3, 0],
          f"{dirs}")
    front, rear = seen[0][1], seen[1][1]
    check("and the sky behind is not the sky ahead",
          front is not None and rear is not None and rear < front,
          f"{front} segments ahead, {rear} behind")


def check_kit():
    """The ECM, the energy bomb, the escape capsule and the laser mounts."""
    print("the ship's kit")
    t = syms.table()
    need = ["P_ECM", "P_EBOMB", "P_ESCPOD", "PENERGY", "PSHIELD_F", "DOCKED",
            "P_FREECARGO", "P_LARGECARGO", "KILLS", "PLASERS", "PLASTEMP",
            "LAS_PULSE", "UNIV", "U.SIZE",
            "U.TYPE", "U.FLAGS", "U.TARGET", "U.X", "U.Y", "U.Z", "U.EXPL",
            "U.ENERGY", "SH_MISSILE", "UF_MISSILE"]
    if any(n not in t for n in need):
        check("kit symbols found", False,
              f"missing {[n for n in need if n not in t]}")
        return

    def poke_slot(slot, name, val):
        return poke_at(int(slot_field(t, slot, name), 8), val)

    # A missile with the commander's name on it, poked into a free slot:
    # it flies itself, and the shields feel it.
    #
    # It goes in the LAST slot, and the number is worked out from NUNIV
    # rather than written down.  The sky grew from eight slots to ten,
    # slot 7 stopped being the last one, and the station's Vipers and
    # the traffic started landing in it - which reads as a missile that
    # was never spent and is really a Viper that arrived after it.  The
    # faster the game runs, the more frames there are in the same number
    # of emulated ticks and the more often it happens.
    last = int(t["NUNIV"], 8) - 1

    def incoming(slot=last):    # the station's Vipers take the earlier
                                # ones now that it patrols
        return [poke_slot(slot, "U.TYPE", int(t["SH_MISSILE"], 8)),
                poke_slot(slot, "U.FLAGS", int(t["UF_MISSILE"], 8) | 1),
                poke_slot(slot, "U.TARGET", -1),
                poke_slot(slot, "U.ENERGY", 120),
                poke_slot(slot, "U.EXPL", 0),
                # the slot is poked, not UNIV_ADDed, so whatever speed
                # and heading its last tenant left are still in it; with
                # sixteen slots the last one has had tenants, and a
                # missile that inherits a canister's drift flies away
                # from the commander at 400 a frame (2026-09-19)
                poke_slot(slot, "U.SPEED", 0),
                poke_slot(slot, "U.X", 0),
                poke_slot(slot, "U.Y", 0),
                poke_slot(slot, "U.Z", 1500)]

    # The slot is WATCHED rather than read at the end.  Lave is a busy
    # place: the poked missile closes, strikes and is gone by about the
    # eightieth tick, and by the hundred and sixtieth something else out
    # there has locked on and put a missile of its own in the slot that
    # has just come free.  Reading the slot once, at the end, therefore
    # said "the missile was never spent" about a completely different
    # missile - and did so only once the renderer got quick enough to
    # give the AI the extra frames to do it in.
    script = BOOT + ["press 107", "run 60"] + incoming()
    for _ in range(10):
        script += ["run 20", f"peekcpu {t['PSHIELD_F']}",
                   f"peekcpu {slot_field(t, last, 'U.TYPE')}"]
    script += ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    rows = [v[i:i + 2] for i in range(0, len(v) - 1, 2)]
    if rows:
        shields = [r[0] for r in rows]
        types = [r[1] for r in rows]
        check("a missile fired at you arrives", min(shields) < 255,
              f"forward shield fell to {min(shields)}")
        check("and is spent when it does", 0 in types,
              f"slot over the run {types}")

    # ... unless the ECM is switched on, which costs the banks
    #
    # The explosion counter is WATCHED, not read once at a fixed tick,
    # for the same reason the slot above is: it counts DOWN a frame at a
    # time, so a faster build has already finished with it by the time a
    # single peek arrives.  Reading it at the thirtieth tick said
    # "countdown 2" on one build and "countdown 0" on one a few percent
    # quicker, and the second was the one that had done the job sooner.
    script = BOOT + ["press 107", "run 60",
                     poke_dev(t, "P_ECM")] + incoming() + ["press 031"]
    for _ in range(10):
        script += ["run 6",
                   f"peekcpu {slot_field(t, last, 'U.EXPL')}",
                   f"peekcpu {slot_field(t, last, 'U.TYPE')}"]
    script += [f"peekcpu {t['PENERGY']}",
               f"peekcpu {t['PSHIELD_F']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 22:
        expl = v[0:20:2]
        types = v[1:20:2]
        energy, shield = v[20], v[21]
        # The shield is no evidence either way: whatever else is in the
        # sky is shooting the whole time.  What says the ECM worked is
        # the missile coming apart before it arrived - seen breaking up
        # at any point in the run, or simply gone from the slot.
        check("the ECM breaks a missile up",
              any(e != 0 for e in expl) or 0 in types,
              f"countdowns {expl}, slot {types}, shield {shield}")
        # its cost - four a frame for the twelve frames the field runs
        # - is check_ecm's business

    # the energy bomb clears the sky and pays for what it kills
    script = BOOT + ["press 107", "run 150",
                     f"peekcpu {t['KILLS']}",
                     poke_dev(t, "P_EBOMB"), "press 032", "run 40",
                     f"peekcpu {t['KILLS']}", peek_dev(t, "P_EBOMB"), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 3:
        check("the energy bomb clears the sky", v[1] > v[0],
              f"{v[0]} kills before, {v[1]} after")
        check("and is used up", not dev_fitted(t, "P_EBOMB", v[2]),
              f"{v[2]:o}")

    # the escape capsule: a new ship, in the station, with nothing in it
    script = BOOT + ["press 107", "run 60",
                     poke_dev(t, "P_ESCPOD"),
                     poke_dev(t, "P_LARGECARGO"),          # the larger bay,
                     poke_at(int(t["P_FREECARGO"], 8), 35),  # 35 tonnes free
                     "press 035", "run 60",
                     f"peekcpu {t['DOCKED']}", peek_dev(t, "P_ESCPOD"),
                     f"peekcpu {t['P_FREECARGO']}", peek_dev(t, "P_LARGECARGO"),
                     "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("kit")))]
    if len(v) >= 4:
        check("the capsule puts you back in the station", v[0] == 1, str(v[0]))
        check("and is gone with the ship it left",
              not dev_fitted(t, "P_ESCPOD", v[1]), f"{v[1]:o}")
        check("along with everything bolted to it",
              v[2] == 20 and not dev_fitted(t, "P_LARGECARGO", v[3]),
              f"{v[2]} tonnes free, bay {v[3]:o}")

    # a mount with no gun in it does nothing at all
    script = BOOT + ["press 107", "run 60", "press 030", "run 40",
                     "keydown 107", "run 40", "keyup 107",
                     f"peekcpu {t['PLASTEMP']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if v:
        check("the trigger is dead where there is no gun", v[0] == 0,
              f"laser temperature {v[0]}")
    script = BOOT + ["press 107", "run 60",
                     poke_at(int(t["PLASERS"], 8) + 2,
                             int(t["LAS_PULSE"], 8)),         # a pulse laser aft
                     "press 030", "run 40",
                     "keydown 107", "run 40", "keyup 107",
                     f"peekcpu {t['PLASTEMP']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if v:
        check("and fires where there is one", v[0] > 0,
              f"laser temperature {v[0]}")


def check_collisions():
    """Ships that run into the commander break up on his hull."""
    print("collisions")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "U.TYPE", "U.X", "U.Y", "U.Z", "U.FLAGS",
            "U.EXPL", "KILLS", "PSHIELD_F", "SH_SIDEWINDER"]
    if any(n not in t for n in need):
        check("collision symbols found", False)
        return

    def poke_slot(slot, name, val):
        return poke_at(int(slot_field(t, slot, name), 8), val)

    script = BOOT + ["press 107", "run 60",
                     f"peekcpu {t['KILLS']}",
                     poke_slot(5, "U.TYPE", int(t["SH_SIDEWINDER"], 8)),
                     poke_slot(5, "U.FLAGS", 0),
                     poke_slot(5, "U.EXPL", 0),
                     poke_slot(5, "U.X", 0),
                     poke_slot(5, "U.Y", 0),
                     poke_slot(5, "U.Z", 40)] + mind(t, 5, "SIDEWINDERH", still=True) + [
                     "run 40",
                     f"peekcpu {t['KILLS']}",
                     f"peekcpu {t['PSHIELD_F']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 3:
        check("the collision run answered", False, f"{len(v)} peeks")
        return
    check("a ship flown into breaks up", v[1] > v[0],
          f"{v[0]} kills before, {v[1]} after")
    check("and the hull pays for it", v[2] < int(t["ENERGY_MAX"], 8),
          f"forward shield {v[2]}")


def peek_byte(t, name, off=0):
    """The peekcpu command for the word holding byte NAME+off."""
    return f"peekcpu {(int(t[name], 8) + off) & ~1:o}"


def byte_of(t, name, word, off=0):
    """Byte NAME+off out of peek_byte's word (odd addresses are the high
    half)."""
    return (word >> 8) & 0xFF if (int(t[name], 8) + off) & 1 else word & 0xFF


def poke_byte(t, name, val, off=0):
    """pokecpu writes bytes: one byte of the record, alone."""
    return f"pokecpu {int(t[name], 8) + off:o} {val & 0xFF:o}"


def check_missions():
    """Legend's missions (src/mission.mac, src/ovl_mission.mac): the nova.
    A galactic jump with a kill's leave to issue one puts the commander
    in a system whose star is going nova, the tank dry; the market asks
    him to take the refugees, which fits the life support and sells the
    hold; launching lights the fuse and the star swells; a jump out goes
    to a galaxy at random; and the refugees set down at a main station
    elsewhere pay a hundred gem-stones.  In the first galaxy nothing is
    issued."""
    print("missions: the nova")
    t = syms.table()
    need = ["P_M1", "P_MSTAT", "P_MCOMPLETE", "P_FUEL", "P_GALAXY", "P_COLOUR",
            "P_LIFESUPPORT", "P_FREECARGO", "CARGO", "NOVA_R", "SCREEN", "DOCKED",
            "GALNUM", "P_GALDRIVE"]
    if any(n not in t for n in need):
        check("mission symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    chart = ["press 004", ui_ready(t)]
    market = ["press 004", ui_ready(t)] * 3 + ["press 004"] + mission_ready(t)
    # 1. issued on arrival in galaxy 1 (the standard drive from Lave)
    script = list(BOOT) + [poke_dev(t, "P_GALDRIVE")] + chart + ["press 107", ui_ready(t, frames=1),
        f"peekcpu {t['GALNUM']}", peek_byte(t, "P_M1"), peek_byte(t, "P_MCOMPLETE"),
        f"peekcpu {t['P_FUEL']}", peek_byte(t, "P_COLOUR"), peek_byte(t, "P_MSTAT")]
    # 2. the market asks; Д takes them aboard
    script += market + ["press 057", ui_ready(t), peek_byte(t, "P_M1", 1), peek_dev(t, "P_LIFESUPPORT"),
        f"peekcpu {t['P_FREECARGO']}", f"peekcpu {t['SCREEN']}"]
    # 3. back to the cockpit (СТОП round to 0) and out: the fuse, the swelling
    script += ["press 004", ui_ready(t)] * 6 + [f"peekcpu {t['SCREEN']}", "press 107", ui_ready(t, frames=3), peek_byte(t, "P_M1"),
        f"peekcpu {t['NOVA_R']}", "run 60", f"peekcpu {t['NOVA_R']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("nova")))]
    if len(v) < 14:
        check("the nova run answered", False, f"{len(v)} peeks")
        return
    gal, m1, comp, fuel, col, mstat = v[0], byte_of(t, "P_M1", v[1]), byte_of(t, "P_MCOMPLETE", v[2]), \
        v[3], byte_of(t, "P_COLOUR", v[4]), byte_of(t, "P_MSTAT", v[5])
    check("a jump into galaxy 1 with leave to issue one: the nova, a red star, the tank dry",
          gal == 1 and m1 == 1 and comp & 1 and fuel == 0 and col == 2 and not mstat & 0x80,
          f"galaxy {gal}, M1 {m1}, complete {comp:o}, fuel {fuel}, colour {col}, stat {mstat:o}")
    aboard = byte_of(t, "P_M1", v[6], 1)
    check("the market asks, and yes takes the refugees: life support fitted, no room left",
          aboard == 1 and dev_fitted(t, "P_LIFESUPPORT", v[7]) and v[8] == 0 and v[9] == 4,
          f"aboard {aboard}, life support {v[7]:o}, free {v[8]}, screen {v[9]}")
    m1, r1, r2 = byte_of(t, "P_M1", v[11]), signed(v[12]), signed(v[13])
    check("launching lights the fuse, and the star swells",
          m1 == 2 and 0 < r1 < r2, f"screen {v[10]}, M1 {m1}, radius {r1} then {r2}")

    # 4. the jump out of the nova's system goes to another galaxy at
    #    random, and the nova is behind; the refugees are still aboard
    script = list(BOOT) + [poke_byte(t, "P_M1", 2), poke_byte(t, "P_M1", 1, 1),
        poke_byte(t, "P_MSTAT", 0)] + chart + [
        "press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1)] + steady_drive(t) + ["press 107", ui_ready(t, frames=1),
        f"peekcpu {t['GALNUM']}", peek_byte(t, "P_M1"), peek_byte(t, "P_M1", 1), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("nova")))]
    if len(v) >= 3:
        check("the jump out goes to a galaxy of the eight at random, the refugees aboard",
              0 <= v[0] < 8 and byte_of(t, "P_M1", v[1]) == 0 and byte_of(t, "P_M1", v[2], 1) == 1,
              f"galaxy {v[0]}, M1 {byte_of(t, 'P_M1', v[1])}, aboard {byte_of(t, 'P_M1', v[2], 1)}")

    # 5. set down at a main station with no nova: a hundred gem-stones
    script = list(BOOT) + [poke_byte(t, "P_M1", 0), poke_byte(t, "P_M1", 1, 1),
        poke_byte(t, "P_MCOMPLETE", 0)] + market + ["press 107", ui_ready(t, frames=1),
        peek_byte(t, "P_M1", 1), f"peekcpu {a['CARGO'] + 30:o}", peek_byte(t, "P_MCOMPLETE"),
        f"peekcpu {t['P_FREECARGO']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("nova")))]
    if len(v) >= 4:
        check("set down at a main station, the refugees pay a hundred gem-stones",
              byte_of(t, "P_M1", v[0], 1) == 0 and v[1] == 100 and byte_of(t, "P_MCOMPLETE", v[2]) & 1
              and v[3] > 0, f"aboard {byte_of(t, 'P_M1', v[0], 1)}, gems {v[1]}, "
              f"complete {byte_of(t, 'P_MCOMPLETE', v[2]):o}, free {v[3]}")

    # 6. a jump in the first galaxy issues nothing, and the leave is kept
    script = list(BOOT) + chart + ["press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1)] + \
        steady_drive(t) + ["press 107", ui_ready(t, frames=1), f"peekcpu {t['GALNUM']}",
        peek_byte(t, "P_M1"), peek_byte(t, "P_MSTAT"), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("nova")))]
    if len(v) >= 3:
        check("in the first galaxy nothing is issued",
              v[0] == 0 and byte_of(t, "P_M1", v[1]) == 0 and byte_of(t, "P_MSTAT", v[2]) & 0x80,
              f"galaxy {v[0]}, M1 {byte_of(t, 'P_M1', v[1])}, stat {byte_of(t, 'P_MSTAT', v[2]):o}")


def check_missions2():
    """Missions 2 and 3 and the alien computer (src/mission.mac): the
    cloaked Asp's wreck lets go the cloaking device, which the scoop
    fits; the cloak goes on and off with its energy; an Asp gone from
    the sky lets another come; the 128th Targon under the laser lets go
    the alien computer; mission 2 and 3 are issued on arrival by the
    rating's bits; the Targon station is offered at the dock (the naval
    ECM fitted at once), is the target on arrival, is angry, comes down
    to a missile of the commander's, and pays at the next dock."""
    print("missions: the cloaked Asp, the alien computer, the Targon station")
    t = syms.table()
    need = ["P_M2", "P_M3", "P_MSTAT", "P_MCOMPLETE", "P_MALIEN", "P_CLOAK", "P_ALIENCOMP",
            "P_ECM", "P_FUELSCOOPS", "UF_MISSION", "UF_MISSILE", "SH_CARGOHC", "SH_CARGOHA",
            "SH_ASPH", "SH_MISSILEH", "P_RATING", "SYS_INDEX", "P_DOCKCOMP", "DOCKED", "NUNIV"]
    if any(n not in t for n in need):
        check("mission symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    nuniv = a["NUNIV"]
    fly = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t)
    types = [f"peekcpu {slot_field(t, k, 'U.TYPE')}" for k in range(nuniv)]

    def run(script, name="missions2"):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk(name)))]

    # 1. the marked Asp, shot down: the cloaking device's container
    asp = ship_pokes(t, 3, "ASPH", z=1000, energy=10, hyper=False, facing=True, still=True,
                     **{"U.FLAGS": 1 | a["UF_MISSION"]})
    v = run(fly + asp + [poke_byte(t, "P_M2", 2), "keydown 107", "run 120", "keyup 107",
                         peek_byte(t, "P_M2")] + types)
    if len(v) >= 1 + nuniv:
        check("the marked Asp shot down lets go the cloaking device's container",
              byte_of(t, "P_M2", v[0]) == 3 and a["SH_CARGOHC"] in v[1:],
              f"M2 {byte_of(t, 'P_M2', v[0])}, slots {v[1:]}")

    # 2. scooped: the cloak fitted, mission 2 complete and closed
    box = ship_pokes(t, 3, "CARGOHC", z=300, hostile=False, hyper=False)
    v = run(fly + [poke_dev(t, "P_FUELSCOOPS"), poke_dev(t, "P_CLOAK", fitted=False),
                   poke_byte(t, "P_M2", 3), poke_byte(t, "P_MSTAT", 0x42),
                   poke_byte(t, "P_MCOMPLETE", 0)] + box + ["run 30",
                   peek_dev(t, "P_CLOAK"), peek_byte(t, "P_MCOMPLETE"), peek_byte(t, "P_MSTAT"),
                   peek_byte(t, "P_M2")])
    if len(v) >= 4:
        check("scooped, it fits the cloak and completes mission 2",
              dev_fitted(t, "P_CLOAK", v[0]) and byte_of(t, "P_MCOMPLETE", v[1]) & 2
              and not byte_of(t, "P_MSTAT", v[2]) & 0x40 and byte_of(t, "P_M2", v[3]) == 0,
              f"cloak {v[0]:o}, complete {byte_of(t, 'P_MCOMPLETE', v[1]):o}, "
              f"stat {byte_of(t, 'P_MSTAT', v[2]):o}, M2 {byte_of(t, 'P_M2', v[3])}")

    # 3. the cloak: on at #50 of energy; and 4. an Asp gone lets another come
    far = ship_pokes(t, 3, "ASPH", z=3000, energy=200, hyper=False, still=True,
                     **{"U.FLAGS": a["UF_MISSION"]})
    v = run(fly + far + [poke_byte(t, "P_M2", 2), "run 60", peek_byte(t, "P_M2")])
    w = run(fly + [poke_byte(t, "P_M2", 1), "run 20", peek_byte(t, "P_M2")])
    if v and w:
        check("the Asp's cloak goes on with its energy, and an Asp gone lets another come",
              byte_of(t, "P_M2", v[0]) == 1 and byte_of(t, "P_M2", w[0]) == 0,
              f"M2 {byte_of(t, 'P_M2', v[0])} with the Asp, {byte_of(t, 'P_M2', w[0])} without")

    # 5. the 128th Targon under the laser: the alien computer's container
    targ = ship_pokes(t, 3, "TARGONH", z=1000, energy=10, hyper=False, facing=True, still=True)
    v = run(fly + targ + [poke_byte(t, "P_MALIEN", 0xFE), "keydown 107", "run 120", "keyup 107",
                          peek_byte(t, "P_MALIEN")] + types)
    if len(v) >= 1 + nuniv:
        check("the 128th Targon under the laser lets go the alien computer",
              byte_of(t, "P_MALIEN", v[0]) == 0 and a["SH_CARGOHA"] in v[1:],
              f"counter {byte_of(t, 'P_MALIEN', v[0])}, slots {v[1:]}")
    box = ship_pokes(t, 3, "CARGOHA", z=300, hostile=False, hyper=False)
    v = run(fly + [poke_dev(t, "P_FUELSCOOPS"), poke_byte(t, "P_MCOMPLETE", 0)] + box +
            ["run 30", peek_dev(t, "P_ALIENCOMP"), peek_byte(t, "P_MCOMPLETE")])
    if len(v) >= 2:
        check("and scooped, it is fitted and its bit complete",
              dev_fitted(t, "P_ALIENCOMP", v[0]) and byte_of(t, "P_MCOMPLETE", v[1]) & 8,
              f"device {v[0]:o}, complete {byte_of(t, 'P_MCOMPLETE', v[1]):o}")

    # 6. issued on arrival in galaxy 1, by the rating's third byte against
    #    what is complete: bit 1 open - the Asp may come; bit 2 - the station
    chart = ["press 004", ui_ready(t)]
    gal = [poke_dev(t, "P_GALDRIVE")] + chart + ["press 107", ui_ready(t, frames=1)]
    v = run(list(BOOT) + [poke_byte(t, "P_RATING", 1, 2), poke_byte(t, "P_MCOMPLETE", 1)] + gal +
            [peek_byte(t, "P_MSTAT"), peek_byte(t, "P_M1")])
    w = run(list(BOOT) + [poke_byte(t, "P_RATING", 3, 2), poke_byte(t, "P_MCOMPLETE", 3)] + gal +
            [peek_byte(t, "P_M3"), peek_byte(t, "P_MCOMPLETE")])
    if len(v) >= 2 and len(w) >= 2:
        check("on arrival: the Asp's leave when the nova is behind, the station after it",
              byte_of(t, "P_MSTAT", v[0]) & 0x42 == 0x42 and byte_of(t, "P_M1", v[1]) == 0
              and byte_of(t, "P_M3", w[0]) == 1 and byte_of(t, "P_MCOMPLETE", w[1]) & 4,
              f"stat {byte_of(t, 'P_MSTAT', v[0]):o}, M3 {byte_of(t, 'P_M3', w[0])}, "
              f"complete {byte_of(t, 'P_MCOMPLETE', w[1]):o}")

    # 7. offered at the next dock: yes fits the naval ECM and names the system
    dock = [poke_dev(t, "P_DOCKCOMP"), "press 107", "run 50"] + ["press 166", "run 20"] * 4 + ["run 700"]
    v = run(list(BOOT) + [poke_byte(t, "P_M3", 2), poke_byte(t, "P_M3", 9, 1)] + dock +
            ["press 057", "run 120", "press 107", "run 60", f"peekcpu {t['DOCKED']}",
             peek_byte(t, "P_M3"), peek_dev(t, "P_ECM")])
    if len(v) >= 3:
        ecm = byte_of(t, "P_ECM", v[2])
        check("docking, the station is offered; yes fits the naval ECM",
              v[0] == 1 and byte_of(t, "P_M3", v[1]) == 3 and ecm & 0xC1 == 1,
              f"docked {v[0]}, M3 {byte_of(t, 'P_M3', v[1])}, ECM {ecm:o}")

    # 8. arriving at the target: 4, and the station there is angry.  The
    #    jump is the nova check's; where it lands is read off a first run
    jump = chart + ["press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1)] + steady_drive(t) + ["press 107", ui_ready(t, frames=1)]
    v = run(list(BOOT) + jump + [f"peekcpu {t['SYS_INDEX']}"])
    if not v:
        check("the jump run answered", False)
        return
    there = v[-1]
    v = run(list(BOOT) + [poke_byte(t, "P_M3", 3), poke_byte(t, "P_M3", there, 1)] + jump +
            [peek_byte(t, "P_M3"), "press 107", "run 60", f"peekcpu {slot_field(t, 2, 'U.FLAGS')}"])
    if len(v) >= 2:
        check("arriving at the target makes it 4, and the station there is angry",
              byte_of(t, "P_M3", v[0]) == 4 and v[1] & 1, f"M3 {byte_of(t, 'P_M3', v[0])}, "
              f"station flags {v[1]:o}")

    # 9. a missile of the commander's with the naval ECM aboard brings it
    #    down; the next arrival makes it 5, and the next dock pays.  After
    #    a launch the station is ahead: the missile is put between
    missile = ship_pokes(t, 3, "MISSILEH", z=600, hostile=False, hyper=False,
                         **{"U.FLAGS": a["UF_MISSILE"], "U.TARGET": 3, "U.ENERGY": 250})
    v = run(fly + [poke_byte(t, "P_M3", 4), poke_byte(t, "P_M3", 200, 1),
                   poke_byte(t, "P_ECM", 1)] + missile + ["run 400", peek_byte(t, "P_M3"),
                   f"peekcpu {slot_field(t, 2, 'U.FLAGS')}", f"peekcpu {slot_field(t, 2, 'U.TYPE')}"])
    if len(v) >= 3:
        check("a missile of the commander's, the naval ECM aboard, brings the station down",
              byte_of(t, "P_M3", v[0]) & 8 and not (v[2] and v[1] & 2),
              f"M3 {byte_of(t, 'P_M3', v[0]):o}, slot 2 type {v[2]} flags {v[1]:o}")
    v = run(list(BOOT) + [poke_byte(t, "P_M3", 0x0C), poke_byte(t, "P_MCOMPLETE", 0),
                          poke_at(a["P_RATING"], 1), poke_at(a["P_RATING"] + 2, 0)] + jump + [peek_byte(t, "P_M3")] + dock +
            ["press 107", "run 60", f"peekcpu {t['DOCKED']}", peek_byte(t, "P_M3"),
             peek_byte(t, "P_MCOMPLETE"), f"peekcpu {a['P_RATING'] + 2:o}"])
    if len(v) >= 5:
        check("the next arrival makes it 5, and the next dock pays #FFFF and completes it",
              byte_of(t, "P_M3", v[0]) == 5 and v[1] == 1 and byte_of(t, "P_M3", v[2]) == 0
              and byte_of(t, "P_MCOMPLETE", v[3]) & 4 and v[4] >= 1,
              f"M3 {byte_of(t, 'P_M3', v[0])} then {byte_of(t, 'P_M3', v[2])}, docked {v[1]}, "
              f"complete {byte_of(t, 'P_MCOMPLETE', v[3]):o}, rating high {v[4]}")


def check_missions3():
    """Missions 4 and 5 (src/mission.mac, src/ovl_mission.mac): issued on
    arrival by what is complete, the rating and the kills; the
    Constrictor's trail - the offer, the rumours at the named systems,
    the galaxy hop, the last phase's leave, the kill, the naval laser;
    the plans - the offer forty light years off, the interception, the
    arrival and the naval energy unit."""
    print("missions: the Constrictor and the plans")
    t = syms.table()
    need = ["P_M4", "P_M5", "P_MCOMPLETE", "P_DESTR", "P_RATING", "P_LASERS", "P_ENERGYUNIT",
            "SYS_INDEX", "WITCH", "DOCKED", "UF_MISSION", "NUNIV"]
    if any(n not in t for n in need):
        check("mission symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}

    def run(script):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk("missions3")))]

    def m4(w, off=0):
        return byte_of(t, "P_M4", w, off)

    chart = ["press 004", ui_ready(t)]
    gal = [poke_dev(t, "P_GALDRIVE")] + chart + ["press 107", ui_ready(t, frames=1)]
    jump = chart + ["press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1)] + steady_drive(t) + ["press 107", ui_ready(t, frames=1)]
    dock = [poke_dev(t, "P_DOCKCOMP"), "press 107", "run 50"] + ["press 166", "run 20"] * 4 + ["run 700"]
    kills = lambda n: poke_at(a["P_DESTR"], n)

    # 1. issued: the Constrictor after 0, 1, 2 with 800 kills; the plans
    #    after 4 with 1280
    v = run(list(BOOT) + [poke_byte(t, "P_RATING", 1, 2), poke_byte(t, "P_MCOMPLETE", 7), kills(800)] +
            gal + [peek_byte(t, "P_M4"), peek_byte(t, "P_M1")])
    w = run(list(BOOT) + [poke_byte(t, "P_RATING", 2, 2), poke_byte(t, "P_MCOMPLETE", 0x17), kills(1280)] +
            gal + [peek_byte(t, "P_M5")])
    x = run(list(BOOT) + [poke_byte(t, "P_RATING", 1, 2), poke_byte(t, "P_MCOMPLETE", 7), kills(799)] +
            gal + [peek_byte(t, "P_M4"), peek_byte(t, "P_M1")])
    if len(v) >= 2 and w and len(x) >= 2:
        check("the Constrictor is issued with 800 kills, the plans with 1280; short, a basic one",
              m4(v[0]) == 1 and byte_of(t, "P_M5", w[0]) == 1 and m4(x[0]) == 0
              and byte_of(t, "P_M1", x[1]) == 0,
              f"M4 {m4(v[0])}, M5 {byte_of(t, 'P_M5', w[0])}, short: M4 {m4(x[0])}")

    # 2. the offer at the dock: a system of this galaxy, not this one
    v = run(list(BOOT) + [poke_byte(t, "P_M4", 1)] + dock + ["press 057", "run 120", "press 107",
            "run 60", f"peekcpu {t['DOCKED']}", peek_byte(t, "P_M4"), peek_byte(t, "P_M4", 1),
            peek_byte(t, "P_M4", 2)])
    if len(v) >= 4:
        check("the Constrictor offered: yes, and the trail starts in another system",
              v[0] == 1 and m4(v[1]) == 4 and m4(v[2], 1) == 0 and m4(v[3], 2) != 7,
              f"docked {v[0]}, M4 {m4(v[1]):o}, galaxy {m4(v[2], 1)}, system {m4(v[3], 2)}")

    # 3. a rumour due in phase 1: the next system, a hop counted; in
    #    phase 2 the next galaxy
    v = run(list(BOOT) + [poke_byte(t, "P_M4", 0o204), poke_byte(t, "P_M4", 7, 2)] + dock +
            ["press 107", "run 60", peek_byte(t, "P_M4"), peek_byte(t, "P_M4", 2)])
    w = run(list(BOOT) + [poke_byte(t, "P_M4", 0o210), poke_byte(t, "P_M4", 47, 1)] + dock +
            ["press 107", "run 60", peek_byte(t, "P_M4"), peek_byte(t, "P_M4", 1)])
    if len(v) >= 2 and len(w) >= 2:
        check("a rumour at the dock: the next system and a hop, or the next galaxy round",
              m4(v[0]) == 5 and m4(v[1], 2) != 7 and m4(w[0]) == 0o10 and m4(w[1], 1) == 0,
              f"phase 1: M4 {m4(v[0]):o}, system {m4(v[1], 2)}; phase 2: M4 {m4(w[0]):o}, "
              f"galaxy {m4(w[1], 1)}")

    # 4. arrivals: at the named system a rumour is due, and in the last
    #    phase the ship may come; elsewhere nothing
    v = run(list(BOOT) + jump + [f"peekcpu {t['SYS_INDEX']}"])
    if not v:
        check("the jump run answered", False)
        return
    there = v[-1]
    v = run(list(BOOT) + [poke_byte(t, "P_M4", 4), poke_byte(t, "P_M4", 0, 1),
                          poke_byte(t, "P_M4", there, 2)] + jump + [peek_byte(t, "P_M4")])
    w = run(list(BOOT) + [poke_byte(t, "P_M4", 0o20), poke_byte(t, "P_M4", 0, 1),
                          poke_byte(t, "P_M4", there, 2)] + jump + [peek_byte(t, "P_M4")])
    x = run(list(BOOT) + [poke_byte(t, "P_M4", 4), poke_byte(t, "P_M4", 0, 1),
                          poke_byte(t, "P_M4", (there + 1) & 0xFF, 2)] + jump + [peek_byte(t, "P_M4")])
    if v and w and x:
        check("at the named system a rumour is due, in the last phase leave for the ship",
              m4(v[0]) == 0o204 and m4(w[0]) == 0o60 and m4(x[0]) == 4,
              f"{m4(v[0]):o}, last {m4(w[0]):o}, elsewhere {m4(x[0]):o}")

    # 5. the galaxy hop the trail pointed at lands on phase 3 with a
    #    rumour due at the arrival; any other galactic jump ends it
    v = run(list(BOOT) + [poke_byte(t, "P_M4", 0o10), poke_byte(t, "P_M4", 1, 1)] + gal +
            [peek_byte(t, "P_M4"), peek_byte(t, "P_M4", 2), f"peekcpu {t['SYS_INDEX']}"])
    w = run(list(BOOT) + [poke_byte(t, "P_M4", 0o10), poke_byte(t, "P_M4", 5, 1)] + gal +
            [peek_byte(t, "P_M4")])
    if len(v) >= 3 and w:
        check("the galaxy the trail named lands on its third phase; another ends it",
              m4(v[0]) == 0o214 and m4(v[1], 2) == v[2] and m4(w[0]) == 0,
              f"M4 {m4(v[0]):o}, system {m4(v[1], 2)} of {v[2]}; elsewhere {m4(w[0]):o}")

    # 6. the Constrictor shot down on the last phase wins it; the reward
    #    at the dock is the naval laser in the first lesser mount
    # the phase is set before the launch: the sky's hulls are chosen as
    # it is laid out, and the Constrictor's only on the last phase
    fly = list(BOOT) + [poke_byte(t, "P_M4", 0o160), "press 107", "run 40"] + clear_traffic(t)
    con = ship_pokes(t, 3, "CONSTRICTORH", z=1000, energy=10, hyper=False, facing=True, still=True,
                     **{"U.FLAGS": 1 | a["UF_MISSION"]})
    # and again once it is in the sky: until then the book-keeping has
    # rightly said it was gone
    v = run(fly + con + [poke_byte(t, "P_M4", 0o160), "keydown 107", "run 120", "keyup 107",
                         peek_byte(t, "P_M4")])
    w = run(list(BOOT) + [poke_byte(t, "P_M4", 2), poke_byte(t, "P_MCOMPLETE", 0)] + dock +
            ["press 107", "run 60", peek_byte(t, "P_M4"), peek_byte(t, "P_MCOMPLETE"),
             f"peekcpu {t['P_LASERS']}"])
    if v and len(w) >= 3:
        check("the Constrictor shot down wins it, and the dock pays the naval laser",
              m4(v[0]) == 2 and m4(w[0]) == 0 and byte_of(t, "P_MCOMPLETE", w[1]) & 0x10
              and w[2] == int(t["LAS_NAVAL"], 8),
              f"M4 {m4(v[0])} then {m4(w[0])}, complete {byte_of(t, 'P_MCOMPLETE', w[1]):o}, "
              f"front gun {w[2]}")

    # 7. the plans: offered forty light years off or more; carried, a jump
    #    is intercepted on the roll that would otherwise go through; at
    #    the target 3, and the dock there pays the naval energy unit
    lave = galaxy_model(7)
    v = run(list(BOOT) + [poke_byte(t, "P_M5", 1)] + dock + ["press 057", "run 120", "press 107",
            "run 60", peek_byte(t, "P_M5"), peek_byte(t, "P_M4", 2)])
    if len(v) >= 2:
        far = sys_distance(lave, galaxy_model(m4(v[1], 2)))
        check("the plans offered: yes, to a system forty light years off or more",
              byte_of(t, "P_M5", v[0]) == 4 and far >= 400, f"M5 {byte_of(t, 'P_M5', v[0])}, "
              f"system {m4(v[1], 2)} at {far}")
    intercept = [poke_at(int(t["WI_PLANS"],8),256), poke_at(int(t["HYP_NOROLL"],8),0)]
    v = run(list(BOOT) + [poke_byte(t, "P_M5", 4)] + jump[:-2] + intercept +
            ["press 107", ui_ready(t, frames=1), f"peekcpu {t['WITCH']}"])
    w = run(list(BOOT) + [poke_byte(t, "P_M5", 4), poke_byte(t, "P_M4", 0, 1),
                          poke_byte(t, "P_M4", there, 2)] + [poke_at(int(t["WI_ODDS"], 8), 0)] +
            chart + ["press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1), poke_at(int(t["HYP_NOROLL"], 8), 1),
                     "press 107", ui_ready(t, frames=1), peek_byte(t, "P_M5"), f"peekcpu {t['WITCH']}"])
    x = run(list(BOOT) + [poke_byte(t, "P_M5", 3), poke_byte(t, "P_MCOMPLETE", 0),
                          poke_byte(t, "P_ENERGYUNIT", 0x80)] + dock +
            ["press 107", "run 60", peek_byte(t, "P_M5"), peek_byte(t, "P_MCOMPLETE"),
             peek_dev(t, "P_ENERGYUNIT")])
    if v and len(w) >= 2 and len(x) >= 3:
        eu = byte_of(t, "P_ENERGYUNIT", x[2])
        check("carrying the plans a jump is intercepted; at the target 3; the dock pays",
              v[0] == 1 and w[1] == 0 and byte_of(t, "P_M5", w[0]) == 3
              and byte_of(t, "P_M5", x[0]) == 0 and byte_of(t, "P_MCOMPLETE", x[1]) & 0x20 and eu == 1,
              f"witch {v[0]}; arrival M5 {byte_of(t, 'P_M5', w[0])} (witch {w[1]}); "
              f"then M5 {byte_of(t, 'P_M5', x[0])}, complete {byte_of(t, 'P_MCOMPLETE', x[1]):o}, "
              f"energy unit {eu:o}")


def check_missions4():
    """Mission 6, Confrontation (src/mission.mac, src/ovl_mission.mac):
    issued after a war that is over; its three parts given at a military
    station, each with its reward - the naval capture system and drones,
    the Targoid energy unit and the leftmost world of a galaxy, the
    counter-attack - and the Targoid laser at the end; the spies and the
    cruiser taken by the drone; the part-two world Targon-held on
    arrival; the cruiser and its escort there; the third part won by
    its station coming down."""
    print("missions: Confrontation")
    t = syms.table()
    need = ["P_M6", "P_M3", "P_M4", "P_MCOMPLETE", "P_WAR", "P_DESTR", "P_RATING", "P_DRONE",
            "P_ENERGYUNIT", "P_LASERS", "P_RND", "CARGO", "G_DRONE", "DOCKED", "DOCKED_AT",
            "BK_MILITARY", "SH_MILITARYST2H", "SH_TARGONINTH", "UF_MISSION", "UF_DERELICT",
            "BD_FREE", "MISS_LOCK", "P_FREECARGO", "NUNIV", "U.SIZE", "UNIV", "U.MAT", "PSPEED"]
    if any(n not in t for n in need):
        check("mission symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    nuniv, usize = a["NUNIV"], a["U.SIZE"]
    import struct

    def run(script):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk("missions4")))]

    def m6(w, off=0):
        return byte_of(t, "P_M6", w, off)

    chart = ["press 004", ui_ready(t)]
    gal = [poke_dev(t, "P_GALDRIVE")] + chart + ["press 107", ui_ready(t, frames=1)]
    jump = chart + ["press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1)] + \
        steady_drive(t) + ["press 107", ui_ready(t, frames=1)]

    # 1. issued: the war over, 1792 kills, 0, 1, 2, 4, 5 complete
    v = run(list(BOOT) + [poke_byte(t, "P_RATING", 3, 2), poke_byte(t, "P_MCOMPLETE", 0x37),
                          poke_byte(t, "P_WAR", 1), poke_at(a["P_DESTR"], 1792)] + gal +
            [peek_byte(t, "P_M6")])
    w = run(list(BOOT) + [poke_byte(t, "P_RATING", 3, 2), poke_byte(t, "P_MCOMPLETE", 0x37),
                          poke_at(a["P_DESTR"], 1792)] + gal + [peek_byte(t, "P_M6")])
    if v and w:
        check("Confrontation is issued after a war that is over, and not before",
              m6(v[0]) == 1 and m6(w[0]) == 0, f"M6 {m6(v[0])} after the war, {m6(w[0])} without")

    # the military base three rows up from Lave: where it lands, read off
    # a first run's sky, then flown into, level and slow
    dump = ROOT / "tmp" / "verify-m6.bin"
    dump.parent.mkdir(exist_ok=True)
    if dump.exists():
        dump.unlink()
    run(list(BOOT) + jump + ["press 107", ui_ready(t, frames=2), f"dumpcpu {t['UNIV']} {usize * nuniv} {dump}"])
    if not dump.exists():
        check("the base run answered", False)
        return
    d = dump.read_bytes()
    mil = [i for i in range(nuniv) if struct.unpack_from("<H", d, i * usize)[0] == a["SH_MILITARYST2H"]]
    if not mil:
        check("a military base three rows up", False)
        return
    mil = mil[0]
    ahead = [poke_at(a["PSPEED"], 0), poke_at(int(slot_field(t, mil, "U.X"), 8), 0),
             poke_at(int(slot_field(t, mil, "U.Y"), 8), 0), poke_at(int(slot_field(t, mil, "U.Z"), 8), 600),
             poke_at(int(slot_field(t, mil, "U.XH"), 8), 0), poke_at(int(slot_field(t, mil, "U.YH"), 8), 0),
             poke_at(int(slot_field(t, mil, "U.ZH"), 8), 0)] + \
        [poke_at(int(slot_field(t, mil, "U.MAT"), 8) + 2 * k, 16384 if k in (0, 4, 8) else 0) for k in range(9)]

    def at_base(setup, keys):
        return list(BOOT) + setup + jump + ["press 107", ui_ready(t, frames=2)] + ahead + ["run 300",
                f"peekcpu {t['DOCKED_AT']}"] + keys

    # 2. the first part: yes, three to six spies, the capture system, drones
    v = run(at_base([poke_byte(t, "P_M6", 1)], ["press 057", "run 120", "press 107", ui_ready(t, frames=2),
            peek_byte(t, "P_M6"), peek_byte(t, "P_M6", 1), peek_dev(t, "P_DRONE"),
            f"peekcpu {a['CARGO'] + 2 * a['G_DRONE']:o}"]))
    if len(v) >= 5:
        dr = byte_of(t, "P_DRONE", v[3])
        check("at a military station the spy hunt is offered: yes, spies to take, the kit for it",
              v[0] == a["BK_MILITARY"] and m6(v[1]) == 2 and 3 <= m6(v[2], 1) <= 6 and dr == 1
              and v[4] == 20, f"docked at {v[0]}, M6 {m6(v[1])}, spies {m6(v[2], 1)}, "
              f"drone {dr:o}, drones {v[4]}")
    # 3. the second: the leftmost world of the galaxy PilotRnd names, and
    #    the Targoid energy unit
    v = run(at_base([poke_byte(t, "P_M6", 3)], ["press 107", ui_ready(t, frames=2), peek_byte(t, "P_M6"),
            peek_byte(t, "P_M6", 1), peek_byte(t, "P_M4", 2), peek_byte(t, "P_RND"),
            peek_dev(t, "P_ENERGYUNIT")]))
    if len(v) >= 6:
        g = byte_of(t, "P_RND", v[4]) & 63
        g = g - 48 if g >= 48 else g
        best = min(range(256), key=lambda i: (galaxy_model(i, g)["x"], abs(galaxy_model(i, g)["y"] - 128), i))
        check("the sabotage: the leftmost world of the galaxy PilotRnd names, the Targoid unit",
              m6(v[1]) == 4 and m6(v[2], 1) == g and byte_of(t, "P_M4", v[3], 2) == best
              and byte_of(t, "P_ENERGYUNIT", v[5]) == 2,
              f"M6 {m6(v[1])}, galaxy {m6(v[2], 1)} of {g}, world {byte_of(t, 'P_M4', v[3], 2)} "
              f"of {best}, unit {byte_of(t, 'P_ENERGYUNIT', v[5]):o}")
    # 4. the end: the Targoid laser in the first mount without one
    v = run(at_base([poke_byte(t, "P_M6", 7), poke_byte(t, "P_MCOMPLETE", 0)],
                    ["press 107", ui_ready(t, frames=2), peek_byte(t, "P_M6"), peek_byte(t, "P_MCOMPLETE"),
                     f"peekcpu {t['P_LASERS']}"]))
    if len(v) >= 4:
        check("and at the end the Targoid laser, the mission complete",
              m6(v[1]) == 0 and byte_of(t, "P_MCOMPLETE", v[2]) & 0x40 and v[3] == int(t["LAS_TARGOID"], 8),
              f"M6 {m6(v[1])}, complete {byte_of(t, 'P_MCOMPLETE', v[2]):o}, front gun {v[3]}")

    # 5. arrivals: the part-two world is Targon-held; the third part is won
    #    by its station down (P_M3 5 at the jump)
    v = run(list(BOOT) + jump + [f"peekcpu {t['SYS_INDEX']}"])
    there = v[-1] if v else 0
    v = run(list(BOOT) + [poke_byte(t, "P_M6", 4), poke_byte(t, "P_M6", 0, 1),
                          poke_byte(t, "P_M4", there, 2)] + jump + [peek_byte(t, "P_M3")])
    w = run(list(BOOT) + [poke_byte(t, "P_M6", 6), poke_byte(t, "P_M3", 5)] + jump +
            [peek_byte(t, "P_M6"), peek_byte(t, "P_M3")])
    if v and len(w) >= 2:
        check("arriving at the part-two world it is Targon-held; a station down wins the third",
              byte_of(t, "P_M3", v[0]) == 4 and m6(w[0]) == 7 and byte_of(t, "P_M3", w[1]) == 0,
              f"M3 {byte_of(t, 'P_M3', v[0])}; M6 {m6(w[0])}, M3 {byte_of(t, 'P_M3', w[1])}")

    # 6. next to that world the unfinished cruiser comes, with its escort
    fly = list(BOOT) + [poke_byte(t, "P_M6", 4), "press 107", ui_ready(t, frames=2)] + clear_traffic(t)
    near = [poke_byte(t, "P_M3", 4)] + [poke_at(int(slot_field(t, 0, f), 8), v_) for f, v_ in
                                         (("U.X", 0), ("U.Y", 0), ("U.Z", 4000), ("U.XH", 0),
                                          ("U.YH", 0), ("U.ZH", 0))]
    types = [f"peekcpu {slot_field(t, k, 'U.TYPE')}" for k in range(nuniv)]
    flags = [f"peekcpu {slot_field(t, k, 'U.FLAGS')}" for k in range(nuniv)]
    kinds = [f"peekcpu {slot_field(t, k, 'U.KIND')}" for k in range(nuniv)]
    v = run(fly + near + ["run 20"] + types + flags + kinds)
    if len(v) >= 3 * nuniv:
        cru = [i for i in range(nuniv) if v[i] == a["SH_TARGONINTH"] and v[nuniv + i] & a["UF_MISSION"]]
        # the escort by its kind: a Targon 6 whose hull the sky has not
        # loaded comes as another of the Targons' hulls (TYPE_AVAIL)
        targ = sum(1 for i in range(3, nuniv) if v[i] and i not in cru and v[2 * nuniv + i] & 7 == 4)
        check("next to the Targon-held world, the cruiser and three to five Targons",
              len(cru) == 1 and 3 <= targ <= 5, f"cruiser in {cru}, {targ} Targons")

    # 7. the drone takes a spy (the last one ends the first part) and the
    #    cruiser (the second), the roll forced
    armed = [poke_dev(t, "P_DRONE"), poke_at(a["CARGO"] + 2 * a["G_DRONE"], 2),
             poke_at(a["BD_FREE"], 256), "press 017", "run 5"]
    lock = ["press 113", "run 5", "press 113", "run 5"]
    spy = ship_pokes(t, 3, "TARGONSPYH", z=3000, hostile=False, hyper=False,
                     **{"U.FLAGS": a["UF_DERELICT"]})
    st = ship_stats("TARGONINTH")
    cru = ship_pokes(t, 3, "TARGONINTH", z=3000, hostile=False, hyper=False, still=True,
                     **{"U.FLAGS": a["UF_MISSION"]})
    cru += [poke_at(int(slot_field(t, 3, "U.KIND"), 8), ((st["flags"] & 0xFF) << 8) | (st["type"] | 8))]
    v = run(list(BOOT) + [poke_byte(t, "P_M6", 2), "press 107", ui_ready(t, frames=2)] + clear_traffic(t) +
            [poke_at(a["PSPEED"], 0), poke_byte(t, "P_M6", 2), poke_byte(t, "P_M6", 1, 1)] + armed + spy +
            lock + ["run 200", peek_byte(t, "P_M6")])
    w = run(list(BOOT) + [poke_byte(t, "P_M6", 4), "press 107", ui_ready(t, frames=2)] + clear_traffic(t) +
            [poke_at(a["PSPEED"], 0)] + armed + cru + lock + ["run 200", peek_byte(t, "P_M6")])
    if v and w:
        check("the drone takes the last spy, and the cruiser",
              m6(v[0]) == 3 and m6(w[0]) == 5, f"M6 {m6(v[0])} after the spy, {m6(w[0])} after the cruiser")


def war_zone(level, param, x, y, war_y):
    """MS_ZONE (src/mission.mac) in Python: inside the zone of a war at
    LEVEL (the P_WAR byte), PARAM 0 / #3C / #78, for a system at x, y."""
    r = min(((level * 2) & 0xFF) + param, 255) >> 1
    dy, dx = abs(war_y - y), x >> 1
    s_ = dy * dy + dx * dx
    return s_ <= 0xFFFF and s_ < r * r


def check_missions5():
    """The Targon war (src/mission.mac, src/ovl_mission.mac): it breaks out
    on a kill that carries the rating, with the alien computer found and
    nothing open; a rank's promotion falls due on such a kill; the war
    grows and shrinks on its clock; arrivals in the occupied zone are at
    the Targons' station; at the front the station offers a rank - with
    the refugees to take - and promotes on the task done; the goods and
    the refugees count toward the tasks; and the war over, the pilot is
    stood down."""
    print("missions: the war")
    t = syms.table()
    need = ["P_RANK", "P_WAR", "P_M3", "P_M1", "P_MCOMPLETE", "P_RATING", "P_JUMPS", "WAR_T",
            "WAR_Y", "DOCKED", "CARGO", "P_FREECARGO", "UF_HOSTILE"]
    if any(n not in t for n in need):
        check("war symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}

    def run(script):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk("missions5")))]

    rank = lambda w: byte_of(t, "P_RANK", w)
    war = lambda w, o=0: byte_of(t, "P_WAR", w, o)
    dock = [poke_dev(t, "P_DOCKCOMP"), "press 107", "run 50"] + ["press 166", "run 20"] * 4 + ["run 700"]
    market = ["press 004", ui_ready(t)] * 3 + ["press 004"]
    market_modal = market + mission_ready(t)
    market = market + [ui_ready(t)]

    # 1. the outbreak: a kill carries the rating into its third byte, and
    #    the war is tested on the byte as it then stands (#21, odd, against
    #    the jumps' high byte 1)
    fly = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t)
    krait = ship_pokes(t, 3, "KRAITH", z=1000, energy=5, hyper=False, facing=True, still=True)
    v = run(fly + krait + [poke_byte(t, "P_MCOMPLETE", 8), poke_at(a["P_RATING"], 0xFFFF),
                           poke_at(a["P_RATING"] + 2, 0x20), poke_at(a["P_JUMPS"], 0x100),
                           "keydown 107", "run 120", "keyup 107", peek_byte(t, "P_RANK"),
                           peek_byte(t, "P_WAR"), peek_byte(t, "P_WAR", 1)])
    w = run(fly + krait + [poke_byte(t, "P_RANK", 0o202), poke_byte(t, "P_WAR", 0o205),
                           poke_at(a["P_RATING"], 0xFFFF), "keydown 107", "run 120", "keyup 107",
                           peek_byte(t, "P_RANK")])
    if len(v) >= 3 and w:
        check("a kill carrying the rating: the Targons invade, and a promotion falls due",
              rank(v[0]) == 0o201 and war(v[1]) == 0o201 and war(v[2], 1) < 8 and rank(w[0]) == 0o203,
              f"rank {rank(v[0]):o}, war {war(v[1]):o} in galaxy {war(v[2], 1)}; "
              f"serving, rank {rank(w[0]):o}")

    # 2. the war's clock: a level up while it spreads, down as it recedes
    v = run(fly + [poke_byte(t, "P_WAR", 0o201), poke_at(a["WAR_T"], 0xFFF0), ui_ready(t, frames=2),
                   peek_byte(t, "P_WAR")])
    w = run(fly + [poke_byte(t, "P_WAR", 5), poke_at(a["WAR_T"], 0xFFF0), ui_ready(t, frames=2),
                   peek_byte(t, "P_WAR")])
    if v and w:
        check("the war grows a level on its clock while rising, and shrinks falling",
              war(v[0]) == 0o202 and war(w[0]) == 4, f"{war(v[0]):o}, {war(w[0]):o}")

    # the war in galaxy 0, at a level that has Lave at the front and not
    # taken: worked out here the way MS_ZONE works it
    lave = galaxy_model(7)
    left = min(range(256), key=lambda i: (galaxy_model(i)["x"], abs(galaxy_model(i)["y"] - 128), i))
    wy = galaxy_model(left)["y"]
    front = [L for L in range(2, 128) if war_zone(0x80 | L, 0x3C, lave["x"], lave["y"], wy)
             and not war_zone(0x80 | L, 0, lave["x"], lave["y"], wy)]
    taken = [L for L in range(2, 128) if war_zone(0x80 | L, 0, lave["x"], lave["y"], wy)]
    calm = [L for L in range(2, 128) if not war_zone(0x80 | L, 0x3C, lave["x"], lave["y"], wy)]
    if not front or not taken or not calm:
        check("a war level for each of Lave's zones", False, f"{front[:2]} {taken[:2]} {calm[:2]}")
        return
    at = lambda L: [poke_byte(t, "P_WAR", 0x80 | L), poke_byte(t, "P_WAR", 0, 1)]

    # 3. at the front the station offers a rank; yes, and the orders; the
    #    market then asks to take refugees
    v = run(list(BOOT) + at(front[0]) + [poke_byte(t, "P_RANK", 0o201)] + dock +
            ["press 057", "run 120", "press 107", ui_ready(t), f"peekcpu {t['DOCKED']}",
             peek_byte(t, "P_RANK")] + market_modal + ["press 057", ui_ready(t), peek_byte(t, "P_M1", 1)])
    if len(v) >= 3:
        check("at the front: a rank offered and taken, then refugees to take aboard",
              v[0] == 1 and rank(v[1]) == 0o202 and byte_of(t, "P_M1", v[2], 1) == 2,
              f"docked {v[0]}, rank {rank(v[1]):o}, aboard {byte_of(t, 'P_M1', v[2], 1)}")
    # 4. a promotion due with the task done: the next rank
    v = run(list(BOOT) + at(front[0]) + [poke_byte(t, "P_RANK", 0o203), poke_byte(t, "P_WAR", 1, 2)] +
            dock + ["press 107", "run 60", peek_byte(t, "P_RANK")])
    w = run(list(BOOT) + at(front[0]) + [poke_byte(t, "P_RANK", 0o203), poke_byte(t, "P_WAR", 0, 2)] +
            dock + ["press 107", "run 60", peek_byte(t, "P_RANK")])
    if v and w:
        check("promoted with the task done, and not without it",
              rank(v[0]) == 0o204 and rank(w[0]) == 0o203, f"{rank(v[0]):o}, {rank(w[0]):o}")
    # 5. refugees set down away from the front: a trip counted, the task
    #    done past two to four
    v = run(list(BOOT) + at(calm[0]) + [poke_byte(t, "P_RANK", 0o202), poke_byte(t, "P_M1", 2, 1),
                                         poke_byte(t, "P_WAR", 5, 3), poke_byte(t, "P_WAR", 0, 2)] +
            market_modal + ["press 107", ui_ready(t), peek_byte(t, "P_M1", 1), peek_byte(t, "P_WAR", 2)])
    if len(v) >= 2:
        check("refugees set down away from the front: the sergeant's task done",
              byte_of(t, "P_M1", v[0], 1) == 0 and war(v[1], 2) & 1,
              f"aboard {byte_of(t, 'P_M1', v[0], 1)}, flags {war(v[1], 2):o}")
    # 6. a lieutenant's food sold at the front: the 256th tonne does it
    v = run(list(BOOT) + at(front[0]) + [poke_byte(t, "P_RANK", 0o204), poke_byte(t, "P_WAR", 0o377, 3),
                                          poke_byte(t, "P_WAR", 0, 2), poke_at(a["CARGO"], 3)] +
            market + ["press 116", "run 40", peek_byte(t, "P_WAR", 2), peek_byte(t, "P_WAR", 3)])
    if len(v) >= 2:
        check("a lieutenant's food sold at the front counts, and the 256th completes it",
              war(v[0], 2) & 2 and war(v[1], 3) == 0, f"flags {war(v[0], 2):o}, count {war(v[1], 3)}")
    # 7. arriving in the occupied zone: the Targons' station.  Leaving from
    #    the war's rear zone is intercepted one jump in two (the tunnel
    #    draws first, so no seed settles it): the first seed of a few that
    #    arrives is the one tested
    v = []
    for k in range(6):
        v = run(list(BOOT) + at(taken[0]) + [poke_byte(t, "P_M3", 0), poke_at(int(t["WI_ODDS"], 8), 0)] +
                ["press 004", ui_ready(t)] + ["press 154", ui_ready(t, frames=1)] * 2 +
                [poke_at(int(t["RNDSEED"], 8), 1000 + 77 * k), "press 107", ui_ready(t, frames=1),
                 f"peekcpu {t['SYS_INDEX']}", peek_byte(t, "P_M3"), f"peekcpu {t['WITCH']}"])
        if len(v) >= 3 and v[2] == 0:
            break
    if len(v) >= 3:
        there = galaxy_model(v[0])
        want = war_zone(0x80 | taken[0], 0, there["x"], there["y"], wy)
        check("an arrival in the occupied zone is at the Targons' station",
              v[2] == 0 and (byte_of(t, "P_M3", v[1]) == 4) == want, f"system {v[0]}, occupied {want}, "
              f"M3 {byte_of(t, 'P_M3', v[1])}, intercepted {v[2]} ({k + 1} tries)")
    # 8. the war over: a pilot with a rank is stood down, a rank up
    v = run(list(BOOT) + [poke_byte(t, "P_WAR", 1), poke_byte(t, "P_RANK", 0o204)] + dock +
            ["press 107", "run 60", peek_byte(t, "P_RANK")])
    if v:
        check("the war over, the pilot is stood down a rank up",
              rank(v[0]) == 0o305, f"rank {rank(v[0]):o}")


def check_missions6():
    """The war's last tasks (src/mission.mac): a station the Targons hold
    can be locked; the troops' craft flies at it, lands, and the
    occupation falls back; a major's missile on an occupied station
    counts; and a jump cut short beside the war's first world meets the
    command base."""
    print("missions: the war's stations")
    t = syms.table()
    need = ["P_RANK", "P_WAR", "P_M3", "P_M1", "MISS_LOCK", "MISS_KIND", "MF_DESCENT", "WAR_X",
            "WAR_Y", "HOME_X", "HOME_Y", "PFUEL", "WI_ODDS", "WITCH", "UF_STATION", "UF_MISSILE",
            "NUNIV"]
    if any(n not in t for n in need):
        check("war symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    nuniv = a["NUNIV"]

    def run(script):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk("missions6")))]

    war = lambda w, o=0: byte_of(t, "P_WAR", w, o)
    lave = galaxy_model(7)
    left = min(range(256), key=lambda i: (galaxy_model(i)["x"], abs(galaxy_model(i)["y"] - 128), i))
    wx, wy = galaxy_model(left)["x"], galaxy_model(left)["y"]
    taken = [L for L in range(2, 128) if war_zone(0x80 | L, 0, lave["x"], lave["y"], wy)]
    at = lambda L: [poke_byte(t, "P_WAR", 0x80 | L), poke_byte(t, "P_WAR", 0, 1)]
    ahead = [poke_at(int(slot_field(t, 2, f), 8), v_) for f, v_ in
             (("U.X", 0), ("U.Y", 0), ("U.Z", 3000), ("U.XH", 0), ("U.YH", 0), ("U.ZH", 0))]
    fly = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t)

    # 1. the lock: the Targons' station, and not a station of ours
    v = run(fly + ahead + [poke_byte(t, "P_M3", 4), "run 10", "press 113", "run 10",
                           f"peekcpu {t['MISS_LOCK']}"])
    w = run(fly + ahead + [poke_byte(t, "P_M3", 0), "run 10", "press 113", "run 10",
                           f"peekcpu {t['MISS_LOCK']}"])
    if v and w:
        check("the space bar locks a station the Targons hold, and no other",
              v[0] == 3 and w[0] == 0, f"lock {v[0]} held, {w[0]} ours")

    # 2. the troops: in the occupied zone, the craft lands; the war falls
    #    back until this system is out of it; the station is gone.
    # Keep the planet beyond the barrier's range and the bay unmanned.
    # Clearing existing traffic alone lets PLANET_BARRIER spawn Targons
    # which can destroy the craft before it reaches the station.
    landing_only = [poke_at(int(slot_field(t, 0, 'U.Z'), 8), 0),
                    poke_at(int(slot_field(t, 0, 'U.ZH'), 8), 1),
                    poke_at(int(slot_field(t, 2, 'U.FLAGS'), 8),
                            int(t['UF_STATION'], 8) | int(t['UF_HOSTILE'], 8) |
                            int(t['UF_DERELICT'], 8))]
    L = taken[0]
    v = run(fly + ahead + landing_only + at(L) + [poke_byte(t, "P_M3", 4), poke_byte(t, "P_M1", 3, 1),
                                   poke_byte(t, "P_WAR", 0, 2), poke_at(a["MISS_KIND"], a["MF_DESCENT"]),
                                   poke_at(a["MISS_LOCK"], 3), "press 113",
                                   f"runpc {t['MS_LANDING']} 600", ui_ready(t, frames=2),
                                   peek_byte(t, "P_WAR"), peek_byte(t, "P_WAR", 2), peek_byte(t, "P_M3"),
                                   peek_byte(t, "P_M1", 1), f"peekcpu {slot_field(t, 2, 'U.TYPE')}",
                                   f"peekcpu {slot_field(t, 2, 'U.FLAGS')}"])
    if len(v) >= 6:
        lvl = war(v[0])
        check("the troops land: the task done, the war falling back out of this system",
              war(v[1], 2) & 0x10 and not lvl & 0x80 and lvl < L
              and not war_zone(lvl, 0, lave["x"], lave["y"], wy) and byte_of(t, "P_M3", v[2]) == 0
              and byte_of(t, "P_M1", v[3], 1) == 0 and not (v[4] and v[5] & int(t["UF_STATION"], 8)),
              f"war {L:o} -> {lvl:o}, flags {war(v[1], 2):o}, M3 {byte_of(t, 'P_M3', v[2])}, "
              f"aboard {byte_of(t, 'P_M1', v[3], 1)}, slot 2 {v[4]} ({v[5]:o})")

    # 3. a major's missile on an occupied station, the naval ECM aboard:
    #    past two to four of them, the task done
    missile = ship_pokes(t, 3, "MISSILEH", z=600, hostile=False, hyper=False,
                         **{"U.FLAGS": a["UF_MISSILE"], "U.TARGET": 3, "U.ENERGY": 250})
    v = run(fly + at(L) + [poke_byte(t, "P_M3", 4), poke_byte(t, "P_ECM", 1), poke_byte(t, "P_RANK", 0o210),
                           poke_byte(t, "P_WAR", 5, 3), poke_byte(t, "P_WAR", 0, 2)] + missile +
            ["run 400", peek_byte(t, "P_WAR", 2)])
    if v:
        check("a major's missile on an occupied station counts toward his task",
              war(v[0], 2) & 8, f"flags {war(v[0], 2):o}")

    # 4. the command base: a jump from where its midpoint falls one right
    #    of the war's first world and two toward the middle, cut short
    tx, ty = wx + 1, (wy + 2 if wy < 128 else wy - 2)
    dest = galaxy_model(left)                # the jump is to the first world
    hx, hy = 2 * tx - dest["x"], 2 * ty - dest["y"]
    front = [L2 for L2 in range(2, 128) if war_zone(0x80 | L2, 0x3C, tx, ty, wy)]
    if hx < 0 or hy < 0 or hx > 255 or hy > 255 or not front:
        check("a jump that lands beside the war's first world", False, f"from ({hx},{hy})")
        return
    v = run(list(BOOT) + at(front[0]) + [poke_byte(t, "P_RANK", 0o214), poke_byte(t, "P_M3", 0),
            poke_at(a["WI_ODDS"], 256), "press 004", ui_ready(t), poke_at(int(t["CURSYS"], 8), left),
            poke_at(a["HOME_X"], hx), poke_at(a["HOME_Y"], hy), poke_at(a["PFUEL"], 2000),
            "press 107", ui_ready(t, frames=1), f"peekcpu {t['WITCH']}", f"peekcpu {t['HOME_X']}",
            f"peekcpu {t['HOME_Y']}", peek_byte(t, "P_M3")] +
            [f"peekcpu {slot_field(t, k, 'U.FLAGS')}" for k in range(nuniv)] +
            [f"peekcpu {slot_field(t, k, 'U.TYPE')}" for k in range(nuniv)])
    if len(v) >= 4 + 2 * nuniv:
        bases = sum(1 for k in range(nuniv) if v[4 + nuniv + k] and v[4 + k] & a["UF_STATION"])
        check("cut short beside the war's first world, the command base is there",
              v[0] == 1 and (v[1], v[2]) == (tx, ty) and byte_of(t, "P_M3", v[3]) == 4 and bases == 1,
              f"witch {v[0]}, at ({v[1]},{v[2]}) for ({tx},{ty}), M3 {byte_of(t, 'P_M3', v[3])}, "
              f"{bases} station")


def check_missions7():
    """The portals, Raxxla and Retribution (src/portal_fly.mac,
    src/bases.mac, src/galaxy.mac, src/mission.mac, src/ovl_mission.mac):
    a portal beside the star of a system on a diagonal; through an
    ordinary one to a system of this galaxy, no fuel, no interception;
    through Raxxla's to its galaxy, #FF, whose first system is RAXXLA;
    on Retribution through any to the Targons', #FE; Retribution issued,
    offered at a military station, the squad taken aboard there, a held
    world taken at its station; and Raxxla's welcome."""
    print("missions: the portals, Raxxla and Retribution")
    t = syms.table()
    need = ["P_M7", "P_MCOMPLETE", "P_RATING", "P_DESTR", "P_RND", "P_PLANETDATA", "GALNUM",
            "SYS_INDEX", "SYS_NAME", "PFUEL", "WITCH", "NEAR_PORTAL", "SH_PORTALH", "UF_BASE",
            "UF_MISSION", "DOCKED", "DOCKED_AT", "P_M1", "NUNIV", "SH_MILITARYST2H", "U.SIZE",
            "P_GALAXY", "P_PLANET"]
    if any(n not in t for n in need):
        check("portal symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    nuniv, usize = a["NUNIV"], a["U.SIZE"]
    import struct

    def run(script):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk("missions7")))]

    m7 = lambda w, o=0: byte_of(t, "P_M7", w, o)
    dock = [poke_dev(t, "P_DOCKCOMP"), "press 107", "run 50"] + ["press 166", "run 20"] * 4 + ["run 700"]
    fly = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t)

    # 1. the portal: a system on the main diagonal, PilotRnd #D0 up, the
    #    star close - set before the launch, when the sky's hulls are chosen
    diag = [poke_byte(t, "P_PLANETDATA", 90, 1), poke_byte(t, "P_PLANETDATA", 92, 3),
            poke_byte(t, "P_RND", 0xE0)]
    # Keep the spawned portal beyond docking range while observing it.
    sun = [poke_at(int(slot_field(t, 1, f), 8), v_) for f, v_ in
           (("U.X", 0), ("U.Y", 0), ("U.Z", 8000), ("U.XH", 0), ("U.YH", 0), ("U.ZH", 0))]
    v = run(list(BOOT) + diag + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t) + sun + [ui_ready(t, frames=3),
            f"peekcpu {t['NEAR_PORTAL']}"] + [f"peekcpu {slot_field(t, k, 'U.TYPE')}" for k in range(nuniv)])
    if len(v) >= 1 + nuniv:
        check("beside the star of a system on the diagonal, a portal", v[0] == 1 and a["SH_PORTALH"] in v[1:],
              f"near {v[0]}, slots {v[1:]}")

    # 2..4. through a portal poked dead ahead: an ordinary one stays in
    #    the galaxy and costs no fuel; Raxxla's goes to #FF; on
    #    Retribution, to #FE
    ident = [poke_at(int(slot_field(t, 3, "U.MAT"), 8) + 2 * k, 16384 if k in (0, 4, 8) else 0)
             for k in range(9)]
    # Fix the random destination at entry, after all flight/AI draws.
    # Zero state supplies (0, 0), which has a known nearest-system result.
    def portal(flags, pre=()):
        pk = [poke_at(int(slot_field(t, 3, f), 8), v_) for f, v_ in
              (("U.TYPE", a["SH_PORTALH"]), ("U.FLAGS", flags), ("U.EXPL", 0), ("U.SPEED", 0),
               ("U.X", 0), ("U.Y", 0), ("U.Z", 650), ("U.XH", 0), ("U.YH", 0), ("U.ZH", 0))] + ident
        return run(list(BOOT) + list(pre) + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t) +
                   [poke_at(int(t["PSPEED"], 8), 0)] + pk + [f"runpc {t['PORTAL_JUMP']} 1200",
                   poke_at(int(t["RNDSEED"], 8), 0), poke_at(int(t["RNDSEED"], 8) + 2, 0), f"waitcpu {t['P_JUMPS']} 1 1200", ui_ready(t, frames=1), f"peekcpu {t['GALNUM']}",
                   f"peekcpu {t['SYS_INDEX']}", f"peekcpu {t['PFUEL']}", f"peekcpu {t['WITCH']}"])
    v = portal(a["UF_BASE"])
    w = portal(a["UF_BASE"] | a["UF_MISSION"])
    x = portal(a["UF_BASE"], [poke_byte(t, "P_M7", 3)])
    if len(v) >= 4 and len(w) >= 4 and len(x) >= 4:
        box = set(nearest_system(255, px, py) for px in range(0x60, 0x80, 3) for py in range(0x60, 0x70, 3))
        check("an ordinary portal: this galaxy, no fuel, no interception",
              v[0] == 0 and v[1] == nearest_system(0, 0, 0) and v[2] == 70 and v[3] == 0,
              f"galaxy {v[0]}, system {v[1]}, fuel {v[2]}, witch {v[3]}")
        check("Raxxla's portal: galaxy #FF, a system about #70,#68",
              w[0] == 255 and w[1] in box and w[3] == 0, f"galaxy {w[0]}, system {w[1]} of {sorted(box)}")
        check("on Retribution, the Targons' galaxy #FE", x[0] == 254, f"galaxy {x[0]}")

    # 5. Raxxla's first system is RAXXLA (the name the generator gives
    #    system 0 of #FF): through Raxxla's portal, then the data page on
    #    system 0
    pk = [poke_at(int(slot_field(t, 3, f), 8), v_) for f, v_ in
          (("U.TYPE", a["SH_PORTALH"]), ("U.FLAGS", a["UF_BASE"] | a["UF_MISSION"]), ("U.EXPL", 0),
           ("U.SPEED", 0), ("U.X", 0), ("U.Y", 0), ("U.Z", 650), ("U.XH", 0), ("U.YH", 0),
           ("U.ZH", 0))] + ident
    v = run(list(BOOT) + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t) + [poke_at(int(t["PSPEED"], 8), 0)] +
            pk + [f"waitcpu {t['P_JUMPS']} 1 1200", ui_ready(t, frames=1), f"peekcpu {t['GALNUM']}", poke_at(int(t["CURSYS"], 8), 0)] +
            ["press 004", ui_ready(t)] * 3 + [f"peekcpu {a['SYS_NAME']:o}", f"peekcpu {a['SYS_NAME'] + 2:o}",
                                          f"peekcpu {a['SYS_NAME'] + 4:o}"])
    if len(v) >= 4:
        name = b"".join(struct.pack("<H", x_) for x_ in v[-3:])
        check("galaxy #FF's first system is RAXXLA", v[0] == 255 and name == b"RAXXLA",
              f"galaxy {v[0]}, name {name}")

    # 6. Retribution issued: 0..6 complete, the rating's third byte #40,
    #    3000 kills
    gal = [poke_dev(t, "P_GALDRIVE"), "press 004", ui_ready(t), "press 107", ui_ready(t, frames=1)]
    v = run(list(BOOT) + [poke_byte(t, "P_RATING", 0x40, 2), poke_byte(t, "P_MCOMPLETE", 0x7F),
                          poke_at(a["P_DESTR"], 3000)] + gal + [peek_byte(t, "P_M7")])
    if v:
        check("Retribution is issued with missions 1..6 complete", m7(v[0]) == 2, f"M7 {m7(v[0])}")

    # 7. a held world taken at its station: the squad aboard, the bit
    #    cleared, the first word; P_GALAXY is only Legend's number here
    held = [poke_byte(t, "P_M7", 7), poke_at(a["P_GALAXY"], 254)] + \
        [poke_byte(t, "P_M7", 0xFF, 1 + k) for k in range(32)]
    # The squad takes it on a roll under #F8 (MS_DOCKED's RND_BYTE): one
    # dock in 32 the Targons take the ship instead, which is Legend's rule,
    # not a failure.  Which way a boot rolls moves with the boot read, so
    # a few seeds are tried and the first that takes the world is the one
    # checked (a build that grew the resident two sectors met the 1 in
    # 32 every time, 2026-09-27)
    for k in range(4):
        v = run(list(BOOT) + held + [poke_byte(t, "P_M1", 5, 1),
                                     poke_at(int(t["RNDSEED"], 8), 1000 + 77 * k)] + dock +
                ["press 107", ui_ready(t, frames=2), f"peekcpu {t['DOCKED']}", peek_byte(t, "P_M7"),
                 peek_byte(t, "P_M7", 1), peek_byte(t, "P_M1", 1)])
        if len(v) >= 4 and m7(v[1]) == 3:
            break
    if len(v) >= 4:
        check("docked at a held world with the squad: it is taken, the squad gone",
              v[0] == 1 and m7(v[1]) == 3 and m7(v[2], 1) == 0xFE and byte_of(t, "P_M1", v[3], 1) == 0,
              f"docked {v[0]}, M7 {m7(v[1])}, bits {m7(v[2], 1):o}, aboard {byte_of(t, 'P_M1', v[3], 1)}"
              f" ({k + 1} tries)")

    # 8. Raxxla's station, the first time: the welcome and the bit
    v = run(list(BOOT) + [poke_at(a["P_GALAXY"], 255), poke_byte(t, "P_MCOMPLETE", 0)] +
            [poke_at(a["P_PLANET"], 0)] + dock + ["press 107", ui_ready(t, frames=2), peek_byte(t, "P_MCOMPLETE")])
    if v:
        check("at Raxxla's station the League's welcome, and the legend's bit",
              byte_of(t, "P_MCOMPLETE", v[0]) & 0x80, f"complete {byte_of(t, 'P_MCOMPLETE', v[0]):o}")


def check_missions8():
    """The pirates' station, the generation ship and the platform
    (src/mission.mac, src/ovl_mission.mac): a pirate shot down near a
    station the pirates hold is one fewer; docking there, the ship is
    theirs; in deep space a generation ship is docked at, its people ask
    to be carried, and set down at a main station they pay in gems, gold
    and platinum and wipe the record; the platform is death to touch; a
    shot at a generation ship is the law's whole contempt."""
    print("missions: the pirates' station, the generation ship, the platform")
    t = syms.table()
    need = ["PIRATE_ON", "STN_NEAR", "OVL_CUR", "P_M1", "P_LIFESUPPORT", "CARGO", "LEGAL", "WI_ODDS",
            "WITCH", "DOCKED", "DOCKED_AT", "BK_GENSHIP", "SH_SHIPGENH", "SH_PLATFORMH", "UF_BASE",
            "PSPEED"]
    if any(n not in t for n in need):
        check("symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}

    def run(script):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk("missions8")))]

    dock = [poke_dev(t, "P_DOCKCOMP"), "press 107", "run 50"] + ["press 166", "run 20"] * 4 + ["run 700"]
    market = ["press 004", ui_ready(t)] * 3 + ["press 004"] + mission_ready(t)
    fly = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + clear_traffic(t)

    # 1. a pirate shot down near the pirates' station: one fewer
    krait = ship_pokes(t, 3, "KRAITH", z=1000, energy=5, hyper=False, facing=True, still=True)
    # A long held burst can also kill a pirate the station launches later.
    # Fire at the prepared target, then let its explosion finish with the
    # gun released; require exactly one credited kill as well as the tally.
    v = run(fly + krait + [poke_at(a["PIRATE_ON"], 3), poke_at(int(t["KILLS"], 8), 0),
                           "keydown 107", "run 10", "keyup 107", "run 50",
                           f"peekcpu {t['PIRATE_ON']}", f"peekcpu {t['KILLS']}"])
    if v:
        check("a pirate shot down near the pirates' station is one fewer",
              v == [2, 1], f"{v[0]} left after {v[1]} kill(s)")
    # 2. docking there: the pirates take the ship, and the game is over
    v = run(list(BOOT) + [poke_at(a["PIRATE_ON"], 5)] + dock + ["press 107", "run 300",
            f"peekcpu {t['OVL_CUR']}"])
    if v:
        # the key that closed the message may have gone on to the title,
        # which is the commander chooser then: either is the game over
        check("docking at the pirates' station, the ship is theirs: the title again",
              v[0] in (int(t["OVL_TITLE"], 8), int(t["OVL_CMDR"], 8)), f"overlay {v[0]}")

    # 3. deep space: a generation ship dead ahead, docked at; the market
    #    screen, and its people ask to be carried
    witch = list(BOOT) + [poke_at(a["WI_ODDS"], 256), "press 004", ui_ready(t), "press 154", ui_ready(t, frames=1),
                          "press 154", ui_ready(t, frames=1), "press 107", ui_ready(t, frames=1), "press 107", ui_ready(t, frames=2)]
    ident = [poke_at(int(slot_field(t, 3, "U.MAT"), 8) + 2 * k, 16384 if k in (0, 4, 8) else 0)
             for k in range(9)]
    def ahead(kind):
        return [poke_at(int(slot_field(t, 3, f), 8), v_) for f, v_ in
                (("U.TYPE", kind), ("U.FLAGS", a["UF_BASE"]), ("U.EXPL", 0), ("U.SPEED", 0),
                 ("U.ENERGY", 240), ("U.X", 0), ("U.Y", 0), ("U.Z", 600), ("U.XH", 0), ("U.YH", 0),
                 ("U.ZH", 0))] + ident + [poke_at(a["PSPEED"], 0)]
    v = run(witch + [f"peekcpu {t['WITCH']}", poke_byte(t, "P_LIFESUPPORT", 0)] + clear_traffic(t) +
            ahead(a["SH_SHIPGENH"]) + [f"waitcpu {t['DOCKED']} 1 1200", ui_ready(t), f"peekcpu {t['DOCKED']}", f"peekcpu {t['DOCKED_AT']}"] +
            market + ["press 057", "run 60", peek_byte(t, "P_M1", 1)])
    if len(v) >= 4:
        check("in deep space a generation ship is docked at, and its people ask to come",
              v[0] == 1 and v[1] == 1 and v[2] == a["BK_GENSHIP"] and byte_of(t, "P_M1", v[3], 1) == 4,
              f"witch {v[0]}, docked {v[1]} at {v[2]}, aboard {byte_of(t, 'P_M1', v[3], 1)}")
    # 4. set down at a main station: gems, gold, platinum, the record clean
    v = run(list(BOOT) + [poke_byte(t, "P_M1", 4, 1), poke_at(a["LEGAL"], 3000)] + market +
            ["press 107", "run 40", f"peekcpu {a['CARGO'] + 30:o}", f"peekcpu {a['CARGO'] + 26:o}",
             f"peekcpu {a['CARGO'] + 28:o}", f"peekcpu {t['LEGAL']}", peek_byte(t, "P_M1", 1)])
    if len(v) >= 5:
        check("set down, they pay in gems, gold and platinum and wipe the record",
              100 <= v[0] <= 163 and 40 <= v[1] <= 87 and 20 <= v[2] <= 35 and v[3] == 0
              and byte_of(t, "P_M1", v[4], 1) == 0,
              f"gems {v[0]}, gold {v[1]}, platinum {v[2]}, legal {v[3]}")
    # 5. the platform: touching it is death
    v = run(witch + clear_traffic(t) + ahead(a["SH_PLATFORMH"]) + ["run 300", f"peekcpu {t['OVL_CUR']}"])
    if v:
        check("the platform is death to touch", v[0] == int(t["OVL_TITLE"], 8), f"overlay {v[0]}")
    # 6. a shot at a generation ship: the law's whole contempt
    gen = [poke_at(int(slot_field(t, 3, f), 8), v_) for f, v_ in
           (("U.TYPE", a["SH_SHIPGENH"]), ("U.FLAGS", a["UF_BASE"]), ("U.EXPL", 0), ("U.SPEED", 0),
            ("U.ENERGY", 240), ("U.X", 0), ("U.Y", 0), ("U.Z", 2500), ("U.XH", 0), ("U.YH", 0),
            ("U.ZH", 0))] + ident + [poke_at(a["PSPEED"], 0)]
    v = run(witch + clear_traffic(t) + gen + ["run 10", "keydown 107", "run 40", "keyup 107",
                                             f"peekcpu {t['LEGAL']}"])
    if v:
        check("a shot at a generation ship: the law's whole contempt", v[0] == 0xFFFF, f"legal {v[0]:o}")


def legend_genship(goods, rnd):
    """genGenShipPrice (Galaxy/GalaxyData.a80): the generation ship's
    prices.  The base price, the quantity byte and the random part,
    doubled, the gradient's low five bits added for bit 7 set and taken
    off for it clear - no economy in it - and four times that, in
    sixteen bits.  It stocks nothing."""
    P = []
    for p, g, q, m in goods:
        k = g & 31
        c = (p + q + (rnd & m)) * 2 + (k if g & 128 else -k)
        P.append((c * 4) & 0xFFFF)
    return P


def check_missions9():
    """What phase 5 had left: the generation ship's market (its own
    prices, nothing on the shelf), the Cougars a platform launches in
    deep space (and the generation ship launching nothing), and the
    experimental drive's jump to Raxxla ("9" on a chart, Legend's R on
    the jump) - with the drive fitted, and not without it; and a galactic
    jump, which Legend never lets the Targons intercept."""
    print("missions: the generation ship's market, the Cougars, the drive to Raxxla")
    t = syms.table()
    need = ["NGOODS", "P_RND", "MKT_PRICE", "MKT_OPEN", "AST_QTY", "DOCKED_AT", "BK_GENSHIP",
            "WI_ODDS", "WITCH", "SH_SHIPGENH", "SH_PLATFORMH", "SH_COUGARH", "UF_BASE", "PSPEED",
            "PENERGY", "NUNIV", "P_GALDRIVE", "GALNUM", "SYS_INDEX", "PFUEL"]
    if any(n not in t for n in need):
        check("symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    import struct
    a = {n: int(t[n], 8) for n in need}
    ng = a["NGOODS"]

    def run(script, name="missions9"):
        return [int(x, 8) for x in PEEK.findall(run_emu(script + ["quit"], fresh_disk(name)))]

    # 1. the generation ship's market: Legend's prices, and the shelf
    #    that MS_DEEP empties stays empty
    dump = ROOT / "tmp" / "verify-genship.bin"
    if dump.exists():
        dump.unlink()
    v = run(list(BOOT) + [f"peekcpu {a['P_RND'] & ~1:o}", poke_at(a["DOCKED_AT"], a["BK_GENSHIP"])]
            + [poke_at(a["AST_QTY"] + 2 * i, 0) for i in range(ng)]
            + ["press 004", ui_ready(t)] * 4
            + [f"dumpcpu {a['MKT_PRICE']:o} {ng * 2} {dump}", f"peekcpu {t['MKT_OPEN']}"])
    if len(v) >= 2 and dump.exists():
        rnd = (v[0] & 0xFF) if a["P_RND"] % 2 == 0 else (v[0] >> 8)
        got = list(struct.unpack(f"<{ng}H", dump.read_bytes()[:ng * 2]))
        want = legend_genship(legend_goods(), rnd)
        diff = [(i, x, y) for i, (x, y) in enumerate(zip(got, want)) if x != y]
        check("the generation ship trades, at Legend's prices", v[1] == 1 and not diff,
              f"open {v[1]}, rnd {rnd}: {diff[:3]}")
    else:
        check("the generation ship's market answered", False)

    # 2. deep space: a platform launches Cougars, a generation ship nothing
    witch = list(BOOT) + [poke_at(a["WI_ODDS"], 256), "press 004", ui_ready(t), "press 154", ui_ready(t, frames=1),
                          "press 154", ui_ready(t, frames=1), "press 107", ui_ready(t, frames=1), "press 107", ui_ready(t, frames=2)]
    nuniv = a["NUNIV"]

    def sky(key):
        base = ship_pokes(t, 3, key, z=6000, hostile=False, **{"U.FLAGS": a["UF_BASE"], "U.ENERGY": 240})
        script = witch + [f"peekcpu {t['WITCH']}"] + clear_traffic(t) + base
        for _ in range(6):
            script += [poke_at(a["PSPEED"], 0), poke_at(a["PENERGY"], 255), "run 20"]
        script += [f"peekcpu {slot_field(t, s, 'U.TYPE')}" for s in range(3, nuniv)]
        return run(script, "missions9s")

    v = sky("PLATFORMH")
    if len(v) >= 2:
        cougars = sum(1 for x in v[1:] if x == a["SH_COUGARH"])
        check("in deep space the platform launches Cougars", v[0] == 1 and cougars > 0,
              f"witch {v[0]}, {cougars} Cougars, types {v[1:]}")
    v = sky("SHIPGENH")
    if len(v) >= 2:
        # what its bay would launch: the traders it launched before the
        # fix (LA_TRADER, eight types from the Transporter) or a Cougar.
        # Deep space rolls up Targons of its own, and they launch
        # Targlets, so "no other ship at all" is not the question
        tr = int(t["SH_TRANPORTERH"], 8)
        launched = [x for x in v[1:] if tr <= x < tr + 8 or x == a["SH_COUGARH"]]
        check("and the generation ship launches nothing", v[0] == 1 and not launched,
              f"witch {v[0]}, launched {launched}, in the sky {[x for x in v[1:] if x]}")

    # 3. "9" on the chart with the experimental drive: Raxxla, no fuel;
    #    with the standard drive, nothing
    for kind, where in ((2, (255, 0)), (0, (0, 7))):
        v = run(list(BOOT) + [f"pokecpu {a['P_GALDRIVE']:o} {kind:o}", f"peekcpu {t['PFUEL']}",
                              "press 004", ui_ready(t), "press 177", ui_ready(t, frames=1),
                              f"peekcpu {t['GALNUM']}", f"peekcpu {t['SYS_INDEX']}",
                              f"peekcpu {t['PFUEL']}"])
        if len(v) >= 4:
            if kind == 2:
                check("the experimental drive's \"9\" goes to Raxxla, and costs no fuel",
                      (v[1], v[2]) == where and v[3] == v[0], f"galaxy {v[1]}, system {v[2]}, fuel {v[0]}->{v[3]}")
            else:
                check("and with the standard drive it goes nowhere", (v[1], v[2]) == where,
                      f"galaxy {v[1]}, system {v[2]}")

    # 4. a galactic jump is never intercepted (Legend rolls in JumpToPlanet
    #    only): with the odds at certain, the drive still lands in a system
    v = run(list(BOOT) + [poke_dev(t, "P_GALDRIVE"), poke_at(a["WI_ODDS"], 256), "press 004", ui_ready(t),
                          "press 107", ui_ready(t, frames=1), f"peekcpu {t['GALNUM']}", f"peekcpu {t['WITCH']}"])
    if len(v) >= 2:
        check("a galactic jump is never intercepted", v[0] == 1 and v[1] == 0,
              f"galaxy {v[0]}, witch {v[1]}")


def check_ppu_room():
    """What the port keeps in the PPU's spare RAM (2026-09-25,
    docs/platform.md): the overlay cache - a second block
    the firmware gives at start, a copy of each overlay kept as the disk
    gave it, the flight overlay at its head and never the title or the
    chooser, and a cached read a few ticks where the disk takes tens -
    and the tune, which the PPU plays on the second AY chip from its own clock:
    round and round on the title, once on the docking computer, stopped
    by ФИКС, and not stopped by an effect."""
    print("the PPU's room: the overlay cache and the tune")
    t = syms.table()
    need = ["OC_BASE", "OC_NEXT", "OC_OFF", "OVL_TK", "OVL_CUR", "OVL_DIR", "OVL_N", "OVL_FLY", "HBANK_ADDR",
            "OVL_TITLE", "OVL_CMDR", "OC_WORDS", "L2372$", "PP_START", "MUS_PTR", "MUS_CNT",
            "SX_Q", "SX_QH", "FX_KILL", "OVL_SFX", "OVL_BASE", "OVL_END", "P_DOCKCOMP", "DC_ON"]
    if any(n not in t for n in need):
        check("symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    n_ovl = a["OVL_N"]
    oc_tab = a["OVL_DIR"] + 2 * n_ovl

    def pk(n):
        return f"peekcpu {t[n]}"

    # 1. the cache: allocated past the program, filled, and each copy is
    #    the overlay as the disk has it
    names = [line.split(":")[0].strip() for line in (ROOT / "src/ovl.list").read_text().splitlines()
             if line.strip() and not line.startswith("#")]
    round_ = ["press 004", ui_ready(t)] * 10
    tabs = [f"peekcpu {oc_tab + 2 * i:o}" for i in range(len(names))]
    dumps = {i: ROOT / "tmp" / f"verify-oc-{i}.bin" for i in range(len(names))}
    for f in dumps.values():
        if f.exists():
            f.unlink()
    script = list(BOOT) + [pk("L2372$"), pk("OC_BASE"), "press 107", "run 100"] + round_ + tabs
    v = run_emu(script + ["quit"], fresh_disk("pparoom"))
    vals = [int(x, 8) for x in PEEK.findall(v)]
    if len(vals) < 2 + len(names):
        check("the cache run answered", False, f"{len(vals)} peeks")
        return
    block, base, tab = vals[0], vals[1], vals[2:2 + len(names)]
    top = base + 2 * a["OC_WORDS"]
    check("the PPU gives the cache its block, clear of the program and under 100000",
          base > block and top <= 0o100000, f"program {block:o}, cache {base:o}..{top:o}")
    check("the flight overlay is kept at the head, the title and the chooser never",
          tab[a["OVL_FLY"]] == base and tab[a["OVL_TITLE"]] == 0 and tab[a["OVL_CMDR"]] == 0,
          f"fly {tab[a['OVL_FLY']]:o}, title {tab[a['OVL_TITLE']]:o}, chooser {tab[a['OVL_CMDR']]:o}")
    hbank = int(t["HBANK_ADDR"], 8)
    eq, ca = names.index("equip"), names.index("carrier")
    check("the outfitter and the carrier market are kept in plane 0 above the screen, "
          "one after the other, and nothing else is",
          tab[eq] == hbank and hbank < tab[ca] and all(x < hbank for i, x in enumerate(tab) if i not in (eq, ca)),
          f"outfitter {tab[eq]:o}, carrier market {tab[ca]:o}, plane 0 from {hbank:o}")
    check("the effects engine is kept straight after the flight overlay, for good",
          tab[a["OVL_SFX"]] == base + a["OVL_END"] - a["OVL_BASE"],
          f"engine {tab[a['OVL_SFX']]:o}, cache {base:o}")
    # the engine's copy is the one that runs, and keeps its state in
    # itself: it is the disk's image only until its first tick
    kept = [i for i, x in enumerate(tab) if x and i != a["OVL_SFX"]]
    script = list(BOOT) + ["press 107", "run 100"] + round_ + \
        [f"dump 0 {tab[i]:o} {(ROOT / 'build' / f'ovl_{names[i]}.raw').stat().st_size} {dumps[i]}" for i in kept]
    run_emu(script + ["quit"], fresh_disk("pparoom"))
    bad = [names[i] for i in kept
           if not dumps[i].exists() or dumps[i].read_bytes() != (ROOT / "build" / f"ovl_{names[i]}.raw").read_bytes()]
    check("each kept copy is the overlay as the disk has it",
          len(kept) >= 4 and not bad, f"kept {[names[i] for i in kept]}, differing {bad}")

    # 2. Prove which path supplied the overlay. Native RT-11 reads can
    # be as fast as a PPU copy in this probe, so a fixed speed ratio is
    # not a reliable cache assertion. RT_BLOCK records actual DAT reads.
    import json
    entries = json.loads((ROOT/'build/manifest.json').read_text())['entries']
    blocks = {e['file']: e['lba'] for e in entries}
    def back_to_cockpit(off):
        script = list(BOOT) + [poke_at(a["OC_OFF"], off), "press 107", "run 100"] + round_[:-2] + \
            [poke_at(int(t['RT_BLOCK'],8),65535)] + round_[-2:] + \
            [pk("OVL_CUR"), pk("OVL_TK"), pk("RT_BLOCK")]
        vals = [int(x,8) for x in PEEK.findall(run_emu(script+["quit"],fresh_disk("pparoom")))]
        return vals[-3:] if len(vals)>=3 else None
    on,off=back_to_cockpit(0),back_to_cockpit(1)
    if on and off:
        check("the flight overlay uses its cache, and disabling it reads its DAT blocks",
              on[0]==off[0]==a['OVL_FLY'] and on[1]<=5
              and on[2]!=blocks['ovl_fly.raw'] and off[2]==blocks['ovl_fly.raw'],
              f"cached [overlay,ticks,last read] {on}, disk {off}")

    def plane0_loads(off):
        step=["press 004",ui_ready(t)]
        sample=[pk("OVL_CUR"),pk("OVL_TK"),pk("RT_BLOCK")]
        mark=[poke_at(int(t['RT_BLOCK'],8),65535)]
        script=list(BOOT)+[poke_at(a['OC_OFF'],off),"press 107","run 100"]+round_+ \
            step*4+mark+step+sample+step*3+mark+step+sample
        vals=[int(x,8) for x in PEEK.findall(run_emu(script+["quit"],fresh_disk("pparoom")))]
        return vals[-6:] if len(vals)>=6 else None
    on,off=plane0_loads(0),plane0_loads(1)
    if on and off:
        check("plane-0 cached outfitter/carrier pages avoid the DAT reads made with caching disabled",
              on[0]==off[0]==names.index('equip') and on[3]==off[3]==names.index('carrier')
              and on[2]==on[5]==65535 and off[2]==blocks['ovl_equip.raw']
              and off[5]==blocks['ovl_carrier.raw'],f"cached {on}, disk {off}")

    # 3. the tune: MUS_PTR in the PPU's own RAM, where the program went
    mus = a["MUS_PTR"] - a["PP_START"]

    def ppu_peek(block):
        return f"peekw 0 {block + mus:o}"
    PEEKW = re.compile(r"peekw 0 [0-7]+ = ([0-7]+)")
    # the title: playing, still playing after twice its length (537
    # ticks of the PPU's clock, 270 of the emulator's), and ФИКС stops it
    title = list(TITLE_BOOT)                  # the machine's boot menu, the
    out = run_emu(title + [pk("L2372$"), "quit"])   #   title up and its tune on
    blk = [int(x, 8) for x in PEEK.findall(out)]
    if not blk:
        check("the tune run answered", False)
        return
    ptr = ppu_peek(blk[0])
    out = run_emu(title + [ptr, "run 300", ptr, "run 300", ptr, "press 107", "run 100", ptr, "quit"])
    w = [int(x, 8) for x in PEEKW.findall(out)]
    if len(w) >= 4:
        check("the title's tune plays round and round, on the PPU, and ФИКС stops it",
              w[0] and w[1] and w[2] and len({w[0], w[1], w[2]}) == 3 and w[3] == 0, f"{[oct(x) for x in w]}")
    # the docking computer: the tune once; an effect started over it
    # (a ship going up, asked for through the queue) leaves it playing -
    # the two are on different chips now.  The queue's count at that
    # moment is read on one run and moved on by one on the next: the
    # emulator is deterministic, so it is the same count.
    pre = list(BOOT) + [poke_dev(t, "P_DOCKCOMP"), "press 107", "run 50"] + \
        ["press 166", "run 20"] * 4 + [pk("DC_ON"), ptr, "run 20"]
    qh = [int(x, 8) for x in PEEK.findall(run_emu(pre + [pk("SX_QH"), "quit"], fresh_disk("pparoom")))]
    if len(qh) >= 2:
        n = qh[-1]
        boom = [poke_at(a["SX_Q"] + 2 * (n & 7), a["FX_KILL"]), poke_at(a["SX_QH"], n + 1)]
        out = run_emu(pre + boom + ["run 10", pk("SX_QH"), ptr, "run 30", ptr, "quit"], fresh_disk("pparoom"))
        c = [int(x, 8) for x in PEEK.findall(out)]
        w = [int(x, 8) for x in PEEKW.findall(out)]
        if len(c) >= 2 and len(w) >= 3:
            check("the docking computer plays it, and an effect does not stop it",
                  c[0] == 1 and w[0] and c[1] > n and w[1] and w[2] and w[2] != w[1],
                  f"dc {c[0]}, requests {n} -> {c[1]}, tune {[oct(x) for x in w]}")


def check_presentation():
    """Phase 6's title and dashboards (2026-09-25).  The title is Legend's
    logo, compiled from src/res/legend/logo.txt, doubled across; each
    cockpit's dashboard is drawn by its overlay (src/ovl_dash.mac) with
    Legend's scanner dish for it (src/res/legend/scanners.txt), redrawn
    when the cockpit changes, with a missile rack of the cockpit's size
    and a fuel gauge whose full scale is the cockpit's tank.  Each
    picture is checked pixel by pixel against its text: every pixel the
    text lights is lit on the screen, and next to none it leaves dark."""
    print("presentation: the title's logo, the dashboards")
    t = syms.table()
    need = ["CKV_NUM", "CKV_SCAN", "CKV_MAXMISS", "CKV_MAXFUEL", "DASH_CK", "PMISSILES", "P_MISSTYPE",
            "PFUEL", "SCAN_CX", "SCAN_CY", "LBAR_BX", "RACK_Y", "BAR_W", "LBAR_Y", "BAR_STEP"]
    if any(n not in t for n in need):
        check("symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    try:
        from PIL import Image
    except ImportError:
        check("Pillow available for the presentation checks", False)
        return

    def shot(script, name):
        f = ROOT / "tmp" / f"verify-pres-{name}.bmp"
        if f.exists():
            f.unlink()
        run_emu(script + [f"screenshot {f}", "quit"], fresh_disk("pres"))
        return Image.open(f).convert("RGB") if f.exists() else None

    def compare(im, pixels, box):
        """pixels: the (x, y) the picture lights; box: the area it owns.
        -> (lit of those, lit elsewhere in the box)."""
        want = set(pixels)
        hit = sum(1 for p in want if sum(im.getpixel(p)) > 120)
        x0, y0, x1, y1 = box
        stray = sum(1 for y in range(y0, y1) for x in range(x0, x1)
                    if (x, y) not in want and sum(im.getpixel((x, y))) > 120)
        return hit, len(want), stray

    # 1. the title: the logo as the text has it, doubled across from
    #    column 18 and line 4, the emblem yellow and the words white
    rows = [ln for ln in (ROOT / "src/res/legend/logo.txt").read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")]
    px = [(144 + 2 * x + d, 4 + y) for y, r in enumerate(rows) for x, c in enumerate(r) if c != "." for d in (0, 1)]
    yellow = [(144 + 2 * x, 4 + y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == "Y"]
    im = shot(list(TITLE_BOOT), "title")
    if im:
        hit, n, stray = compare(im, px, (144, 4, 144 + 2 * len(rows[0]), 4 + len(rows)))
        yel = sum(1 for p in yellow if im.getpixel(p)[2] < 100 and im.getpixel(p)[0] > 100)
        check("the title is Legend's logo, pixel for pixel",
              hit == n and stray == 0 and yel == len(yellow),
              f"{hit} of {n} lit, {stray} stray, {yel} of {len(yellow)} yellow")

    # 2. the dashboard: each dish where the scanner is, per cockpit
    dishes, cur = {}, None
    for ln in (ROOT / "src/res/legend/scanners.txt").read_text(encoding="utf-8").splitlines():
        if ln.startswith("== "):
            cur = ln[3:].strip()
            dishes[cur] = []
        elif cur and ln and not ln.startswith("#"):
            dishes[cur].append(ln)
    x0, y0 = (a["SCAN_CX"] // 8 - 15) * 8, a["SCAN_CY"] - 34

    def dish_px(name):
        out = []
        for i, r in enumerate(dishes[name]):
            top = y0 + i + (i + 1) // 2          # an even row is drawn twice
            lines = [top] + ([top + 1] if i % 2 == 0 else [])
            for x, c in enumerate(r):
                if c == "#":
                    out += [(x0 + 2 * x + d, y) for y in lines for d in (0, 1)]
        return out
    box = (x0 + 8, y0, x0 + 232, y0 + 69)       # clear of the compass above
    im = shot(list(BOOT), "dash-base")            # docked at start, a Cobra Mk III
    if im:
        want = [p for p in dish_px("base") if box[0] <= p[0] < box[2] and box[1] <= p[1] < box[3]]
        hit, n, stray = compare(im, want, box)
        # the scanner's blips (the station, its stalk) are XORed over the
        # dish: a score of pixels either way is theirs, not the dish's
        check("the dashboard carries the cockpit's own scanner dish (Base), pixel for pixel",
              hit >= n - 16 and stray <= 24, f"{hit} of {n} lit, {stray} stray (the blips)")
    for num, name in ((2, "thd"), (4, "kladov"), (5, "targon")):
        pokes = [poke_at(a["CKV_NUM"], 13), poke_at(a["CKV_SCAN"], num), poke_at(a["CKV_MAXMISS"], 8),
                 poke_at(a["PMISSILES"], 3), poke_at(a["P_MISSTYPE"], 2)]
        im = shot(list(BOOT) + pokes + ["press 004", "run 150"] * 10 + ["run 50"], f"dash-{name}")
        if not im:
            continue
        want = [p for p in dish_px(name) if box[0] <= p[0] < box[2] and box[1] <= p[1] < box[3]]
        hit, n, stray = compare(im, want, box)
        check(f"another cockpit's dish ({name}) when the cockpit changes, pixel for pixel",
              hit >= n - 16 and stray <= 24, f"{hit} of {n} lit, {stray} stray (the blips)")
        if name == "thd":
            # the rack: eight cells, three standard (green), two military
            # (red), three dark
            cells = []
            for k in range(8):
                c = im.getpixel(((a["LBAR_BX"] + k) * 8 + 3, a["RACK_Y"] + 2))
                cells.append("g" if c[1] > 100 and c[0] < 100 else "r" if c[0] > 100 else ".")
            check("the rack holds the cockpit's eight: the standard missiles, then the military",
                  "".join(cells) == "gggrr...", "".join(cells))

    # 3. no rack where the cockpit has none; the fuel gauge's full scale
    #    is the cockpit's tank
    fuel_y = a["LBAR_Y"] + 2 * a["BAR_STEP"] + 2
    pokes = [poke_at(a["CKV_NUM"], 15), poke_at(a["CKV_MAXMISS"], 0), poke_at(a["CKV_MAXFUEL"], 200),
             poke_at(a["PFUEL"], 100)]
    im = shot(list(BOOT) + pokes + ["press 004", "run 150"] * 10 + ["run 50"], "dash-none")
    if im:
        rack = sum(1 for k in range(10) for x in range(8)
                   if sum(im.getpixel(((a["LBAR_BX"] - 6 + k) * 8 + x, a["RACK_Y"] + 3))) > 120)
        lit = sum(1 for k in range(a["BAR_W"]) if sum(im.getpixel(((a["LBAR_BX"] + k) * 8 + 3, fuel_y))) > 120)
        check("no rack, and no label for it, in a cockpit without missiles", rack == 0, f"{rack} pixels lit")
        check("the fuel gauge's full scale is the cockpit's tank: 100 of 200 is half",
              lit == a["BAR_W"] * 100 // 200, f"{lit} of {a['BAR_W']} columns")


def check_splash():
    """Two modal startup pages; one fresh Enter each, then the normal logo."""
    print("startup splash pages")
    from PIL import Image
    t = syms.table()
    out = ROOT / "tmp/splash"
    out.mkdir(exist_ok=True)
    page = f"peekcpu {t['SP_PAGE']}"
    overlay = f"peekcpu {t['OVL_CUR']}"
    script = list(POWER_ON) + [page, f"screenshot {out/'welcome.bmp'}",
        "press 107", "press 004", "press 166", "run 120", page,
        "keydown 153", "run 150", page, f"screenshot {out/'controls.bmp'}",
        "run 300", page, "keyup 153", "run 60", page,
        "press 107", "press 004", "run 60", page,
        "press 153", "run 300", overlay, f"peekcpu {t['TI_TICK']}",
        f"screenshot {out/'logo.bmp'}"] + CHOOSE_KEYS + COMMANDER_KEYS + [
        f"peekcpu {t['DOCKED']}", "press 006", "run 100", "press 027", "run 200",
        overlay, "quit"]
    vals = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("splash")))]
    check("splash run returned every observation", len(vals) == 10, str(vals))
    if len(vals) != 10:
        return
    check("cold boot holds on the welcome; other keys cannot advance", vals[:2] == [1, 1])
    check("first Enter opens controls and holding it does not skip them", vals[2:4] == [2, 2])
    check("releasing Enter and pressing other keys leave controls visible", vals[4:6] == [2, 2])
    check("second Enter reaches the existing animated title", vals[6] == int(t['OVL_TITLE'], 8) and vals[7] > 0)
    check("normal commander selection still reaches the docked game", vals[8] == 1)
    check("new game returns to the logo without replaying startup pages", vals[9] == int(t['OVL_TITLE'], 8))
    for name in ("welcome", "controls", "logo"):
        im = Image.open(out/f"{name}.bmp")
        im.save(out/f"{name}.png")
    # Check the exact Russian footer text against the ROM font, including
    # the empty background; this catches wrong encoding or clipped rows.
    from font_gen import read_font
    from text_gen import to_koi7
    font = read_font(ROOT / "src/res/font/uknc11.txt")
    for name, text, col in (("welcome", "ВВОД: К СПРАВОЧНОМУ ЭКРАНУ", 3),
                            ("controls", "ВВОД: К ИГРЕ", 32)):
        im = Image.open(out/f"{name}.png").convert("RGB")
        codes = to_koi7(text, name)
        wrong = 0
        for i, code in enumerate(codes):
            for y, row in enumerate(font[code]):
                for x in range(8):
                    lit = sum(im.getpixel((8*(col+i)+x, 272+y))) > 120
                    wrong += lit != (row[x] == "#")
        check(f"{name} shows its complete Russian Enter prompt", wrong == 0, f"{wrong} wrong pixels")


def check_palette():
    from verify_palette import check_palette as run
    run(sys.modules[__name__])


def check_title():
    """The game opens on a title screen, with a tune, and asks who is flying."""
    print("the title screen")
    t = syms.table()
    need = ["FLY_TICK", "TI_TICK", "DOCKED", "CMDR_NAME", "SX_QH"]
    if any(n not in t for n in need):
        check("title symbols found", False,
              f"missing {[n for n in need if n not in t]}")
        return
    wav = ROOT / "tmp" / "verify-title.wav"
    wav.parent.mkdir(exist_ok=True)
    disk = fresh_disk("title")                  # no commander: the name is asked

    script = list(TITLE_BOOT) + ["wavstart", "run 300",
              f"peekcpu {t['TI_TICK']}", f"peekcpu {t['FLY_TICK']}",
              f"wavstop {wav}",
              "press 107", "run 700",           # ФИКС starts (BOOT's gaps:
              "press 030", "run 250",            #   the chooser is an overlay
              "press 067", "run 8",             #   read off the disk now)
                                                # and a name: Я
              "press 112", "run 8",             # М
              "press 153", "run 350",            # ВВОД takes it
              f"peekcpu {t['CMDR_NAME']}", f"peekcpu {t['DOCKED']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, disk))]
    if len(v) < 4:
        check("the title run answered", False, f"{len(v)} peeks")
        return
    check("the title holds before the game starts", v[0] > 0 and v[1] == 0,
          f"{v[0]} title frames, {v[1]} flight frames")
    # КОМАНДИР's name is two KOI-7 bytes to a word: Я is 0121, М is 0115
    check("a new commander is asked for a name", v[2] == 0o115 * 256 + 0o121,
          f"first two letters {v[2]:o}")
    check("and the game starts docked afterwards", v[3] == 1, str(v[3]))

    if wav.exists():
        r = subprocess.run([sys.executable, "tools/wav_analyze.py", str(wav)],
                           cwd=ROOT, capture_output=True, text=True)
        m = re.search(r"(\d+)/(\d+) active", r.stdout)
        active = int(m.group(1)) if m else 0
        check("and there is a tune over it", active > 100,
              f"{active} active windows")
    else:
        check("title audio captured", False)


def check_cockpit():
    """What the cockpit tells the commander, and what the ships do about him."""
    print("the cockpit")
    t = syms.table()
    need = ["MISS_LOCK", "LOCK_SHOWN", "LEGAL", "P_DOCKCOMP", "DOCKED",
            "UNIV", "U.SIZE", "U.TYPE", "U.FLAGS", "U.X", "U.Y", "U.Z",
            "U.ENERGY", "U.EXPL", "U.TARGET", "SH_COBRA3", "SH_SIDEWINDER",
            "PENERGY", "PSHIELD_F", "WITCH", "U.AI3", "SHIP_HURT"]
    if any(n not in t for n in need):
        check("cockpit symbols found", False,
              f"missing {[n for n in need if n not in t]}")
        return

    def poke_slot(slot, name, val):
        return poke_at(int(slot_field(t, slot, name), 8), val)

    # ---- the gunsight is really on the screen ------------------------
    # Looking astern right after a launch is the one view with nothing in
    # it, so any lit pixel round the middle is the sight and not a ship.
    shot = ROOT / "tmp" / "verify-sight.bmp"
    if shot.exists():
        shot.unlink()
    # The banks are refilled before the shot for the reason check_views
    # gives: astern the frame rate goes up, the AI shoots per frame, and
    # a dead commander is a screenshot of ИГРА ОКОНЧЕНА in 4x letters
    # rather than of a gunsight.
    alive = [poke_at(int(t["PENERGY"], 8), 255),
             poke_at(int(t["PSHIELD_F"], 8), 255)]
    # Since the bases (2026-09-10) Lave's service station hangs 18000
    # behind the launch point, dead astern, and its dot lands in the
    # sight's hole: the slots after the 1985 layout's five are emptied.
    usize = int(t["U.SIZE"], 8)
    nuniv = int(t["NUNIV"], 8)
    nobases = [poke_slot(slot, "U.TYPE", 0) for slot in range(5, nuniv)]
    script = (BOOT + ["press 107", "run 150"] + nobases + ["press 030"] +
              alive + ["run 20"] + alive + ["run 20"] + alive +
              ["run 20", f"screenshot {shot}", "quit"])
    run_emu(script, fresh_disk("sight"))
    if not shot.exists():
        check("the sight screenshot was taken", False)
    else:
        try:
            from PIL import Image
            im = Image.open(shot).convert("L")
            w, h = im.size
            cx, cy = 320 * w // 640, 100 * h // 288
            lit = [im.getpixel((cx, cy - 15)) > 40,      # the four ticks
                   im.getpixel((cx, cy + 15)) > 40,
                   im.getpixel((cx - 15, cy)) > 40,
                   im.getpixel((cx + 15, cy)) > 40]
            hole = im.getpixel((cx, cy)) <= 40           # and the hole
            check("the gunsight is drawn", all(lit), f"{lit}")
            check("with a hole to see the target through", hole)
        except ImportError:
            check("Pillow available for the sight check", False)

    # ---- a lock says so ---------------------------------------------
    # With a target of its own parked dead ahead, the way check_missiles
    # parks one.  This used to fly for 150 ticks and press space at
    # whatever Lave happened to have in the crosshair, which is not a
    # test of the lock but of the traffic: it passed on one build and
    # failed on the next for no reason but a faster frame rate putting a
    # different ship in front of the gunsight.
    script = BOOT + ["press 107", "run 150"] + clear_traffic(t) + [
                     poke_slot(5, "U.TYPE", int(t["SH_SIDEWINDER"], 8)),
                     poke_slot(5, "U.FLAGS", 0),
                     poke_slot(5, "U.EXPL", 0),
                     poke_slot(5, "U.TARGET", 0),
                     poke_slot(5, "U.ENERGY", 4000),
                     poke_slot(5, "U.X", 0),
                     poke_slot(5, "U.Y", 0),
                     poke_slot(5, "U.Z", 1200),
                     poke_slot(5, "U.SPEED", 0)] + mind(t, 5, "SIDEWINDERH", still=True) + [
                     "run 20",
                     f"peekcpu {t['LOCK_SHOWN']}",
                     "press 113", "run 20",
                     f"peekcpu {t['MISS_LOCK']}", f"peekcpu {t['LOCK_SHOWN']}",
                     # and away it goes - forty ticks on: a press while
                     # the last one's release is still unheard is no edge
                     "run 20", "press 113", "run 20",
                     f"peekcpu {t['LOCK_SHOWN']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("lock")))]
    if len(v) >= 4:
        check("nothing is locked to begin with", v[0] == 0, str(v[0]))
        check("a lock says so on the screen", v[1] != 0 and v[2] == 1,
              f"slot {v[1]}, shown {v[2]}")
        check("and stops saying so when the missile goes", v[3] == 0,
              str(v[3]))

    # ---- an offence can be lived down -------------------------------
    fugitive = int(t["LEGAL_FUGITIVE"], 8)     # two offences, in Legend's units
    offence = int(t["LEGAL_OFFENCE"], 8)
    script = BOOT + [poke_at(int(t["LEGAL"], 8), fugitive),
                     poke_dev(t, "P_DOCKCOMP"), "press 107", "run 50"]
    for _ in range(4):
        script += ["press 166", "run 20"]
    # The banks are refilled as the approach is flown, the way
    # check_views and check_traffic refill them.  LEGAL 2 has the station
    # scramble Vipers, and the law shoots per FRAME: once the renderer
    # got quicker there were enough frames in the same emulated second
    # for five of them to hold the commander at an energy of 3 for as
    # long as the check cared to watch - two thousand ticks was not
    # enough, and no number of ticks would have been.  Kept alive, the
    # computer has him inside by about the four-hundredth.  What is
    # under test here is the offence coming off the record, not whether
    # a wanted commander can outlive the law.
    for _ in range(7):
        script += [poke_at(int(t["PENERGY"], 8), 255),
                   poke_at(int(t["PSHIELD_F"], 8), 255), "run 100"]
    script += [f"peekcpu {t['DOCKED']}", f"peekcpu {t['LEGAL']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("legal")))]
    if len(v) >= 2:
        check("docking works an offence off the record",
              v[0] == 1 and v[1] == fugitive - offence,
              f"docked {v[0]}, status {v[1]}")

    # ---- a trader that is shot at is not the one that runs ------------
    # Legend's trader turns on you (and the sky with it) when shot: what
    # runs is a ship whose faith in its hull is gone, eight hits on, with
    # no station near.  check_ai has the anger; here, the Cobra shot at
    # eight times with the station gone (WITCH keeps the sky empty; the
    # station slot is emptied) and outside the reaction radius has FL3
    # under 16 and flees: F3_FLEE set and its distance growing. Observe
    # eight actual hits: a fixed emulated interval can end between shots.
    fl3 = f"peekcpu {slot_field(t, 5, 'U.AI3')}"
    script = BOOT + ["press 107", "run 60"] + clear_traffic(t) + [poke_at(int(t["WITCH"], 8), 1),
                     poke_at(int(slot_field(t, 2, "U.TYPE"), 8), 0)]
    script += ship_pokes(t, 5, "COBRAMK3HT1", z=1500, hostile=False, energy=4000, hyper=False)
    script += [poke_at(int(t["PSPEED"], 8), 0),        # parked: its distance is its own doing
               fl3, "keydown 107"]
    for _ in range(8):
        # Only the trader can be hit in this fixture. Advance past the
        # routine entry before waiting for the next hit, then read its faith.
        script += [f"runpc {t['SHIP_HURT']} 300", "run 1", fl3]
    script += ["keyup 107", ui_ready(t, frames=20),
               f"peekcpu {slot_field(t, 5, 'U.FLAGS')}", fl3,
               f"peekcpu {slot_field(t, 5, 'U.Z')}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("flee")))]
    faith = [word & 0x7F for word in v[:9]]
    check("eight observed laser hits take fourteen faith each",
          len(v) == 12 and faith == list(range(126, 13, -14)), str(faith))
    if len(v) == 12:
        v = v[-3:]
        check("a trader shot to pieces of its faith runs for it",
              v[0] & 1 and v[1] & 0x80 and v[1] & 0x7F < 16, f"flags {v[0]:o}, faith {v[1] & 0x7F}, fled {v[1] >> 7 & 1}")
        check("and puts distance behind it", v[2] > 1500, f"{v[2]} away")


def check_law():
    """The law as Legend keeps it: a Viper turns on a commander the law
    wants (DirectObject's legal check), shoots only an aggressor
    (MoveObject's police rule), and a kill is judged by its kind
    (TablLegalStatus)."""
    print("the law")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "U.TYPE", "U.FLAGS", "LEGAL", "LEGAL_FUGITIVE", "PSHIELD_F", "PSHIELD_A",
            "PENERGY", "SH_VIPERH", "SH_KRAITH", "SH_COBRAMK3HT1", "AGGRESSOR", "WITCH", "KILLS"]
    if any(n not in t for n in need):
        check("law symbols found", False, f"missing {[n for n in need if n not in t]}")
        return
    a = {n: int(t[n], 8) for n in need}
    alive = [poke_at(a["PENERGY"], 255), poke_at(a["PSHIELD_F"], 255), poke_at(a["PSHIELD_A"], 255),
             poke_at(int(t["PSPEED"], 8), 0)]
    quiet = clear_traffic(t) + [poke_at(a["WITCH"], 1)]
    flags = f"peekcpu {slot_field(t, 5, 'U.FLAGS')}"

    # 1. a peaceful Viper meets a fugitive: hostile within a few reactions;
    #    a clean commander it leaves alone
    def meet(legal):
        script = list(BOOT) + ["press 107", "run 40"] + quiet + [poke_at(a["LEGAL"], legal)]
        script += ship_pokes(t, 5, "VIPERH", x=500, z=3000, hostile=False, energy=4000, hyper=False)
        script += alive + ["run 60", flags, "quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("law")))]
        return v[0] if v else None
    wanted, clean = meet(a["LEGAL_FUGITIVE"]), meet(0)
    check("a Viper turns on a commander the law wants, and only him",
          wanted is not None and wanted & 1 and clean is not None and not clean & 1,
          f"flags {wanted:o} wanted, {clean:o} clean" if wanted is not None and clean is not None else "no answer")

    # 2. the police shoot only an aggressor: a hostile Viper dead ahead, the
    #    shield sampled through a window with AGGRESSOR clear and then set
    def window(aggressor):
        script = list(BOOT) + ["press 107", "run 40"] + quiet + [poke_at(a["AGGRESSOR"], aggressor)]
        # alone in the sky, sample after sample: a hostile policeman makes
        # the whole sky angry (PlayerPirate), the station scrambles Vipers
        # and they fire missiles whoever you are - a blow that is the
        # launch roll's, not the gun's, and not what is measured here
        script += ship_pokes(t, 5, "VIPERH", z=1200, energy=4000, hyper=False, facing=True)
        others = [poke_at(int(slot_field(t, k, "U.TYPE"), 8), 0)
                  for k in [2] + list(range(6, int(t["NUNIV"], 8)))]
        out = []
        for _ in range(30):
            out += alive + others + [poke_at(int(slot_field(t, 5, "U.X"), 8), 0), poke_at(int(slot_field(t, 5, "U.Y"), 8), 0),
                            poke_at(int(slot_field(t, 5, "U.Z"), 8), 1200), "run 10", f"peekcpu {t['PSHIELD_F']}"]
        script += out + ["quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("police")))]
        return sum(1 for x in v if x < 255)
    innocent, guilty = window(0), window(1)
    check("the police hold their fire unless you are an aggressor", innocent == 0 and guilty > 0,
          f"{innocent} hits on the innocent, {guilty} on the aggressor")

    # 3. what a kill is worth to the record: a pirate takes 30 off it, a
    #    trader puts 112 on (v1.09's table), with a floor of nothing; and
    #    to the commander (SHIP_KILLED): the header's bounty into the
    #    purse and its rating points onto the combat rating - read as a
    #    difference, which is also the proof that it was the target that
    #    died and nothing else
    money = [f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}",
             f"peekcpu {t['P_RATING']}", f"peekcpu {int(t['P_RATING'], 8) + 2:o}"]
    def kill(key, legal):
        script = list(BOOT) + ["press 107", "run 40"] + quiet + [poke_at(a["LEGAL"], legal)]
        script += ship_pokes(t, 5, key, z=900, hostile=False, energy=20) + money
        script += ["keydown 107", "run 40", "keyup 107", "run 4", f"peekcpu {t['KILLS']}", f"peekcpu {t['LEGAL']}"]
        script += money + ["quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("kill")))]
        if len(v) != 10:
            return None, None, None, None
        cash = ((v[7] << 16) + v[6]) - ((v[1] << 16) + v[0])
        rating = ((v[9] << 16) + v[8]) - ((v[3] << 16) + v[2])
        return v[4], v[5], cash, rating
    k1, l1, c1, r1 = kill("KRAITH", 50)
    k2, l2, c2, r2 = kill("COBRAMK3HT1", 0)
    check("a pirate's death takes 30 off the record, a trader's puts 112 on",
          k1 and l1 == 20 and k2 and l2 == 112, f"pirate: {k1} kills, record {l1}; trader: {k2} kills, record {l2}")
    kr, cb = ship_stats("KRAITH"), ship_stats("COBRAMK3HT1")
    check("a kill pays its bounty into the purse and its points onto the rating",
          c1 == kr["bounty"] and r1 == kr["rating"] and c2 == cb["bounty"] and r2 == cb["rating"],
          f"pirate: {c1} tenths, {r1} points (header {kr['bounty']}, {kr['rating']}); "
          f"trader: {c2}, {r2} (header {cb['bounty']}, {cb['rating']})")


def check_chart():
    """The chart says what the tank will reach."""
    print("the chart")
    t = syms.table()
    if any(n not in t for n in ("HOME_X", "HOME_Y", "PFUEL")):
        check("chart symbols found", False)
        return
    shot = ROOT / "tmp" / "verify-chart.bmp"
    if shot.exists():
        shot.unlink()
    script = BOOT + ["press 004", ui_ready(),
                     f"peekcpu {t['HOME_X']}", f"peekcpu {t['HOME_Y']}",
                     f"peekcpu {t['PFUEL']}",
                     f"screenshot {shot}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("chart")))]
    if len(v) < 3 or not shot.exists():
        check("the chart run answered", False)
        return
    hx, hy, fuel = v
    # the same arithmetic src/screens.mac uses: x*2.25, y/2 + 20, and
    # 4.5 chart pixels of range per tenth of a light year
    cx = hx * 2 + (hx * 2) // 8
    cy = hy // 2 + 20
    rx = fuel * 4 + fuel // 2
    try:
        from PIL import Image
        im = Image.open(shot).convert("L")
        w, h = im.size
        sx, sy = w / 640.0, h / 288.0

        def lit(x, y):
            if not (0 <= x < 640 and 0 <= y < 288):
                return None
            return im.getpixel((int(x * sx), int(y * sy))) > 40

        # the rightmost point of the range ellipse, and a pixel just
        # outside it
        on = any(lit(cx + rx + dx, cy + dy) for dx in (-1, 0, 1)
                 for dy in (-1, 0, 1) if lit(cx + rx + dx, cy + dy) is not None)
        check("the range circle is drawn", on,
              f"home ({hx},{hy}) -> chart ({cx},{cy}), radius {rx}")
    except ImportError:
        check("Pillow available for the chart check", False)


def check_commanders():
    """A disk holds four commanders, and they do not run into each other."""
    print("commanders")
    t = syms.table()
    need = ["CMDR_SLOT", "CASH_L", "DOCKED", "P_DOCKCOMP", "CMDR_NAME"]
    if any(n not in t for n in need):
        check("commander symbols found", False)
        return
    disk = fresh_disk("cmdrs")
    title = TITLE_BOOT + CHOOSE_KEYS        # to the chooser, with BOOT's own waits: the
                            # chooser loses a key pressed while it reads
                            # the slot names (see BOOT)

    # make a commander in the SECOND slot, buy something, and dock to save
    script = title + ["press 031", f"runpc {t['NAME_READY']} 1200",  # empty slot 2
                      "press 067", "run 8",            # a name: Я
                      "press 153", ui_ready(t),
                      poke_dev(t, "P_DOCKCOMP")]
    for _ in range(5):
        script += ["press 004", ui_ready(t)]              # to the outfitter
    script += ["press 107", ui_ready(t)]                          # buy a missile
    script += ["press 004", ui_ready(t)] * (int(t["NSCREENS"], 8) - 5)  # -> cockpit
    script += ["press 107", ui_ready(t, frames=1), f"peekcpu {t['DOCKED']}"]                          # launch
    for _ in range(4):
        script += ["press 166", "run 20"]              # throttle to zero
    script += [f"waitcpu {t['DOCKED']} 1 2000", ui_ready(t, frames=1), f"peekcpu {t['DOCKED']}",
               f"peekcpu {t['CMDR_SLOT']}", f"peekcpu {t['CASH_L']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, disk))]
    if len(v) != 4:
        check("the commander run answered", False)
        return
    check("the new commander actually launches before the docking save", v[0] == 0)
    v = v[1:]
    check("a commander can be made in any slot", v[1] == 1, f"slot {v[1]}")
    check("and docking saves him there", v[0] == 1, f"docked {v[0]}")
    saved = v[2]

    # the FIRST slot is still empty, so it asks for a name
    script = title + ["press 030", f"runpc {t['NAME_READY']} 1200", "press 153", ui_ready(t),
                      f"peekcpu {t['CASH_L']}", f"peekcpu {t['CMDR_SLOT']}",
                      "quit"]
    w = [int(x, 8) for x in PEEK.findall(run_emu(script, disk))]
    if len(w) >= 2:
        check("the other slots are still empty", w[0] == 1000 and w[1] == 0,
              f"{w[0]} tenths in slot {w[1]}")

    # and the second still has the commander who was saved in it
    script = title + ["press 031", ui_ready(frames=1),
                      f"peekcpu {t['CASH_L']}", f"peekcpu {t['CMDR_SLOT']}",
                      "quit"]
    w = [int(x, 8) for x in PEEK.findall(run_emu(script, disk))]
    if len(w) >= 2:
        check("and the one that was saved comes back",
              w[0] == saved and w[1] == 1, f"{w[0]} tenths, slot {w[1]}")


def check_planets():
    """Who lives there, what the place is known for, and the near map."""
    print("worlds and their neighbours")
    t = syms.table()
    if any(n not in t for n in ("SCREEN", "SYS_SEED", "CURSYS")):
        check("planet symbols found", False)
        return

    # The data page for Lave: the species line comes out of the seed, so
    # it is the same every time - green bug-eyed birds, as it happens.
    shot = ROOT / "tmp" / "verify-data.bmp"
    if shot.exists():
        shot.unlink()
    script = BOOT + ["press 004", ui_ready(t), "press 004", ui_ready(t),
                     "press 004", ui_ready(t),
                     f"peekcpu {t['SCREEN']}", f"screenshot {shot}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("data")))]
    check("the data page is where it should be", v and v[0] == 3,
          f"screen {v[0] if v else None}")
    if shot.exists():
        try:
            from PIL import Image
            im = Image.open(shot).convert("L")
            w, h = im.size
            # the species row and the description row have ink in them
            def row_ink(y):
                yy = int(y * h / 288)
                return sum(1 for x in range(0, w, 2)
                           if im.getpixel((x, yy)) > 40)
            check("it says who lives there", row_ink(124) > 10,
                  f"{row_ink(124)} lit")
            check("and what the place is known for", row_ink(140) > 6,
                  f"{row_ink(140)} lit")
        except ImportError:
            check("Pillow available for the data check", False)

    # The short-range chart: names, and the system you are in at the
    # middle of it.
    shot2 = ROOT / "tmp" / "verify-short.bmp"
    if shot2.exists():
        shot2.unlink()
    script = BOOT + ["press 004", ui_ready(t), "press 004", ui_ready(t),
                     f"peekcpu {t['SCREEN']}", f"screenshot {shot2}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("short")))]
    check("the short-range chart opens", v and v[0] == 2,
          f"screen {v[0] if v else None}")
    if shot2.exists():
        try:
            from PIL import Image
            im = Image.open(shot2).convert("L")
            w, h = im.size
            ink = sum(1 for y in range(int(20 * h / 288), int(170 * h / 288), 2)
                      for x in range(0, w, 2) if im.getpixel((x, y)) > 40)
            check("and has the neighbours' names on it", ink > 400,
                  f"{ink} lit")
        except ImportError:
            check("Pillow available for the chart check", False)


def check_saving():
    """Save a commander by docking, then reboot and find him again.

    Runs on a disposable RT-11 volume and reuses it explicitly for the
    reload. Native commander files and monitor swapping may both write.
    """
    print("saving a commander")
    t = syms.table()
    need = ["PMISSILES", "CASH_L", "P_DOCKCOMP", "DOCKED", "PILOT",
            "PILOT_LEN", "P_TIME", "P_MSTAT"]
    if any(n not in t for n in need):
        check("save symbols found", False)
        return
    disk = fresh_disk("save")

    boot = list(BOOT)
    first = boot + [poke_dev(t, "P_DOCKCOMP")]
    for _ in range(5):
        first += ["press 004", ui_ready(t)]                 # to the outfitter
    first += ["press 107", "run 35",                          # buy a missile
              f"peekcpu {t['PMISSILES']}", f"peekcpu {t['CASH_L']}"]
    first += ["press 004", ui_ready(t)] * (int(t["NSCREENS"], 8) - 5)   # -> cockpit
    first += ["press 107", ui_ready(t, frames=1)]                          # launch
    for _ in range(4):
        first += ["press 166", "run 20"]                 # throttle round to zero
    # Long enough for the computer to roll the ship into line with the
    # slot as well as fly it in: matching the slot is new, and 300 ticks
    # was the budget from before it existed.
    # The whole record is dumped on both sides of the reboot: Legend's
    # PilotDataSaved goes to the disk as it stands, and everything in it
    # but the clock - which runs on - has to come back the same.
    pilot = int(t["PILOT"], 8)
    plen = int(t["PILOT_LEN"], 8)
    before = ROOT / "tmp" / "verify-pilot-before.bin"
    after = ROOT / "tmp" / "verify-pilot-after.bin"
    for f in (before, after):
        if f.exists():
            f.unlink()
    # dumpcpu's length is DECIMAL (atoi in uknc-headless), the address octal
    first += [f"waitcpu {t['DOCKED']} 1 2000", ui_ready(t, frames=1), f"peekcpu {t['DOCKED']}",
              f"dumpcpu {pilot:o} {plen} {before}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(first, disk))]
    if len(v) < 3:
        check("the save run answered", False)
        return
    check("bought before saving", v[0] == 4, f"{v[0]} missiles")
    check("docked, which saves", v[2] == 1, str(v[2]))

    second = boot + [f"peekcpu {t['PMISSILES']}", f"peekcpu {t['CASH_L']}",
                     peek_dev(t, "P_DOCKCOMP"), f"peekcpu {t['CMDR_NAME']}",
                     f"dumpcpu {pilot:o} {plen} {after}", "quit"]
    w = [int(x, 8) for x in PEEK.findall(run_emu(second, disk))]
    if len(w) < 3:
        check("the reload run answered", False)
        return
    check("missiles survive a reboot", w[0] == v[0], f"{w[0]}")
    check("the purse survives", w[1] == v[1], f"{w[1]} tenths")
    check("equipment survives", dev_fitted(t, "P_DOCKCOMP", w[2]), f"{w[2]:o}")
    if len(w) >= 4:
        check("and so does the commander's name", w[3] != 0,
              f"first two letters {w[3]:o}")
    if before.exists() and after.exists():
        a, b = bytearray(before.read_bytes()), bytearray(after.read_bytes())
        clock = int(t["P_TIME"], 8) - pilot
        clock_end = int(t["P_MSTAT"], 8) - pilot
        a[clock:clock_end] = b[clock:clock_end] = b"\0" * (clock_end - clock)
        differ = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
        check("and the whole record, byte for byte, but the clock",
              len(a) == plen and len(b) == plen and not differ,
              f"{len(differ)} bytes differ, first at {differ[:6]}")
    else:
        check("the record was dumped on both sides", False)


def check_compass():
    """The ring above the scanner, and the dot that says where to turn."""
    print("the compass")
    t = syms.table()
    need = ["CO_M", "CO_Z", "UNIV", "U.SIZE", "U.X", "U.Y", "PENERGY",
            "PSHIELD_F"]
    if any(n not in t for n in need):
        check("compass symbols found", False,
              f"missing {[n for n in need if n not in t]}")
        return

    # The ring is drawn once, with the rest of the dashboard frame, so a
    # screenshot catches it whatever the segment buffer is doing.
    shot = ROOT / "tmp" / "verify-compass.bmp"
    if shot.exists():
        shot.unlink()
    run_emu(BOOT + ["press 107", "run 200", f"screenshot {shot}", "quit"],
            fresh_disk("compass"))
    try:
        from PIL import Image
        im = Image.open(shot).convert("L")
        def near(cx, cy):                            # the ring is an octagon
            return any(im.getpixel((x, y)) > 40          # 30 by 18: sample a
                       for x in range(cx - 2, cx + 3)    # little around each
                       for y in range(cy - 2, cy + 3))   # cardinal point
        ring = [near(320, 203), near(320, 217),      # top and bottom
                near(306, 210), near(334, 210)]      # and the two sides
        check("the compass ring is drawn", all(ring), f"{ring}")
    except ImportError:
        check("Pillow available for the compass check", False)

    # And the dot: with the station poked hard to starboard the bearing
    # it works out has to come back with x positive.  CO_M is the largest
    # component it scaled against, which is what says it ran at all.
    def bearing(px, py):
        sx = int(slot_field(t, 2, "U.X"), 8)
        sy = int(slot_field(t, 2, "U.Y"), 8)
        script = BOOT + ["press 107", "run 200",
                         poke_at(sx, px), poke_at(sy, py), "run 2",
                         f"peekcpu {t['CO_M']}", f"peekcpu {t['CO_Z']}", "quit"]
        v = [signed(int(x, 8)) for x in PEEK.findall(
            run_emu(script, fresh_disk("cdot")))]
        return v

    v = bearing(4000, 2000)
    check("and it has a bearing to work with", len(v) >= 2 and v[0] > 0,
          f"largest component {v[0] if v else None}")


def check_manifest():
    """What is in the hold, and a market that moves when it is traded in."""
    print("the hold and the market")
    t = syms.table()
    need = ["CARGO", "P_PRODUCT", "MKT_SEL", "SCREEN", "PI_X0", "PI_Y0", "PI_STEP", "FONT_H"]
    if any(n not in t for n in need):
        check("manifest symbols found", False)
        return
    disk = fresh_disk("manifest")

    # Buy three of the first commodity and two of the second, then read
    # the hold back out of CARGO and look at the status page.
    shot = ROOT / "tmp" / "verify-manifest.bmp"
    if shot.exists():
        shot.unlink()
    script = list(BOOT)     # a copy: += on BOOT would grow it
    for _ in range(4):
        script += ["press 004", ui_ready(t)]              # -> the market
    script += [f"peekcpu {t['P_PRODUCT']}"]
    for _ in range(3):
        script += ["press 133", ui_ready(t, frames=1)]              # three of the first
    script += ["press 134", ui_ready(t, frames=1)]
    for _ in range(2):
        script += ["press 133", ui_ready(t, frames=1)]              # two of the second
    cargo = int(t["CARGO"], 8)
    script += [f"peekcpu {t['P_PRODUCT']}",
               f"peekcpu {cargo:o}", f"peekcpu {cargo + 2:o}",
               "press 004", ui_ready(t), "press 004", ui_ready(t),
               "press 004", ui_ready(t),  # market -> equip -> yard -> pilot
               f"peekcpu {t['SCREEN']}", f"screenshot {shot}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, disk))]
    if len(v) < 5:
        check("the market run answered", False)
        return
    check("three tonnes bought are three tonnes held", v[2] == 3, str(v[2]))
    check("and the second commodity too", v[3] == 2, str(v[3]))
    check("buying takes it off the shelf", v[0] - v[1] == 3,
          f"{v[0]} -> {v[1]} in stock")
    check("the status page is up", v[4] == 7, f"screen {v[4]}")
    if shot.exists():
        try:
            from PIL import Image
            im = Image.open(shot).convert("L")
            from font_gen import read_font
            from market_gen import read_goods
            from text_gen import to_koi7
            font = read_font(ROOT / "src/res/font/uknc11.txt")
            goods = read_goods(ROOT / "src/res/legend/market/goods.txt")
            x0 = int(t["PI_X0"], 8) * 8
            height = int(t["FONT_H"], 8)
            matches = []
            for row, quantity in enumerate((3, 2)):
                name = goods[row][-1]
                if len(name) > 16:
                    name = name[:15] + "."
                text = f"{name:<16} {quantity:4d}"
                y0 = int(t["PI_Y0"], 8) + (13 + row) * int(t["PI_STEP"], 8)
                expected = Image.new("1", (len(text)*8, height))
                for col, char in enumerate(to_koi7(text, "manifest")):
                    for y, pixels in enumerate(font[char]):
                        for x, pixel in enumerate(pixels):
                            if pixel == "#":
                                expected.putpixel((col*8+x,y),1)
                actual = im.crop((x0,y0,x0+len(text)*8,y0+height)).point(lambda p:255 if p>40 else 0,"1")
                matches.append(actual.tobytes() == expected.tobytes())
            check("and it lists what is aboard", all(matches),
                  f"exact commodity names and quantities: {matches}")
        except ImportError:
            check("Pillow available for the manifest check", False)


def legend_goods():
    """Legend's commodity table, (price, grad, quant, mask) a good."""
    rows = []
    for line in (ROOT / "src/res/legend/market/goods.txt").read_text(
            encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            f = line.split("|")[0].split()
            rows.append(tuple(int(x) for x in f[2:6]))
    return rows


def legend_station(goods, rnd, econ):
    """genStationPrice (Galaxy/genData.a80), in Python: the prices and
    the stock of the station's market for the random byte and the
    economy.  The subtraction is the Z80's cpl-and-add, one more than
    the product; alien items are never stocked and eight times the
    price (v1.09) until mission 3 has them."""
    P, Q = [], []
    for p, g, q, m in goods:
        k = (g & 31) * econ
        r = rnd & m
        c = p + r + ((-k - 1) if g & 128 else k)
        P.append((c * 4) & 0xFFFF)
        a = (q + r + (k if g & 128 else -k - 1)) & 0xFF
        Q.append(0 if a & 128 else a & 63)
    P[16] = (P[16] * 8) & 0xFFFF
    Q[16] = 0
    return P, Q


def legend_asteroid(goods, rnd, econ):
    """genAsteriodPrice: the hermit's rock.  The stock is three bits and
    the subtraction is neg; the price adds the quantity byte's low five
    bits (the Z80 reads the wrong byte and the game shipped so); then
    minerals to gems are cut to a quarter with the two shifted-out bits
    added back swapped, and alien items trebled."""
    P, Q = [], []
    for p, g, q, m in goods:
        k = (g & 31) * econ
        r = rnd & m
        a = (q + r + (k if g & 128 else -k)) & 0xFF
        Q.append(a & 7)
        c = p + r + (q & 31) + ((-k - 1) if g & 128 else k)
        P.append((c * 4) & 0xFFFF)
    for i in range(12, 16):
        x = P[i]
        b = ((x & 1) << 1) | ((x >> 1) & 1)
        P[i] = ((x >> 2) + b) & 0xFFFF
    P[16] = (P[16] * 3) & 0xFFFF
    return P, Q


def check_market():
    """Legend's market: both generators number for number, the stock
    that moves, ФИКС, and the bases that do not trade."""
    print("Legend's market")
    t = syms.table()
    need = ["NGOODS", "P_RND", "SYS_ECON", "MKT_PRICE", "P_PRODUCT", "AST_QTY",
            "MKT_OPEN", "DOCKED_AT", "BK_HERMIT", "BK_MILITARY", "CARGO",
            "P_FREECARGO", "CASH_L", "P_LEGAL"]
    if any(n not in t for n in need):
        check("market symbols found", False,
              f"missing {[n for n in need if n not in t][:4]}")
        return
    import struct
    ng = int(t["NGOODS"], 8)
    goods = legend_goods()
    check("38 goods in the table", ng == 38 and len(goods) == 38, f"{ng}")
    mp, pp, aq = (int(t[n], 8) for n in ("MKT_PRICE", "P_PRODUCT", "AST_QTY"))
    prnd = int(t["P_RND"], 8)
    dumps = {n: ROOT / "tmp" / f"verify-market-{n}.bin"
             for n in ("mp", "pp", "aq", "mpa")}
    for f in dumps.values():
        if f.exists():
            f.unlink()
    # dumpcpu's length is decimal
    market = ["press 004", ui_ready(t)] * 4          # -> the market screen
    script = list(BOOT) + [f"peekcpu {prnd & ~1:o}", f"peekcpu {t['SYS_ECON']}"]
    script += market + [f"dumpcpu {mp:o} {ng * 2} {dumps['mp']}",
                        f"dumpcpu {pp:o} {ng * 2} {dumps['pp']}",
                        f"dumpcpu {aq:o} {ng * 2} {dumps['aq']}",
                        # ФИКС on the first row buys all the food there is
                        "press 107", ui_ready(t),
                        f"peekcpu {int(t['CARGO'], 8):o}", f"peekcpu {pp:o}",
                        f"peekcpu {t['P_FREECARGO']}", f"peekcpu {t['CASH_L']}",
                        # and again sells it all back
                        "press 107", ui_ready(t),
                        f"peekcpu {int(t['CARGO'], 8):o}", f"peekcpu {t['CASH_L']}",
                        f"peekcpu {t['P_LEGAL']}",
                        # the hermit's rock: its own list
                        poke_at(int(t["DOCKED_AT"], 8), int(t["BK_HERMIT"], 8))]
    nscreens = int(t["NSCREENS"], 8)
    script += ["press 004", ui_ready(t)] * nscreens + [f"dumpcpu {mp:o} {ng * 2} {dumps['mpa']}",
                                             f"peekcpu {t['MKT_OPEN']}",
               poke_at(int(t["DOCKED_AT"], 8), int(t["BK_MILITARY"], 8))]
    script += ["press 004", ui_ready(t)] * nscreens + [f"peekcpu {t['MKT_OPEN']}",
                                             "press 133", "run 25",
                                             f"peekcpu {int(t['CARGO'], 8):o}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("market")))]
    if len(v) < 11 or not all(f.exists() for f in dumps.values()):
        check("the market run answered", False)
        return
    rnd = (v[0] & 0xFF) if prnd % 2 == 0 else (v[0] >> 8)
    econ = v[1]

    def words(f):
        return list(struct.unpack(f"<{ng}H", f.read_bytes()[:ng * 2]))

    P, Q = legend_station(goods, rnd, econ)
    PA, QA = legend_asteroid(goods, rnd, econ)
    for name, got, want in (("the station's prices are Legend's", words(dumps["mp"]), P),
                            ("and its stock", words(dumps["pp"]), Q),
                            ("the rock's stock is Legend's", words(dumps["aq"]), QA),
                            ("and its prices", words(dumps["mpa"]), PA)):
        diff = [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b]
        check(name, not diff, f"rnd {rnd}, economy {econ}: {diff[:3]}")
    food, stock0 = Q[0], v[3]
    check("ФИКС buys the whole shelf", v[2] == food and stock0 == 0
          and v[4] == 20 - food and v[5] == 1000 - food * P[0],
          f"{v[2]} of {food} aboard, {stock0} left, {v[4]} tonnes free, {v[5]} tenths")
    check("and sells it all back", v[6] == 0 and v[7] == 1000 and v[8] == 0,
          f"{v[6]} aboard, {v[7]} tenths, record {v[8]}")
    check("the rock trades", v[9] == 1, str(v[9]))
    check("a military station does not", v[10] == 0 and v[11] == 0,
          f"open {v[10]}, {v[11]} bought")


def check_traffic():
    """A system that goes on without you: SPAWN_TICK rolls SetRndShip every
    256th frame with under five ships about and no bay near.  The roll is
    forced by poking the frame counter to 255 each cycle, and the sky is
    sampled as it fills; it never fills to the brim."""
    print("traffic")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "U.TYPE", "PENERGY", "PSHIELD_F", "NUNIV", "PSPEED", "FLY_TICK",
            "NACTIVE"]
    if any(n not in t for n in need):
        check("traffic symbols found", False, f"missing {[n for n in need if n not in t]}")
        return
    nuniv = int(t["NUNIV"], 8)
    alive = [poke_at(int(t["PENERGY"], 8), 255), poke_at(int(t["PSHIELD_F"], 8), 255)]
    # The commander is PARKED: the throttle is poked shut every cycle,
    # so he arrives nowhere and the run lasts as long as it is asked to.
    parked = alive + [poke_at(int(t["PSPEED"], 8), 0)]
    script = list(BOOT) + ["press 107", "run 100"]
    for _ in range(40):
        script += parked + [poke_at(int(t["FLY_TICK"], 8), 255), "run 12"]
        script += [f"peekcpu {slot_field(t, sl, 'U.TYPE')}" for sl in range(nuniv)]
    script.append("quit")
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("traf")))]
    rows = [v[i:i + nuniv] for i in range(0, len(v) - nuniv + 1, nuniv)]
    if not rows:
        check("the traffic run answered", False)
        return
    busy = [sum(1 for x in r if x) for r in rows]
    # A system is laid out with six: the world, the sun, the station, a
    # drop, one ship and Lave's service station.  Anything above that
    # arrived on a roll.
    check("the sky gains ships on its own", max(busy) > 6,
          f"{min(busy)}..{max(busy)} of {nuniv} slots over {len(rows)} forced rolls")
    # The roll refuses with five ships about, and a bay launches with
    # under seven; the drops and the rocks are on top of that, so the
    # bound is loose - but the sky must never be full, or nothing could
    # be shot down and nothing could be fired
    check("and never fills the sky", max(busy) < nuniv,
          f"most it held was {max(busy)} of {nuniv}")


def legend_equip():
    """The equipment table, as tools/legend_gen.py reads it."""
    rows = []
    for line in (ROOT / "src/res/legend/equip.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = line.partition("|")[0].split()
        rows.append({"tech": int(f[2]), "mission": int(f[3]), "price": int(f[4]),
                     "milprice": int(f[5]), "dev": None if f[6] == "-" else int(f[6])})
    return rows


def legend_tshift(price, margin):
    """goto118 in EquipShip.a80: halve once, then once per halving of
    margin/2 down to nought."""
    a = margin >> 1
    while True:
        price >>= 1
        a >>= 1
        if a == 0:
            return price


def legend_sale(rows, c, kind, tech, eco, galaxy, legal, complete, fuel_need,
                ship_price=0, wear=0):
    """TestSaleEquip: the price of row C where the commander is, or None.
    KIND is Legend's Docking: 1 station, 2 military, 3 service."""
    if c == 0:
        if fuel_need == 0:
            return None
        price = 4 * eco + galaxy + fuel_need
        if kind == 3:
            price = (price >> 1) or 1
        return price
    if c == 1 and kind == 3:
        price = ship_price >> ((((255 - wear) >> 4) & 15) + 1)
        if tech < 4:
            return None
        return legend_tshift(price, tech - 4)
    r = rows[c]
    margin = tech + 1 - r["tech"]
    if margin < 0 or legal >= 256:
        return None
    if kind == 2:
        price = r["milprice"]
    else:
        if r["mission"] & ~complete & 0xFF:
            return None
        price = r["price"]
    if price == 0:
        return None
    if kind == 3:
        price = legend_tshift(price, margin)
    return price


def check_equip():
    """The outfitter is Legend's shop: its list, its prices, its rules."""
    print("the outfitter: Legend's shop")
    t = syms.table()
    need = ["EQ_LAST", "EQ_ROWITEM", "EQ_NPAGES", "EQ_FIRST", "CASH_L", "CASH_H",
            "P_TECH", "P_ECO", "P_GALAXY", "P_LEGAL", "P_ECM", "P_WEAR",
            "P_LASERS", "PMISSILES", "PFUEL", "DOCKED_AT", "P_MCOMPLETE",
            "P_FREECARGO", "P_CABINS"]
    if any(n not in t for n in need):
        check("outfitter symbols found", False)
        return
    rows = legend_equip()
    rowitem = int(t["EQ_ROWITEM"], 8)
    page = [f"peekcpu {rowitem + 2 * i:o}" for i in range(15)]
    rich = [poke_at(int(t["CASH_L"], 8), 20000), poke_at(int(t["CASH_H"], 8), 1)]
    outfitter = ["press 004", ui_ready(t)] * 5
    again = ["press 004", ui_ready(t)] * int(t["NSCREENS"], 8)   # round the cycle

    def peekb(name):
        """The byte NAME, out of the word peeked at its even address."""
        a = int(t[name], 8)
        return f"peekcpu {a & ~1:o}", a & 1

    def byte(word, odd):
        return (word >> 8) if odd else (word & 0xFF)

    # 1. the list at the station, row for row against the Z80 rules,
    #    with the tanks half empty so that fuel is on it
    pt, pto = peekb("P_TECH")
    pe, peo = peekb("P_ECO")
    script = list(BOOT) + [poke_at(int(t["PFUEL"], 8), 30)] + outfitter + \
        [pt, pe, f"peekcpu {t['P_GALAXY']}", f"peekcpu {t['EQ_LAST']}",
         f"peekcpu {t['EQ_NPAGES']}"] + page + \
        ["press 107", "run 35",                        # ФИКС: the fuel
         f"peekcpu {t['PFUEL']}", f"peekcpu {t['CASH_L']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 22:
        check("the outfitter run answered", False)
        return
    tech, eco, galaxy = byte(v[0], pto), byte(v[1], peo), v[2]
    want = [c for c in range(len(rows))
            if legend_sale(rows, c, 1, tech, eco, galaxy, 0, 0, 40) is not None]
    check("Lave's list is Legend's, row for row",
          v[3] == min(15, len(want)) and v[5:5 + v[3]] == want[:v[3]],
          f"{v[5:5 + v[3]]} against {want[:15]}")
    check("and paged by fifteen", v[4] == (len(want) + 14) // 15, f"{v[4]} pages")
    fuel = legend_sale(rows, 0, 1, tech, eco, galaxy, 0, 0, 40)
    check("fuel fills the tank", v[20] == 70, f"{v[20]} tenths")
    check("at the economy's price", 1000 - v[21] == fuel,
          f"{1000 - v[21]} tenths against {fuel}")

    # 2. the rack: four missiles and no more; a laser into a mount, the
    #    old gun bought back at its list price
    beam = [c for c in want if c != 0].index(8)   # the beam laser's row,
                                                  #   with the tanks full
    script = list(BOOT) + outfitter + \
        ["press 107", "run 35", f"peekcpu {t['PMISSILES']}", f"peekcpu {t['CASH_L']}",
         "press 107", "run 35", f"peekcpu {t['PMISSILES']}", f"peekcpu {t['CASH_L']}"] + \
        rich + ["press 134", "run 25"] * beam + \
        ["press 107", "run 35", f"peekcpu {t['EQ_FIRST']}",   # the mount list
         "press 107", "run 35",                              # the front
         f"peekcpu {t['P_LASERS']}", f"peekcpu {t['EQ_FIRST']}",
         f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 9:
        check("a missile is bought", v[0] == 4 and v[1] == 700, f"{v[0]} for {1000 - v[1]}")
        check("and the rack holds four", v[2] == 4 and v[3] == 700, f"{v[2]} aboard")
        check("a laser opens the mount list", signed(v[4]) == -1, f"EQ_FIRST {v[4]}")
        check("and goes into the mount picked", v[5] == 2, f"gun {v[5]}")
        check("back on the list", signed(v[6]) >= 0, f"EQ_FIRST {v[6]}")
        cash = (v[8] << 16) + v[7]
        check("the old gun bought back at its list price",
              85536 - cash == rows[8]["price"] - rows[6]["price"],
              f"{85536 - cash} tenths for a {rows[8]['price']} laser")

    # 3. the service station: the hull's wear and a broken ECM, at the
    #    repair prices; the military station: its own price list
    script = list(BOOT) + rich + \
        [poke_at(int(t["DOCKED_AT"], 8), 3),
         f"pokecpu {int(t['P_WEAR'], 8):o} 144",         # wear 100
         f"pokecpu {int(t['P_ECM'], 8):o} 100"] + \
        outfitter + [f"peekcpu {t['EQ_LAST']}"] + page + \
        ["press 107", "run 35", pt,                        # the hull
         f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}",
         "press 134", "run 25", "press 107", "run 35",     # the ECM
         peek_dev(t, "P_ECM"), f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}",
         poke_at(int(t["DOCKED_AT"], 8), 2), poke_at(int(t["PMISSILES"], 8), 0)] + \
        again + [f"peekcpu {t['EQ_LAST']}"] + page + \
        ["press 107", "run 35", f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 40:
        check("the service station lists the hull and the broken ECM",
              v[0] == 2 and v[1:3] == [1, 27], f"{v[0]} rows: {v[1:4]}")
        tech = byte(v[16], pto)
        hull = legend_sale(rows, 1, 3, tech, 0, 0, 0, 0, 0, 1500000, 100)
        cash = (v[18] << 16) + v[17]
        check("the hull is repaired at Legend's price", 85536 - cash == hull,
              f"{85536 - cash} against {hull}")
        ecm = legend_sale(rows, 27, 3, tech, 0, 0, 0, 0, 0)
        cash2 = (v[21] << 16) + v[20]
        check("and the ECM mended",
              dev_fitted(t, "P_ECM", v[19])
              and not (byte(v[19], int(t["P_ECM"], 8) & 1) & 0x40),
              f"{v[19]:o}")
        check("for its repair price", cash - cash2 == ecm, f"{cash - cash2} against {ecm}")
        want = [c for c in range(len(rows))
                if legend_sale(rows, c, 2, tech, 0, 0, 0, 0, 0) is not None]
        check("the military station has its own list",
              v[22] == min(15, len(want)) and v[23:23 + v[22]] == want[:v[22]],
              f"{v[23:23 + v[22]]} against {want[:15]}")
        cash3 = (v[39] << 16) + v[38]
        check("and its own prices", cash2 - cash3 == rows[1]["milprice"],
              f"{cash2 - cash3} for a missile")


def legend_catalog():
    """The yard's catalogue, as tools/catalog_gen.py reads it."""
    rows = []
    for line in (ROOT / "src/res/legend/catalog.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = line.partition("|")[2].split()
        rows.append({"date": int(f[0]), "speed": int(f[1]), "tons": int(f[2]),
                     "price": int(f[3]), "ecotech": int(f[13]), "chance": int(f[14]),
                     "mission": int(f[15])})
    return rows


# The record's ship, P_SHIP to the byte before P_RND (src/pilot.mac)
SHIP_LEN = 51
# a device's first equipment row (0: unpriced), YD_DEVROW in the overlay
DEVROW = [14, 15, 16, 17, 18, 0, 19, 21, 24, 27, 29, 31, 33, 34, 35,
          37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48]


def legend_ship_price(rec, rows, cat):
    """CalcPriceShip over the record's own layout: the catalogue price,
    the tank, the missiles, the cabins, the guns and the devices at the
    station's prices, a broken device at half, less the wear's share as
    CalcCashRepairShip works it out."""
    def row(c, half=False):
        return rows[c]["price"] >> (1 if half else 0)

    price = cat[(rec[0] | rec[1] << 8) - 1]["price"]
    tanks = rec[10]
    if not tanks & 0x80:
        price += row(5 if tanks & 0x40 else 4)
    price += (rec[12] | rec[13] << 8) * row(1)
    price += (rec[14] | rec[15] << 8) * row(2)
    price += rec[11] * row(3)
    for i in range(4):
        g = rec[16 + 2 * i] | rec[17 + 2 * i] << 8
        if not g & 0x80:
            price += row(6 + (g & 7))
    for i, r in enumerate(DEVROW):
        d = rec[24 + i]
        if r == 0 or d & 0x80:
            continue
        if i < 6:
            price += row(r)
        elif i == 6:
            price += row(r + (d & 1))
        elif i < 15:
            price += row(r + (d & 3), bool(d & 0x40))
        else:
            price += row(r, bool(d & 0x40))
    return price - (price >> ((((255 - rec[6]) >> 4) & 15) + 1))


def check_yard():
    """The yard is Legend's: its stock, its panel, buying a ship, the
    berths, selling, delivery and the swap."""
    print("the yard: Legend's ships")
    t = syms.table()
    need = ["YD_N", "YD_LIST", "YD_PL", "YD_PH", "YD_DL", "YD_DH", "YD_MODE",
            "P_YARD", "P_SHIPS", "P_SHIP", "P_FREECARGO", "CARGO", "ST_PRICE",
            "CASH_L", "CASH_H", "SCREEN", "P_LASERS", "PFUEL", "PMISSILES",
            "P_TECH", "P_ECO", "P_MCOMPLETE", "P_PLANET"]
    if any(n not in t for n in need):
        check("yard symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    rows, cat = legend_equip(), legend_catalog()
    a = {n: int(t[n], 8) for n in need}
    dump = ROOT / "tmp" / "verify-yard-ship.bin"
    if dump.exists():
        dump.unlink()
    rich = [poke_at(a["CASH_L"], 0), poke_at(a["CASH_H"], 100)]       # 6 553 600
    yard = ["press 004", ui_ready(t)] * 6
    again = ["press 004", ui_ready(t)] * (int(t["NSCREENS"], 8) - 1)   # from the
                                                 #   pilot's page round to the yard

    def peekb(name):
        return f"peekcpu {a[name] & ~1:o}", a[name] & 1

    def byte(word, odd):
        return (word >> 8) if odd else (word & 0xFF)

    # 1. the stock rolled on arrival at Lave passes Legend's gates; the
    #    yard is then stocked by hand - the Adder, the Cobra Mk III and
    #    the Sidewinder - and the Adder bought with three tonnes of food
    #    in the hold and the Cobra put in a berth
    pt, pto = peekb("P_TECH")
    pe, peo = peekb("P_ECO")
    pm, pmo = peekb("P_MCOMPLETE")
    stock = [f"peekcpu {a['P_YARD'] + 2 * i:o}" for i in range(10)]
    # the rolled stock is read, then emptied before the three are put
    # in: what Lave rolls depends on the generator's state at arrival,
    # which the length of the boot read moves (a sector more of
    # resident, and the title has had fewer frames before the key)
    script = list(BOOT) + [pt, pe, pm] + stock + rich + \
        [poke_at(a["P_YARD"] + 2 * i, 0) for i in range(10)] + \
        [f"pokecpu {a['P_YARD'] + i:o} {i + 1:o}" for i in (0, 5, 15)] + \
        [poke_at(a["CARGO"], 3), poke_at(a["P_FREECARGO"], 17),
         f"peekcpu {a['ST_PRICE']:o}", f"peekcpu {t['P_PLANET']}",
         f"dumpcpu {a['P_SHIP']:o} {SHIP_LEN} {dump}"] + yard + \
        [f"peekcpu {t['SCREEN']}", f"peekcpu {t['YD_N']}",
         f"peekcpu {a['YD_LIST']:o}", f"peekcpu {a['YD_LIST'] + 2:o}",
         f"peekcpu {t['YD_PL']}", f"peekcpu {t['YD_PH']}",
         "press 134", "run 25", f"peekcpu {t['YD_PL']}", f"peekcpu {t['YD_PH']}",
         "press 154", "run 25", f"peekcpu {t['YD_PL']}", f"peekcpu {t['YD_PH']}",
         "press 107", ui_ready(t),                            # ФИКС: the Adder
         f"peekcpu {t['SCREEN']}", f"peekcpu {t['P_SHIP']}",
         f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}",
         f"peekcpu {t['P_FREECARGO']}", f"peekcpu {a['CARGO']:o}",
         f"peekcpu {a['P_YARD']:o}", f"peekcpu {a['P_SHIPS']:o}",
         f"peekcpu {a['P_SHIPS'] + 2:o}", f"peekcpu {t['P_LASERS']}",
         f"peekcpu {t['PFUEL']}"] + \
        again + ["press 153", ui_ready(t),                    # ВВОД: the berths
                 f"peekcpu {t['YD_MODE']}", f"peekcpu {t['YD_N']}",
                 f"peekcpu {a['YD_LIST']:o}", f"peekcpu {t['YD_PL']}",
                 f"peekcpu {t['YD_PH']}", f"peekcpu {t['YD_DL']}", f"peekcpu {t['YD_DH']}",
                 "press 133", "run 25", "press 107", ui_ready(t),   # sell it
                 f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}",
                 f"peekcpu {a['P_SHIPS']:o}", f"peekcpu {t['YD_MODE']}",
                 f"peekcpu {t['YD_N']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 47 or not dump.exists():
        check("the yard run answered", False, f"{len(v)} values")
        return
    tech, eco, done = byte(v[0], pto), byte(v[1], peo), byte(v[2], pmo)
    stocked = [b for w in v[3:13] for b in (w & 0xFF, w >> 8)][:19]
    gate = [i for i in range(19)
            if tech >= cat[i]["ecotech"] & 31 and cat[i]["ecotech"] >> 5 >= eco
            and not cat[i]["mission"] & ~done & 0xFF]
    check("the yard's stock passes Legend's gates",
          all(s == 0 or s == i + 1 for i, s in enumerate(stocked))
          and all(i in gate for i, s in enumerate(stocked) if s),
          f"tech {tech}, economy {eco}: {stocked}")
    food, planet = v[13], v[14]
    old = dump.read_bytes()[:SHIP_LEN]
    check("the yard lists what is for sale, in the catalogue's order",
          v[15] == 6 and v[16] == 3 and v[17] == 5 << 8 and v[18] & 0xFF == 15,
          f"screen {v[15]}, {v[16]} rows: {v[17]:o} {v[18]:o}")
    check("the panel prices the Adder", (v[20] << 16) + v[19] == cat[0]["price"],
          f"{(v[20] << 16) + v[19]}")
    check("down and up price the Cobra and the Adder again",
          (v[22] << 16) + v[21] == cat[5]["price"] and (v[24] << 16) + v[23] == cat[0]["price"],
          f"{(v[22] << 16) + v[21]}, {(v[24] << 16) + v[23]}")
    cash = (v[28] << 16) + v[27]
    check("ФИКС buys it and shows the pilot's page", v[25] == 7 and v[26] == 1,
          f"screen {v[25]}, ship {v[26]}")
    check("the hold is sold to the station and the price paid",
          cash == 6553600 + 3 * food - cat[0]["price"] and v[30] == 0,
          f"{cash} against {6553600 + 3 * food - cat[0]['price']}, {v[30]} aboard")
    check("the new ship is bare, with the catalogue's hold",
          v[29] == cat[0]["tons"] and v[34] == 0o200 and v[35] == 0,
          f"{v[29]} tonnes, gun {v[34]:o}, fuel {v[35]}")
    check("it leaves the yard and the Cobra takes a berth here",
          v[31] & 0xFF == 0 and v[32] == 6 and v[33] & 0xFF == planet,
          f"yard {v[31]:o}, berth {v[32]:o} {v[33]:o}")
    worth = legend_ship_price(old, rows, cat)
    check("the berths list it, priced with its fittings",
          v[36] == 1 and v[37] == 1 and v[38] & 0xFF == 0 and (v[40] << 16) + v[39] == worth,
          f"mode {v[36]}, {v[37]} rows, {(v[40] << 16) + v[39]} against {worth}")
    check("and it is here, so it can be selected", v[41] == 0 and v[42] == 0,
          f"delivery {(v[42] << 16) + v[41]}")
    cash2 = (v[44] << 16) + v[43]
    check("sold for that, the berth empties and the yard comes back",
          cash2 - cash == worth and v[45] & 0xFF == 0 and v[46] == 0 and v[47] == 2,
          f"{cash2 - cash} for it, berth {v[45]:o}, mode {v[46]}, {v[47]} rows")

    # 2. the same purchase, then the berthed Cobra moved two galaxies
    #    away: delivery at 2475.3 Cr a galaxy, then the swap; then moved
    #    to another system of this galaxy, eight times the distance
    lave, other = galaxy_model(planet), galaxy_model(0)
    script = list(BOOT) + rich + [f"pokecpu {a['P_YARD']:o} 1"] + yard + \
        ["press 107", ui_ready(t),
         f"pokecpu {a['P_SHIPS'] + 1:o} 2"] + \
        again + ["press 153", ui_ready(t),
                 f"peekcpu {t['YD_DL']}", f"peekcpu {t['YD_DH']}",
                 "press 133", "run 25", "press 134", "run 25",   # deliver
                 "press 107", ui_ready(t),
                 f"peekcpu {t['CASH_L']}", f"peekcpu {t['CASH_H']}",
                 f"peekcpu {a['P_SHIPS']:o}", f"peekcpu {t['YD_DL']}",
                 "press 107", ui_ready(t),                          # select
                 f"peekcpu {t['SCREEN']}", f"peekcpu {t['P_SHIP']}",
                 f"peekcpu {t['P_LASERS']}", f"peekcpu {t['PMISSILES']}",
                 f"peekcpu {a['P_SHIPS']:o}", f"peekcpu {t['P_FREECARGO']}",
                 f"pokecpu {a['P_SHIPS'] + 2:o} 0"] + \
        again + ["press 153", ui_ready(t),
                 f"peekcpu {t['YD_DL']}", f"peekcpu {t['YD_DH']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 14:
        check("the delivery run answered", False, f"{len(v)} values")
        return
    check("two galaxies away, delivery costs 2475.3 Cr a galaxy",
          (v[1] << 16) + v[0] == 2 * 24753, f"{(v[1] << 16) + v[0]}")
    cash = (v[3] << 16) + v[2]
    check("paid for, the ship is here", 6553600 - cat[0]["price"] - cash == 2 * 24753
          and v[4] == 6 and v[5] == 0, f"{6553600 - cat[0]['price'] - cash} paid, berth {v[4]:o}")
    check("selecting it swaps the ships, kit and all",
          v[6] == 7 and v[7] == 6 and v[8] == 0 and v[9] == 3 and v[10] == 1 and v[11] == 20,
          f"screen {v[6]}, ship {v[7]}, gun {v[8]:o}, {v[9]} missiles, berth {v[10]:o}, "
          f"{v[11]} tonnes")
    check("in this galaxy, delivery is eight times the distance",
          (v[13] << 16) + v[12] == 8 * sys_distance(lave, other),
          f"{(v[13] << 16) + v[12]} against {8 * sys_distance(lave, other)}")


def check_access():
    """The access menu: Legend's Save/Load over the port's slots - a save
    into another slot under an edited name, an empty slot refused, and
    a load that restarts the game as that commander."""
    print("the access menu")
    t = syms.table()
    need = ["SV_MODE", "SV_SEL", "SV_MSG", "S_V_SAVED", "S_V_FILEERR", "CMDR_SLOT",
            "CASH_L", "SCREEN", "DOCKED", "P_NAME", "NSCREENS", "DOCKED_AT"]
    if any(n not in t for n in need):
        check("access menu symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    menu = ["press 004", ui_ready(t)] * (a["NSCREENS"] - 2)     # the ninth screen
    name = [f"peekcpu {a['P_NAME'] + 2 * i:o}" for i in range(4)]
    script = list(BOOT) + [poke_at(a["CASH_L"], 5000)] + menu + \
        [f"peekcpu {t['SCREEN']}", f"peekcpu {t['SV_MODE']}",
         "press 107", ui_ready(t), f"peekcpu {t['SV_MODE']}", f"peekcpu {t['SV_SEL']}",   # load list
         "press 153", ui_ready(t), f"peekcpu {t['SV_MODE']}",                             # back
         "press 134", "run 25", "press 107", ui_ready(t),                                 # save list
         "press 134", "run 25", f"peekcpu {t['SV_MODE']}", f"peekcpu {t['SV_SEL']}",   # slot 2
         "press 107", "run 40",                                                        # the name
         "press 067", "run 20", "press 153", ui_ready(t),                                 # Я, ВВОД
         f"peekcpu {t['SV_MODE']}", f"peekcpu {t['SV_MSG']}", f"peekcpu {t['CMDR_SLOT']}"] + name + \
        [poke_at(a["CASH_L"], 7777),
         "press 107", ui_ready(t), f"peekcpu {t['SV_SEL']}",                              # load list, on slot 2
         "press 134", "run 25", "press 134", "run 25", "press 107", ui_ready(t),          # slot 4: nobody
         f"peekcpu {t['SV_MSG']}", f"peekcpu {t['SCREEN']}",
         "press 154", "run 25", "press 154", "run 25", "press 107", ui_ready(t),         # slot 2
         f"peekcpu {t['SCREEN']}", f"peekcpu {t['DOCKED']}", f"peekcpu {t['CASH_L']}",
         f"peekcpu {t['CMDR_SLOT']}"] + name + \
        [poke_at(a["DOCKED_AT"], int(t["BK_FUEL"], 8))] + menu + \
        ["press 107", ui_ready(t), f"peekcpu {t['SV_MODE']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("access")))]
    if len(v) < 24:
        check("the access menu run answered", False, f"{len(v)} values")
        return
    check("the access menu is the ninth screen", v[0] == a["NSCREENS"] - 2 and v[1] == 0,
          f"screen {v[0]}, mode {v[1]}")
    check("ФИКС opens the load list on his own slot, ВВОД comes back",
          v[2] == 1 and v[3] == 0 and v[4] == 0, f"mode {v[2]}, slot {v[3]}, then {v[4]}")
    check("the second line opens the save list", v[5] == 2 and v[6] == 1,
          f"mode {v[5]}, slot {v[6]}")
    jameson = [19793, 21317, 20047]          # ЯМЕСОН in KOI-7, two letters a word
    check("saving asks the name, edited from what it is, and says so",
          v[7] == 0 and v[8] == a["S_V_SAVED"] and v[9] == 1
          and v[10:13] == jameson and v[13] == 0o121,
          f"mode {v[7]}, message {v[8]:o}, slot {v[9]}, name {v[10:14]}")
    check("the slot saved into is his from now on", v[14] == 1, f"list opens on {v[14]}")
    check("an empty slot is refused", v[15] == a["S_V_FILEERR"] and v[16] == a["NSCREENS"] - 2,
          f"message {v[15]:o}, screen {v[16]}")
    check("loading restarts the game as that commander, docked",
          v[17] == 0 and v[18] == 1 and v[19] == 5000 and v[20] == 1,
          f"screen {v[17]}, docked {v[18]}, {v[19]} tenths, slot {v[20]}")
    check("with the name he was saved under", v[21:24] == jameson and v[24] == 0o121,
          f"{v[21:25]}")
    check("the menu opens at the main station only", v[25] == 0, f"mode {v[25]}")


def legend_cockpits():
    """The cockpit blocks' rule fields, as tools/cockpit_gen.py reads them."""
    rows = []
    for line in (ROOT / "src/res/legend/cockpits.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        v = [int(x) for x in line.partition("|")[2].split()]
        rows.append(dict(zip(["maxmiss", "enunits", "maxfuel", "tonnage", "turrets", "scanner"], v)))
    return rows


def check_cockpit_block():
    """The ship's limits are its cockpit block's: the Cobra's at the start,
    a Cobra Mk IV's after the yard, and the throttle climbs to the hull's
    speed in five steps."""
    print("the cockpit block")
    t = syms.table()
    need = ["CKV_MAXMISS", "CKV_ENUNITS", "CKV_MAXFUEL", "CKV_TONS", "CKV_TURRETS",
            "CKV_SCAN", "CKV_MAXSPEED", "CKV_STEP", "PSPEED", "P_YARD", "CASH_L",
            "CASH_H", "PFUEL", "P_FREECARGO", "PMISSILES", "P_SHIP"]
    if any(n not in t for n in need):
        check("cockpit symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    cat, cocks = legend_catalog(), legend_cockpits()
    ships = {x.index: x for x in shiplib.read_dir(ROOT / "src/res/legend/ships")}
    catrows = [l for l in (ROOT / "src/res/legend/catalog.txt").read_text(encoding="utf-8").splitlines()
               if l.strip() and not l.startswith("#")]
    cockpit_of = [int(l.partition("|")[2].split()[5]) for l in catrows]
    hull_of = [int(l.partition("|")[2].split()[4]) for l in catrows]

    def expect(ship):
        c = cocks[cockpit_of[ship - 1]]
        return [c["maxmiss"], c["enunits"], c["maxfuel"], c["tonnage"], c["turrets"],
                c["scanner"], ships[hull_of[ship - 1]].speed]

    ckv = [f"peekcpu {t[n]}" for n in ("CKV_MAXMISS", "CKV_ENUNITS", "CKV_MAXFUEL",
                                        "CKV_TONS", "CKV_TURRETS", "CKV_SCAN", "CKV_MAXSPEED")]
    rich = [poke_at(a["CASH_L"], 0), poke_at(a["CASH_H"], 100)]
    script = list(BOOT) + ckv + ["press 107", "run 60"]                 # launch
    for _ in range(6):
        script += ["press 166", "run 20", f"peekcpu {t['PSPEED']}"]       # the throttle
    script += ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 13:
        check("the cockpit run answered", False, f"{len(v)} values")
        return
    want = expect(6)
    check("the Cobra flies with cockpit 0's limits", v[:7] == want, f"{v[:7]} against {want}")
    top, speed, climb = want[6], 16, []          # a launch is at 16
    for _ in range(6):
        speed = 0 if speed == top else min(speed + (top + 4) // 5, top)
        climb.append(speed)
    check("the throttle climbs to the hull's speed in steps, then stops",
          v[7:13] == climb, f"{v[7:13]} against {climb}")

    # a Cobra Mk IV out of the yard, over whatever the yard rolled into
    # its first row: cockpit 5 - eight missiles, a hundred tenths of
    # fuel, eighty tonnes; the outfitter fills the tank
    script = list(BOOT) + rich + [f"pokecpu {a['P_YARD']:o} 10"] + \
        ["press 004", ui_ready(t)] * 6 + ["press 107", "run 60"] + ckv + \
        [f"peekcpu {t['P_SHIP']}", f"peekcpu {t['P_FREECARGO']}"] + \
        ["press 004", ui_ready(t)] * (int(t["NSCREENS"], 8) - 2) + \
        ["press 107", "run 35", f"peekcpu {t['PFUEL']}"] + \
        ["press 107", "run 35"] * 9 + [f"peekcpu {t['PMISSILES']}", "quit"]   # the top
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]           #   row is
    if len(v) < 11:                                                  #   the missile
        check("the yard run answered", False, f"{len(v)} values")   #   once the
        return                                                       #   tank is full
    want = expect(8)
    check("a Cobra Mk IV flies with cockpit 5's", v[7] == 8 and v[:7] == want,
          f"ship {v[7]}: {v[:7]} against {want}")
    check("and its hold", v[8] == want[3], f"{v[8]} tonnes free")
    check("the outfitter fills its tank", v[9] == want[2], f"{v[9]} tenths")
    check("and its rack", v[10] == want[0], f"{v[10]} missiles")


def check_energy():
    """Energy as Legend keeps it: banks of ENERGY_MAX drained first to
    last, a point an interrupt back into the last bank short of full,
    the shields after the banks and twice as fast with a generator, a
    hit costing the facing shield five blows and the banks the rest."""
    print("energy banks and shields")
    t = syms.table()
    need = ["PBANKS", "PSHIELD_F", "PSHIELD_A", "CKV_ENUNITS", "ENERGY_MAX", "RC_LAST",
            "P_ENERGYUNIT", "P_SHIELDGEN", "SH_SIDEWINDER", "SS_COLLIDE", "P_MILSHIELDS"]
    if any(n not in t for n in need):
        check("energy symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    full = a["ENERGY_MAX"]
    banks = [f"peekcpu {a['PBANKS'] + 2 * i:o}" for i in range(4)]
    shields = [f"peekcpu {t['PSHIELD_F']}", f"peekcpu {t['PSHIELD_A']}"]

    def poke_slot(slot, field, val):
        return poke_at(int(slot_field(t, slot, field), 8), val)

    # 1. docked: the last bank fills first at a point an interrupt, the
    #    shields only once the banks are full, twice as fast with the
    #    generator; a naval energy unit makes four points of one. Sample
    #    at RECHARGE boundaries and count RC_LAST, the interrupts already
    #    applied, so no partially completed batch enters the comparison.
    script = list(BOOT) + [f"runpc {t['RECHARGE']} 1200"] + banks + shields + \
        [poke_at(a["PBANKS"] + 4, 100), poke_at(a["PBANKS"] + 6, 100),
         poke_at(a["PSHIELD_F"], 100), poke_at(a["PSHIELD_A"], 100),
         f"peekcpu {t['RC_LAST']}", "run 1", f"runpc {t['RECHARGE']} 1200", f"peekcpu {t['RC_LAST']}"] + banks + shields + \
        [poke_at(a["PBANKS"] + 4, full), poke_at(a["PBANKS"] + 6, full),
         f"peekcpu {t['RC_LAST']}", "run 1", f"runpc {t['RECHARGE']} 1200", f"peekcpu {t['RC_LAST']}"] + shields + \
        [poke_dev(t, "P_SHIELDGEN"), poke_at(a["PSHIELD_F"], 100), poke_at(a["PSHIELD_A"], 100),
         f"peekcpu {t['RC_LAST']}", "run 1", f"runpc {t['RECHARGE']} 1200", f"peekcpu {t['RC_LAST']}"] + shields + \
        [f"pokecpu {a['P_ENERGYUNIT']:o} 1", poke_at(a["PBANKS"] + 6, 100),   # naval
         f"peekcpu {t['RC_LAST']}", "run 1", f"runpc {t['RECHARGE']} 1200", f"peekcpu {t['RC_LAST']}"] + banks + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 28:
        check("the energy run answered", False, f"{len(v)} values")
        return
    check("a Cobra starts with four full banks and full shields",
          v[:4] == [full] * 4 and v[4:6] == [full] * 2, f"{v[:6]}")
    n = v[7] - v[6]
    check("the last bank fills first, a point an interrupt, the shields waiting",
          v[8:12] == [full, full, 100, 100 + n] and v[12:14] == [100, 100],
          f"{n} interrupts: banks {v[8:12]}, shields {v[12:14]}")
    n = v[15] - v[14]
    check("with the banks full, a point on each shield an interrupt",
          v[16:18] == [100 + n, 100 + n], f"{n} interrupts: {v[16:18]}")
    n = v[19] - v[18]
    check("two with a shield generator", v[20:22] == [100 + 2 * n, 100 + 2 * n],
          f"{n} interrupts: {v[20:22]}")
    n = v[23] - v[22]
    check("a naval energy unit makes four points of one",
          v[24:28] == [full, full, full, min(full, 100 + 4 * n)],
          f"{n} interrupts: {v[24:28]}")

    # 2. a Sidewinder run into: its collision byte five times off the
    #    forward shield, and the blows it cannot cover off the first
    #    bank; the same with military shields, which halve what the
    #    shield feels but not what the banks take
    ships = {x.index: x for x in shiplib.read_dir(ROOT / "src/res/legend/ships")}
    blow = ships[a["SH_SIDEWINDER"] - 1].collide
    # Observe the impact over a window: three ticks can end just before
    # COLLIDE_STEP reaches the prepared ship. Each run starts with a full
    # ship/commander fixture, no traffic or bay, and a stationary target.
    v = []
    for military in (False, True):
        setup = (list(BOOT) + [poke_dev(t, "P_FUELSCOOPS"), "press 107", "run 40"]
                 + clear_traffic(t) + [poke_at(int(t["WITCH"], 8), 1),
                   poke_slot(2, "U.TYPE", 0), poke_at(int(t["PSPEED"], 8), 0),
                   poke_dev(t, "P_MILSHIELDS", fitted=military)]
                 + [poke_at(a["PBANKS"]+2*i, full) for i in range(4)]
                 + [poke_at(a["PSHIELD_F"], full), poke_at(a["PSHIELD_A"], full)]
                 + ship_pokes(t, 3, "SIDEWINDERH", z=40, hostile=False,
                              energy=4000, hyper=False, still=True))
        samples = [int(x, 8) for x in PEEK.findall(run_emu(
            setup + sum((["run 1"] + banks + shields for _ in range(20)), []) + ["quit"],
            fresh_disk("energy-impact")))]
        v += [min(samples[i::6]) for i in range(6)]

    def model(shield, bank, felt, struck):
        for left in range(5, 0, -1):
            if shield < felt:
                return 0, bank - (left - 1) * struck
            shield -= felt
        return shield, bank

    # the peek comes a frame or so after the blow, and a frame recovers
    # up to sixteen points into whatever is lowest
    def near(got, want):
        return want <= got <= want + 16

    want = model(full, full, blow, blow)
    check("a collision is the hull's collision byte, five blows on the shield and the rest on the banks",
          near(v[4], want[0]) and near(v[0], want[1]) and v[5] == full and v[1:4] == [full] * 3,
          f"blow {blow}: shield {v[4]}, bank {v[0]} against {want}")
    want = model(full, full, blow >> 1, blow)
    check("military shields halve what the shield feels, not what the banks take",
          near(v[10], want[0]) and near(v[6], want[1]), f"shield {v[10]}, bank {v[6]} against {want}")


def check_lasers():
    """The guns as Legend fires them (FireLaser): a pulse laser every
    other frame at eight heat a shot, a beam-class gun every frame at
    ten, a mining laser every eighth; the gun sheds two a frame, four
    with the cooling booster, cuts out at LASER_MAX and reads LASER_CAP
    at most; a shot costs the banks four; a hit is LaserDamages."""
    print("lasers")
    t = syms.table()
    need = ["PLASTEMP", "PLASERS", "LAS_TICK", "LAS_SHOTS", "PBANKS", "PSPEED",
            "LASER_MAX", "LASER_CAP", "LAS_PULSE", "LAS_BEAM", "LAS_MIL",
            "LAS_MINING", "P_LASERCOOL", "ENERGY_MAX", "SH_KRAIT", "U.ENERGY"]
    if any(n not in t for n in need):
        check("laser symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    full = a["ENERGY_MAX"]
    cap, cut = a["LASER_CAP"], a["LASER_MAX"]
    tick, shots, temp = (f"peekcpu {t[n]}" for n in ("LAS_TICK", "LAS_SHOTS", "PLASTEMP"))
    script = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t) + [poke_at(a["PSPEED"], 0)]
    bursts = []

    def burst(kind, ticks, before=(), after=()):
        """Fit KIND to the forward mount, cold, hold the trigger for
        TICKS, and read the frames, the shots and the heat.  The sky is
        emptied first, every time: traffic arrives during the earlier
        bursts, and what it does depends on the build's random path -
        a Fer-de-Lance shot the shields down and the bank the sixth
        burst reads to nothing (2026-09-24, late)."""
        bursts.append(len(after))
        script.extend(clear_traffic(t))
        script.extend([poke_at(a["PLASERS"], a[kind]), poke_at(a["PLASTEMP"], 0), *before,
                       tick, shots, "keydown 107", f"run {ticks}", tick, shots, temp,
                       *after, "keyup 107", "run 4"])

    burst("LAS_PULSE", 40)
    burst("LAS_BEAM", 16)     # an empty sky runs at 20 fps: 40 ticks cut it out
    burst("LAS_MINING", 80)
    burst("LAS_BEAM", 120)
    burst("LAS_PULSE", 40, before=[poke_dev(t, "P_LASERCOOL")])
    banks = [poke_at(a["PBANKS"] + 2 * i, full) for i in range(3)] + [poke_at(a["PBANKS"] + 6, 0)]
    burst("LAS_BEAM", 40, before=[poke_dev(t, "P_LASERCOOL", False)] + banks,
          after=[f"peekcpu {t['PBANKS']}"])
    energy = f"peekcpu {slot_field(t, 5, 'U.ENERGY')}"
    target = [poke_at(int(slot_field(t, 5, n), 8), v) for n, v in [
        ("U.TYPE", a["SH_KRAIT"]), ("U.FLAGS", 0), ("U.EXPL", 0), ("U.TARGET", 0),
        ("U.X", 0), ("U.Y", 0), ("U.Z", 900), ("U.SPEED", 0), ("U.ENERGY", 4000)]]
    target += mind(t, 5, "KRAITH", still=True)
    burst("LAS_MIL", 12, before=target + ["run 2"], after=[energy])
    script.append("quit")
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 5 * len(bursts) + sum(bursts):
        check("the laser run answered", False, f"{len(v)} values")
        return
    got = []
    phase = []
    for n in bursts:
        f, s, h = v[2] - v[0], v[3] - v[1], v[4]
        got.append((f, s, h, v[5:5 + n]))
        phase.append(v[0])
        v = v[5 + n:]
    f, s, h, _ = got[0]
    check("a pulse laser fires every other frame, eight a shot less two a frame",
          abs(2 * s - f) <= 3 and abs(h - (8 * s - 2 * f)) <= 10 and s > 2,
          f"{s} shots in {f} frames, heat {h}")
    f, s, h, _ = got[1]
    # (the frames are counted from the key press, and the key reaches the
    # key word a tick later: a frame at 20 fps, up to two at 28)
    check("a beam laser every frame, ten a shot",
          0 <= f - s <= 2 and abs(h - (10 * s - 2 * f)) <= 12 and s > 5,
          f"{s} shots in {f} frames, heat {h}")
    f, s, h, _ = got[2]
    # a trigger that was up fires at once and then on every eighth frame
    # (LASER_STEP), so a burst that starts the frame before a multiple of
    # eight gets one shot more than the frames over eight: 8s - f can
    # reach 15 (nine shots in 59 frames, 2026-09-24, when the boot's
    # random path moved the frame the burst began on)
    check("a mining laser every eighth, and never warm",
          abs(8 * s - f) <= 16 and h <= 8 and s > 1,
          f"{s} shots in {f} frames from tick {phase[2] % 8} of 8, heat {h}")
    f, s, h, _ = got[3]
    check(f"held, the gun cuts out at {cut} and reads {cap} at most",
          cut - 6 <= h <= cap and s <= f - 8, f"{s} shots in {f} frames, heat {h}")
    f, s, h, _ = got[4]
    check("the cooling booster sheds four a frame", h <= 12 and s > 2,
          f"{s} shots in {f} frames, heat {h}")
    f, s, h, (bank,) = got[5]
    check("a shot costs the banks four, off the first bank",
          abs(bank - (full - 4 * s)) <= 4 and s > 5, f"{s} shots, bank {bank}")
    f, s, h, (left,) = got[6]
    hit = 4000 - left
    check("a military laser hit is Legend's 23", hit >= 23 and hit % 23 == 0 and hit <= 23 * s,
          f"{hit} off the target in {s} shots")


def byte_at(t, name, word):
    """The byte NAME out of the word peeked at its even address."""
    return (word >> 8) & 0xFF if int(t[name], 8) & 1 else word & 0xFF


def check_damage():
    """Legend's HeavyDamage: a blow the shield feels of HEAVY_BLOW or more
    counts on the wear byte and rolls for the tank, a device or a tonne;
    a broken device is no device."""
    print("heavy damage")
    t = syms.table()
    devs = ["P_ENERGYUNIT", "P_GALDRIVE", "P_ECM", "P_INJECTORS", "P_EBOMB", "P_AUTOECM",
            "P_AUTOPOD", "P_DRONE", "P_SHIELDGEN", "P_MILSHIELDS", "P_LASERCOOL", "P_CLOAK",
            "P_ALIENCOMP", "P_OREPROC", "P_ESCPOD", "P_FUELCOLL", "P_FUELSCOOPS",
            "P_DOCKCOMP", "P_AUTOTAKE", "P_EJECT"]
    need = ["P_WEAR", "PSHIELD_F", "PSHIELD_A", "PBANKS", "ENERGY_MAX", "SH_SIDEWINDER",
            "SH_COBRAMK3HT1", "P_CARGO", "NGOODS_L", "PFUEL", "DC_ON", "HEAVY_BLOW",
            "DEV_BROKEN"] + devs
    if any(n not in t for n in need):
        check("damage symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    full, ngoods = a["ENERGY_MAX"], a["NGOODS_L"]
    ships = {x.index: x for x in shiplib.read_dir(ROOT / "src/res/legend/ships")}
    light = ships[a["SH_SIDEWINDER"] - 1].collide
    heavy = ships[a["SH_COBRAMK3HT1"] - 1].collide
    if not light < a["HEAVY_BLOW"] <= heavy:
        check("a Sidewinder is under the heavy blow and a Cobra over it", False,
              f"{light}, {heavy} against {a['HEAVY_BLOW']}")
        return

    def poke_slot(slot, field, val):
        return poke_at(int(slot_field(t, slot, field), 8), val)

    def ram(kind):
        return [poke_slot(5, "U.TYPE", a[kind]), poke_slot(5, "U.FLAGS", 0),
                poke_slot(5, "U.EXPL", 0), poke_slot(5, "U.X", 0), poke_slot(5, "U.Y", 0),
                poke_slot(5, "U.Z", 40)] + mind(t, 5, a[kind], still=True) + [ui_ready(t, frames=2)]
    refill = [poke_at(a["PSHIELD_F"], full), poke_at(a["PSHIELD_A"], full)] + \
        [poke_at(a["PBANKS"] + 2 * i, full) for i in range(4)]
    # every breakable device but the military shields, which would halve
    # the blow under the threshold; a tonne of everything; a full tank
    fit = [poke_dev(t, d) for d in devs if d != "P_MILSHIELDS"]
    hold = [poke_at(a["P_CARGO"] + 2 * i, 1) for i in range(ngoods)] + [poke_at(a["PFUEL"], 70)]
    wear = f"peekcpu {a['P_WEAR'] & ~1:o}"
    lo, hi = a["P_ENERGYUNIT"] & ~1, a["P_EJECT"] | 1
    devwords = [f"peekcpu {w:o}" for w in range(lo, hi, 2)]
    cargo = [f"peekcpu {a['P_CARGO'] + 2 * i:o}" for i in range(ngoods)]
    rams = 30
    script = list(BOOT) + ["press 107", "run 150"] + clear_traffic(t) + fit + hold + \
        ram("SH_SIDEWINDER") + [wear] + refill
    for _ in range(rams):
        script += ram("SH_COBRAMK3HT1") + refill
    script += [wear, f"peekcpu {t['PFUEL']}"] + devwords + cargo + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 3 + len(devwords) + ngoods:
        check("the damage run answered", False, f"{len(v)} values")
        return
    w0, w1, fuel = byte_at(t, "P_WEAR", v[0]), byte_at(t, "P_WEAR", v[1]), v[2]
    raw = []
    for word in v[3:3 + len(devwords)]:
        raw += [word & 0xFF, word >> 8]
    fitted = raw[a["P_ENERGYUNIT"] - lo:a["P_ENERGYUNIT"] - lo + len(devs)]
    broken = [d for d, b in zip(devs, fitted) if b & a["DEV_BROKEN"]]
    # the scoops are fitted, so what the Cobras spill lands in the hold:
    # a spoiled tonne shows as a good emptied, not as a smaller hold
    empty = [i for i, n in enumerate(v[3 + len(devwords):3 + len(devwords) + ngoods][:32]) if n == 0]
    check(f"a Sidewinder's {light} is not heavy damage", w0 == 0, f"wear {w0}")
    check(f"a Cobra's {heavy} is, and the wear byte counts each", w1 == rams, f"wear {w1}")
    # a roll of 64 does nothing 47 times: thirty of them all blank once
    # in ten thousand runs
    check("and the roll drains the tank, breaks a device or spoils a tonne",
          fuel == 0 or broken or empty,
          f"fuel {fuel}, broken {broken}, goods emptied {empty}")

    # a broken docking computer is no docking computer
    script = list(BOOT) + [f"pokecpu {a['P_DOCKCOMP']:o} {a['DEV_BROKEN']:o}",
                           "press 107", "run 50"]
    for _ in range(4):
        script += ["press 166", "run 20"]
    script += [f"peekcpu {t['DC_ON']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if v:
        check("a broken docking computer does not answer the shut throttle", v[0] == 0,
              f"DC_ON {v[0]}")


def check_ecm():
    """Missiles and the ECM as Legend has them: one ECM field of
    ECM_FRAMES that costs your banks four a frame, breaks up ordinary
    missiles and spares military ones unless a naval ECM of yours is
    on; the auto-ECM; the 8 key picking the rack; a ship with an ECM
    answering your missile; and a hit worth 160 or 255."""
    print("missiles and the ECM")
    t = syms.table()
    need = ["ECM_TIME", "P_ECM", "P_AUTOECM", "PBANKS", "ENERGY_MAX", "ECM_FRAMES",
            "UF_MILMISS", "F3_ECM", "UF_MISSILE", "SH_MISSILE", "P_MISSTYPE", "PMISSILES",
            "SH_SIDEWINDER", "SH_PYTHONHT", "KILLS", "MISS_DMG", "DEV_NAVAL", "ECM_ON",
            "AUTOECM_ARMED", "AUTOECM_OUT", "NUNIV"]
    if any(n not in t for n in need):
        check("ECM symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    full, last = a["ENERGY_MAX"], a["NUNIV"] - 1

    def poke_slot(slot, field, val):
        return poke_at(int(slot_field(t, slot, field), 8), val)

    def incoming(slot, military=False):
        flags = a["UF_MISSILE"] | 1 | (a["UF_MILMISS"] if military else 0)
        return [poke_slot(slot, "U.TYPE", a["SH_MISSILE"]), poke_slot(slot, "U.FLAGS", flags),
                poke_slot(slot, "U.TARGET", -1), poke_slot(slot, "U.ENERGY", 120),
                poke_slot(slot, "U.EXPL", 0), poke_slot(slot, "U.X", 0),
                poke_slot(slot, "U.Y", 0), poke_slot(slot, "U.Z", 1500)]

    def state(slot):
        return [f"peekcpu {slot_field(t, slot, 'U.EXPL')}", f"peekcpu {slot_field(t, slot, 'U.TYPE')}"]

    def broken(expl, ty):
        return expl != 0 or ty != a["SH_MISSILE"]

    ecm_word = f"peekcpu {a['P_ECM'] & ~1:o}"
    fly = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t)

    # 1. the field: twelve frames, yours switched on for them, four off
    #    the first bank a frame (the last bank is emptied so the
    #    recovery goes there), and an ordinary missile coming apart
    banks = [poke_at(a["PBANKS"] + 2 * i, full) for i in range(3)] + [poke_at(a["PBANKS"] + 6, 0)]
    script = fly + [poke_dev(t, "P_ECM")] + banks + incoming(last) + \
        ["press 031", "run 2", f"peekcpu {t['ECM_TIME']}", ecm_word, "run 6"] + state(last) + \
        ["run 40", f"peekcpu {t['ECM_TIME']}", ecm_word, f"peekcpu {t['PBANKS']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 7:
        check("the ECM run answered", False, f"{len(v)} values")
        return
    on0, on1 = byte_at(t, "P_ECM", v[1]), byte_at(t, "P_ECM", v[5])
    check(f"the ECM runs {a['ECM_FRAMES']} frames, switched on for them and off after",
          0 < v[0] <= a["ECM_FRAMES"] and on0 & a["ECM_ON"] and v[4] == 0 and not on1 & a["ECM_ON"],
          f"time {v[0]} then {v[4]}, byte {on0:o} then {on1:o}")
    cost = 4 * a["ECM_FRAMES"]
    check(f"and costs the banks four a frame, {cost} in all",
          abs(v[6] - (full - cost)) <= 4, f"first bank {v[6]} against {full - cost}")
    check("an ordinary missile comes apart under it", broken(v[2], v[3]),
          f"countdown {v[2]}, slot {v[3]}")

    # 2. kinds: a naval ECM of yours breaks a military missile; an
    #    ordinary one lets it through while the standard one goes
    script = fly + [f"pokecpu {a['P_ECM']:o} {a['DEV_NAVAL']:o}"] + incoming(last - 1, True) + \
        ["press 031", "run 6"] + state(last - 1) + \
        ["run 40", poke_dev(t, "P_ECM")] + incoming(last - 1, True) + incoming(last) + \
        ["press 031", "run 6"] + state(last - 1) + state(last) + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 6:
        check("the kinds run answered", False, f"{len(v)} values")
        return
    check("a naval ECM switched on breaks a military missile too", broken(v[0], v[1]),
          f"countdown {v[0]}, slot {v[1]}")
    check("an ordinary ECM does not: it flies through while the standard one comes apart",
          not broken(v[2], v[3]) and broken(v[4], v[5]),
          f"military {v[2]}/{v[3]}, standard {v[4]}/{v[5]}")

    # 3. the auto-ECM answers a launch (the launch sets AUTOECM_OUT);
    #    the 8 key picks the military rack and the launch draws on it
    flags = [f"peekcpu {slot_field(t, s, 'U.FLAGS')}" for s in range(3, a["NUNIV"])]
    armed = a["AUTOECM_ARMED"] | a["AUTOECM_OUT"]
    script = fly + [poke_dev(t, "P_ECM"), f"pokecpu {a['P_AUTOECM']:o} {armed:o}", ui_ready(t, frames=2),
                    f"peekcpu {t['ECM_TIME']}", "run 60",
                    poke_at(a["PMISSILES"], 3), poke_at(a["P_MISSTYPE"], 1),
                    poke_slot(5, "U.TYPE", a["SH_SIDEWINDER"]), poke_slot(5, "U.FLAGS", 0),
                    poke_slot(5, "U.EXPL", 0), poke_slot(5, "U.TARGET", 0), poke_slot(5, "U.X", 0),
                    poke_slot(5, "U.Y", 0), poke_slot(5, "U.Z", 1200), poke_slot(5, "U.SPEED", 0),
                    poke_slot(5, "U.ENERGY", 70)] + mind(t, 5, "SIDEWINDERH", still=True) + ["run 20",
                    "press 017", "run 5", "press 113", "run 30", "press 113", "run 5",
                    f"peekcpu {t['P_MISSTYPE']}", f"peekcpu {t['PMISSILES']}"] + flags + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 3 + len(flags):
        check("the auto-ECM run answered", False, f"{len(v)} values")
        return
    check("the auto-ECM, armed, fires the ECM the frame a missile is launched at you",
          v[0] > 0, f"time {v[0]}")
    # what the mark on the missile does is the Python's business, below:
    # in an empty sky the missile has struck before a peek can see it
    check("8 picks the military rack, and the launch draws on it",
          v[1] == 0 and v[2] == 3, f"military {v[1]}, standard {v[2]}")

    # 4. a ship with an ECM answers your missile; a hit is worth 160 to
    #    a Python's 250, or 255 from the military rack
    python = [poke_slot(5, "U.TYPE", a["SH_PYTHONHT"]), poke_slot(5, "U.FLAGS", 0),
              poke_slot(5, "U.EXPL", 0), poke_slot(5, "U.TARGET", 0), poke_slot(5, "U.X", 0),
              poke_slot(5, "U.Y", 0), poke_slot(5, "U.Z", 1200), poke_slot(5, "U.SPEED", 0),
              poke_slot(5, "U.ENERGY", 250)] + mind(t, 5, "PYTHONHT", still=True) + \
        [poke_slot(5, "U.AI3", 0x7E | a["F3_ECM"])]      # its ECM is oFlg_3's bit 0 now
    hull = [f"peekcpu {slot_field(t, 5, 'U.ENERGY')}", f"peekcpu {slot_field(t, 5, 'U.TYPE')}",
            f"peekcpu {t['KILLS']}"]
    # the station goes: your missile in the sky angers everyone, the
    # station scrambles Vipers, and one of them rammed the commander
    # for a kill this check is not about (2026-09-24)
    # ... and the commander is parked: angry, the Python holds where it
    # is, and it was the commander flying into it that killed it
    script = fly + [poke_at(a["PMISSILES"], 4), poke_at(a["P_MISSTYPE"], 2),
                    poke_at(int(slot_field(t, 2, "U.TYPE"), 8), 0), poke_at(int(t["PSPEED"], 8), 0)] + python + \
        ["run 20", "press 113", "run 30", "press 113"]
    for _ in range(10):
        script += ["run 4", f"peekcpu {t['ECM_TIME']}"]
    # (the lowest energy the Python reaches, sampled: its hull knits
    # itself back four a reaction, and at 28 fps 150 ticks were enough to
    # knit all 160 back before a single look, 2026-09-27)
    low = [f"peekcpu {slot_field(t, 5, 'U.ENERGY')}"]
    script += hull + [poke_slot(5, "U.AI3", 0x7E), "run 40",
                      "press 113", "run 10", "press 113"] + ["run 5"] + (low + ["run 5"]) * 30 + hull + \
        ["press 017", "run 5", "press 113", "run 10", "press 113", "run 150"] + hull + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 49:
        check("the Python run answered", False, f"{len(v)} values")
        return
    times, first, lows, second, third = v[:10], v[10:13], v[13:43], v[43:46], v[46:49]
    second = [min(lows)] + second[1:]
    check("a ship with an ECM answers your missile, and is not hit",
          any(x > 0 for x in times) and first[0] == 250 and first[2] == 0,
          f"field {times}, energy {first[0]}, kills {first[2]}")
    check(f"a standard missile takes {a['MISS_DMG']} off a Python and leaves it flying",
          250 - a["MISS_DMG"] <= second[0] < 250 and second[1] == a["SH_PYTHONHT"] and second[2] == 0,   # its hull knits itself four a reaction after (src/ai.mac)
          f"energy {second[0]}, type {second[1]}, kills {second[2]}")
    check("a military one finishes it", third[2] == 1, f"kills {third[2]}, energy {third[0]}")


def check_cloak():
    """The cloak and the auto-eject as Legend has them: 9 switches the
    cloak on only with the last bank full, it costs four a frame, your
    shots give you away (a byte that halves a frame to a floor of 63)
    and a hostile mostly holds its fire under it, a broken one goes
    off; the capsule fires itself under POD_BANK and halves the legal
    record."""
    print("the cloak and the auto-eject")
    t = syms.table()
    need = ["P_CLOAK", "CLOAK_ON", "CLOAK_SEEN", "CLOAK_SEEN_FLOOR", "CLOAK_SEEN_SHOT", "PBANKS",
            "ENERGY_MAX", "FLY_TICK", "CKV_ENUNITS", "P_ESCPOD", "P_AUTOPOD", "AUTOPOD_ARMED",
            "POD_BANK", "LEGAL", "DOCKED", "DEV_BROKEN", "PSHIELD_F", "SH_KRAIT", "UF_HOSTILE",
            "NUNIV"]
    if any(n not in t for n in need):
        check("cloak symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    full = a["ENERGY_MAX"]
    last_bank = a["PBANKS"] + 6                    # a Cobra's fourth
    fly = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t)
    on, seen, tick = (f"peekcpu {t[n]}" for n in ("CLOAK_ON", "CLOAK_SEEN", "FLY_TICK"))

    # 1. the switch, the cost, the shot that gives you away, the break
    script = fly + [f"peekcpu {t['CKV_ENUNITS']}", poke_dev(t, "P_CLOAK"), poke_at(last_bank, 100),
                    "press 177", "run 10", on, poke_at(last_bank, full), "press 177", "run 10", on] + \
        [poke_at(a["PBANKS"] + 2 * i, full) for i in range(3)] + [poke_at(last_bank, 0), tick,
         "run 40", tick, f"peekcpu {t['PBANKS']}", "keydown 107"] + \
        ["run 1", seen] * 16 + ["keyup 107",
         "run 12", seen, f"pokecpu {a['P_CLOAK']:o} {a['DEV_BROKEN']:o}", "run 3", on, "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 24:
        check("the cloak run answered", False, f"{len(v)} values")
        return
    # the shot's bit is set by LASER_STEP and halved by the next frame's
    # CLOAK_STEP, so one peek at a fixed tick lands on either side of
    # the halving as the frame phase drifts: the byte is sampled every
    # tick while the trigger is held and its highest value is the one
    # that says whether a shot ever set bit 7 (2026-09-19)
    # (sixteen ticks since the boot grew by the war's first search of the
    # galaxy, 2026-09-25: eight had stopped straddling a shot)
    v[6:22] = [max(v[6:22])]
    check("9 switches the cloak on only with the last bank full, and off again",
          v[0] == 4 and v[1] == 0 and v[2] == 1, f"{v[0]} banks: {v[1]} then {v[2]}")
    frames = v[4] - v[3]
    check("and it costs the banks four a frame", abs(v[5] - (full - 4 * frames)) <= 8 and frames > 5,
          f"first bank {v[5]} after {frames} frames")
    check("a shot of yours gives you away, and it fades to the floor",
          v[6] >= a["CLOAK_SEEN_SHOT"] and v[7] == a["CLOAK_SEEN_FLOOR"], f"seen {v[6]} then {v[7]}")
    check("a broken cloak goes off", v[8] == 0, f"on {v[8]}")

    # 2. the auto-eject: fitted, armed, the last bank under the line
    script = fly + [poke_dev(t, "P_ESCPOD"), f"pokecpu {a['P_AUTOPOD']:o} {a['AUTOPOD_ARMED']:o}",
                    # well under the line: RECHARGE puts up to sixteen points
                    # into the last bank on its next turn, and a poke eight
                    # under came back at 56 before AUTOPOD_STEP read it
                    poke_at(a["LEGAL"], 100), poke_at(last_bank, a["POD_BANK"] - 40), "run 12",
                    f"peekcpu {t['DOCKED']}", peek_dev(t, "P_ESCPOD"), f"peekcpu {t['LEGAL']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("cloak")))]
    if len(v) >= 3:
        check(f"the auto-eject fires the capsule under {a['POD_BANK']} in the last bank, and the record is halved",
              v[0] == 1 and not dev_fitted(t, "P_ESCPOD", v[1]) and v[2] == 50,
              f"docked {v[0]}, capsule {v[1]:o}, legal {v[2]}")

    # 3. Repeated, controlled firing opportunities. Keep the Krait's
    # heading and mind pointed at the commander and forbid hyperspace;
    # otherwise it can turn away or leave during a timed firing window.
    # HP_TICK records a hit even if the shield recovers before the peek.
    samples = 256
    slot = 3
    ready = ship_pokes(t, slot, "KRAITH", z=1200, energy=4000,
                       hyper=False, facing=True)
    ready += [poke_at(a["PSHIELD_F"], full)]
    ready += [poke_at(a["PBANKS"]+2*i, full) for i in range(4)]
    ready += [poke_at(int(t["HP_TICK"], 8), 65535), poke_at(int(t["HP_INT"], 8), 0)]
    field = slot_field(t, slot, "U.TYPE")
    seed = [poke_at(int(t["RNDSEED"], 8), 0x0511),
            poke_at(int(t["RNDSEED"], 8)+2, 0x2026)]

    def window():
        return sum((ready + ["run 10", f"peekcpu {t['HP_TICK']}",
                             f"peekcpu {field}", on] for _ in range(samples)), [])

    setup = (list(BOOT) + ["press 107", "run 40"] + clear_traffic(t)
             + [poke_at(int(t["WITCH"], 8), 1),
                poke_at(int(slot_field(t, 2, "U.TYPE"), 8), 0),
                poke_at(int(t["PSPEED"], 8), 0),
                poke_at(int(t["RATING_H"], 8), 256)])
    script = (setup + seed + window() + [poke_dev(t, "P_CLOAK")] + ready
              + ["press 177", "run 10", poke_at(a["CLOAK_SEEN"], a["CLOAK_SEEN_FLOOR"])]
              + seed + window() + ["quit"])
    values = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("hostile")))]
    rows = [values[i:i+3] for i in range(0, len(values), 3)]
    open_, cloaked = (sum(row[0] != 65535 for row in phase)
                      for phase in (rows[:samples], rows[samples:]))
    stable = (len(rows) == samples*2 and
              all(row[1] == a["SH_KRAIT"] for row in rows) and
              all(row[2] == 0 for row in rows[:samples]) and
              all(row[2] == 1 for row in rows[samples:]))
    check("a hostile lined up on you mostly holds its fire under the cloak",
          stable and open_ > 0 and cloaked < open_,
          f"hit windows {open_} open, {cloaked} cloaked; attacker/cloak stable {stable}")


def check_jdrive():
    """The J-drive, the injectors and the collector as Legend has them
    (src/jdrive.mac): held, with nothing mass-locking it, every body
    and bay comes JD_STEP nearer a frame; a Krait on the scanner locks
    it and the same key is then the injectors, if fitted - INJ_SPEED
    instead of the throttle, the stick dead, a tenth of fuel every
    INJ_FRAMES; the collector makes a tenth every COLL_FRAMES of
    drive."""
    print("the J-drive and the injectors")
    t = syms.table()
    need = ["JD_STEP", "JD_BODY", "JD_LOCKED", "JD_SPEED", "INJ_SPEED", "INJ_FRAMES", "COLL_FRAMES",
            "P_FUELCOLL", "P_INJECTORS", "PFUEL", "PSPEED", "PROLL", "FLY_TICK", "SH_KRAIT",
            "DEV_RUN"]
    if any(n not in t for n in need):
        check("J-drive symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    last = a["SH_KRAIT"]

    def slot(sl, f, v):
        return poke_at(int(slot_field(t, sl, f), 8), v)

    def peek(sl, f):
        return f"peekcpu {slot_field(t, sl, f)}"

    # the sky: nothing but the bodies and the station, and the station
    # pushed out past BASE_U, because a launch leaves it inside it and
    # the drive is locked at the bay's door, as it is in Legend.  And
    # WITCH set, which is the one switch that stops TRAFFIC_STEP: a
    # ship arriving at 7000 mass-locks the drive, as it should, and
    # one arrived inside 167 frames on the first run of this check
    fly = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t) + \
        [poke_at(a["PSPEED"], 0), slot(2, "U.Z", 20000), poke_at(int(t["WITCH"], 8), 1)]
    tick, fuel = f"peekcpu {t['FLY_TICK']}", f"peekcpu {t['PFUEL']}"

    # 1. the drive: the world comes nearer by JD_STEP a frame while
    #    nothing locks it, and the collector fills the tank a tenth every
    #    COLL_FRAMES of that.  The world is parked past sixteen bits
    #    (61440; the high word poked AFTER widen_positions' sign
    #    extension) so that it takes ninety-odd frames to come within
    #    JD_BODY and lock the drive, the station behind and receding;
    #    the run is sampled every ten ticks and only the intervals that
    #    end unlocked are counted, because the lock is the rule, not a
    #    failure. Allow 400 ticks: the filled sun slows the final approach,
    #    and 200 stopped short of the lock despite correct movement/frame.
    zl, zh = f"peekcpu {slot_field(t, 0, 'U.Z')}", f"peekcpu {slot_field(t, 0, 'U.ZH')}"
    sample = [zl, zh, tick, f"peekcpu {t['JD_LOCKED']}", fuel]
    script = fly + [poke_dev(t, "P_FUELCOLL"), poke_at(a["PFUEL"], 10), slot(2, "U.Z", -30000),
                    slot(0, "U.Z", 0xF000), poke_at(int(slot_field(t, 0, "U.ZH"), 8), 0), "run 2"] + \
        sample + ["keydown 075"] + (["run 10"] + sample) * 40 + ["keyup 075", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    rows = [v[i:i + 5] for i in range(0, len(v) - 4, 5)]
    if len(rows) < 41:
        check("the drive run answered", False, f"{len(rows)} samples")
        return
    z = [signed(r[1]) * 65536 + r[0] for r in rows]
    drive, bad = 0, []
    for i in range(2, len(rows)):                        # the first interval holds
        if rows[i][3] or z[i] == z[i - 1]:               #   the key's own latency;
            continue                                     #   locked by the end: not counted
                                                         #   - and a world that did not
                                                         #   move is locked: JD_LOCKED is
                                                         #   cleared at the top of every
                                                         #   frame, so one peek can be a
                                                         #   mid-frame 0 (2026-09-25, when
                                                         #   the frames got faster)
        frames = rows[i][2] - rows[i - 1][2]
        moved = z[i - 1] - z[i]
        drive += frames
        if abs(moved - a["JD_STEP"] * frames) > a["JD_STEP"]:
            bad.append((moved, frames))
    check("held, the J-drive brings the world JD_STEP nearer a frame",
          drive >= 40 and not bad and (rows[-1][3] == 1 or z[-1] == z[-2])
          and z[-1] < a["JD_BODY"] + 2 * a["JD_STEP"],
          f"{drive} frames of drive, off by {bad[:3]}, then locked {rows[-1][3]} at {z[-1]}")
    gain = rows[-1][4] - 10
    check("and the collector makes a tenth of fuel every COLL_FRAMES of it",
          1 <= gain <= drive // a["COLL_FRAMES"] + 1, f"fuel {rows[-1][4]} after {drive} frames of drive")

    # 2. a Krait on the scanner locks the drive; the key is then the
    #    injectors, when a pair is fitted: INJ_SPEED, the stick dead, a
    #    tenth every INJ_FRAMES, and off again with the key
    krait = [slot(5, "U.TYPE", last), slot(5, "U.FLAGS", 0), slot(5, "U.EXPL", 0),
             slot(5, "U.ENERGY", 100), slot(5, "U.SPEED", 0), slot(5, "U.X", 0),
             slot(5, "U.Y", 0), slot(5, "U.Z", 8000)] + mind(t, 5, last, still=True)
    # (8000 ahead, not 3000: the injectors fly at INJ_SPEED a frame, and
    # the faster renderer of 2026-09-26 fitted 65 frames into the run -
    # the ship reached the Krait, the lock broke and the J-drive took
    # over; JD_LOCK is 13824, so 8000 locks and is never reached)
    # JD_LOCKED is cleared at the top of every frame and set again after
    # the scan: one sample is a mid-frame read (it read 0 with the Krait
    # in plain view, 2026-09-24 late), so three are taken and the best
    # kept
    lock = f"peekcpu {t['JD_LOCKED']}"
    script = fly + krait + [peek(0, "U.Z"), "keydown 075", "run 8", lock, "run 6", lock, "run 6", peek(0, "U.Z"),
                            lock, f"peekcpu {t['JD_SPEED']}", "keyup 075", "run 5",
                            poke_dev(t, "P_INJECTORS"), poke_at(a["PFUEL"], 20), peek(1, "U.Z"), tick,
                            "keydown 075", "keydown 116",
                            "run 96", f"peekcpu {t['JD_SPEED']}", peek_dev(t, "P_INJECTORS"),
                            "run 2", f"peekcpu {t['JD_SPEED']}", peek_dev(t, "P_INJECTORS"),
                            "run 2", peek(1, "U.Z"), tick,
                            f"peekcpu {t['JD_SPEED']}", peek_dev(t, "P_INJECTORS"), fuel,
                            f"peekcpu {t['PROLL']}", "keyup 075", "keyup 116", "run 20",
                            f"peekcpu {t['JD_SPEED']}", peek_dev(t, "P_INJECTORS"), "quit"]
    v = [signed(int(x, 8)) for x in PEEK.findall(run_emu(script, fresh_disk("jdrive")))]
    if len(v) < 20:
        check("the injector run answered", False, f"{len(v)} values")
        return
    locked = max(v[1], v[2], v[4])
    check("a ship on the scanner mass-locks the drive",
          v[0] == v[3] and locked == 1 and v[5] == 0, f"world {v[0]} -> {v[3]}, locked {locked}, speed {v[5]}")
    # the speed and the device's running bit are set in the frame and
    # can be peeked between (2026-09-25: a faster frame put the last
    # peek there): three samples of each, the best kept
    v = v[6:]
    samples = [(v[2], v[3]), (v[4], v[5]), (v[8], v[9])]
    v = [v[0], v[1], v[6], v[7], max(x for x, _ in samples)] + \
        [max((d & 0xFF) & a["DEV_RUN"] for _, d in samples)] + v[10:]
    frames = v[3] - v[1]
    moved = v[0] - v[2]
    check("and the same key is then the injectors: INJ_SPEED instead of the throttle",
          v[4] == a["INJ_SPEED"] and v[5]
          and abs(moved - a["INJ_SPEED"] * frames) <= 2 * a["INJ_SPEED"],
          f"speed {v[4]}, running {v[5]:o}, sun {moved} over {frames} frames")
    check("a tenth of fuel every INJ_FRAMES, and the stick dead",
          abs((20 - v[6]) - frames // a["INJ_FRAMES"]) <= 1 and v[7] == 0,
          f"fuel {v[6]} after {frames} frames, roll {v[7]}")
    check("and off again with the key", v[8] == 0 and not ((v[9] & 0xFF) & a["DEV_RUN"]),
          f"speed {v[8]}, device {v[9] & 0xFF:o}")


def check_bombs():
    """The two bombs (BOMB_FIRE): each spares one hull, told by its
    speed - the energy bomb the Targon mother ship (39), the Q-bomb the
    Targon-6 (38) - and is spent."""
    print("the two bombs")
    t = syms.table()
    need = ["SH_TARGONH", "SH_TARGON6H", "SH_COBRAMK3HT1", "P_EBOMB"]
    if any(n not in t for n in need):
        check("bomb symbols found", False, f"missing {[n for n in need if n not in t]}")
        return
    a = {n: int(t[n], 8) for n in need}

    def ship(sl, ty, z):
        return [poke_at(int(slot_field(t, sl, f), 8), v) for f, v in
                (("U.TYPE", ty), ("U.FLAGS", 0), ("U.EXPL", 0), ("U.ENERGY", 100),
                 ("U.SPEED", 0), ("U.X", 0), ("U.Y", 0), ("U.Z", z))] + mind(t, sl, ty, still=True)

    three = ship(5, a["SH_TARGONH"], 4000) + ship(6, a["SH_COBRAMK3HT1"], 5000) + \
        ship(7, a["SH_TARGON6H"], 6000)
    expl = [f"peekcpu {slot_field(t, sl, 'U.EXPL')}" for sl in (5, 6, 7)]
    fly = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t) + three

    v = [int(x, 8) for x in PEEK.findall(run_emu(
        fly + [poke_dev(t, "P_EBOMB"), "press 032", "run 5"] + expl + [peek_dev(t, "P_EBOMB"), "quit"]))]
    if len(v) >= 4:
        check("the energy bomb breaks up everything but the Targon mother ship, and is spent",
              v[0] == 0 and v[1] > 0 and v[2] > 0 and not dev_fitted(t, "P_EBOMB", v[3]),
              f"explosions {v[:3]}, device {v[3]:o}")
    v = [int(x, 8) for x in PEEK.findall(run_emu(
        fly + [f"pokecpu {a['P_EBOMB']:o} 1", "press 032", "run 5"] + expl + ["quit"],
        fresh_disk("bombs")))]
    if len(v) >= 3:
        check("and the Q-bomb everything but the Targon-6", v[0] > 0 and v[1] > 0 and v[2] == 0,
              f"explosions {v[:3]}")


def check_autotake():
    """"8" cycles the space bar's functions round what there is something
    for; with the auto-take fitted a locked canister flies itself into
    the scoop, and with fuel in the extra tank the space bar refuels."""
    print("the auto-take and the tank")
    t = syms.table()
    need = ["MISS_KIND", "MISS_LOCK", "UF_TAKEN", "P_AUTOTAKE", "P_FUELSCOOPS", "P_TANKS",
            "P_FREECARGO", "PFUEL", "PSPEED", "SH_CANISTER", "CKV_MAXFUEL"]
    if any(n not in t for n in need):
        check("auto-take symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    # the canister is in slot 3, the first the lock's search meets: a
    # ship the station launches lands in the first FREE slot, and with
    # the canister in 5 the lock took it instead (2026-09-24, late)
    can = [poke_at(int(slot_field(t, 3, f), 8), v) for f, v in
           (("U.TYPE", a["SH_CANISTER"]), ("U.FLAGS", 0), ("U.EXPL", 0), ("U.ENERGY", 10),
            ("U.SPEED", 0), ("U.X", 0), ("U.Y", 0), ("U.Z", 3000))] + mind(t, 3, a["SH_CANISTER"])
    fly = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t) + [poke_at(a["PSPEED"], 0)]
    kind = f"peekcpu {t['MISS_KIND']}"

    # 1. the functions: a new commander has missiles and nothing else,
    #    so "8" goes straight round to them; with the device it stops at
    #    the auto-take; the locked canister is marked and comes in.  The
    #    hold is counted good by good: a plain canister holds anything
    #    at all, and three of the goods take no tonne of the free space
    ngoods = int(t["NGOODS"], 8)
    dump0, dump1 = ROOT / "tmp" / "verify-take0.bin", ROOT / "tmp" / "verify-take1.bin"
    script = fly + can + ["press 017", "run 5", kind, poke_dev(t, "P_AUTOTAKE"), poke_dev(t, "P_FUELSCOOPS"),
                          f"peekcpu {t['P_FREECARGO']}", f"dumpcpu {t['CARGO']} {ngoods * 2} {dump0}",
                          "press 017", "run 5", kind, "press 113", "run 5",
                          f"peekcpu {t['MISS_LOCK']}", "press 113", "run 5",
                          f"peekcpu {slot_field(t, 3, 'U.FLAGS')}", f"peekcpu {t['MISS_LOCK']}", "run 100",
                          f"peekcpu {slot_field(t, 3, 'U.TYPE')}", f"peekcpu {t['P_FREECARGO']}",
                          f"dumpcpu {t['CARGO']} {ngoods * 2} {dump1}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 8 or not dump0.exists() or not dump1.exists():
        check("the auto-take run answered", False, f"{len(v)} values")
        return
    import struct
    held = [sum(struct.unpack_from("<H", d.read_bytes(), 2 * i)[0] for i in range(ngoods))
            for d in (dump0, dump1)]
    check('"8" cycles only the functions there is something for', v[0] == 0 and v[2] == 3,
          f"without the device {v[0]}, with it {v[2]}")
    check("the space bar locks, and marks the locked canister as taken",
          v[3] == 4 and v[4] & a["UF_TAKEN"] and v[5] == 0, f"lock {v[3]}, flags {v[4]:o}, then {v[5]}")
    check("and it flies itself into the scoop", v[6] != a["SH_CANISTER"] and held[1] == held[0] + 1,
          f"slot {v[6]}, held {held[0]} -> {held[1]}, free {v[1]} -> {v[7]}")

    # 2. the tank: ten tenths in it, the main one fifty short of seventy
    script = fly + [f"pokecpu {a['P_TANKS']:o} 112", poke_at(a["PFUEL"], 50), "press 017", "run 5", kind,
                    "press 113", "run 5", f"peekcpu {t['PFUEL']}", f"peekcpu {t['P_TANKS']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("tank")))]
    if len(v) >= 3:
        check("and with fuel in the extra tank the space bar pours it into the main one",
              v[0] == 5 and v[1] == 60 and (v[2] & 0o77) == 0, f"function {v[0]}, fuel {v[1]}, tank {v[2] & 0xFF:o}")


def check_drone():
    """The boarding drone as Legend has it: "8" stops at it only with the
    system fitted and a drone in the hold; the space bar sends one at a
    locked wreck that can be boarded and refuses a manned ship; the
    drone flies there and is spent; the roll takes the wreck into a free
    berth - the yard's number, this galaxy and world - and it leaves by
    hyperspace, or fails: on the standard drone's roll alone, or with
    every berth taken."""
    print("the boarding drone")
    t = syms.table()
    need = ["MISS_KIND", "MISS_LOCK", "P_DRONE", "P_CARGO", "P_FREECARGO", "P_SHIPS", "G_DRONE",
            "SH_DRONEH", "SH_COBRAMK3HT1", "KB_PLAYER", "KB_DRONE", "UF_DERELICT", "BD_FREE",
            "BD_NAVAL", "MF_DRONE", "PSPEED", "NYARD", "SLOT_LEN", "P_GALAXY", "P_PLANET"]
    if any(n not in t for n in need):
        check("drone symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    cargo = a["P_CARGO"] + 2 * a["G_DRONE"]
    kind = f"peekcpu {t['MISS_KIND']}"
    fly = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t) + [poke_at(a["PSPEED"], 0)]
    # the wreck is in slot 3, the first the lock's search meets (a ship
    # the station launches lands in the first FREE slot, and took the
    # lock when the wreck was in 5); the drone lands in the first free
    # slot after it and is found by its type
    wreck = ship_pokes(t, 3, "COBRAMK3HT1", z=3000, hostile=False, hyper=False,
                       **{"U.FLAGS": a["UF_DERELICT"]})
    manned = ship_pokes(t, 3, "COBRAMK3HT1", z=3000, hostile=False, hyper=False)
    DS = range(4, 8)                    # where the drone may land
    armed = [poke_dev(t, "P_DRONE"), poke_at(cargo, 2)]
    lock_launch = ["press 113", "run 5", f"peekcpu {t['MISS_LOCK']}", "press 113", "run 5"]

    def word(slot, field):
        return f"peekcpu {slot_field(t, slot, field)}"

    def drone_of(v):
        # (type, kind, target) of the slot holding the drone, or None
        for i, s_ in enumerate(DS):
            if v[3 * i] == a["SH_DRONEH"]:
                return v[3 * i:3 * i + 3]
        return None

    def drone_born(v):
        d = drone_of(v)
        return d is not None and (d[1] & 0xFF) & a["KB_PLAYER"] and (d[1] & 0xFF) & a["KB_DRONE"] and d[2] == 4

    NB = 3 * len(DS)
    born = [w for s_ in DS for w in (word(s_, "U.TYPE"), word(s_, "U.KIND"), word(s_, "U.TARGET"))] + \
        [f"peekcpu {cargo:o}", f"peekcpu {t['P_FREECARGO']}"]

    # 1. the function, and the launch: a manned Cobra is refused, a
    #    wreck gets the drone and the hold is a tonne lighter
    script = fly + manned + ["press 017", "run 5", kind] + armed + \
        ["press 017", "run 5", kind, "press 017", "run 5", kind, "press 017", "run 5", kind,
         f"peekcpu {t['P_FREECARGO']}"] + lock_launch + born + wreck + lock_launch + born + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 5 + 2 * (1 + NB + 2):
        check("the drone launch run answered", False, f"{len(v)} values")
        return
    check('"8" stops at the drone only with the system and a drone in the hold',
          v[0] == 0 and v[1] == a["MF_DRONE"] and v[2] == 0 and v[3] == a["MF_DRONE"],
          f"functions {v[0:4]}")
    first, second = v[5:5 + 1 + NB + 2], v[5 + 1 + NB + 2:]
    check("the space bar locks on a manned Cobra and refuses to send a drone at it",
          first[0] == 4 and drone_of(first[1:]) is None and first[1 + NB] == 2,
          f"lock {first[0]}, drone {drone_of(first[1:])}, hold {first[1 + NB]}")
    d = drone_of(second[1:])
    check("and sends one at the same hull with nobody aboard, a tonne out of the hold",
          second[0] == 4 and drone_born(second[1:]) and second[1 + NB] == 1 and second[2 + NB] == v[4] + 1,
          f"lock {second[0]}, drone {d}, hold {second[1 + NB]}, free {v[4]} -> {second[2 + NB]}")

    # 2. the boarding, with the roll forced: the drone is spent, the
    #    berth holds the Cobra (the yard's 6) here, and the wreck leaves
    def run_boarding(setup, name):
        script = fly + armed + ["press 017", "run 5"] + wreck + setup + lock_launch
        per = 1 + len(DS)
        for _ in range(30):
            script += ["run 5", word(3, "U.TYPE")] + [word(s_, "U.TYPE") for s_ in DS]
        script += [f"peekcpu {a['P_SHIPS']:o}", f"peekcpu {a['P_SHIPS'] + 2:o}",
                   f"peekcpu {t['P_GALAXY']}", f"peekcpu {t['P_PLANET']}", "quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk(name)))]
        if len(v) < 1 + 30 * per + 4:
            check(f"the {name} run answered", False, f"{len(v)} values")
            return None
        samples = [v[1 + k * per:1 + (k + 1) * per] for k in range(30)]
        wrecks = [smp[0] for smp in samples]
        drones = [a["SH_DRONEH"] in smp[1:] for smp in samples]
        tail = v[1 + 30 * per:]
        return dict(spent=any(drones) and not drones[-1],
                    gone=0 in wrecks, stayed=all(w == a["SH_COBRAMK3HT1"] for w in wrecks),
                    berth=tail[0] & 0xFF, galaxy=tail[0] >> 8, planet=tail[1] & 0xFF,
                    here=(tail[2] & 0xFF, tail[3] & 0xFF))

    r = run_boarding([poke_at(a["BD_FREE"], 256)], "boarded")
    if r:
        check("the drone reaches the wreck and is spent, and on the roll the wreck is taken",
              r["spent"] and r["gone"] and r["berth"] == 6,
              f"spent {r['spent']}, gone {r['gone']}, berth {r['berth']}")
        check("into a free berth as the yard's ship, at this galaxy and world",
              r["berth"] == 6 and (r["galaxy"], r["planet"]) == r["here"],
              f"berth {r['berth']} at {r['galaxy']}/{r['planet']}, here {r['here']}")
    r = run_boarding([poke_at(a["BD_FREE"], 0)], "notboarded")
    if r:
        check("the standard drone fails on its roll alone: the wreck stays and no berth fills",
              r["spent"] and r["stayed"] and r["berth"] == 0,
              f"spent {r['spent']}, stayed {r['stayed']}, berth {r['berth']}")
    r = run_boarding([poke_at(a["BD_FREE"], 0), poke_at(a["BD_NAVAL"], 256),
                      f"pokecpu {a['P_DRONE']:o} 1"], "naval")
    if r:
        check("the naval drone has a roll of its own", r["spent"] and r["gone"] and r["berth"] == 6,
              f"spent {r['spent']}, gone {r['gone']}, berth {r['berth']}")
    full = [f"pokecpu {a['P_SHIPS'] + k * a['SLOT_LEN']:o} 1" for k in range(a["NYARD"])]
    r = run_boarding([poke_at(a["BD_FREE"], 256)] + full, "noberth")
    if r:
        check("with every berth taken the boarding fails", r["spent"] and r["stayed"] and r["berth"] == 1,
              f"spent {r['spent']}, stayed {r['stayed']}, berth {r['berth']}")


def legend_seed(galaxy):
    """Legend's SetGalaxyData_A: the six seed bytes from an offset of
    bits 5-3 of the galaxy number, each rotated left bits 2-0 places."""
    if galaxy >= 254:                 # the Targons' (#5C) and Raxxla's (#5D):
        v, bs = 0x5C if galaxy == 254 else 0x5D, []   # a byte rotated on
        for _ in range(6):
            bs.append(v)
            v = ((v << 1) | (v >> 7)) & 0xFF
        return [bs[0] | bs[1] << 8, bs[2] | bs[3] << 8, bs[4] | bs[5] << 8]
    base = [0x4A, 0x5A, 0x48, 0x02, 0x53, 0xB7] * 2
    r, t = (galaxy >> 3) & 7, galaxy & 7
    bs = [((b << t) | (b >> (8 - t))) & 0xFF if t else b for b in base[r:r + 6]]
    return [bs[0] | bs[1] << 8, bs[2] | bs[3] << 8, bs[4] | bs[5] << 8]


def nearest_system(galaxy, x, y):
    """GAL_JUMP's arrival: the first system of GALAXY nearest to (x, y)
    by SYS_DISTANCE, the strict compare keeping the earlier one."""
    best, best_d = 0, None
    for i in range(256):
        d = sys_distance(galaxy_model(i, galaxy), dict(x=x, y=y))
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best


def check_galaxies():
    """Legend's forty-eight galaxies and three drives: the chart's
    galaxy draws from Legend's seed rule; the standard drive goes to
    the next galaxy, is used up and lands at the system nearest the
    cursor; the military one steps the chart three either way and jumps
    where it points without being used up; the experimental one steps
    anywhere up to 47; without a drive nothing steps or jumps; and 47
    goes round to 0."""
    print("the galaxies and the drives")
    t = syms.table()
    need = ["GALNUM", "CHART_GAL", "SYS_INDEX", "P_GALDRIVE", "SYS_X", "SYS_Y", "DOCKED",
            "SCREEN", "NGALAXY", "CURSYS"]
    if any(n not in t for n in need):
        check("galaxy symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    check("forty-eight galaxies", a["NGALAXY"] == 48, str(a["NGALAXY"]))
    chart = ["press 004", ui_ready(t)]
    step_up, step_down = ["press 031", ui_ready(t, frames=1)], ["press 030", ui_ready(t, frames=1)]
    jump = ["press 107", ui_ready(t, frames=1)]

    def peeks(*names):
        return [f"peekcpu {t[n]}" for n in names]

    # 1. the seed rule: the chart drawing galaxy 9 (the second byte
    #    order, twisted once) leaves SYS_X/SYS_Y as its system 7
    script = list(BOOT) + [poke_at(a["CHART_GAL"], 9)] + chart + peeks("SYS_X", "SYS_Y", "GALNUM") + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    m = galaxy_model(7, 9)
    if len(v) >= 3:
        check("the chart draws another galaxy from Legend's seed rule",
              (v[0], v[1]) == (m["x"], m["y"]) and v[2] == 0,
              f"system 7 of galaxy 9 at ({v[0]},{v[1]}), model ({m['x']},{m['y']})")

    # 2. the standard drive: the next galaxy, used up, the nearest system
    #    to where the cursor (Lave) was, still in the dock
    lave = galaxy_model(7)
    script = list(BOOT) + [poke_dev(t, "P_GALDRIVE")] + chart + jump + \
        peeks("GALNUM", "SYS_INDEX", "DOCKED", "SCREEN", "CHART_GAL") + [peek_dev(t, "P_GALDRIVE"), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 6:
        want = nearest_system(1, lave["x"], lave["y"])
        check("the standard drive goes to the next galaxy and is used up",
              v[0] == 1 and v[4] == 1 and not dev_fitted(t, "P_GALDRIVE", v[5]), f"galaxy {v[0]}, chart {v[4]}, drive {v[5]:o}")
        check("and lands at the system nearest where the cursor was, still in the dock",
              v[1] == want and v[2] == 1 and v[3] == 0, f"system {v[1]} against {want}, docked {v[2]}, screen {v[3]}")

    # 3. the military drive: the chart steps three up and no further,
    #    back down to 0 and no further, and ФИКС on a system of the
    #    galaxy shown jumps there, the drive kept
    script = list(BOOT) + [f"pokecpu {a['P_GALDRIVE']:o} 1"] + chart + step_up * 5 + peeks("CHART_GAL") + \
        step_down * 7 + peeks("CHART_GAL") + step_up + peeks("CHART_GAL") + jump + \
        peeks("GALNUM", "SYS_INDEX") + [peek_dev(t, "P_GALDRIVE"), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 6:
        there = galaxy_model(7, 1)
        want = nearest_system(1, there["x"], there["y"])
        check("the military drive lets the chart step three galaxies either way, inside 0..47",
              v[0] == 3 and v[1] == 0 and v[2] == 1, f"steps {v[0:3]}")
        check("and ФИКС on a system of the galaxy shown jumps there without using it up",
              v[3] == 1 and v[4] == want and dev_fitted(t, "P_GALDRIVE", v[5]),
              f"galaxy {v[3]}, system {v[4]} against {want}, drive {v[5]:o}")

    # 4. the experimental drive steps anywhere, to 47 and no further; no
    #    drive steps nowhere and jumps nowhere
    script = list(BOOT) + [f"pokecpu {a['P_GALDRIVE']:o} 2"] + chart + step_up * 10 + peeks("CHART_GAL") + \
        [poke_at(a["CHART_GAL"], 47)] + step_up + peeks("CHART_GAL") + \
        [poke_at(a["CHART_GAL"], 0), poke_dev(t, "P_GALDRIVE", fitted=False)] + step_up + peeks("CHART_GAL") + \
        ["press 107", ui_ready(t, frames=1)] + peeks("GALNUM") + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 4:
        check("the experimental drive steps the chart anywhere, up to 47",
              v[0] == 10 and v[1] == 47, f"steps {v[0]}, then {v[1]}")
        check("with no drive the chart stays and ФИКС on your own system goes nowhere",
              v[2] == 0 and v[3] == 0, f"chart {v[2]}, galaxy {v[3]}")

    # 5. from the last galaxy the standard drive goes round to the first
    script = list(BOOT) + [poke_at(a["GALNUM"], 47), poke_at(a["CHART_GAL"], 47), poke_dev(t, "P_GALDRIVE")] + \
        chart + jump + peeks("GALNUM") + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if v:
        check("from galaxy 47 the standard drive goes round to 0", v[0] == 0, f"galaxy {v[0]}")


def check_list():
    """The list of systems on the galaxy chart (Legend's PrnListPlanet):
    "3" opens it with a navigation array and not without, the arrows
    walk a system and a page in it, the cursor's travel time is
    CalcTravelTime's, and another galaxy's list wants the experimental
    array."""
    print("the list of systems")
    t = syms.table()
    need = ["CURSYS", "P_ADVNAV", "CHART_GAL", "PFUEL", "CH_LIST", "CH_TIME", "P_GALDRIVE"]
    if any(n not in t for n in need):
        check("list symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    chart = ["press 004", ui_ready(t)]
    toggle, up, down, right, left = (["press 032", ui_ready(t, frames=1)], ["press 154", ui_ready(t, frames=1)], ["press 134", ui_ready(t, frames=1)],
                                     ["press 133", ui_ready(t, frames=1)], ["press 116", ui_ready(t, frames=1)])

    def peeks(*names):
        return [f"peekcpu {t[n]}" for n in names]

    # 1. without an array "3" does nothing and ↑ is still sixteen systems;
    #    with one the list opens, ↑ is one system and → a page
    script = list(BOOT) + chart + toggle + peeks("CH_LIST") + up + peeks("CURSYS") + \
        [poke_at(a["CURSYS"], 7), poke_dev(t, "P_ADVNAV")] + toggle + peeks("CH_LIST") + \
        up + peeks("CURSYS") + right + peeks("CURSYS") + down + down + peeks("CURSYS") + left + \
        peeks("CURSYS", "CH_TIME", "PFUEL") + toggle + peeks("CH_LIST") + up + peeks("CURSYS") + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) < 11:
        check("the list run answered", False, f"{len(v)} values")
        return
    check('"3" opens the list only with a navigation array', v[0] == 0 and v[1] == 23 and v[2] == 1,
          f"without {v[0]} (up went to {v[1]}), with {v[2]}")
    check("in the list the arrows walk a system and a page", v[3] == 6 and v[4] == 26 and v[5] == 28 and v[6] == 8,
          f"cursor {v[3:7]}")
    lave = galaxy_model(7)
    d = sys_distance(galaxy_model(8), lave)
    want = d * d // 10 if d <= v[8] else 6 * d
    check("the cursor's travel time is the fuel squared over ten, or six times it beyond a jump",
          v[7] == want, f"system 8 at {d} tenths, fuel {v[8]}: {v[7]} against {want}")
    check('"3" again is the chart', v[9] == 0 and v[10] == 24, f"list {v[9]}, up went to {v[10]}")

    # 2. another galaxy's list: refused with the standard array, shown
    #    with the experimental one; and stepping the galaxy away from
    #    this one with the standard array drops back to the chart
    script = list(BOOT) + [poke_dev(t, "P_ADVNAV"), f"pokecpu {a['P_GALDRIVE']:o} 2"] + chart + \
        ["press 031", ui_ready(t, frames=1)] + toggle + peeks("CH_LIST", "CHART_GAL") + \
        [f"pokecpu {a['P_ADVNAV']:o} 1"] + toggle + peeks("CH_LIST") + \
        ["press 030", ui_ready(t, frames=1), poke_dev(t, "P_ADVNAV"), "press 031", ui_ready(t, frames=1)] + peeks("CH_LIST", "CHART_GAL") + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 5:
        check("another galaxy's list wants the experimental array",
              v[0] == 0 and v[1] == 1 and v[2] == 1, f"standard {v[0]} (galaxy {v[1]}), experimental {v[2]}")
        check("and stepping away from this galaxy with the standard array is the chart again",
              v[3] == 0 and v[4] == 1, f"list {v[3]}, galaxy {v[4]}")


def legend_contracts(rnd, mask, rate, gov, pop, fuel, navarray, price, dist, here):
    """Legend's genPlanetContracts (genContracts.a80) as src/ovl_ctgen.mac
    transliterates it: the twelve offers of a system from the record's
    random byte RND, the twelve availability bits MASK, the delivery
    rating's high byte RATE, this system's government and population,
    the tank (tenths), whether a navigation array is fitted, the
    station's prices (ST_PRICE) and DIST(planet) in tenths of a light
    year.  Its arithmetic is Legend's to the bit: the byte generator
    IntRnd_C with the bits shifting through it, the table multiply that
    loses min(a, b) on an odd sum, the sign-and-magnitude adds, the
    24-bit products with their middle taken, the odd third byte of a
    passenger's fee.  Returns twelve dicts; a missing offer has rate
    0x80 and only its type is meaningful."""
    st = dict(c=rnd & 0xFF, h=0x5A, l=0x31, mask=mask & 0xFFFF)

    def R():
        a = st["c"] + st["h"]
        c1 = a > 255
        a = (2 * (a & 255) + c1) & 255
        a = (a + (st["mask"] & 255)) & 255
        a2 = a + (st["mask"] >> 8)
        c4 = a2 > 255
        a = a2 & 255
        st["c"] = a
        a = (a + st["l"] + c4) & 255
        st["h"] = a
        st["l"] = st["c"]
        st["c"] = a
        return a

    def shift(cin):
        bit = st["mask"] & 1
        st["mask"] = (st["mask"] >> 1) | (0x8000 if cin else 0)
        return bit

    def mulq(a, c):
        return a * c - (min(a, c) if (a + c) & 1 else 0)

    def mul24(a, b):
        return (a * b) & 0xFFFFFF

    def hi16(v):
        return (v >> 8) & 0xFFFF

    def smadd(a, b):
        sa, sb, ma, mb = a & 0x8000, b & 0x8000, a & 0x7FFF, b & 0x7FFF
        if sa == sb:
            return sa | min(ma + mb, 0x7FFF)
        return (sa | (ma - mb)) if ma >= mb else (sb | (mb - ma))

    def smadd8(a, b):
        sa, sb, ma, mb = a & 0x80, b & 0x80, a & 0x7F, b & 0x7F
        if sa == sb:
            return sa | min(ma + mb, 127)
        return (sa | (ma - mb)) if ma >= mb else (sb | (mb - ma))

    def travel(d):
        if d <= fuel:
            return (d * d) // 10
        return 6 * d if navarray else 0

    rep7 = (rate >> 4) & 7
    neg = bool(rate & 0x80)
    rep = -rep7 if neg else rep7

    def fee_cargo(good, num, d):
        f = (-min((num >> 3) & 0xFF, 56)) & 0xFF
        if neg:
            if rate & 0x40:
                f <<= 1
            if rate & 0x20:
                f <<= 1
        pr = price[good]
        adv = mul24(num, hi16(mul24(f, pr)))
        per = (hi16(mul24(pr >> 2, (2 * d) & 0xFFFF)) + (7 - gov) * 8) & 0xFFFF
        return mul24(num, per), adv

    def fee_pkg(d):
        r = R()
        lo = hi16(mul24(0x2000 + r, d))
        c = 0
        if not neg:
            lo += hi16((d << (rep7 + 7)) & 0xFFFFFF)
            c += lo >> 16
            lo &= 0xFFFF
        lo += (7 - gov) << 8
        c += lo >> 16
        lo &= 0xFFFF
        return ((c & 0xFF) << 16) | lo, 0

    def fee_pass(d, t):
        term = (hi16((mul24(d, d) << 1) & 0xFFFFFF) << 2) & 0xFFFF
        if (t & 0xE0) == 0x60:
            term = (term << 1) & 0xFFFF
        r = R()
        term = (term + hi16(mul24(((256 + r) << 3) & 0xFFFF, d))) & 0xFFFF
        a = (7 - gov) * 4
        term = (term + ((a * a) << 4)) & 0xFFFF
        coef = sum(R() for _ in range(6)) >> 1
        q = hi16(mul24(coef, term))
        fee = ((1 if q & 0x8000 else 0) << 16) | q
        n = (((8 - rep) >> 1) + 1) >> 1
        return fee, fee >> n

    def skill(d):
        r1 = R()
        de = 0x8000 | ((2 * r1 + 256) & 0x7FFF)
        r2 = R()
        s1 = smadd(2 * r2, de)
        t = (s1 & 0x8000) | (((s1 & 0x7FFF) << 6) & 0x7FFF)
        s2 = smadd((d << 5) & 0xFFFF, t)
        if s2 & 0x8000:
            return 0, 1
        a = (s2 >> 8) & 0xFF
        return (0x70, 0) if a >= 0x70 else (a, 1)

    def numprod():
        for _ in range(4):
            good = (mulq(R(), 38) >> 8) & 0xFF
            if 13 <= good <= 15:
                if rate >= 0x80:
                    continue
                if rate >= 0x68:
                    break
                continue
            break
        else:
            return None, (0 if rate >= 0x80 else 1)
        while True:
            c2 = 1
            if 13 <= good <= 15:
                c = 11 if good == 15 else 6
                c2 = (((sum(mulq(R(), c) for _ in range(3))) >> 8) & 0xFF) + 1
            r1 = (R() & 0x1F) + 1
            r2 = (R() & 0x0F) + 1
            qty = (mulq(r2, r1) * c2) & 0xFFFF
            if qty > 19:
                break
        qty = min(qty, 750 if c2 == 1 else 960)
        if c2 == 1 and qty > 125:
            r = R()
            if r & 1:
                qty >>= 1
            if r & 2:
                qty >>= 1
        return (good, qty), None

    def none(cin, t):
        shift(cin)
        return dict(rate=0x80, type=t)

    def gen_one(kind):
        t = (R() & 0x3F) | kind
        if R() & 0x80:
            return none(1, t)
        pl = R()
        if pl == here:
            return none(0, t)
        d = dist(pl)
        tm = travel(d)
        r = R()
        if t & 0x80:
            within = (hi16(mul24(281 + r, tm)) + 40) & 0xFFFF
        else:
            x = smadd8(7 - gov, rep7 | (0x80 if neg else 0))
            prod = mulq(x & 0x7F, r) | (0x8000 if x & 0x80 else 0)
            s = smadd(prod, 256)
            if s & 0x8000:
                return none(1, t)
            within = (((s & 0x7FFF) & ~1) + tm) & 0xFFFF
        num = None
        if t & 0x80:
            fee, adv = fee_pkg(d)
        elif t & 0x40:
            fee, adv = fee_pass(d, t)
        else:
            got, cin = numprod()
            if got is None:
                return none(cin, t)
            t, num = got
            fee, adv = fee_cargo(t, num, d)
        sk, cin = skill(d) if t & 0xC0 else (0, 0)
        bit = shift(cin)
        return dict(rate=sk if bit else 0x80, planet=pl, adv=adv, fee=fee,
                    time=within, num=num, type=t)

    left = 12
    r = R()
    e = (r & 7) >> 1
    if r & 1:
        e = -e
    if pop >= 50:
        e += 1
    if pop < 30:
        e -= 1
    a = max(0, min(5, rep + e))
    out = []
    for _ in range(a):
        out.append(gen_one(0x80))
        left -= 1
    for _ in range(left >> 1):
        out.append(gen_one(0x40))
        left -= 1
    for _ in range(left):
        out.append(gen_one(0))
    return out


def contract_bytes(rec):
    """A contract as src/contract.mac lays it out (C.*): fourteen bytes."""
    rate, planet, adv, fee, time, num, typ = rec
    return [rate, planet, adv & 0xFF, (adv >> 8) & 0xFF, (adv >> 16) & 0xFF,
            (fee >> 16) & 0xFF, fee & 0xFF, (fee >> 8) & 0xFF,
            time & 0xFF, (time >> 8) & 0xFF, num & 0xFF, (num >> 8) & 0xFF, typ, 0]


def contract_of(b):
    """The inverse, from fourteen bytes to a dict."""
    return dict(rate=b[0], planet=b[1], adv=b[2] | b[3] << 8 | b[4] << 16,
                fee=b[6] | b[7] << 8 | b[5] << 16, time=b[8] | b[9] << 8,
                num=b[10] | b[11] << 8, type=b[12])


def check_carrier():
    """The carrier market: the twelve offers are Legend's number for
    number, a contract taken moves into the record with its deposit
    paid and its goods aboard, the log tears one up at a price, the
    docking settles what was delivered, a jump takes its time off the
    clock of every contract, the escape capsule and a new ship leave the
    passengers behind, and a galactic jump tears up every contract."""
    print("the carrier market")
    t = syms.table()
    need = ["PLANET_CT", "P_CONTRACT", "P_CONTRACTS", "P_DELIV", "P_RND", "ST_PRICE",
            "SYS_GOVT", "SYS_POP", "PFUEL", "CT_N", "CT_PAGE", "CT_UMSG", "CT_ROWS",
            "S_C_TAKEN", "S_C_REFUSED", "CASH_L", "P_CARGO", "P_FREECARGO", "NSCREENS",
            "CT_FRESH", "P_DOCKCOMP", "DOCKED", "P_ESCPOD", "SCREEN", "C.SIZE",
            "P_GALDRIVE", "GALNUM", "CASH_H", "P_YARD", "P_SHIP"]
    if any(n not in t for n in need):
        check("carrier symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    csize = a["C.SIZE"]
    menu = ["press 004", ui_ready(t)] * (a["NSCREENS"] - 1)     # the last screen
    fire, up, down, left, enter = (["press 107", ui_ready(t, frames=1)], ["press 154", ui_ready(t, frames=1)],
                                   ["press 134", ui_ready(t, frames=1)], ["press 116", ui_ready(t, frames=1)],
                                   ["press 153", ui_ready(t, frames=1)])

    def poke_bytes(addr, bs):
        return f"pokecpu {addr:o} " + " ".join(f"{b:o}" for b in bs)

    def peeks(*names):
        return [f"peekcpu {t[n]}" for n in names]

    # 1. the offers, against the model; then one of them crafted, taken,
    #    logged and torn up
    offers = ROOT / "tmp" / "verify-offers.bin"
    prices = ROOT / "tmp" / "verify-prices.bin"
    rows = ROOT / "tmp" / "verify-rows.bin"
    taken = ROOT / "tmp" / "verify-taken.bin"
    for f in (offers, prices, rows, taken):
        if f.exists():
            f.unlink()
    crafted = contract_bytes((0, 8, 100, 2000, 500, 5, 0))   # 5 t of food to system 8
    script = list(BOOT) + menu + peeks("P_RND", "P_DELIV", "SYS_GOVT", "SYS_POP", "PFUEL", "CT_N", "SCREEN") + \
        [f"dumpcpu {t['PLANET_CT']} {12 * csize} {offers}",
         f"dumpcpu {t['ST_PRICE']} 76 {prices}", f"dumpcpu {t['CT_ROWS']} 12 {rows}",
         poke_bytes(a["PLANET_CT"], crafted), poke_at(a["CASH_L"], 1000)] + left + \
        fire + up + fire + peeks("CASH_L", "P_CARGO", "P_FREECARGO", "P_CONTRACTS", "CT_UMSG", "PLANET_CT") + \
        [f"dumpcpu {t['P_CONTRACT']} {csize} {taken}"] + enter + peeks("CT_PAGE", "CT_N") + \
        fire + up + fire + peeks("CASH_L", "P_DELIV", "P_CONTRACT", "CT_UMSG", "CT_N") + ["quit"]
    out = run_emu(script)
    v = [int(x, 8) for x in PEEK.findall(out)]
    if len(v) < 19 or not offers.exists():
        check("the carrier market run answered", False, f"{len(v)} values")
        return
    rnd, rating, gov, pop, fuel, n, screen = v[:7]
    rnd = (rnd >> 8) if a["P_RND"] & 1 else rnd      # a byte, on its side of the word
    rnd &= 0xFF
    check("the carrier market is the last screen", screen == a["NSCREENS"] - 1, f"screen {screen}")
    price = list(struct_words(prices.read_bytes()[:76]))
    lave = galaxy_model(7)
    model = legend_contracts(rnd, 0xFFF, (rating >> 8) & 0xFF, gov, pop, fuel, False, price,
                             lambda pl: sys_distance(galaxy_model(pl), lave), 7)
    got = [contract_of(offers.read_bytes()[i * csize:(i + 1) * csize]) for i in range(12)]
    bad = []
    for i, (m, g) in enumerate(zip(model, got)):
        keys = ["rate", "type"] if m["rate"] == 0x80 else \
            [k for k in m if k != "num" or m["type"] < 0x40]
        if any(m[k] != g[k] for k in keys):
            bad.append((i, {k: m[k] for k in keys}, {k: g[k] for k in keys}))
    check("the twelve offers are Legend's, number for number", not bad,
          f"rnd {rnd}: {bad[:2]}" if bad else f"rnd {rnd}, {sum(m['rate'] != 0x80 for m in model)} offered")
    order = [i for k in (0, 0x40, 0x80) for i, m in enumerate(model)
             if m["rate"] != 0x80 and (m["type"] & 0xC0) == k]
    check("the list is cargo, then passengers, then parcels",
          n == len(order) and list(rows.read_bytes()[:len(order)]) == order,
          f"{n} rows {list(rows.read_bytes()[:12])} against {order}")
    cash, food, free, bits, msg, slot0, page, nlog = v[7:15]
    check("a contract taken: the deposit paid, the goods aboard, the offer gone",
          cash == 900 and food == 5 and free == 15 and bits == 0xFFE and msg == a["S_C_TAKEN"]
          and slot0 & 0xFF == 0x80,
          f"{cash} tenths, {food} t food, {free} free, bits {bits:o}, message {msg:o}, offer {slot0 & 0xFF:o}")
    check("and it is the pilot's, in this galaxy, as it was offered",
          list(taken.read_bytes()[:csize - 1]) == [0] + crafted[1:csize - 1], f"{list(taken.read_bytes()[:csize])}")
    check("ВВОД shows the log with it", page == 2 and nlog == 1, f"page {page}, {nlog} rows")
    cash, rating, slot, msg, nlog = v[15:20]
    check("torn up: the deposit is lost, the rating falls by its worth over 128",
          cash == 900 and rating == 0x8010 and slot & 0xFF == 0x80 and msg == a["S_C_REFUSED"] and nlog == 0,
          f"{cash} tenths, rating {rating:o}, slot {slot & 0xFF:o}, message {msg:o}, {nlog} rows")

    # 2. docking settles: cargo delivered in time pays and rates, a late
    #    passenger pays without rating, a parcel elsewhere waits
    slots = [contract_bytes((0, 7, 100, 2000, 300, 5, 0)),
             contract_bytes((0, 7, 50, 1000, 0, 1, 0x41)),
             contract_bytes((0, 8, 0, 500, 0, 0, 0x85))]
    script = list(BOOT) + [poke_bytes(a["P_CONTRACT"] + i * csize, b) for i, b in enumerate(slots)] + \
        [poke_at(a["P_CARGO"], 5), poke_at(a["P_FREECARGO"], 15), poke_dev(t, "P_DOCKCOMP"),
         "press 107", "run 50"] + ["press 166", "run 20"] * 4 + \
        ["run 700"] + peeks("DOCKED", "CASH_L", "P_CARGO", "P_FREECARGO", "P_DELIV", "P_CONTRACT") + \
        [f"peekcpu {a['P_CONTRACT'] + csize:o}", f"peekcpu {a['P_CONTRACT'] + 2 * csize:o}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("carrier")))]
    if len(v) >= 8:
        check("docked: the delivery pays its fee and returns the deposit, the goods leave the hold",
              v[0] == 1 and v[1] == 1000 + 100 + 2000 + 1000 and v[2] == 0 and v[3] == 20,
              f"docked {v[0]}, {v[1]} tenths, {v[2]} t food, {v[3]} free")
        check("in time it rates; late it only pays; elsewhere it waits",
              v[4] == 16 and v[5] & 0xFF == 0x80 and v[6] & 0xFF == 0x80 and v[7] & 0xFF == 0,
              f"rating {v[4]:o}, slots {v[5] & 0xFF:o} {v[6] & 0xFF:o} {v[7] & 0xFF:o}")

    # 3. a jump takes its time off the clock of every contract, and puts
    #    fresh offers on the table
    # (an intercepted jump makes no fresh offers: the roll is ruled out)
    script = list(BOOT) + [poke_bytes(a["P_CONTRACT"], contract_bytes((0, 7, 0, 500, 500, 0, 0x85))),
                           poke_at(int(t["WI_ODDS"], 8), 0), "press 004", ui_ready(t)] + up * 3 + ["press 107", ui_ready(t, frames=1)] + \
        peeks("PFUEL", "CT_FRESH", "P_CONTRACTS") + [f"peekcpu {a['P_CONTRACT'] + 8:o}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 4:
        spent = 70 - v[0]
        check("a jump takes its time off every contract, and the offers are made anew",
              v[3] == 500 - spent * spent // 10 and v[1] == 1 and v[2] == 0xFFFF,
              f"{spent} tenths of fuel, {v[3]} tenths of an hour left, fresh {v[1]}, bits {v[2]:o}")

    # 4. the escape capsule leaves the passengers behind: the advance
    #    goes back and the rating falls
    script = list(BOOT) + [poke_bytes(a["P_CONTRACT"], contract_bytes((0, 8, 50, 1000, 300, 1, 0x41))),
                           poke_bytes(a["P_CONTRACT"] + csize, contract_bytes((0, 8, 0, 500, 300, 0, 0x85))),
                           "press 107", ui_ready(t, frames=1), poke_dev(t, "P_ESCPOD"), "press 035", "run 60"] + \
        peeks("DOCKED", "CASH_L", "P_DELIV", "P_CONTRACT") + [f"peekcpu {a['P_CONTRACT'] + csize:o}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("carrier")))]
    if len(v) >= 5:
        check("the escape capsule leaves the passengers behind, with their advance",
              v[0] == 1 and v[1] == 950 and v[2] == 0x8008 and v[3] & 0xFF == 0x80 and v[4] & 0xFF == 0,
              f"docked {v[0]}, {v[1]} tenths, rating {v[2]:o}, slots {v[3] & 0xFF:o} {v[4] & 0xFF:o}")

    # 5. a galactic jump tears up every contract (JumpToGalaxy's
    #    RefuseAllContracts): the cargo's deposit is lost, the passenger's
    #    advance goes back, the parcel is simply gone, and the rating
    #    loses what each would have earned - (advance + fee) / 128, so
    #    11, 8 and 3 here
    three = [contract_bytes((0, 8, 1000, 500, 300, 5, 0)),
             contract_bytes((0, 8, 50, 1000, 300, 1, 0x41)),
             contract_bytes((0, 8, 0, 500, 300, 0, 0x85))]
    slots = [f"peekcpu {a['P_CONTRACT'] + i * csize:o}" for i in range(3)]
    script = list(BOOT) + [poke_bytes(a["P_CONTRACT"] + i * csize, b) for i, b in enumerate(three)] + \
        [poke_dev(t, "P_GALDRIVE"), "press 004", ui_ready(t), "press 107", "run 90"] + \
        peeks("GALNUM", "CASH_L", "CASH_H", "P_DELIV") + slots + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("carrier")))]
    check("a galactic jump tears up every contract, at what each costs",
          len(v) == 7 and v[0] == 1 and (v[2] << 16) + v[1] == 950 and v[3] == 0x8016
          and all(x & 0xFF == 0x80 for x in v[4:]),
          f"galaxy {v[:1]}, {(v[2] << 16) + v[1] if len(v) > 2 else '?'} tenths, "
          f"rating {v[3] if len(v) > 3 else 0:o}, slots {[x & 0xFF for x in v[4:]]}")

    # 6. a change of ship takes the cabins, and the passengers with them
    #    (YD_CHANGE's RefuseAllContracts, v1.09: the passengers only);
    #    the cargo contract stays
    two = [contract_bytes((0, 8, 1000, 500, 300, 5, 0)), contract_bytes((0, 8, 50, 1000, 300, 1, 0x41))]
    script = list(BOOT) + [poke_at(a["CASH_L"], 0), poke_at(int(t["CASH_H"], 8), 100),
                           f"pokecpu {int(t['P_YARD'], 8):o} 1"] + \
        [poke_bytes(a["P_CONTRACT"] + i * csize, b) for i, b in enumerate(two)] + \
        ["press 004", ui_ready(t)] * 6 + ["press 107", ui_ready(t, frames=1)] + \
        peeks("P_SHIP", "P_DELIV") + slots[:2] + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("carrier")))]
    check("a new ship leaves the passengers behind and keeps the cargo",
          len(v) == 4 and v[0] == 1 and v[1] == 0x8008 and v[2] & 0xFF == 0 and v[3] & 0xFF == 0x80,
          f"ship {v[:1]}, rating {v[1] if len(v) > 1 else 0:o}, slots {[x & 0xFF for x in v[2:]]}")


def struct_words(b):
    """Little-endian words out of a byte string."""
    for i in range(0, len(b) - 1, 2):
        yield b[i] | (b[i + 1] << 8)


def check_modes():
    """The advanced compass's modes and the scanner's."""
    print("the compass's modes and the scanner's")
    t = syms.table()
    need = ["CO_MODE", "CO_M", "CO_Z", "P_ADVCOMPASS", "SCAN_MODE", "SEGPREV", "SH_CANISTER", "PSPEED"]
    if any(n not in t for n in need):
        check("mode symbols found", False, f"missing {[n for n in need if n not in t]}")
        return
    a = {n: int(t[n], 8) for n in need}
    fly = list(BOOT) + ["press 107", "run 60"] + clear_traffic(t) + [poke_at(a["PSPEED"], 0)]
    mode = f"peekcpu {t['CO_MODE']}"

    # the compass: no mode without the device; mode 3 is the station,
    # poked behind; mode 4 the military base, which Lave has not
    script = fly + ["press 112", "run 5", mode, poke_dev(t, "P_ADVCOMPASS")] + \
        ["press 112", "run 5"] * 3 + [mode, poke_at(int(slot_field(t, 2, "U.Z"), 8), -5000), "run 3",
                                      f"peekcpu {t['CO_M']}", f"peekcpu {t['CO_Z']}", "press 112", "run 5",
                                      mode, f"peekcpu {t['CO_M']}", "quit"]
    v = [signed(int(x, 8)) for x in PEEK.findall(run_emu(script))]
    if len(v) >= 6:
        check("the compass has no modes without the advanced compass, and cycles them with it",
              v[0] == 0 and v[1] == 3, f"modes {v[0]} then {v[1]}")
        check("mode 3 points at the station, and mode 4 at nothing where there is no military base",
              v[2] == 5000 and v[3] == -5000 and v[4] == 4 and v[5] == 0,
              f"bearing {v[2]}/{v[3]}, then mode {v[4]} bearing {v[5]}")

    # the scanner: a canister in the cube; ships only draws fewer
    # segments, drops only fewer, and the blink is seen both ways
    can = [poke_at(int(slot_field(t, 5, f), 8), v) for f, v in
           (("U.TYPE", a["SH_CANISTER"]), ("U.FLAGS", 0), ("U.EXPL", 0), ("U.ENERGY", 10),
            ("U.SPEED", 0), ("U.X", 2000), ("U.Y", 0), ("U.Z", 3000))] + mind(t, 5, a["SH_CANISTER"])
    # (every count is taken with the rest of the sky emptied again: the
    # traffic keeps arriving, and on the faster renderer of 2026-09-26 a
    # ship turned up between the first count and the others)
    quiet = [poke_at(int(slot_field(t, k, "U.TYPE"), 8), 0)
             for k in range(3, int(t["NUNIV"], 8)) if k != 5]
    seg = f"peekcpu {t['SEGPREV']}"
    script = fly + can + quiet + ["run 6", seg] + (quiet + ["press 070", "run 6", seg]) * 2 + ["press 070"] + \
        (quiet + ["run 3", seg]) * 6 + quiet + ["press 070", "run 6", seg, f"peekcpu {t['SCAN_MODE']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("scanner")))]
    if len(v) >= 11:
        check("the scanner's modes leave the drops off the dish, then the ships",
              v[1] < v[0] and v[2] < v[0], f"segments {v[0]}, ships only {v[1]}, drops only {v[2]}")
        check("blink them, and come round to everything",
              min(v[3:9]) < v[0] <= max(v[3:9]) and v[9] == v[0] and v[10] == 0,
              f"blinking {v[3:9]}, round {v[9]} mode {v[10]}")


def check_find():
    """Naming a system on the chart instead of walking to it."""
    print("finding a system")
    t = syms.table()
    if any(n not in t for n in ("CURSYS", "FI_LEN", "FIND_BUF")):
        check("find symbols found", False)
        return

    def search(keys):
        script = BOOT + ["press 004", ui_ready(t), "press 153", "run 30"]
        for k in keys:
            script += [f"press {k}", "run 20"]
        script += ["press 153", "run 90", f"peekcpu {t['CURSYS']}", "quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("find")))]
        return v[0] if v else None

    # Т-И finds ТИТИОР and Л-А finds ЛАРЕРИ, which are systems 2 and 12 of
    # galaxy 1; Ж-Ж is not the start of any name in it.
    check("a name puts the cursor on the system", search([114, 73]) == 2,
          f"cursor {search([114, 73])}")
    check("and a different name on a different one", search([56, 72]) == 12,
          f"cursor {search([56, 72])}")
    check("a name that is nowhere leaves it alone", search([137, 137]) == 7,
          f"cursor {search([137, 137])}")


def check_ai():
    """What the ships have on their minds, as Legend has it (src/ai.mac)."""
    print("what the ships have on their minds")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "U.AI", "U.KIND", "U.TURN", "U.AI3", "U.TARGET", "U.MAT",
            "PENERGY", "PSHIELD_F", "WITCH", "AGGRESSOR", "UF_DERELICT", "UF_HOSTILE",
            "SH_KRAITH", "SH_VIPERH", "SH_COBRAMK3HT1", "SH_ESCAPEPODH", "SH_PYTHONHT",
            "AI_HYPER", "NUNIV", "PSPEED"]
    if any(n not in t for n in need):
        check("AI symbols found", False, f"missing {[n for n in need if n not in t]}")
        return
    a = {n: int(t[n], 8) for n in need}
    univ, usize = a["UNIV"], a["U.SIZE"]
    alive = [poke_at(a["PENERGY"], 255), poke_at(a["PSHIELD_F"], 255), poke_at(int(t["PSPEED"], 8), 0)]
    # a sky of their own: the traffic swept out and kept out (WITCH is
    # the switch that stops SPAWN_TICK), and the station's launches off
    quiet = clear_traffic(t) + [poke_at(a["WITCH"], 1)]

    def word(slot, name, off=0):
        return f"peekcpu {univ + slot * usize + int(t[name], 8) + off:o}"

    # 1. a hostile off to one side, facing away, rolls onto the plane,
    #    pitches round and puts its nose on you (OBJ_STEER): the
    #    cosine between its nose (column 2 of its matrix) and the line
    #    to you, before and after
    def nose_cos(v):
        px, py, pz = (signed(q) for q in v[0:3])
        m = [signed(q) for q in v[3:12]]
        d = (-px, -py, -pz)
        L = (px * px + py * py + pz * pz) ** 0.5 or 1
        return (m[2] * d[0] + m[5] * d[1] + m[8] * d[2]) / 16384 / L
    reads = [word(5, "U.X"), word(5, "U.Y"), word(5, "U.Z")] + [word(5, "U.MAT", 2 * i) for i in range(9)]
    # no station: near one a Krait is shy of you (F2_SHY) and turns away
    # on its reaction frames, and its nose hunts between the two
    script = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + quiet + [poke_at(int(slot_field(t, 2, "U.TYPE"), 8), 0)]
    script += ship_pokes(t, 5, "KRAITH", x=3000, z=3000, energy=4000)
    script += reads + alive + ["run 60"] + reads + alive + ["run 60"] + reads + ["quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("steer")))]
    if len(v) >= 36:
        c0, c1, c2 = nose_cos(v[0:12]), nose_cos(v[12:24]), nose_cos(v[24:36])
        check("a hostile facing away turns its nose onto you",
              c0 < 0 and c2 > 0.8, f"cos {c0:+.2f} -> {c1:+.2f} -> {c2:+.2f}")

    # 2. a pirate with the police in the sky goes for them first
    #    (SetNewTargetObj's list: bit 4 before you), at its counter's
    #    end - 10 is slot 9 plus one, which is how a target is named
    script = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + quiet
    script += ship_pokes(t, 8, "KRAITH", z=6000, energy=200)
    script += ship_pokes(t, 9, "VIPERH", x=400, z=6400, hostile=False, energy=200)
    for _ in range(8):
        script += alive + ["run 20", word(8, "U.TARGET")]
    script.append("quit")
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("prey")))]
    check("a pirate goes for the police before it goes for you", 10 in v, f"targets {v}")

    # 3. a trader with a full hull and nobody to fight stays peaceful and,
    #    with the station in the sky, heads home to it now and then
    #    (MoveAllObjects' goto662: one odd frame in two its container
    #    target is the station's slot+1, which is 3 here)
    script = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + quiet
    script += ship_pokes(t, 5, "PYTHONHT", x=800, z=4000, hostile=False, speed=10, hyper=False)
    for _ in range(8):
        script += alive + [ui_ready(t, frames=1), word(5, "U.LAUNCH"), word(5, "U.FLAGS")]
    script.append("quit")
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("trader")))]
    if len(v) >= 16:
        check("a peaceful trader stays peaceful and heads for the station",
              not any(f & 1 for f in v[1::2]) and 3 in [w >> 8 for w in v[0::2]],
              f"flags {[oct(f) for f in v[1::2]]}, home {[w >> 8 for w in v[0::2]]}")

    # 4. under an eighth of its energy a ship with a capsule fires it and
    #    drifts (ReactionObject's critical band): a Cobra at 10 of 150,
    #    a capsule in the sky - briefly: Legend's capsule header has the
    #    hyperspace bit without the fighting one, which is MoveAllObjects'
    #    "leaving" state, and it is gone in four frames - and UF_DERELICT
    #    on the Cobra after.  The station goes too, or its anger at a
    #    hostile trader scrambles Vipers into the sky under test.
    script = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + quiet + [poke_at(int(slot_field(t, 2, "U.TYPE"), 8), 0)]
    script += ship_pokes(t, 5, "COBRAMK3HT1", x=600, z=3000, energy=10, hostile=False, hyper=False)
    script += alive
    for _ in range(60):                 # the capsule lands in the first free
        script += ["run 1", word(2, "U.TYPE")]   # slot, the station's
    script += ["run 60", word(5, "U.FLAGS"), word(2, "U.TYPE"), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("pod")))]
    if len(v) >= 62:
        check("a ship near death fires its capsule, which leaves, and is nobody's after",
              a["SH_ESCAPEPODH"] in v[:60] and v[60] & a["UF_DERELICT"] and v[61] == 0,
              f"capsule seen {a['SH_ESCAPEPODH'] in v[:60]}, flags {v[60]:o}, slot 2 after {v[61]}")

    # 5. a ship with nothing to do but leave, leaves: AI_HYPER alone and a
    #    counter of one is eight frames of hyperspace and an empty slot
    script = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + quiet
    script += ship_pokes(t, 5, "PYTHONHT", x=800, z=4000, hostile=False)
    script += [poke_at(int(slot_field(t, 5, "U.AI"), 8), (1 << 8) | a["AI_HYPER"]),
               alive[0], "run 8", word(5, "U.TYPE"), word(5, "U.AI"), ui_ready(t, frames=12), word(5, "U.TYPE"), "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("hyper")))]
    if len(v) >= 3:
        check("a ship with nothing to keep it leaves by hyperspace",
              v[2] == 0, f"type {v[0]} (AI {v[1] & 0xFF:o}) then {v[2]}")

    # 6. shooting a trader makes it hostile and you an aggressor
    #    (FireLaser's goto603): the anger, and the record of it
    script = list(BOOT) + ["press 107", ui_ready(t, frames=2)] + quiet
    script += ship_pokes(t, 5, "COBRAMK3HT1", z=700, hostile=False, energy=4000)
    script += [f"peekcpu {t['AGGRESSOR']}", "keydown 107", "run 30", "keyup 107", "run 4",
               word(5, "U.FLAGS"), f"peekcpu {t['AGGRESSOR']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("anger")))]
    if len(v) >= 3:
        check("a trader that is shot at turns on you, and you are an aggressor",
              v[0] == 0 and v[1] & 1 and v[2] == 1, f"aggressor {v[0]} -> {v[2]}, flags {v[1]:o}")


def check_hulls():
    """The hull bank and the set a system gets from it (src/hull.mac).

    The 55 Legend hulls live in the video planes above the screen and
    are copied into HULL_BASE..HULL_END per system.  Lave gets a Coriolis
    and the core set the 1985 rules name; three rows up the chart is a
    tech 11 world, which gets a Dodo and loses the Coriolis; and every
    loaded record is the bank's own bytes, which is the whole disk ->
    planes -> RAM path proved at once.
    """
    print("hulls: the bank, and what a system gets from it")
    import ships_gen
    t = syms.table()
    core = ["SH_CORIOLIS", "SH_MISSILE", "SH_CANISTER", "SH_ALLOY",
            "SH_ESCAPEPOD", "SH_SPLINTER", "SH_ASTEROID", "SH_HERMIT",
            "SH_VIPER", "SH_COBRA3", "SH_COBRA3P", "SH_PYTHON", "SH_PYTHONP",
            "SH_ASP", "SH_FERDELANCE", "SH_THARGOID", "SH_THARGON",
            "SH_SIDEWINDER", "SH_KRAIT"]
    need = ["SHIP_TABLE", "NSHIPS", "HULL_BASE", "HULL_END", "HULL_FILL",
            "STATION_TYPE", "SH_CORIOLISH", "SH_DODOH", "SH_SHIPGENH",
            "UNIV", "U.SIZE", "NUNIV", "U.FLAGS", "SYS_TECH"] + core
    if any(n not in t for n in need):
        check("hull symbols found", False,
              f"{[n for n in need if n not in t][:4]}")
        return
    # the generator's reading of Legend's cargo byte, against the market
    goods = (ROOT / "src/res/legend/market/goods.txt").read_text(encoding="utf-8")
    labels = [l.split()[1] for l in goods.splitlines()
              if l.strip() and not l.startswith("#")]
    ships = shiplib.read_dir(ROOT / "src/res/legend/ships")
    byk = {x.key: x for x in ships}
    loot = {"ESCAPEPODH": "SLAVES", "ALLOYS1H": "ALLOYS", "MINERALSH": "MINERALS"}
    got = {k: labels[(ships_gen.cargo_1985(byk[k].cargo) >> 4) + 1] for k in loot}
    check("Legend's cargo byte lands each drop on its market item",
          got == loot, f"{got}")

    n = int(t["NSHIPS"], 8)
    base, end = int(t["HULL_BASE"], 8), int(t["HULL_END"], 8)
    usize, nuniv = int(t["U.SIZE"], 8), int(t["NUNIV"], 8)
    uflags = int(t["U.FLAGS"], 8)
    dumps = [ROOT / "tmp" / f"verify-hulls-{k}.bin"
             for k in ("table", "area", "univ", "table2", "univ2")]
    dumps[0].parent.mkdir(exist_ok=True)
    script = BOOT + [
        "press 107", "run 100",                      # launched, at Lave
        f"dumpcpu {t['SHIP_TABLE']} {n * 2} {dumps[0]}",
        f"dump 1 {t['HBANK_ADDR']} 6806 {dumps[1]}",
        f"dump 2 {t['HBANK_ADDR']} 6806 {dumps[1]}.hi",
        f"dumpcpu {t['UNIV']} {usize * nuniv} {dumps[2]}",
        f"peekcpu {t['STATION_TYPE']}", f"peekcpu {t['HULL_FILL']}",
        f"peekcpu {t['SYS_TECH']}",
        "press 004", ui_ready(t),                       # the chart, three rows
        "press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1),  # up, and jump
        "press 154", ui_ready(t, frames=1), "press 107", ui_ready(t, frames=1),
        f"dumpcpu {t['SHIP_TABLE']} {n * 2} {dumps[3]}",
        f"dumpcpu {t['UNIV']} {usize * nuniv} {dumps[4]}",
        f"peekcpu {t['STATION_TYPE']}", f"peekcpu {t['SYS_TECH']}", "quit"]
    vals = [int(v, 8) for v in PEEK.findall(run_emu(script))]
    if len(vals) < 5 or not all(d.exists() for d in dumps):
        check("the hull tables were dumped", False)
        return
    import struct
    station, fill, tech, station2, tech2 = vals
    table = [struct.unpack_from("<H", dumps[0].read_bytes(), i * 2)[0]
             for i in range(n)]
    table2 = [struct.unpack_from("<H", dumps[3].read_bytes(), i * 2)[0]
              for i in range(n)]
    area = bytearray(13612)
    area[0::2] = dumps[1].read_bytes()
    area[1::2] = Path(str(dumps[1])+".hi").read_bytes()

    def addr(tab, name):
        return tab[int(t[name], 8) - 1]

    check("Lave, tech 5, gets a Coriolis",
          tech + 1 <= 8 and station == int(t["SH_CORIOLISH"], 8),
          f"tech {tech + 1}, station type {station}")
    missing = [k for k in core if not addr(table, k)]
    check("the core set the 1985 rules name is loaded", not missing,
          f"{missing}" if missing else f"{len(core)} types")
    loaded = sum(1 for a in table if a)
    check("and the extras fill the area to its end",
          loaded > len(core) and 0 < fill <= 5120 and 5120 - fill < 512,
          f"{loaded} of {n} types, {5120 - fill} bytes left in roster budget")
    check("a hull the rules never ask for stays on the disk",
          addr(table, "SH_SHIPGENH") == 0 and addr(table, "SH_DODOH") == 0,
          f"generation ship at {addr(table, 'SH_SHIPGENH')}, "
          f"Dodo at {addr(table, 'SH_DODOH')}")
    check("a pirate that borrows a trader's hull shares the record",
          addr(table, "SH_COBRA3P") == addr(table, "SH_COBRA3") != 0,
          f"{addr(table, 'SH_COBRA3P'):o} / {addr(table, 'SH_COBRA3'):o}")
    bad = []
    for i, s_ in enumerate(ships):
        if not table[i]:
            continue
        rec = ships_gen.record_bytes(shiplib.hull_of(s_, ships))
        off = (table[i] - int(t["HBANK_ADDR"], 8))*2
        if area[off:off + len(rec)] != rec:
            bad.append(s_.key)
    check("every loaded record is the bank's, byte for byte", not bad,
          f"{bad[:3]}" if bad else f"{loaded} records")

    def station_slot(dump):
        d = dump.read_bytes()
        for i in range(nuniv):
            ty = struct.unpack_from("<H", d, i * usize)[0]
            if ty and struct.unpack_from("<H", d, i * usize + uflags)[0] & 2:
                return ty
        return 0

    check("the station in the sky is the kind that was chosen",
          station_slot(dumps[2]) == station, f"{station_slot(dumps[2])}")
    check("three rows up is a tech 11 world, and it gets a Dodo",
          tech2 + 1 == 11 and station2 == int(t["SH_DODOH"], 8),
          f"tech {tech2 + 1}, station type {station2}")
    check("with the Coriolis gone and the core set kept",
          addr(table2, "SH_CORIOLISH") == 0 and addr(table2, "SH_DODOH") != 0
          and all(addr(table2, k) for k in core if k != "SH_CORIOLIS"),
          f"Coriolis at {addr(table2, 'SH_CORIOLISH')}, Dodo at "
          f"{addr(table2, 'SH_DODOH'):o}")
    check("and the Dodo is the station in that sky",
          station_slot(dumps[4]) == station2, f"{station_slot(dumps[4])}")



def steady_drive(t):
    """Suppress interception for a check of arrival, using the game's
    existing galactic/portal no-roll gate.  A seed is not stable across
    tunnel animation changes: the tunnel consumes random values too."""
    return [poke_at(int(t["HYP_NOROLL"], 8), 1)]


def check_bases():
    """The bases besides the station (src/bases.mac): which ones a system
    has, by Legend's rules; docking at one and launching from it; and
    the ring, which is flown through for a fare."""
    print("bases: the service station, the military base, the ring")
    t = syms.table()
    need = ["UNIV", "U.SIZE", "NUNIV", "U.FLAGS", "U.MAT", "PSPEED", "DOCKED",
            "DOCKED_AT", "SYS_BASES", "SYS_GOVT", "SYS_TECH", "CASH_L",
            "SH_FUELSTH", "SH_RINGH", "SH_MILITARYST2H", "UF_BASE",
            "SB_FUEL", "SB_RING", "SB_MILITARY", "BK_FUEL", "RING_FARE"]
    if any(n not in t for n in need):
        check("base symbols found", False, f"{[n for n in need if n not in t][:4]}")
        return
    usize, nuniv = int(t["U.SIZE"], 8), int(t["NUNIV"], 8)
    univ, uflags = int(t["UNIV"], 8), int(t["U.FLAGS"], 8)
    ufbase = int(t["UF_BASE"], 8)
    q1 = 16384

    import struct

    def slots(dump):
        """(type, flags, z) per occupied slot."""
        d = dump.read_bytes()
        out = []
        for i in range(nuniv):
            ty = struct.unpack_from("<H", d, i * usize)[0]
            if ty:
                out.append((ty, struct.unpack_from("<H", d, i * usize + uflags)[0],
                            struct.unpack_from("<h", d, i * usize + 6)[0]))
        return out

    def bases(dump):
        return sorted(ty for ty, fl, _z in slots(dump) if fl & ufbase)

    def identity(slot):
        return [poke_at(univ + slot * usize + int(t["U.MAT"], 8) + 2 * k,
                        q1 if k in (0, 4, 8) else 0) for k in range(9)]

    dumps = [ROOT / "tmp" / f"verify-bases-{k}.bin" for k in ("lave", "up", "launch", "ring")]
    dumps[0].parent.mkdir(exist_ok=True)
    jump = ["press 004", ui_ready(t), "press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1),
            "press 154", ui_ready(t, frames=1)] + steady_drive(t) + ["press 107", ui_ready(t, frames=1)]
    # Lave, then three rows up; the service station is slot 5 at Lave
    # (the first slot the 1985 layout leaves) and is poked dead ahead,
    # level and slow, which is the docking test; a launch follows
    fuel = 5
    to_up = BOOT + ["press 107", "run 100",
                     f"dumpcpu {t['UNIV']} {usize * nuniv} {dumps[0]}",
                     f"peekcpu {t['SYS_BASES']}", f"peekcpu {t['SYS_GOVT']}",
                     f"peekcpu {t['SYS_TECH']}",
                     poke_at(int(t["PSPEED"], 8), 0),
                     poke_at(int(slot_field(t, fuel, "U.X"), 8), 0),
                     poke_at(int(slot_field(t, fuel, "U.Y"), 8), 0),
                     poke_at(int(slot_field(t, fuel, "U.Z"), 8), 600)] + identity(fuel) + [
                     f"waitcpu {t['DOCKED']} 1 2000", ui_ready(t, frames=1), f"peekcpu {t['DOCKED']}", f"peekcpu {t['DOCKED_AT']}",
                     "press 107", ui_ready(t, frames=2),
                     f"dumpcpu {t['UNIV']} {usize * nuniv} {dumps[2]}",
                     f"peekcpu {t['DOCKED_AT']}"] + jump
    script = to_up + [f"dumpcpu {t['UNIV']} {usize * nuniv} {dumps[1]}",
                     f"peekcpu {t['SYS_BASES']}", f"peekcpu {t['SYS_GOVT']}",
                     f"peekcpu {t['SYS_TECH']}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("bases")))]
    if len(v) < 9 or not all(d.exists() for d in dumps[:3]):
        check("the bases run answered", False)
        return
    lave_b, lave_g, lave_t, docked, at, at2, up_b, up_g, up_t = v
    fuelst = int(t["SH_FUELSTH"], 8)
    ringh = int(t["SH_RINGH"], 8)
    milst = int(t["SH_MILITARYST2H"], 8)
    check("Lave, dictatorship of tech 5, gets a service station and nothing else",
          lave_b == int(t["SB_FUEL"], 8) and bases(dumps[0]) == [fuelst],
          f"government {lave_g}, tech {lave_t + 1}, bases {lave_b:o}, in the sky {bases(dumps[0])}")
    check("docking at it is docking, and the bay is remembered",
          docked == 1 and at == int(t["BK_FUEL"], 8), f"docked {docked}, at {at}")
    after = [(ty, z) for ty, fl, z in slots(dumps[2]) if fl & ufbase]
    check("and a launch puts THAT bay ahead, the station further off",
          at2 == 0 and after and after[0][0] == fuelst and 5000 < after[0][1] < 6100
          and any(fl & 2 and z > 20000 for _ty, fl, z in slots(dumps[2])),
          f"docked_at {at2}, bases {after}")
    check("three rows up, corporate state of tech 11: a ring, a military base, a service station",
          up_b == int(t["SB_RING"], 8) | int(t["SB_MILITARY"], 8) | int(t["SB_FUEL"], 8)
          and bases(dumps[1]) == sorted([fuelst, ringh, milst]),
          f"government {up_g}, tech {up_t + 1}, bases {up_b:o}, in the sky {bases(dumps[1])}")

    # the ring: through it with the fare, and the sky is laid out again.
    # The approach is the first run's, dock and all: a launch straight
    # into the jump leaves the generator where a misjump comes up, and
    # witchspace has no ring.  Which slot the ring lands in depends on
    # the traffic already there when the sky is laid out, so it is read
    # off the first run's dump of that sky, not assumed
    ring = [i for i in range(nuniv)
            if struct.unpack_from("<H", dumps[1].read_bytes(), i * usize)[0] == ringh]
    if not ring:
        check("the ring is in the sky three rows up", False)
        return
    ring = ring[0]
    # and nothing else about: the ships the system rolls on arrival move
    # with the random state, which moves with every disk read the boot
    # makes or saves (the overlay cache, 2026-09-25, put a ship there
    # that shot the commander dead in the ring's mouth) - so the traffic
    # goes, and the bases and the station stay
    calm = [poke_at(int(slot_field(t, i, "U.TYPE"), 8), 0)
            for i, (ty, fl, _z) in enumerate(
                (struct.unpack_from("<H", dumps[1].read_bytes(), k * usize)[0],
                 struct.unpack_from("<H", dumps[1].read_bytes(), k * usize + uflags)[0], 0)
                for k in range(nuniv))
            if i >= 3 and ty and not fl & ufbase]
    script = to_up + calm + [
                     poke_at(int(t["CASH_L"], 8), 5000),
                     poke_at(int(slot_field(t, ring, "U.X"), 8), 0),
                     poke_at(int(slot_field(t, ring, "U.Y"), 8), 0),
                     poke_at(int(slot_field(t, ring, "U.Z"), 8), 650)] + identity(ring) + [
                     "run 200", f"peekcpu {t['CASH_L']}", f"peekcpu {t['DOCKED']}",
                     f"dumpcpu {t['UNIV']} {usize * nuniv} {dumps[3]}", "quit"]
    v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("bases")))]
    if len(v) < 2 or not dumps[3].exists():
        check("the ring run answered", False)
        return
    rings = [z for ty, fl, z in slots(dumps[3]) if ty == ringh]
    cash, docked = v[-2], v[-1]          # the approach carries peeks of its own
    check("the ring takes the fare and puts you back at the orbit",
          cash == 5000 - int(t["RING_FARE"], 8) and docked == 0
          and rings and -5000 < rings[0] < -2000,
          f"{cash} tenths left, docked {docked}, ring at z {rings}")

    # and turned away (GoJumpRing): the law's high byte, or a purse short
    # of the fare, and nothing is taken and nothing moves - once a pass,
    # so the till is not charged again on the frames still inside
    # The ship is stopped in the ring's mouth: refused, it would fly on
    # into the ring's hull and die of it, and this passed only while the
    # frames were too slow to get there inside the 200 ticks
    for what, legal, purse in (("an outlaw", 300, 5000), ("a short purse", 0, 1000)):
        script = to_up + calm + [
                         poke_at(int(t["PSPEED"], 8), 0),
                         poke_at(int(t["CASH_L"], 8), purse),
                         poke_at(int(t["LEGAL"], 8), legal),
                         poke_at(int(slot_field(t, ring, "U.X"), 8), 0),
                         poke_at(int(slot_field(t, ring, "U.Y"), 8), 0),
                         poke_at(int(slot_field(t, ring, "U.Z"), 8), 650)] + identity(ring) + [
                         "run 200", f"peekcpu {t['CASH_L']}",
                         f"dumpcpu {t['UNIV']} {usize * nuniv} {dumps[3]}", "quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("bases")))]
        rings = [z for ty, fl, z in slots(dumps[3]) if ty == ringh] if dumps[3].exists() else []
        check(f"{what} is turned away at the ring, and the sky stays",
              v and v[-1] == purse and rings and rings[0] > -2000,
              f"{v[-1] if v else None} tenths, ring at z {rings}")



def check_turrets():
    """А turns the laser turrets (RotateLasers, the pause menu's): two
    swap front and rear, four move every gun one mount round, and fewer
    move nothing."""
    print("turrets")
    t = syms.table()
    need = ["P_LASERS", "CKV_TURRETS"]
    if any(n not in t for n in need):
        check("turret symbols found", False)
        return
    las, tur = int(t["P_LASERS"], 8), int(t["CKV_TURRETS"], 8)
    got = []
    for n in (4, 2, 1):
        script = BOOT + ["press 107", "run 100", poke_at(tur, n)] + [
            poke_at(las + 2 * k, v) for k, v in enumerate((1, 2, 3, 4))] + [
            "press 072", "run 20"] + [f"peekcpu {las + 2 * k:o}" for k in range(4)] + ["quit"]
        got.append([int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("turrets")))][-4:])
    check("four turrets: the left gun to the front, front to right, right to rear, rear to left",
          got[0] == [3, 4, 2, 1], f"{got[0]}")
    check("two: front and rear change places", got[1] == [2, 1, 3, 4], f"{got[1]}")
    check("one: nothing moves", got[2] == [1, 2, 3, 4], f"{got[2]}")


def check_pause():
    """The pause menu (src/ovl_pause.mac, Cmd_PauseInGame): АР2 stops the
    game and the clock, the letters flip Legend's options, ПРОБЕЛ goes
    on; and what each option does - the launch prompt, the sound, the
    stick's inversion both ways, inertia and steady turn, the auto-ECM's
    and the auto-eject's arming, the Targons' interception
    of every jump, docking with the slot not level, and Q's new game."""
    print("the pause menu")
    t = syms.table()
    need = ["OPTIONS", "OVL_CUR", "OVL_PAUSE", "FLY_TICK", "DOCKED", "PROLL",
            "SX_QH", "WITCH", "P_SEC", "TI_TICK", "OPT_DEFAULT", "PSPEED",
            "ALIGN_SHOW", "PPITCH", "P_AUTOECM", "P_AUTOPOD", "AUTOECM_ARMED"]
    if any(n not in t for n in need):
        check("pause symbols found", False,
              f"missing {[n for n in need if n not in t]}")
        return
    o = int(t["OPTIONS"], 8)
    opt = lambda v: poke_at(o, v)
    run = lambda sc: [int(x, 8) for x in PEEK.findall(run_emu(sc, fresh_disk("pause")))]
    clock = [peek_byte(t, "P_SEC")]
    sec = lambda w: byte_of(t, "P_SEC", w)

    # 1. the menu: the game stands, the clock with it, letters flip bits
    v = run(BOOT + clock + ["press 006", "run 100", f"peekcpu {t['OVL_CUR']}",
            f"peekcpu {t['FLY_TICK']}", "run 300", f"peekcpu {t['FLY_TICK']}",
            "press 070", "run 20", f"peekcpu {t['OPTIONS']}",
            "press 055", "run 20", f"peekcpu {t['OPTIONS']}",
            "press 113", ui_ready(t, frames=1)] + clock + [f"peekcpu {t['FLY_TICK']}",
            # 2. U asks before the launch: Т no, then Ф launches and stops asking
            "press 107", "run 60", f"peekcpu {t['DOCKED']}",
            "press 114", "run 60", f"peekcpu {t['DOCKED']}",
            "press 107", "run 60", f"peekcpu {t['SX_QH']}", "press 047", "run 20",
            f"peekcpu {t['DOCKED']}", f"peekcpu {t['OPTIONS']}",
            f"peekcpu {t['SX_QH']}", "quit"])
    if len(v) < 14:
        check("the pause run answered", False, f"{len(v)} peeks")
        return
    check("АР2 brings up the pause menu", v[1] == int(t["OVL_PAUSE"], 8), f"overlay {v[1]}")
    check("and the game stands still under it", v[3] == v[2], f"{v[2]} -> {v[3]} frames")
    check("Ы turns the sound off, Г the launch prompt on",
          v[4] & 1 == 0 and v[5] & 0o200, f"{v[4]:o}, {v[5]:o}")
    check("ПРОБЕЛ goes on with the game", v[7] > v[3], f"{v[3]} -> {v[7]} frames")
    check("and the clock did not run while it stood",
          (sec(v[6]) - sec(v[0])) % 50 <= 6, f"seconds {sec(v[0])} -> {sec(v[6])}, "
          "and 16 stood still")
    check("ФИКС asks before launching, and Т says no",
          v[8] == 1 and v[9] == 1, f"docked {v[8]}, {v[9]}")
    check("Ф launches and stops asking", v[11] == 0 and not v[12] & 0o200,
          f"docked {v[11]}, options {v[12]:o}")
    check("with the sound off the launch asks for no sound", v[13] == v[10],
          f"requests {v[10]} -> {v[13]}")

    # 3. the stick: inverted, steady, and inertial or not
    p = int(t["PROLL"], 8)
    v = run(BOOT + ["press 107", "run 100",
            opt(0o2), poke_at(p, 0), "keydown 116", "run 10", f"peekcpu {t['PROLL']}", "keyup 116",
            "run 3",                  # the release reaches the key word a tick late
            opt(0o20), poke_at(p, 5), "run 20", f"peekcpu {t['PROLL']}",
            opt(0), poke_at(p, 5), ui_ready(t, frames=6), f"peekcpu {t['PROLL']}",
            opt(0), poke_at(p, 8), "keydown 116", "run 6", f"peekcpu {t['PROLL']}", "keyup 116",
            "run 30", opt(0o10), poke_at(p, 8), "keydown 116", "run 6", f"peekcpu {t['PROLL']}",
            "keyup 116", "quit"])
    if len(v) >= 5:
        v = [signed(x) for x in v]
        check("B inverts the stick: ← rolls right", v[0] > 0, f"roll {v[0]}")
        check("D keeps a turn when the stick is let go", v[1] == 5, f"roll {v[1]}")
        check("and without it the stick springs back", v[2] == 0, f"roll {v[2]}")
        check("an opposite key stops a turn dead", v[3] <= 0, f"roll {v[3]}")
        check("R makes it slow the turn instead", 0 < v[4] < 8, f"roll {v[4]}")
    else:
        check("the stick run answered", False, f"{len(v)} peeks")

    # 3b. Y turns the pitch over as B turns the roll; and У and З, Legend's
    #     E and P, arm the auto-ECM and the auto-eject - bit 5 of their own
    #     device bytes, flipped whether the device is fitted or not
    q = int(t["PPITCH"], 8)
    v = run(BOOT + ["press 107", "run 100",
            opt(0), poke_at(q, 0), "keydown 154", "run 10", f"peekcpu {t['PPITCH']}", "keyup 154", "run 30",
            opt(0o4), poke_at(q, 0), "keydown 154", "run 10", f"peekcpu {t['PPITCH']}", "keyup 154", "run 3",
            peek_byte(t, "P_AUTOECM"), peek_byte(t, "P_AUTOPOD"),
            "press 006", "run 100", "press 051", "run 20", "press 157", "run 20", "press 113", ui_ready(t, frames=1),
            peek_byte(t, "P_AUTOECM"), peek_byte(t, "P_AUTOPOD"), "quit"])
    if len(v) >= 6:
        up, flipped = signed(v[0]), signed(v[1])
        armed = int(t["AUTOECM_ARMED"], 8)
        before = (byte_of(t, "P_AUTOECM", v[2]), byte_of(t, "P_AUTOPOD", v[3]))
        after = (byte_of(t, "P_AUTOECM", v[4]), byte_of(t, "P_AUTOPOD", v[5]))
        # (the sign, not the size: how far the stick has got in ten
        # ticks depends on how many frames fit into them)
        check("Y turns the pitch over", up != 0 and flipped != 0 and (up < 0) != (flipped < 0),
              f"pitch {up}, then {flipped}")
        check("E and P flip the auto-ECM's and the auto-eject's arming bit",
              all((b ^ a_) == armed for b, a_ in zip(before, after)),
              f"{before[0]:o} -> {after[0]:o}, {before[1]:o} -> {after[1]:o}")
    else:
        check("the Y/E/P run answered", False, f"{len(v)} peeks")

    # 4. F: the Targons stop every jump
    v = run(BOOT + ["press 107", "run 100", opt(0o41),
            "press 004", ui_ready(t), "press 154", ui_ready(t, frames=1), "press 154", ui_ready(t, frames=1),
            "press 154", ui_ready(t, frames=1), "press 107", ui_ready(t, frames=1), f"peekcpu {t['WITCH']}", "quit"])
    check("F: every jump is intercepted", v[-1:] == [1], f"witch {v}")

    # 5. C: docking with the slot across, the station poked dead ahead
    #    and rolled a quarter turn
    univ, usize = int(t["UNIV"], 8), int(t["U.SIZE"], 8)
    mat = univ + 2 * usize + int(t["U.MAT"], 8)
    rolled = [poke_at(mat + 2 * k, w) for k, w in
              enumerate((0, 0o177777 - 16383, 0, 16384, 0, 0, 0, 0, 16384))]
    park = ["press 107", "run 100"] + clear_traffic(t) + [
        poke_at(int(t["PSPEED"], 8), 0), poke_at(int(t["PROLL"], 8), 0),
        poke_at(int(slot_field(t, 2, "U.X"), 8), 0),
        poke_at(int(slot_field(t, 2, "U.Y"), 8), 0),
        poke_at(int(slot_field(t, 2, "U.Z"), 8), 600),
        poke_at(int(slot_field(t, 2, "U.SPEED"), 8), 0)] + rolled
    # (the refusal is ALIGN_SHOW, the warning's countdown, at once; a
    # docking is DOCKED after the tunnel has run)
    v = run(BOOT + park + [opt(1), "run 12", f"peekcpu {t['ALIGN_SHOW']}",
                           f"peekcpu {t['DOCKED']}", "quit"])
    check("the slot across the way turns you back", len(v) == 2 and v[0] > 0 and v[1] == 0,
          f"warning {v[:1]}, docked {v[1:]}")
    v = run(BOOT + park + [opt(0o101), "run 150", f"peekcpu {t['DOCKED']}", "quit"])
    check("C lets you in all the same", v[-1:] == [1], f"docked {v}")

    # 6. Q: a new game, from the title
    v = run(BOOT + ["press 006", "run 100", "press 027", "run 200",
            f"peekcpu {t['OVL_CUR']}", f"peekcpu {t['TI_TICK']}", "quit"])
    check("Q starts the game again from the title",
          len(v) >= 2 and v[0] == int(t["OVL_TITLE"], 8) and v[1] > 0,
          f"overlay {v[:1]}, title frames {v[1:2]}")


def check_sound():
    """Legend's sound (2026-09-26): its effects engine on the PPU
    (src/ppu_sfx.mac), fed by the CPU's queue (src/sound.mac), playing
    Legend's own effects (src/res/legend/sfx.txt) on the first AY chip,
    the tune on the second.  The effects are Legend's byte for byte; the
    boot hands the engine to the PPU; a request lands in its channel's
    slot for its priority and plays out; the laser is its gun's sound;
    the ECM's goes round until the field ends; the sound switched off
    asks for nothing; and it is heard."""
    print("sound")
    r = subprocess.run([sys.executable, "tools/sfx_gen.py", "--check"],
                       cwd=ROOT, capture_output=True, text=True)
    check("Legend's 26 effects, byte for byte", r.returncode == 0, r.stdout.strip())
    t = syms.table()
    need = ["SX_HOOK", "PP_START", "L2372$", "OVL_DIR", "OVL_N", "OVL_SFX", "OVL_BASE",
            "SX_SEQ", "SX_QH", "OPTIONS", "ECM_TIME", "P_LASERS"]
    if any(n not in t for n in need):
        check("sound symbols found", False, f"missing {[n for n in need if n not in t][:4]}")
        return
    a = {n: int(t[n], 8) for n in need}
    PEEKW = re.compile(r"peekw 0 [0-7]+ = ([0-7]+)")
    oc_sfx = a["OVL_DIR"] + 2 * a["OVL_N"] + 2 * a["OVL_SFX"]
    seq = a["SX_SEQ"] - a["OVL_BASE"]            # the slots, from the image's start

    # 1. the hook: where the PPU calls is where the cache keeps the engine
    v = [int(x, 8) for x in PEEK.findall(run_emu(list(BOOT) + [
        f"peekcpu {t['L2372$']}", f"peekcpu {oc_sfx:o}", "quit"]))]
    if len(v) < 2:
        check("the sound run answered", False)
        return
    block, eng = v
    hook = block + a["SX_HOOK"] - a["PP_START"]
    w = [int(x, 8) for x in PEEKW.findall(run_emu(list(BOOT) + [f"peekw 0 {hook:o}", "quit"]))]
    check("the boot hands the engine to the PPU", eng and w == [eng], f"hook {w}, engine {eng:o}")

    def slot(ch, pr):
        return f"peekw 0 {eng + seq + 4 * (ch * 8 + pr):o}"

    # 2. the launch (B, 7) plays and ends; the laser (B, 6) is the gun's;
    #    the ECM (B, 6) goes round until the field ends, then the empty one
    las = int(t["P_LASERS"], 8)
    ecm = [poke_dev(t, "P_ECM")] if "P_ECM" in t else []
    # Native file reads defer sound ticks; observe the launch throughout
    # its loading window instead of assuming it is active on tick 20.
    launch_samples = 100
    script = list(BOOT) + ecm + ["press 107"] + ["run 1", slot(1, 7)] * launch_samples
    script += ["run 170", slot(1, 7),
                                 f"peekcpu {las:o}", "keydown 107", "run 6", slot(1, 6),
                                 "keyup 107", "run 60", slot(1, 6),
                                 "press 031", "run 4", slot(1, 6), f"peekcpu {t['ECM_TIME']}",
                                 poke_at(a["ECM_TIME"], 100), "run 10", slot(1, 6),
                                 f"peekcpu {t['ECM_TIME']}", poke_at(a["ECM_TIME"], 1),
                                 "run 100", slot(1, 6),
                                 "quit"]
    out = run_emu(script, fresh_disk("sound"))
    w = [int(x, 8) for x in PEEKW.findall(out)]
    c = [int(x, 8) for x in PEEK.findall(out)]
    w = [max(w[:launch_samples], default=0)] + w[launch_samples:]
    if len(w) >= 7 and c:
        check("the launch is heard and ends", w[0] != 0 and w[1] == 0, f"{w[0]:o} -> {w[1]:o}")
        # the laser's slot points into its effect: past SX_TAB, and the
        # effect of the gun's type (the front mount's)
        check("the trigger plays the gun's own sound, and it ends",
              w[2] > eng and w[3] == 0, f"{w[2]:o} -> {w[3]:o}, gun {c[0] & 7}")
        # Hold the field beyond the effect's thirteen ticks to prove the
        # loop, then end it. Natural twelve-frame duration is checked by
        # check_ecm; assuming it outlasts fourteen ticks depends on fps.
        check("the ECM's sound goes round while its field lasts, and stops",
              w[4] != 0 and w[5] != 0 and w[6] == 0 and len(c) >= 3 and c[2] > 0,
              f"{[oct(x) for x in w[4:7]]}, field {c[1:3]}")

    # 3. the sound off: nothing is asked for; on, the fight is heard
    def fight(on):
        wav = ROOT / "tmp" / f"verify-sound-{on}.wav"
        if wav.exists():
            wav.unlink()
        script = list(BOOT) + ["press 107", "run 250", poke_at(a["OPTIONS"], on),
                               f"peekcpu {t['SX_QH']}", "wavstart", "keydown 107", "run 60",
                               "keyup 107", f"peekcpu {t['SX_QH']}", f"wavstop {wav}", "quit"]
        v = [int(x, 8) for x in PEEK.findall(run_emu(script, fresh_disk("sound")))]
        r = subprocess.run([sys.executable, "tools/wav_analyze.py", str(wav)],
                           cwd=ROOT, capture_output=True, text=True)
        m = re.search(r"(\d+)/(\d+) active", r.stdout)
        return v, int(m.group(1)) if m else -1
    von, hon = fight(1)
    voff, hoff = fight(0)
    if len(von) >= 2 and len(voff) >= 2:
        check("with the sound on the laser is heard", von[1] > von[0] and hon > 20,
              f"{von[1] - von[0]} requests, {hon} active windows")
        check("and off it asks for nothing and nothing is heard", voff[1] == voff[0] and hoff == 0,
              f"{voff[1] - voff[0]} requests, {hoff} active windows")


def check_keyfile():
    """The key file (tools/keyfile.py, KEY_INIT): the build's sector is
    src/res/setup.txt's, and a disk given another one boots with its keys
    and its options."""
    print("the key file")
    t = syms.table()
    need = ["OPTIONS", "VIEW_DIR", "KEYS_LBA"]
    if any(n not in t for n in need):
        check("key file symbols found", False)
        return
    lba = int(t["KEYS_LBA"], 8)
    ref = ROOT / "tmp" / "verify-keys.bin"
    ref.parent.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "tools/keyfile.py", "src/res/setup.txt",
                    "--bin", str(ref)], cwd=ROOT, check=True)
    from rt11fs import Volume
    dat = Volume(DSK).find("ELITE.DAT")
    sec = DSK.read_bytes()[(dat.block+lba)*512:(dat.block+lba+1)*512]
    check("the disk's key file is src/res/setup.txt's", sec == ref.read_bytes())
    # a player's own: the views on Ж instead of 1, no sound, every jump
    # intercepted
    mine = ROOT / "tmp" / "verify-setup.txt"
    text = (ROOT / "src/res/setup.txt").read_text(encoding="utf-8")
    text = re.sub(r"^VIEW\s*=.*$", "VIEW = Ж", text, flags=re.M)
    text = re.sub(r"^SOUND\s*=.*$", "SOUND = 0", text, flags=re.M)
    text = re.sub(r"^INTERCEPT\s*=.*$", "INTERCEPT = 1", text, flags=re.M)
    mine.write_text(text, encoding="utf-8")
    disk = fresh_disk("keyfile")
    r = subprocess.run([sys.executable, "tools/keyfile.py", str(mine), "--disk", str(disk)],
                       cwd=ROOT, capture_output=True, text=True)
    check("keyfile.py writes a disk's key file", r.returncode == 0,
          "" if r.returncode == 0 else r.stderr.strip()[-200:])
    v = [int(x, 8) for x in PEEK.findall(run_emu(BOOT + [
        f"peekcpu {t['OPTIONS']}", "press 107", "run 100",
        "press 030", "run 20", f"peekcpu {t['VIEW_DIR']}",
        "press 137", "run 20", f"peekcpu {t['VIEW_DIR']}", "quit"], disk))]
    if len(v) < 3:
        check("the key file run answered", False, f"{len(v)} peeks")
        return
    check("its options are the game's at boot", v[0] & 0o377 == 0o40, f"{v[0]:o}")
    check("1 no longer turns the view", v[1] == 0, f"view {v[1]}")
    check("and Ж does", v[2] == 1, f"view {v[2]}")


def check_rt11():
    import verify_rt11
    verify_rt11.check_rt11(sys.modules[__name__])


def check_rules():
    import verify_rules
    verify_rules.check_rules(sys.modules[__name__])


def check_completion():
    import verify_completion
    verify_completion.check_completion(sys.modules[__name__])


# The emulator groups, in the order they run.  Named so that one of them
# can be run on its own: the whole suite drives the emulator dozens of
# times and takes minutes, which is too long a wait to put between one
# change and the next.
GROUPS = [
    ("rt11", "check_rt11"), ("emulator", "check_emulator"), ("combat", "check_combat_and_sound"),
    ("hyperspace", "check_hyperspace"), ("station", "check_station_and_trade"),
    ("missiles", "check_missiles"), ("dockcomp", "check_dockcomp"),
    ("culling", "check_culling"), ("cargo", "check_cargo"),
    ("escorts", "check_escorts"), ("sun", "check_sun"),
    ("views", "check_views"), ("kit", "check_kit"),
    ("collisions", "check_collisions"), ("missions", "check_missions"),
    ("missions2", "check_missions2"), ("missions3", "check_missions3"),
    ("missions4", "check_missions4"), ("missions5", "check_missions5"),
    ("missions6", "check_missions6"), ("missions7", "check_missions7"),
    ("missions8", "check_missions8"), ("missions9", "check_missions9"),
    ("ppu", "check_ppu_room"), ("presentation", "check_presentation"),
    ("palette", "check_palette"), ("splash", "check_splash"), ("title", "check_title"), ("cockpit", "check_cockpit"),
    ("law", "check_law"), ("chart", "check_chart"),
    ("commanders", "check_commanders"), ("planets", "check_planets"),
    ("worlds", "check_worlds"),
    ("witchspace", "check_witchspace"), ("saving", "check_saving"),
    ("compass", "check_compass"), ("manifest", "check_manifest"),
    ("market", "check_market"),
    ("traffic", "check_traffic"), ("equip", "check_equip"), ("yard", "check_yard"),
    ("access", "check_access"), ("cockpitblock", "check_cockpit_block"), ("energy", "check_energy"), ("lasers", "check_lasers"), ("damage", "check_damage"), ("ecm", "check_ecm"), ("cloak", "check_cloak"),
    ("jdrive", "check_jdrive"), ("bombs", "check_bombs"), ("autotake", "check_autotake"),
    ("drone", "check_drone"), ("modes", "check_modes"),
    ("find", "check_find"), ("ai", "check_ai"), ("galaxies", "check_galaxies"),
    ("list", "check_list"),
    ("hulls", "check_hulls"), ("bases", "check_bases"), ("carrier", "check_carrier"),
    ("turrets", "check_turrets"), ("pause", "check_pause"), ("docking", "check_docking"),
    ("keyfile", "check_keyfile"), ("sound", "check_sound"),
    ("completion", "check_completion"), ("rules", "check_rules"),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--skip-emu", action="store_true")
    ap.add_argument("--only", metavar="GROUP",
                    help="run one emulator group: "
                         + ", ".join(name for name, _ in GROUPS))
    args = ap.parse_args(argv)
    if args.only:
        names = dict(GROUPS)
        if args.only not in names:
            sys.exit(f"error: no group {args.only!r}; try one of "
                     + ", ".join(names))
        keep_pristine()
        before = CHECK_COUNT
        if args.only == "emulator":
            check_emulator(check_galaxy())  # it compares Lave with the model
        else:
            globals()[names[args.only]]()
        if CHECK_COUNT == before:
            check(f"{args.only} executed assertions", False)
        print()
        if FAILS:
            print(f"{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
            return 1
        print(f"all {CHECK_COUNT} checks passed")
        return 0
    syms.check_fresh()
    if (ROOT / "orig/ELITE.SCL").exists():
        check_resources()
    else:
        # the 1985 disk left the tree when Elite Legend became the source
        # (2026-09-10); its resources stay checked in and the checks that
        # need the image to compare against are skipped, not failed
        print("resources round-trip: skipped, orig/ELITE.SCL is not here")
    check_legend_resources()
    lave = check_galaxy()
    if not args.skip_emu:
        keep_pristine()
        for name, function in GROUPS:
            before = CHECK_COUNT
            if name == "emulator":
                check_emulator(lave)
            else:
                globals()[function]()
            if CHECK_COUNT == before:
                check(f"{name} executed assertions", False)
    print()
    if FAILS:
        print(f"{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print(f"all {CHECK_COUNT} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
