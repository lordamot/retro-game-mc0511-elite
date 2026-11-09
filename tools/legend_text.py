#!/usr/bin/env python3
"""legend_text.py - Elite Legend's Russian text -> src/res/legend/text/.

    python3 tools/legend_text.py [--out src/res/legend/text] [--force]

Every message file under `INCLUDE/Menu/Messages`, `INCLUDE/Menu/*Msg.a80`
and `INCLUDE/Engine/Messages` is read with `IFDEF Russian` taken and
the English branch dropped, and each 0-terminated message becomes one
line:

    LABEL[+n]|text with {CODE arg,arg} for the control bytes

where LABEL is the source label the message block starts at and n its
number within the block (Legend finds a message by counting zero bytes
from the block's label - FindMessage in PrintTxt.a80 - so the number is
what the game's code passes).  Control codes are the names PrintTxt.a80
gives them (nSetCrdXY, nFlgPrn_1xx, ...) with their argument bytes;
codes without a name are {#nn}.  A byte that is neither text nor a
known code is kept as {#nn} too, so nothing is lost on the way through.

The port's screens are redesigned, not copied, so the coordinates in
these codes are a record of where Legend put things, not instructions;
the words are what matter.  `make verify` checks the files back
against the sources.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from legend_ships import number, split_args   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "orig/legend/EliteLegend_v1_09_source/INCLUDE"
OUT = ROOT / "src/res/legend/text"

# how many argument bytes each control code carries, from
# AdrCtrlProcMessage's handlers in PrintTxt.a80 (0 where the handler
# reads none)
CODES = {
    0x01: ("nFlgPrn_xx1", 0), 0x02: ("nFlgPrn_2xx", 0), 0x03: ("nPrnGalNum", 0),
    0x04: ("nPlanetDest", 0), 0x05: ("nPrnPlanetPresent", 0), 0x06: ("nFlgPrn_1xx", 0),
    0x07: ("nPrnPilotName", 0), 0x08: ("nFlgPrn0xx", 0), 0x09: ("nClearDescrMsg", 0),
    0x0A: ("nPrnRndPairChr", 0), 0x0B: ("nPrnPlDestCase", 0), 0x0C: ("nCloseDescrMsg", 0),
    0x0D: ("nPause24I", 0), 0x0E: ("nSetAdrMsg", 2),
    0x10: ("nSetCrdXY", 2), 0x11: ("nSetCrdX", 1), 0x12: ("nNamePackage", 0),
    0x13: ("nNamePassenger", 0), 0x14: ("nTravelTime", 0), 0x15: ("nNameGoods", 0),
    0x16: ("nSetPixCrdY", 1), 0x17: ("nSetZnkCrd", 0), 0x18: ("nSetPixCrdX", 1),
    0x19: ("nNumGoods", 0), 0x1A: ("nDest", 0), 0x1B: ("nWithin", 0), 0x1C: ("nFee", 0),
    0x1D: ("nAdvance", 0), 0x1E: ("nPlanetOccup", 0),
}
NAMES = {name: code for code, (name, _) in CODES.items()}

FILES = (sorted((SRC / "Menu/Messages").glob("*Rus*.a80"))
         + [SRC / "Menu/Messages/MenuMsg.a80", SRC / "Menu/Messages/Ships.a80"]
         + sorted((SRC / "Menu").glob("*Msg.a80"))
         + sorted((SRC / "Engine/Messages").glob("*Rus*.a80"))
         + sorted((SRC / "Engine/Messages").glob("*R.a80"))
         + [SRC / "Engine/Messages/eTxtViewScr.a80",
            SRC / "Engine/Messages/eTxtViewScrLow.a80"])


def russian_lines(path):
    """The file's lines with IFDEF Russian / ELSE / ENDIF resolved for
    Russian, other IFDEFs left in (their bodies kept), comments and
    /* */ blocks dropped."""
    text = path.read_bytes().decode("cp866", errors="replace")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    out = []
    stack = []          # (is_russian_block, keep)
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].rstrip()
        s = line.strip()
        m = re.match(r"^(IFDEF|IFNDEF)\s+(\w+)", s, re.I)
        if m:
            sym = m.group(2)
            if sym in ("Russian", "RussianEquip"):
                keep = m.group(1).upper() == "IFDEF"
                stack.append((True, keep))
            else:
                stack.append((False, True))
            continue
        if re.match(r"^ELSE\b", s, re.I) and stack:
            rus, keep = stack[-1]
            stack[-1] = (rus, (not keep) if rus else True)
            continue
        if re.match(r"^ENDIF\b", s, re.I) and stack:
            stack.pop()
            continue
        if all(keep for _, keep in stack):
            out.append(line)
    return out


def items_of(argstr):
    """A db argument list -> list of ('s', text) / ('b', value) / ('n', name)."""
    items = []
    i = 0
    n = len(argstr)
    while i < n:
        c = argstr[i]
        if c in " \t,":
            i += 1
            continue
        if c == '"':
            j = argstr.index('"', i + 1)
            items.append(("s", argstr[i + 1:j]))
            i = j + 1
            continue
        j = i
        while j < n and argstr[j] not in ",":
            j += 1
        tok = argstr[i:j].strip()
        i = j
        if not tok:
            continue
        try:
            items.append(("b", number(tok) & 0xFF))
        except ValueError:
            items.append(("n", tok))
    return items


def extract(path):
    """-> list of (label, index, rendered message) for the file."""
    messages = []
    label = None
    count = 0
    cur = []            # items of the message being built
    pending_args = 0
    pending_code = None

    def flush():
        nonlocal cur, count
        if cur:
            messages.append((label or "?", count, "".join(cur)))
            count += 1
        cur = []

    for line in russian_lines(path):
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z@_][\w@]*)\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            lab, rest = m.group(1).lstrip("@"), m.group(2).strip()
            if re.match(r"^(equ|EQU|=)\b", rest):
                continue
            if not rest or re.match(r"^(db|dw|defb|dm)\b", rest, re.I):
                if cur:
                    flush()
                label, count = lab, 0
                line = rest
                if not line:
                    continue
            else:
                continue
        # a line may hold several statements: `db 1: dw txtCommander: db 0`
        stmts, buf, quoted = [], "", False
        for ch in line:
            if ch == '"':
                quoted = not quoted
            if ch == ":" and not quoted:
                stmts.append(buf)
                buf = ""
            else:
                buf += ch
        stmts.append(buf)
        items = []
        for st in stmts:
            m = re.match(r"^\s*(db|defb|dm)\s+(.*)$", st, re.I)
            if m:
                items.extend(items_of(m.group(2)))
                continue
            m = re.match(r"^\s*dw\s+(.*)$", st, re.I)
            if m:                       # a word: an address of another message
                for tok in split_args(m.group(1)):
                    items.append(("w", tok))
        for kind, val in items:
            if kind == "w":
                cur.append("{dw " + val + "}")
                continue
            if kind == "s":
                cur.append(val)
                continue
            if kind == "n":
                if val in NAMES:
                    kind, val = "b", NAMES[val]
                else:
                    cur.append("{" + val + "}")
                    continue
            b = val
            if pending_args:
                cur.append(("," if cur and cur[-1][-1] != " " and pending_code else " ") + str(b))
                pending_args -= 1
                if pending_args == 0:
                    cur.append("}")
                    pending_code = None
                continue
            if b == 0:
                flush()
                continue
            if b in CODES:
                name, nargs = CODES[b]
                if nargs:
                    cur.append("{" + name)
                    pending_args = nargs
                    pending_code = name
                else:
                    cur.append("{" + name + "}")
            elif 0x20 <= b < 0x80:
                cur.append(chr(b))
            else:
                cur.append("{#%02X}" % b)
    flush()
    return messages


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists() and any(out.glob("*.txt")) and not args.force:
        sys.exit(f"error: {out} has text (use --force)")
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for path in FILES:
        if not path.exists():
            continue
        msgs = extract(path)
        if not msgs:
            continue
        # Menu/Messages and Engine/Messages both have ProductsRus and
        # DevicesRus: the directory tells them apart
        prefix = "_".join(path.parent.relative_to(SRC).parts).lower().replace("messages", "msg")
        name = f"{prefix}_{path.stem.replace('.', '_')}"
        lines = [f"# {path.relative_to(ROOT)} - extracted by tools/legend_text.py;",
                 "# `make extract` overwrites it.  LABEL+n|text; {code args} are",
                 "# Legend's control bytes (PrintTxt.a80).", ""]
        for label, idx, text in msgs:
            lines.append(f"{label}+{idx}|{text}")
        (out / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        total += len(msgs)
        print(f"{len(msgs):4d} {name}")
    print(f"{total} messages -> {out}")


if __name__ == "__main__":
    main()
