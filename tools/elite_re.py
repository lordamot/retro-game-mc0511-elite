#!/usr/bin/env python3
"""Reverse-engineering library for the Russian ZX Spectrum release of Elite.

The original this port works from is `orig/ELITE.SCL` - a TR-DOS disk image
of the Russian localisation of Elite (Torus / Firebird, 1985).  This module
knows how to

  * read the .SCL catalogue and pull the four files out of it,
  * rebuild the 48K Spectrum memory image the BASIC loader would produce,
  * decode the game's text encoding (KOI-7 Cyrillic + a 44-entry digram
    token table) into Unicode.

Nothing here interprets the original's Z80 code; the extractors in
`tools/extract_res.py` use these primitives to pull the port's resources out
of the image, and the port itself re-implements the engine from scratch.

Run as a script for a quick report:

    python3 tools/elite_re.py catalogue
    python3 tools/elite_re.py strings [--from ADDR] [--to ADDR]
    python3 tools/elite_re.py image tmp/img.bin
"""

import argparse
import os
import struct
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCL = os.path.join(REPO, "orig", "ELITE.SCL")

# ---------------------------------------------------------------- .SCL ----

class SclFile:
    """One catalogue entry of a .SCL image."""

    def __init__(self, name, kind, start, length, sectors, data):
        self.name = name
        self.kind = kind          # 'B' = BASIC, 'C' = CODE
        self.start = start        # catalogue start address
        self.length = length
        self.sectors = sectors
        self.data = data          # exactly `length` bytes for CODE files

    def __repr__(self):
        return (f"<SclFile {self.name!r} {self.kind} "
                f"start=0x{self.start:04X} len={self.length}>")


def read_scl(path=SCL):
    """Parse a .SCL image into a list of SclFile."""
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:8] != b"SINCLAIR":
        raise ValueError(f"{path}: not a .SCL image")
    count = blob[8]
    off = 9
    entries = []
    for _ in range(count):
        rec = blob[off:off + 14]
        off += 14
        entries.append((rec[0:8].decode("latin1").strip(),
                        chr(rec[8]),
                        struct.unpack("<H", rec[9:11])[0],
                        struct.unpack("<H", rec[11:13])[0],
                        rec[13]))
    files = []
    pos = off
    for name, kind, start, length, sectors in entries:
        raw = blob[pos:pos + sectors * 256]
        pos += sectors * 256
        files.append(SclFile(name, kind, start, length, sectors,
                             raw[:length] if kind == "C" else raw))
    return files


# The BASIC loader (ELITE1KR) does, in order:
#     LOAD "elite$" CODE          -> its own address, 0x98D2
#     RANDOMIZE USR 39122         -> runs it (loading-screen helper)
#     LOAD "elitr2" CODE          -> 0x7000, the game itself
#     LOAD "elitr1" CODE 16384    -> the visible line says 16384, but that
#                                    number is never used
#
# The `16384` in line 70 is decorative.  Loading is done by the machine
# code hidden in the REM on line 10, which sets up its own descriptor -
# `LD HL,$D021 / LD DE,$5B00 / LD BC,$14FF` - so elitr1 lands at 0x5B00,
# ending exactly where elitr2 begins.  Measured, not inferred: the ship
# table AdrDataShips sits at file offset 0x680 of elitr1 and at 0x6180 in
# nzeemin's disassembly of the same build, and 0x6180 - 0x680 = 0x5B00.
LOAD_MAP = [("elitr2", 0x7000), ("elitr1", 0x5B00)]

CODE_ORG = 0x7000
CODE_END = 0x10000


def load_image(path=SCL):
    """Rebuild the 64K Spectrum address space as the loader leaves it."""
    files = {f.name: f for f in read_scl(path)}
    img = bytearray(0x10000)
    for name, addr in LOAD_MAP:
        f = files[name]
        img[addr:addr + len(f.data)] = f.data
    return bytes(img)


# ---------------------------------------------------------------- text ----

# The localisation stores text in KOI-7 (ГОСТ 13052-74): the Latin letter
# positions 0x40..0x5F carry uppercase Cyrillic.  Digits, space and
# punctuation are plain ASCII.
KOI7 = {
    "@": "Ю", "A": "А", "B": "Б", "C": "Ц", "D": "Д", "E": "Е", "F": "Ф",
    "G": "Г", "H": "Х", "I": "И", "J": "Й", "K": "К", "L": "Л", "M": "М",
    "N": "Н", "O": "О", "P": "П", "Q": "Я", "R": "Р", "S": "С", "T": "Т",
    "U": "У", "V": "Ж", "W": "В", "X": "Ь", "Y": "Ы", "Z": "З", "[": "Ш",
    "\\": "Э", "]": "Щ", "^": "Ч", "_": "Ъ",
}

# Two 2-letter-pair tables sit back to back at 0xFD9B.  The first twelve
# pairs are the syllables the galaxy generator builds system names out of
# (the classic Elite scheme, with a Russian syllable set); the thirty-two
# after them are the text tokens, so a string byte 0x80..0x9F stands for
# one pair.
NAMEPAIR_ADDR = 0xFD9B
NAMEPAIR_COUNT = 12
DIGRAM_ADDR = 0xFDB3
DIGRAM_COUNT = 32


def _pairs(img, addr, count):
    return [img[addr + 2 * i: addr + 2 * i + 2].decode("latin1")
            for i in range(count)]


def read_digrams(img, addr=DIGRAM_ADDR, count=DIGRAM_COUNT):
    """The text token table as a list of 2-character KOI-7 strings."""
    return _pairs(img, addr, count)


def read_namepairs(img):
    """The syllable table the galaxy generator names systems from."""
    return _pairs(img, NAMEPAIR_ADDR, NAMEPAIR_COUNT)


def koi7(text):
    """KOI-7 (as Latin) -> Unicode Cyrillic."""
    return "".join(KOI7.get(c, c) for c in text)


def decode_string(img, addr, digrams=None, maxlen=255):
    """Decode one 0-terminated game string; returns (text, next_addr).

    Bytes 0x20..0x7F are literal KOI-7, 0x80.. are digram tokens, and
    control bytes below 0x20 are layout codes kept as ``{nn}`` markers so
    round-trips stay lossless.
    """
    if digrams is None:
        digrams = read_digrams(img)
    out = []
    i = addr
    end = min(addr + maxlen, len(img))
    while i < end:
        c = img[i]
        i += 1
        if c == 0:
            break
        if c >= 0x80:
            k = c - 0x80
            out.append(digrams[k] if k < len(digrams) else f"{{{c:02X}}}")
        elif c < 0x20:
            out.append(f"{{{c:02X}}}")
        else:
            out.append(chr(c))
    return koi7("".join(out)), i


def scan_strings(img, lo=0xF100, hi=0xFC00, minlen=3):
    """Walk a region as a run of 0-terminated strings."""
    digrams = read_digrams(img)
    found = []
    addr = lo
    while addr < hi:
        start = addr
        text, addr = decode_string(img, start, digrams)
        if addr == start:
            addr += 1
            continue
        if len(text) >= minlen:
            found.append((start, text))
    return found


# ---------------------------------------------------------------- main ----

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("catalogue", help="list the .SCL contents")
    p = sub.add_parser("image", help="write the rebuilt 64K image")
    p.add_argument("out")
    p = sub.add_parser("strings", help="decode a region as game strings")
    p.add_argument("--from", dest="lo", default="0xF100")
    p.add_argument("--to", dest="hi", default="0xFC00")
    p = sub.add_parser("digrams", help="print the digram token table")
    args = ap.parse_args()

    if args.cmd == "catalogue":
        for f in read_scl():
            print(f"{f.name:10s} {f.kind} start=0x{f.start:04X} "
                  f"len={f.length:6d} sectors={f.sectors}")
        return
    if args.cmd == "image":
        with open(args.out, "wb") as fh:
            fh.write(load_image())
        print(f"-> {args.out}")
        return
    img = load_image()
    if args.cmd == "digrams":
        for i, d in enumerate(read_digrams(img)):
            print(f"0x{0x80 + i:02X} {d!r} = {koi7(d)}")
        return
    if args.cmd == "strings":
        for addr, text in scan_strings(img, int(args.lo, 0), int(args.hi, 0)):
            print(f"0x{addr:04X}  {text}")


if __name__ == "__main__":
    main()
