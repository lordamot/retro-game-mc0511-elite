#!/usr/bin/env python3
"""keyfile.py - the key file: src/res/setup.txt into the PPU's key tables.

    python3 tools/keyfile.py src/res/setup.txt --out build/keytab.mac \\
        --bin build/keys.bin [--force]           # what the build runs
    python3 tools/keyfile.py MY.txt --disk build/elite.dsk
                                                 # new keys onto a disk
    python3 tools/keyfile.py MY.txt --check      # what goes where, and
                                                 #   which rows are shared
    python3 tools/keyfile.py --names             # the keys it knows

Legend reads a setup.ini at load (INCLUDE/Loader/SetUpINI.a80); this
port reads one sector, KEYS_LBA, at boot (KEY_INIT, src/input.mac).  The
sector is the PPU's four key tables exactly as src/ppu.mac walks them -
KEYON_CODES, KEYOFF_CODES, KEYON2_CODES, KEYOFF2_CODES, (code, bits)
pairs each ending on bits of 0, every table padded to a fixed size so
that they sit at fixed places - then a magic word and the options'
defaults.  KEY_INIT copies the tables into the PPU's copy of its program
over the ones the build assembled, which are the same file's (keytab.mac),
so a disk without the sector still has the keys the build was made with.

A make code is the scancode; a release is 0200 | the matrix ROW (the low
four bits), so an OFF table is by row, and a release clears every bit of
its row (KEYBOARD.md, docs/platform.md).
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# command -> (key word 0 or 1, bit): K_* and KB_* in src/defs.mac
COMMANDS = {
    "ROLL_LEFT": (0, 0o1), "ROLL_RIGHT": (0, 0o2),
    "PITCH_UP": (0, 0o4), "PITCH_DOWN": (0, 0o10),
    "FIRE": (0, 0o20), "ENTER": (0, 0o40), "STOP": (0, 0o100),
    "PAUSE": (0, 0o200), "THROTTLE": (0, 0o400), "MISSILE": (0, 0o1000),
    "VIEW": (0, 0o2000), "ECM": (0, 0o4000), "BOMB": (0, 0o10000),
    "POD": (0, 0o20000), "MISSKIND": (0, 0o40000), "CLOAK": (0, 0o100000),
    "JDRIVE": (1, 0o1), "COMPASS": (1, 0o2), "SCANNER": (1, 0o4),
    "TURRET": (1, 0o10),
}
# the ones a finger stays on: a key sharing a row with one of these lets
# it go when it is released
HELD = {"ROLL_LEFT", "ROLL_RIGHT", "PITCH_UP", "PITCH_DOWN", "FIRE",
        "JDRIVE"}

# option -> OPT_* bit (src/defs.mac)
OPTIONS = {
    "SOUND": 0o1, "INVERT": 0o2, "INVERT_UD": 0o4, "INERTIA": 0o10,
    "STEADY_TURN": 0o20, "INTERCEPT": 0o40, "EASY_DOCK": 0o100,
    "LAUNCH_CONFIRM": 0o200,
}

# the keys by name: KEYBOARD.md's table (tools/keymap.py's sweep)
KEYS = {
    "←": 0o116, "→": 0o133, "↑": 0o154, "↓": 0o134,
    "ФИКС": 0o107, "ВВОД": 0o153, "ДОП.ВВОД": 0o166, "СТОП": 0o4,
    "АР2": 0o6, "ПРОБЕЛ": 0o113, "ЗАБОЙ": 0o132,
    "1": 0o30, "2": 0o31, "3": 0o32, "4": 0o13, "5": 0o34, "6": 0o35,
    "7": 0o16, "8": 0o17, "9": 0o177, "0": 0o176,
    "Й": 0o27, "Ц": 0o50, "У": 0o51, "К": 0o52, "Е": 0o33, "Н": 0o54,
    "Г": 0o55, "Ш": 0o36, "Щ": 0o37, "З": 0o157, "Х": 0o156, "Ъ": 0o155,
    "Ф": 0o47, "Ы": 0o70, "В": 0o71, "А": 0o72, "П": 0o53, "Р": 0o74,
    "О": 0o75, "Л": 0o56, "Д": 0o57, "Ж": 0o137, "Э": 0o136,
    "Я": 0o67, "Ч": 0o110, "С": 0o111, "М": 0o112, "И": 0o73,
    "Т": 0o114, "Ь": 0o115, "Б": 0o76, "Ю": 0o77,
}
ALIASES = {"LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓",
           "SPACE": "ПРОБЕЛ", "ТАБ": "АР2"}

# fixed table sizes, in (code, bits) pairs WITH the terminator: the
# PPU's program has exactly this much room for each (src/ppu_keys.mac)
CAP = (21, 15, 9, 9)          # KEYON, KEYOFF, KEYON2, KEYOFF2
TABLE_WORDS = 2 * sum(CAP)
MAGIC = 0o153125              # "the sector is a key file"


def key_code(name, where):
    k = ALIASES.get(name.upper(), name)
    if k in KEYS:
        return KEYS[k]
    if k.upper() in KEYS:
        return KEYS[k.upper()]
    if re.fullmatch(r"0[0-7]+", k):
        v = int(k, 8)
        if 0 < v < 0o200:
            return v
    sys.exit(f"error: {where}: no key called {name!r} "
             "(keyfile.py --names lists them)")


def parse(path):
    """-> ({command: [codes]}, options word)."""
    binds, opts = {}, 0
    seen = set()
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8")
                            .splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        where = f"{path}:{n}"
        name, eq, value = line.partition("=")
        name, value = name.strip().upper(), value.split()
        if not eq or not value:
            sys.exit(f"error: {where}: expected NAME = VALUE")
        if name in seen:
            sys.exit(f"error: {where}: {name} given twice")
        seen.add(name)
        if name in COMMANDS:
            binds[name] = [key_code(v, where) for v in value]
        elif name in OPTIONS:
            if value[0] not in ("0", "1") or len(value) > 1:
                sys.exit(f"error: {where}: {name} is 0 or 1")
            if value[0] == "1":
                opts |= OPTIONS[name]
        else:
            sys.exit(f"error: {where}: no command or option {name!r}")
    return binds, opts


def tables(binds):
    """The four tables as lists of (code, bits) pairs, without the ends."""
    on = [{}, {}]
    off = [{}, {}]
    for cmd, codes in binds.items():
        w, bit = COMMANDS[cmd]
        for c in codes:
            on[w][c] = on[w].get(c, 0) | bit
            off[w][c & 0o17] = off[w].get(c & 0o17, 0) | bit
    out = [sorted(on[0].items()), sorted(off[0].items()),
           sorted(on[1].items()), sorted(off[1].items())]
    names = ("KEYON_CODES", "KEYOFF_CODES", "KEYON2_CODES", "KEYOFF2_CODES")
    for t, cap, nm in zip(out, CAP, names):
        if len(t) + 1 > cap:
            sys.exit(f"error: {nm} would hold {len(t)} entries and has "
                     f"room for {cap - 1}")
    return out


def words(tabs):
    """The four tables, padded, as TABLE_WORDS words."""
    w = []
    for t, cap in zip(tabs, CAP):
        body = [x for pair in t for x in pair]
        w += body + [0] * (2 * cap - len(body))
    assert len(w) == TABLE_WORDS
    return w


def sector(tabs, opts):
    w = words(tabs) + [MAGIC, opts]
    b = bytearray(512)
    for i, v in enumerate(w):
        b[2 * i:2 * i + 2] = v.to_bytes(2, "little")
    return bytes(b)


def macro(tabs, opts, src):
    names = ("KEYON_CODES", "KEYOFF_CODES", "KEYON2_CODES", "KEYOFF2_CODES")
    lines = [f"; the PPU's key tables, from {src} by tools/keyfile.py -",
             "; generated, do not edit.  (code, bits) pairs, each table",
             "; ending on bits of 0 and padded to a fixed size: KEY_INIT",
             "; (src/input.mac) copies the key file's over them at boot.",
             f"KEYTAB_WORDS = {TABLE_WORDS}.",
             f"KEYS_MAGIC = {MAGIC:o}",
             f"OPT_DEFAULT = {opts:o}",
             "KEYTAB:"]
    for t, cap, nm in zip(tabs, CAP, names):
        lines.append(f"{nm}:")
        for code, bits in t:
            lines.append(f"\t\t.WORD\t{code:o},{bits:o}")
        pad = 2 * (cap - len(t))      # zeros, written out: the ends
        while pad:                    #   must be there in the image
            n = min(pad, 8)
            lines.append("\t\t.WORD\t" + ",".join(["0"] * n))
            pad -= n
    return "\n".join(lines) + "\n"


def report(binds, tabs):
    """What goes where, and the rows a held key shares."""
    rev = {}
    for cmd, codes in binds.items():
        for c in codes:
            rev.setdefault(c, []).append(cmd)
    knames = {v: k for k, v in KEYS.items()}
    warn = []
    rows = {}
    for c, cmds in rev.items():
        rows.setdefault(c & 0o17, []).append((c, cmds))
        if len(cmds) > 1:
            warn.append(f"{knames.get(c, f'{c:o}')} does {', '.join(cmds)}")
    for row, keys in sorted(rows.items()):
        held = [c for c, cmds in keys if HELD & set(cmds)]
        if held and len(held) < len(keys):    # ↑ and ↓ together are one
                                              #   axis, not a trap
            desc = "; ".join(f"{knames.get(c, f'{c:o}')} {'/'.join(cmds)}"
                             for c, cmds in keys)
            warn.append(f"row {row:02o} is shared with a held key: {desc}")
    for cmd in COMMANDS:
        if cmd not in binds:
            warn.append(f"{cmd} has no key")
    return warn, rev, knames


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("setup", nargs="?", default="src/res/setup.txt")
    ap.add_argument("--out", help="the PPU tables as MACRO-11")
    ap.add_argument("--bin", help="the key file's sector")
    ap.add_argument("--disk", help="write the sector onto this .dsk")
    ap.add_argument("--check", action="store_true",
                    help="list the keys and the shared rows")
    ap.add_argument("--names", action="store_true",
                    help="list the key names")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    if a.names:
        for k, v in sorted(KEYS.items(), key=lambda kv: kv[1]):
            print(f"{v:04o}  {k}")
        print("aliases: " + ", ".join(f"{k}={v}" for k, v in ALIASES.items()))
        return 0

    binds, opts = parse(ROOT / a.setup if not Path(a.setup).is_absolute()
                        else a.setup)
    tabs = tables(binds)
    sec = sector(tabs, opts)

    if a.out:
        out = Path(a.out)
        if out.exists() and not a.force:
            sys.exit(f"error: {out} exists (use --force)")
        out.write_text(macro(tabs, opts, a.setup))
    if a.bin:
        Path(a.bin).write_bytes(sec)
    if a.check or a.disk:
        warn, rev, knames = report(binds, tabs)
        if a.check:
            for c in sorted(rev):
                print(f"{c:04o} row {c & 0o17:02o}  "
                      f"{knames.get(c, '?'):10} {', '.join(rev[c])}")
            print(f"options: {opts:03o} = " + (", ".join(
                n for n, b in OPTIONS.items() if opts & b) or "none"))
        for w in warn:
            print(f"warning: {w}", file=sys.stderr)
    if a.disk:
        from rt11fs import Volume
        disk = Path(a.disk)
        volume = Volume(disk)
        data = volume.find('ELITE.DAT')
        if data is None or data.length < 3:
            sys.exit('error: ELITE.DAT not found or truncated')
        # Version 1 DAT: header block 0, overlay directory 1, keys 2.
        if bytes(volume.img[data.block*512:data.block*512+9]) != b'ELITE11\0\1':
            sys.exit('error: incompatible ELITE.DAT')
        offset = (data.block+2)*512
        volume.img[offset:offset+512] = sec
        pending = disk.with_suffix(disk.suffix+'.new')
        volume.save(pending)
        pending.replace(disk)
        print(f'wrote the key file in {disk}:ELITE.DAT')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
