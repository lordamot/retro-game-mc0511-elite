#!/usr/bin/env python3
"""legend_tables.py - Elite Legend's game tables -> src/res/legend/.

    python3 tools/legend_tables.py [--out src/res/legend] [--force]

Reads, from `orig/legend/EliteLegend_v1_09_source/INCLUDE`:

  Galaxy/GalaxyData.a80   TableBasePrice (38 commodities, 4 bytes each)
                          and BaseGalaxyData (the galaxy seed)
  Menu/Messages/ProductsRus.a80   the commodities' Russian names
  InfoShips.a80           the ship yard: 20 ships, 22 bytes each
  Menu/Messages/Ships.a80 their names
  Menu/priceEquip.a80     equipment: tech level, mission gate, two prices
  Menu/Messages/DevicesRus.a80    the equipment's Russian names

and, from `../Cocpits/Cocpit_Var/Ship.var_NN.a80`, the rule fields of
the twenty cockpit blocks (the rest of a block is where the Spectrum
dashboard's indicators sit, which this port lays out for itself);

and writes `market/goods.txt`, `catalog.txt`, `equip.txt`, `galaxy.txt`
and `cockpits.txt` under the output directory, one record a line, every
field the source has, as text a generator can read and a person can check.
Nothing is assembled; `make verify` checks these back against the
sources.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from legend_ships import number, read_source, split_args   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "orig/legend/EliteLegend_v1_09_source/INCLUDE"
OUT = ROOT / "src/res/legend"
HEAD = "# Extracted from orig/legend by tools/legend_tables.py; `make extract` overwrites it.\n"


def raw_lines(path):
    return path.read_bytes().decode("cp866", errors="replace").splitlines()


def strings_under(path, start_label):
    """The `db "...",0` strings after a label, in order, with the +NN
    comment index when there is one."""
    out = []
    on = False
    for raw in raw_lines(path):
        if re.match(rf"^{re.escape(start_label)}\b", raw):
            on = True
            continue
        if not on:
            continue
        m = re.search(r'db\s+"([^"]*)"\s*,\s*0', raw)
        if m:
            out.append(m.group(1))     # the block may continue past a label
    return out


def goods():
    lines = raw_lines(SRC / "Galaxy/GalaxyData.a80")
    rows = []
    on = False
    for raw in lines:
        if raw.strip() == "TableBasePrice":
            on = True
            continue
        if on:
            s = raw.split(";", 1)
            body = s[0].strip()
            comment = s[1].strip() if len(s) > 1 else ""
            if body.startswith("db"):
                vals = [number(t) for t in split_args(body[2:])]
                rows.append((vals, comment))
            elif rows and body.startswith(";"):
                continue
            elif rows and not body and not comment:
                continue
            elif rows and body and not body.startswith("db"):
                break
    names = strings_under(SRC / "Menu/Messages/ProductsRus.a80", "Msg_Products1")
    if len(rows) != 38 or len(names) != 38:
        sys.exit(f"error: {len(rows)} price rows, {len(names)} names; expected 38")
    text = [HEAD, "# index key price grad quant mask | Russian name",
            "# price+grad: the base price word; grad's low 5 bits times the economy",
            "# is added (bit 7 set: subtracted); quant the base quantity; mask what",
            "# of the system's random byte joins in - genStationPrice in genData.a80.\n"]
    for i, ((p, g, q, m), comment) in enumerate(rows):
        key = re.sub(r"\s*\(.*", "", comment).strip().upper().replace(" ", "_").replace("/", "_").replace("-", "_")
        text.append(f"{i:2d} {key:16s} {p:3d} {g:3d} {q:3d} {m:3d} | {names[i]}")
    return "\n".join(text) + "\n"


def catalog():
    entries = []
    cur = None
    for raw in raw_lines(SRC / "InfoShips.a80"):
        m = re.match(r"^;([0-9A-Fa-f]{2}) -+ (.+)$", raw)
        if m:
            cur = {"n": int(m.group(1), 16), "name": m.group(2).strip(), "vals": []}
            entries.append(cur)
            continue
        if cur is None:
            continue
        body = raw.split(";", 1)[0].strip()
        mm = re.match(r"^(db|dw|dd)\s+(.*)$", body)
        if mm:
            for t in split_args(mm.group(2)):
                cur["vals"].append(number(t))
    fields = ["date", "speed", "tonnage", "price", "obj", "cockpit", "base_tonnage",
              "fit0", "fit1", "fit2", "fit3", "fit4", "fit5", "ecotech", "chance", "mission"]
    text = [HEAD, "# n name | " + " ".join(fields),
            "# date: in-service year; obj: AdrDataShips number of its hull; cockpit 0..19;",
            "# fit0..5: which equipment fits (bit per item, priceEquip order);",
            "# ecotech: bits 7-5 minimum economy, 4-0 minimum tech level;",
            "# chance: of being for sale; mission: PilotMissionComplete gate.\n"]
    for e in entries:
        if len(e["vals"]) != len(fields):
            sys.exit(f"error: ship {e['name']}: {len(e['vals'])} fields, expected {len(fields)}")
        text.append(f"{e['n']:2d} {e['name']:22s} | " + " ".join(str(v) for v in e["vals"]))
    return "\n".join(text) + "\n", len(entries)


def equip():
    rows = []
    for raw in raw_lines(SRC / "Menu/priceEquip.a80"):
        body, _, comment = raw.partition(";")
        stmts = [s.strip() for s in body.split(":") if s.strip()]
        if not stmts:
            continue
        # a line is: [label] db tech,mission : dbdw station : dbdw military
        first = stmts[0]
        m = re.match(r"^(\w+)?\s*db\s+(.+)$", first)
        if not m or len(stmts) != 3:
            continue
        label = m.group(1) or ""
        tech, mission = [number(t) for t in split_args(m.group(2))]
        prices = []
        for s in stmts[1:]:
            mm = re.match(r"^dbdw\s+(.+)$", s)
            if not mm:
                break
            prices.append(number(mm.group(1)))
        if len(prices) != 2:
            continue
        rows.append((label, tech, mission, prices[0], prices[1], comment.strip()))
    names = strings_under(SRC / "Menu/Messages/DevicesRus.a80", "msgEquip")
    devs = device_of_row()
    text = [HEAD, "# n label tech mission station_price military_price dev | Russian name",
            "# tech: minimum tech level (255 = Raxxla only); mission: gate on",
            "# PilotMissionComplete; prices in tenths of a credit, 0 = not sold there;",
            "# dev: for the devices (rows 14 on), type*64 + the byte's index in",
            "# PilotDevices (AdrTablEquip in EquipShip.a80) - fitted when that byte,",
            "# masked with 0x83, equals the type.\n"]
    for i, (label, tech, mission, ps, pm, comment) in enumerate(rows):
        name = names[i] if i < len(names) else "?"
        dev = f"{devs[i]:3d}" if i in devs else "  -"
        text.append(f"{i:2d} {label or '-':16s} {tech:3d} {mission:3d} {ps:8d} {pm:8d} {dev} | {name}")
    return "\n".join(text) + "\n", len(rows), len(names)


def device_of_row():
    """AdrTablEquip: which byte of PilotDevices each equipment row is,
    and which type in its low bits, as {row: type * 64 + index}."""
    index = {}
    inside = False
    for line in read_source(SRC / "Pilot.var.a80"):
        if re.match(r"^PilotDevices\b", line):
            inside = True
        elif re.match(r"^EndPilotShip\b", line):
            break
        elif inside:
            m = re.match(r"^(\w+)\s+db\s", line)
            if m:
                index[m.group(1)] = len(index)
    devs = {}
    inside = False
    row = 14                    # the table starts at equipment row #0E
    for line in read_source(SRC / "Menu/EquipShip.a80"):
        if re.match(r"^AdrTablEquip\b", line):
            inside = True
            continue
        if inside:
            m = re.match(r"^\s*db\s+%([01]{8})\+(\w+)-PilotDevices", line)
            if not m:
                if devs:
                    break
                continue
            bits, name = m.groups()
            devs[row] = (int(bits, 2) >> 6) * 64 + index[name]
            row += 1
    if len(devs) != 35:
        sys.exit(f"error: AdrTablEquip: {len(devs)} rows read, 35 expected")
    return devs


COCKPIT_FIELDS = [("cocpMaxMiss", "maxmiss"), ("cocpMaxEnUnit", "enunits"),
                  ("cocpMaxFuel", "maxfuel"), ("shipTonnage", "tonnage"),
                  ("shipTurrets", "turrets"), ("cocpScanerNum", "scanner")]


def cockpits():
    """The twenty cockpit blocks' rule fields: missiles, energy units,
    fuel, tonnage, turrets and the scanner variant."""
    rows = []
    for n in range(20):
        path = SRC.parent / "Cocpits/Cocpit_Var" / f"Ship.var_{n:02d}.a80"
        vals = {}
        for raw in raw_lines(path):
            body = raw.split(";", 1)[0].strip()
            m = re.match(r"^(\w+)\s+d[bw]\s+(\S+)$", body)
            if m and m.group(1) in dict(COCKPIT_FIELDS):
                vals[m.group(1)] = number(m.group(2))
        missing = [f for f, _ in COCKPIT_FIELDS if f not in vals]
        if missing:
            sys.exit(f"error: {path.name}: no {missing}")
        rows.append([vals[f] for f, _ in COCKPIT_FIELDS])
    text = [HEAD, "# n | " + " ".join(k for _, k in COCKPIT_FIELDS),
            "# Cocpits/Cocpit_Var/Ship.var_NN.a80, the fields the rules read: maxmiss",
            "# (cocpMaxMiss, 0..8), enunits (cocpMaxEnUnit, energy banks, 1..7), maxfuel",
            "# (cocpMaxFuel, tenths of a light year), tonnage (shipTonnage, the hold",
            "# without the larger bay), turrets (shipTurrets: 0 none, 1 front only, 2",
            "# front/rear, 4 all round), scanner (cocpScanerNum: bits 2-0 which of the",
            "# scanner drawings, bits 7-6 what it shows).  The catalogue's cockpit",
            "# column says which block a ship flies with.\n"]
    for n, r in enumerate(rows):
        text.append(f"{n:2d} | " + " ".join(str(v) for v in r))
    return "\n".join(text) + "\n", len(rows)


def galaxy():
    for line in read_source(SRC / "Galaxy/GalaxyData.a80"):
        m = re.match(r"^@?BaseGalaxyData\s+db\s+(.*)$", line)
        if m:
            vals = [number(t) for t in split_args(m.group(1))]
            return (HEAD + "# BaseGalaxyData: the seed of galaxy 1 (six bytes, then the first\n"
                    "# five again so a galaxy's seed is read at a rotation), in\n"
                    "# GalaxyData.a80.  The same #4A5A 4802 53B7 as the 1985 game.\n"
                    "seed " + " ".join(str(v) for v in vals) + "\n")
    sys.exit("error: BaseGalaxyData not found")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    targets = {"market/goods.txt": None, "catalog.txt": None,
               "equip.txt": None, "galaxy.txt": None, "cockpits.txt": None}
    if not args.force and any((out / t).exists() for t in targets):
        sys.exit(f"error: tables exist under {out} (use --force)")
    g = goods()
    c, nships = catalog()
    e, nequip, nnames = equip()
    x = galaxy()
    k, ncock = cockpits()
    for rel, body in (("market/goods.txt", g), ("catalog.txt", c),
                      ("equip.txt", e), ("galaxy.txt", x), ("cockpits.txt", k)):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    print(f"38 goods, {nships} ships, {nequip} equipment rows ({nnames} names), "
          f"{ncock} cockpits -> {out}")


if __name__ == "__main__":
    main()
