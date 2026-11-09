#!/usr/bin/env python3
"""mission_text.py - Elite Legend's mission screens -> a text bank on disk.

    python3 tools/mission_text.py src/res/legend/text/menu_MissionsMsg.txt \
        --out build/mistext.mac [--force]

Reads the extracted MissionsMsg.a80 (tools/legend_text.py) and writes two
files beside --out:

  mistext.bin  the bank: every message 0-terminated, back to back, laid
               on the disk at MTEXT_LBA0 (src/defs.mac) by build_elite.py;
  mistext.mac  MT_<NAME> = its byte offset in the bank, a word table
               MT_<NAME>_T for a message with variants (FindMessage's
               consecutive strings), and MTEXT_SECTORS - assembled into
               the mission overlay (src/ovl_mission.mac), which reads a
               message's sectors when it prints one.

The text is KOI-7 (src/text.mac's font), upper case, with Legend's
control bytes (Main/PrintTxt.a80) turned into the port's:

  1 x y   nSetCrdXY: the cursor to Legend's column x, row y
  2       nPlanetOccup: the mission's system name (MS_NAME)
  3       the two digits of a galaxy number (Msg_InfoMiss62g's "00")
  4       nPause24I: a pause
  0       the end

Legend's case flags (nFlgPrn*) are dropped - the font has no lower
case - and its sub-messages #B0..#BB are written out in place, nested
ones included.  "(Y/N)" becomes "(Д/Н)", the keys the overlay reads.
Two messages Legend patches at run time are split into their cases:
Msg_ShipBoard with #B0 or #B1 (ПИРАТАМИ / ТАРГОНАМИ) is MT_BOARDP and
MT_BOARDT, and Msg_InfoMiss62 runs on into Msg_InfoMiss62g, whose "00"
is the galaxy.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_gen import to_koi7                       # noqa: E402

WINDOW = 1024           # the overlay reads the two sectors from the one
                        # a message starts in: one that would run past
                        # them starts on the next sector instead


def parse(path):
    """-> {label: [text of +0, +1, ...]} in file order."""
    out = {}
    order = []
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line or line.startswith("#") or "|" not in line:
            continue
        lab, text = line.split("|", 1)
        m = re.fullmatch(r"(\w+)\+(\d+)", lab.strip())
        if not m:
            continue
        name, n = m.group(1), int(m.group(2))
        if name not in out:
            out[name] = []
            order.append(name)
        assert len(out[name]) == n, (name, n)
        out[name].append(text)
    return out, order


def encode(text, msgs, label, depth=0):
    """Legend's marked-up text -> port bytes (no terminator)."""
    out = []
    pos = 0
    for m in re.finditer(r"\{([^}]*)\}", text):
        lit = text[pos:m.start()]
        pos = m.end()
        out += to_koi7(lit.replace("(Y/N)", "(Д/Н)"), label)
        code = m.group(1)
        if code.startswith("nSetCrdXY"):
            _, x, y = code.split(",")
            out += [1, int(x), int(y)]
        elif code == "nPlanetOccup":
            out.append(2)
        elif code == "nPause24I":
            out.append(4)
        elif code.startswith("nFlgPrn"):
            pass
        elif code.startswith("#B"):
            n = int(code[2:], 16)
            sub = {0: "Msg_Pirates", 1: "Msg_Targons"}.get(n, f"msgMission_B{n:X}")
            out += encode(msgs[sub][0], msgs, label, depth + 1)
        elif code.startswith("'") and code.endswith("'"):
            out += to_koi7(code[1:-1], label)
        else:
            raise SystemExit(f"{label}: control {code!r} not understood")
    out += to_koi7(text[pos:].replace("(Y/N)", "(Д/Н)"), label)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if os.path.exists(args.out) and not args.force:
        sys.exit(f"error: {args.out} exists (use --force)")
    msgs, order = parse(args.source)

    # what goes in the bank: (MT name, [bytes of each variant])
    items = []
    skip = {"AdrMsgMissions", "Msg_Pirates", "Msg_Targons", "Msg_ShipBoard",
            "Msg_ShipBoardn", "Msg_InfoMiss62", "Msg_InfoMiss62g"}
    board = msgs["Msg_ShipBoard"][0] + msgs["Msg_ShipBoardn"][0]
    items.append(("BOARDP", [encode(board, msgs, "BOARDP")]))
    items.append(("BOARDT", [encode(board.replace("{#B0}", "{#B1}", 1), msgs, "BOARDT")]))
    m62 = msgs["Msg_InfoMiss62"][0] + msgs["Msg_InfoMiss62g"][0]
    assert "ГАЛАКТИКЕ 00 " in m62
    enc = encode(m62.replace("ГАЛАКТИКЕ 00 ", "ГАЛАКТИКЕ @ "), msgs, "INFOMISS62")
    enc = [3 if b == ord("@") else b for b in enc]
    items.append(("INFOMISS62", [enc]))
    for name in order:
        if name in skip or name.startswith("msgMission_"):
            continue
        mt = re.sub(r"^Msg_", "", name).upper()
        items.append((mt, [encode(t, msgs, mt) for t in msgs[name]]))

    bank = bytearray()
    lines = [f"; generated by tools/mission_text.py from {args.source} -"
             " do not edit", ""]
    for mt, variants in items:
        offs = []
        for v in variants:
            if len(v) + 1 > WINDOW:
                sys.exit(f"error: {mt} is {len(v) + 1} bytes, over {WINDOW}")
            if len(bank) % 512 + len(v) + 1 > WINDOW:
                bank += bytes(512 - len(bank) % 512)
            offs.append(len(bank))
            bank += bytes(v) + b"\0"
        lines.append(f"MT_{mt} = {offs[0]:o}")
        if len(offs) > 1:
            lines.append(f"MT_{mt}_T:\t.WORD\t" + ", ".join(f"{o:o}" for o in offs))
    sectors = (len(bank) + 511) // 512
    bank += bytes(sectors * 512 - len(bank))
    lines += ["", f"MTEXT_SECTORS = {sectors:o}\t; {len(bank)} bytes", ""]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    with open(os.path.join(os.path.dirname(args.out), "mistext.bin"), "wb") as fh:
        fh.write(bank)
    print(f"wrote {args.out}: {len(items)} messages, {sectors} sectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
