#!/usr/bin/env python3
"""tables_extract.py - pull the commodity table out of orig/ELITE.SCL.

The seventeen tradeable goods live at 0x701B of the loaded image as
4-byte records:

    +0  base price
    +1  packed gradient: bit 7 = negative, bits 6..5 = the unit the
        good is sold in (0 tonnes, 1 kilogrammes, 2 grammes), bits
        4..0 = magnitude
    +2  base quantity
    +3  the mask the market fluctuation is taken through

Writes src/res/market/goods.txt, which tools/market_gen.py compiles.
Names come from src/res/text/strings.txt, in the original's own order.

    python3 tools/tables_extract.py [--out src/res/market/goods.txt] [--force]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elite_re                                   # noqa: E402

GOODS_ADDR = 0x701B
NGOODS = 17
UNITS = {0: "t", 1: "kg", 2: "g"}

# The port's label for each good, in the original's order; the Russian
# wording lives in src/res/text/strings.txt under the same labels.
LABELS = ["FOOD", "TEXTILES", "RADIO", "SLAVES", "LIQUOR", "LUXURY",
          "NARCOTICS", "COMPUTERS", "MACHINERY", "ALLOYS", "FIREARMS",
          "FURS", "MINERALS", "GOLD", "PLATINUM", "GEMS", "ALIEN"]


def extract(img):
    out = []
    for i in range(NGOODS):
        a = GOODS_ADDR + i * 4
        price, packed, quant, mask = img[a], img[a + 1], img[a + 2], img[a + 3]
        grad = packed & 0x1F
        if packed & 0x80:
            grad = -grad
        unit = UNITS[(packed >> 5) & 3]
        out.append((LABELS[i], price, grad, quant, mask, unit))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", default="src/res/market/goods.txt")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if os.path.exists(args.out) and not args.force:
        sys.exit(f"error: {args.out} exists (use --force)")

    img = elite_re.load_image()
    rows = extract(img)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("# The seventeen tradeable goods, extracted from\n"
                 "# orig/ELITE.SCL by tools/tables_extract.py.  `make\n"
                 "# extract` rewrites this file.\n#\n"
                 "# label  baseprice  gradient  basequant  mask  unit\n#\n"
                 "# A system's price for a good is\n"
                 "#     (baseprice + (fluct & mask) + economy*gradient) * 4\n"
                 "# and its quantity\n"
                 "#     baseprice's counterpart: basequant + (fluct & mask)\n"
                 "#                              - economy*gradient\n"
                 "# which is why a farming world sells food cheaply and an\n"
                 "# industrial one sells computers cheaply.\n\n")
        for label, price, grad, quant, mask, unit in rows:
            fh.write(f"{label:10s} {price:4d} {grad:4d} {quant:4d} "
                     f"0x{mask:02X} {unit}\n")
    print(f"-> {args.out}: {len(rows)} goods")

    # The 32 syllables the galaxy generator names systems from.  They are
    # the same table the original's text uses as two-letter tokens - one
    # table serving both, exactly as Elite has always done it.
    pairs_out = os.path.join(os.path.dirname(args.out) or ".",
                             "..", "text", "pairs.txt")
    pairs_out = os.path.normpath(pairs_out)
    os.makedirs(os.path.dirname(pairs_out), exist_ok=True)
    pairs = elite_re.read_digrams(img)
    with open(pairs_out, "w", encoding="utf-8") as fh:
        fh.write("# The 32 name syllables, extracted from orig/ELITE.SCL\n"
                 "# (the pair table at 0xFDB3).  One per line, in KOI-7 as\n"
                 "# the original stores them; the comment is the Cyrillic.\n"
                 "# `make extract` rewrites this file.\n\n")
        for i, pr in enumerate(pairs):
            fh.write(f"{pr}\t; {i:2d}  {elite_re.koi7(pr)}\n")
    print(f"-> {pairs_out}: {len(pairs)} syllables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
