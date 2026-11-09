#!/usr/bin/env python3
"""planet_extract.py - the words the original describes a world with.

Two tables come out of orig/ELITE.SCL:

  * the SPECIES table at 0xF2FE - twenty-three words in four groups, and
    in exactly the order every Elite uses them: three of size, six of
    colour, six of characteristic and eight of kind, so
    "large green slimy frogs" is four indices into it;

  * the words the DESCRIPTION generator draws on, scattered through the
    token table from 0xF6xx to 0xFAxx: hazards, attractions and the
    adjectives that go with them.

Two things about the original's own encoding are worth knowing, because
neither is standard KOI-7 and both were found by reading words that did
not make sense until they did: the localisation draws **Ч on the J
position** (so 'JERN' is ЧЕРН, black) and **Э on the '3' position** (so
'3ЛЕКТРОНИКА' is ЭЛЕКТРОНИКА).  `--raw` prints what the bytes say
before those two corrections.

The file this writes has two columns: the stem as the disk has it, and
the form the game prints.  The stems are the original's and `make
verify` checks them against the image; the endings are written out here,
because Russian adjectives need them and the original assembles them
with a suffix table this port does not copy.

    python3 tools/planet_extract.py --out src/res/text/planet.txt [--force]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elite_re                                    # noqa: E402

SPECIES_ADDR = 0xF2FE
SPECIES_GROUPS = [("size", 3), ("colour", 6), ("trait", 6), ("kind", 8)]

# Where each description word sits in the token table.  Addresses, not
# guesses: every one of them is checked on the way out.
DESCRIPTION = [
    ("hazard", 0xF6FE, "ЦУНАМИ"),
    ("hazard", 0xF707, "ЗЕМЛЕТРЯСЕНИЯ"),
    ("hazard", 0xF711, "СОЛНЕЧНЫЕ БУРИ"),
    ("hazard", 0xF9C4, "ВУЛКАНЫ"),
    ("hazard", 0xF9A7, "ОБЛАКА ПЫЛИ"),
    ("hazard", 0xF9B1, "АЙСБЕРГИ"),
    ("hazard", 0xF747, "ГРОЗЫ"),
    ("hazard", 0xF6EC, "ВОЙНЫ"),
    ("sight", 0xF79B, "КАЗИНО"),
    ("sight", 0xF790, "НОЧНАЯ ЖИЗНЬ"),
    ("sight", 0xF741, "РАСТЕНИЯ"),
    ("sight", 0xF74C, "НАРОД"),
    ("sight", 0xF6A9, "ТУРИСТЫ"),
    ("sight", 0xF1DE, "КОЛОНИЯ РАБОВ"),
    ("sight", 0xF778, "БОГАТСТВА"),
    ("quality", 0xF950, "ДРЕВНИЕ"),
    ("quality", 0xF956, "НЕОБЫЧНЫЕ"),
    ("quality", 0xF95E, "ЭКСЦЕНТРИЧНЫЕ"),
    ("quality", 0xF89E, "ЖУТКИЕ"),
    ("quality", 0xF8C5, "ЖЕСТОКИЕ"),
    ("quality", 0xF8CF, "УЖАСНЫЕ"),
    ("quality", 0xF898, "ЗАБАВНЫЕ"),
    ("quality", 0xF8BC, "СЛУЧАЙНЫЕ"),
]

# The displayed forms of the species words, in the order the original
# holds them.  The stem beside each one is what the disk says.
SPECIES_SHOWN = ["РОГАТЫЕ", "СИЛЬНЫЕ", "СЛАБЫЕ",
                 "ЗЕЛЕНЫЕ", "КРАСНЫЕ", "ЖЕЛТЫЕ", "КОРИЧНЕВЫЕ", "ЧЕРНЫЕ", "",
                 "ЛИПКИЕ", "УСАТЫЕ", "ЯДОВИТЫЕ", "КРАСИВЫЕ", "ЖИРНЫЕ",
                 "МОХНАТЫЕ",
                 "ЗМЕИ", "ЖАБЫ", "ПТИЦЫ", "КАЛЬМАРЫ", "ОРЛЫ", "ГУМАНОИДЫ",
                 "ТИГРЫ", "ТАРАКАНЫ"]

FIXUPS = str.maketrans({"Й": "Ч", "3": "Э"})


def decode(img, addr, raw=False):
    """One word of the original's, tokens expanded, quirks corrected."""
    digrams = [elite_re.koi7(p) for p in elite_re.read_digrams(img)]
    out = []
    i = addr
    while img[i]:
        c = img[i]
        i += 1
        if 0x20 <= c < 0x80:
            out.append(elite_re.koi7(chr(c)))
        elif 0x80 <= c <= 0x9F:
            out.append(digrams[c - 0x80])
        elif 0xE4 <= c <= 0xFF and c - 0xE4 < len(digrams):
            out.append(digrams[c - 0xE4])
        else:
            out.append("")                  # a control byte: nothing to print
    text = "".join(out)
    return text if raw else text.translate(FIXUPS)


def species(img, raw=False):
    out = []
    addr = SPECIES_ADDR
    for group, count in SPECIES_GROUPS:
        for _ in range(count):
            out.append((group, addr, decode(img, addr, raw)))
            while img[addr]:
                addr += 1
            addr += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--raw", action="store_true",
                    help="print the words before the Ч/Э corrections")
    args = ap.parse_args(argv)
    img = elite_re.load_image()

    rows = []
    for i, (group, addr, stem) in enumerate(species(img, args.raw)):
        shown = SPECIES_SHOWN[i] if i < len(SPECIES_SHOWN) else stem
        rows.append((group, addr, stem, shown))
    for group, addr, shown in DESCRIPTION:
        rows.append((group, addr, decode(img, addr, args.raw), shown))

    lines = ["# The words a world is described with, out of orig/ELITE.SCL.",
             "# Written by tools/planet_extract.py - `make extract` rewrites it.",
             "#",
             "# group | address in the original | its stem there | what is printed",
             "#",
             "# The stems are checked against the image by `make verify`; the",
             "# endings are written out here because Russian needs them and the",
             "# original assembles them from a suffix table this port does not",
             "# copy.  The original draws Ч on the J position and Э on '3', so",
             "# 'JERN' is ЧЕРН - see tools/planet_extract.py.",
             "#",
             "# A few stems keep a leading lowercase Latin byte ('h ', 'q ')",
             "# and one keeps trailing spaces: they are in the original's own",
             "# string and are left verbatim so the round-trip is exact.  The",
             "# colour list really does have six slots with one of them empty",
             "# - the world whose seed picks it is described without a colour.",
             ""]
    for group, addr, stem, shown in rows:
        lines.append(f"{group}\t{addr:#06x}\t{stem}\t{shown}")
    text = "\n".join(lines) + "\n"

    if not args.out:
        print(text)
        return 0
    if os.path.exists(args.out) and not args.force:
        sys.exit(f"error: {args.out} exists (use --force)")
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"-> {args.out}: {len(rows)} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
