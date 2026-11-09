#!/usr/bin/env python3
"""build_elite.py - build the UKNC Elite disk from src/.

Pipeline:
  1. generate resources and assemble the MACRO-11 resident;
  2. link a native ELITE.SAV with the RT-11 header and load bitmap;
  3. assemble overlays and package file-relative blocks in ELITE.DAT;
  4. install these files on a copy of the supplied RT-11 volume,
     preserving commander files (or migrating the previous raw format).

Usage:
    python3 tools/build_elite.py [OUTPUT.dsk] [--build-dir build] [--force]
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent

def prog_size():
    """The padded image size, read from src/defs.mac.

    It used to be a copy of the number kept here, and a copy is a number
    waiting to disagree: the day the image was grown, the assembler
    padded to the new size and the disk builder wrote the old one.
    """
    text = (REPO_ROOT / "src/defs.mac").read_text(encoding="utf-8")
    m = re.search(r"^PROG_SIZE\s*=\s*([0-7]+)", text, re.M)
    if not m:
        sys.exit("error: PROG_SIZE not found in src/defs.mac")
    return int(m.group(1), 8)


PROG_SIZE = prog_size()       # padded program image (src/defs.mac says)
PROG_SECTORS = PROG_SIZE // 512

# Generated sources: (tool, args...) -> build/<name>.mac.  Kept as a table
# so a new resource is one line here plus one line in src/elite.list.
GENERATORS = [
    ("tools/font_gen.py", ["src/res/font/uknc11.txt"], "font8.mac",
     "font compilation failed"),
    ("tools/font_gen.py", ["src/res/font/latin11.txt"], "splash_font.mac",
     "splash Latin font compilation failed", ["--prefix", "SPLAT"]),
    ("tools/text_gen.py", ["src/res/text/strings.txt"], "strings.mac",
     "string compilation failed"),
    ("tools/market_gen.py", ["src/res/legend/market/goods.txt"], "market.mac",
     "commodity table compilation failed"),
    ("tools/ships_gen.py", ["src/res/legend/ships"], "ships.mac",
     "ship blueprint compilation failed"),
    ("tools/music_gen.py", ["src/res/music/title.txt"], "music.mac",
     "music compilation failed"),
    ("tools/keyfile.py", ["src/res/setup.txt"], "keytab.mac",
     "key file compilation failed"),
    ("tools/sfx_gen.py", ["src/res/legend/sfx.txt"], "sfx.mac",
     "sound effects compilation failed"),
    ("tools/logo_gen.py", ["src/res/legend/logo.txt"], "logo.mac",
     "logo compilation failed"),
    ("tools/scanner_gen.py", ["src/res/legend/scanners.txt"], "scanners.mac",
     "scanner dish compilation failed"),
    ("tools/planet_gen.py", ["src/res/text/planet.txt"], "planet.mac",
     "planet vocabulary compilation failed"),
    ("tools/legend_gen.py", ["src/res/legend/equip.txt"], "legend_equip.mac",
     "Legend equipment table compilation failed"),
    # the same tables in parts, for the overlays that read only some
    # columns: the window is sized by its largest tenant
    ("tools/legend_gen.py", ["src/res/legend/equip.txt"], "legend_equip_names.mac",
     "Legend equipment names compilation failed", ["--part", "names"]),
    ("tools/legend_gen.py", ["src/res/legend/equip.txt"], "legend_equip_price.mac",
     "Legend equipment prices compilation failed", ["--part", "price"]),
    ("tools/catalog_gen.py", ["src/res/legend/catalog.txt"], "legend_catalog.mac",
     "Legend ship catalogue compilation failed"),
    ("tools/catalog_gen.py", ["src/res/legend/catalog.txt"], "legend_catalog_fit.mac",
     "Legend ship fit masks compilation failed", ["--part", "fit"]),
    ("tools/mission_text.py", ["src/res/legend/text/menu_MissionsMsg.txt"],
     "mistext.mac", "mission text compilation failed"),
    ("tools/cockpit_gen.py", ["src/res/legend/cockpits.txt", "src/res/legend/catalog.txt"],
     "legend_cockpit.mac", "Legend cockpit table compilation failed"),
]


def run_tool(argv, fail_message):
    r = subprocess.run([sys.executable] + [str(a) for a in argv],
                       cwd=REPO_ROOT)
    if r.returncode != 0:
        sys.exit(f"error: {fail_message}")


def assemble(src, obj, lst):
    macro11 = REPO_ROOT / "bin/macro11/macro11"
    r = subprocess.run([str(macro11), "-m", "orig/rt11/SYSMAC.SML", "-yus", "-ysl", "64",
                        "-o", str(obj), "-l", str(lst), str(src)],
                       capture_output=True, text=True, cwd=REPO_ROOT)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 or "***ERROR" in out or "%%%" in out:
        print(out[-8000:])
        sys.exit("error: assembly failed - see the messages above "
                 f"(full listing: {lst})")
    return out


def overlay_list():
    """src/ovl.list -> [(name, [module paths])], in overlay-number order."""
    out = []
    for line in (REPO_ROOT / "src/ovl.list").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, mods = line.partition(":")
        out.append((name.strip(), [REPO_ROOT / m for m in mods.split()]))
    return out


def resident_symbols(lst):
    """The resident's labels as `NAME = address` lines, for an overlay to
    assemble against.  Labels only - the equates come from defs.mac,
    which the overlay includes itself - and nothing local."""
    import syms as symmod
    lines = ["; the resident's labels and equates, out of build/elite.lst -",
             "; generated, do not edit"]
    # defs.mac's own equates are left out: the overlay includes defs.mac
    indefs = set(re.findall(r"^([A-Z][A-Z_0-9.$]*)\s*=", 
                            (REPO_ROOT / "src/defs.mac").read_text(), re.M))
    # the resident's listing only: with the overlays' listings in, a stale
    # build/ovl_*.lst would hand an overlay its own labels back at the
    # addresses of the previous layout, and it would refuse to assemble
    for name, value in symmod.table(overlays=False).items():
        if name not in indefs:
            lines.append(f"{name} = {value}")
    return "\n".join(lines) + "\n"


def build(output, build_dir, force):
    required = ("bin/macro11/macro11", "orig/rt11/SYSMAC.SML",
                "orig/rt11/RT11BASE.DSK")
    missing = [name for name in required if not (REPO_ROOT / name).is_file()]
    if missing:
        sys.exit("error: missing local build inputs: " + ", ".join(missing)
                 + ". Run make toolchain for the assembler and supply the RT-11 "
                   "files as described in docs/setup.md.")
    build_dir = Path(build_dir)
    if not build_dir.is_absolute():
        build_dir = REPO_ROOT / build_dir
    build_dir.mkdir(parents=True, exist_ok=True)
    output = Path(output)
    if not output.is_absolute():
        output = REPO_ROOT / output
    if output.exists() and not force:
        sys.exit(f"error: {output} exists (use --force to overwrite)")

    # 1. generated sources (skipped while a generator has no input yet)
    for tool, args, out_name, msg, *part in GENERATORS:
        if not (REPO_ROOT / tool).exists():
            continue
        if not all((REPO_ROOT / a).exists() for a in args):
            continue
        extra = list(part[0]) if part else []
        if tool.endswith("text_gen.py"):
            pairs = REPO_ROOT / "src/res/text/pairs.txt"
            if pairs.exists():
                extra = ["--pairs", pairs]
        if tool.endswith("ships_gen.py"):
            extra = ["--bank", build_dir / "hulls.bin"]
        if tool.endswith("keyfile.py"):
            extra = ["--bin", build_dir / "keys.bin"]
        run_tool([tool] + args + extra
                 + ["--out", build_dir / out_name, "--force"], msg)

    # A paired identity catches stale SAV/DAT combinations before PPU takeover.
    identity = hashlib.sha256()
    inputs = sorted(p for p in (REPO_ROOT/'src').rglob('*') if p.is_file())
    inputs += sorted((REPO_ROOT/'tools').glob('*.py'))
    inputs += [REPO_ROOT/'orig/rt11/SYSMAC.SML']
    for p in inputs:
        identity.update(str(p.relative_to(REPO_ROOT)).encode()+b'\0')
        identity.update(p.read_bytes())
        identity.update(b'\0')
    header = b'ELITE11\0' + bytes([1]) + bytes(7) + identity.digest()[:16]
    (build_dir / 'rt11_header.mac').write_text('RT_HEADER:\n' + ''.join(
        ' .BYTE ' + ','.join(str(x)+'.' for x in header[i:i+8]) + '\n'
        for i in range(0,32,8)))

    # 2. concatenate + assemble
    modules = []
    for line in (REPO_ROOT / "src/elite.list").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        modules.append(REPO_ROOT / line)
    cat = []
    for m in modules:
        if not m.exists():
            sys.exit(f"error: module {m} is missing")
        cat.append(f"; ------- {m.relative_to(REPO_ROOT)} -------\n")
        cat.append(m.read_text())
    src = build_dir / "elite.mac"
    src.write_text("".join(cat))
    obj = build_dir / "elite.obj"
    assemble(src, obj, build_dir / "elite.lst")

    from savlink import link
    link(str(obj), str(build_dir / 'ELITE.SAV'), stack=0o1000)
    # Debuggers use a CPU-addressed image; it is the exact SAV, not a raw loader.
    (build_dir / 'elite.raw').write_bytes((build_dir / 'ELITE.SAV').read_bytes())

    # 3b. the resident's size, for the eye
    from syms import table as symtable
    t = symtable()
    used = int(t["PROG_USED"], 8) if "PROG_USED" in t else PROG_SIZE
    print(f"resident: {used} of {PROG_SIZE} bytes ({PROG_SIZE - used} free)")

    # 4. Overlays assemble at OVL_BASE; their blocks are relative to DAT.
    entries = []
    ovl_base = int(t["OVL_BASE"], 8)
    ovl_end = int(t["OVL_END"], 8)
    ovl_dir_lba = int(t["OVL_DIR_LBA"], 8)
    lba = int(t["OVL_LBA0"], 8)
    syms_src = build_dir / "resident_syms.mac"
    syms_src.write_text(resident_symbols(build_dir / "elite.lst"))
    directory = []
    for n, (name, mods) in enumerate(overlay_list()):
        cat = [f"; ------- overlay {n}: {name} -------\n",
               (REPO_ROOT / "src/defs.mac").read_text(),
               f"; ------- the resident's labels -------\n",
               syms_src.read_text(),
               f"\n\t. = OVL_BASE\n"]
        for m in mods:
            if not m.exists():
                sys.exit(f"error: overlay {name}: module {m} is missing")
            cat.append(f"; ------- {m.relative_to(REPO_ROOT)} -------\n")
            cat.append(m.read_text())
        cat.append("\n\t.END\n")
        osrc = build_dir / f"ovl_{name}.mac"
        osrc.write_text("".join(cat))
        oobj = build_dir / f"ovl_{name}.obj"
        assemble(osrc, oobj, build_dir / f"ovl_{name}.lst")
        oraw = build_dir / f"ovl_{name}.raw"
        run_tool(["tools/obj2bin.py", oobj, oraw, "--base", f"{ovl_base:o}"],
                 f"linking overlay {name} failed")
        size = oraw.stat().st_size
        if size > ovl_end - ovl_base:
            sys.exit(f"error: overlay {name} is {size} bytes, the window "
                     f"holds {ovl_end - ovl_base}")
        sectors = (size + 511) // 512
        entries.append({"file": oraw.name, "lba": lba, "sectors": sectors})
        directory.append((lba, sectors))
        print(f"overlay {n} {name}: {size} bytes, {sectors} blocks at DAT block {lba}")
        lba += sectors
    # 5. the hull bank, at its fixed sector after the overlays
    hull_lba = int(t["HULL_LBA0"], 8)
    if lba > hull_lba:
        sys.exit(f"error: the overlays run to LBA {lba - 1}, past the hull "
                 f"bank at HULL_LBA0 = {hull_lba}")
    bank = build_dir / "hulls.bin"
    bank_sectors = (bank.stat().st_size + 511) // 512
    if bank_sectors != int(t["HULL_BANK_SECTORS"], 8):
        sys.exit("error: HULL_BANK_SECTORS in build/ships.mac disagrees "
                 "with build/hulls.bin")
    entries.append({"file": bank.name, "lba": hull_lba, "sectors": bank_sectors})
    print(f"hull bank: {bank.stat().st_size} bytes, {bank_sectors} blocks "
          f"at DAT block {hull_lba}")
    # 6. the missions' text bank (build/mistext.bin), after the hull bank
    mt_lba = int(t["MTEXT_LBA0"], 8)
    if mt_lba < hull_lba + bank_sectors:
        sys.exit(f"error: MTEXT_LBA0 = {mt_lba} is inside the hull bank")
    mtext = build_dir / "mistext.bin"
    mt_sectors = mtext.stat().st_size // 512
    entries.append({"file": mtext.name, "lba": mt_lba, "sectors": mt_sectors})
    print(f"mission text: {mt_sectors} blocks at DAT block {mt_lba}")
    dirsec = bytearray(512)
    for n, (l, c) in enumerate(directory):
        dirsec[n * 4:n * 4 + 2] = l.to_bytes(2, "little")
        dirsec[n * 4 + 2:n * 4 + 4] = c.to_bytes(2, "little")
    (build_dir / "ovl_dir.bin").write_bytes(dirsec)
    entries.append({"file": "ovl_dir.bin", "lba": ovl_dir_lba, "sectors": 1})
    # 7. the key file (tools/keyfile.py), which KEY_INIT reads at boot
    entries.append({"file": "keys.bin", "lba": int(t["KEYS_LBA"], 8),
                    "sectors": 1})
    # Resource offsets are relative to ELITE.DAT, never physical disk LBAs.
    dat = bytearray((max(e['lba'] + e['sectors'] for e in entries)+1)*512)
    # Mission messages read two blocks even when their first is the last
    # text block. Preserve the old zero guard sector inside the data file.
    dat[:len(header)] = header
    occupied = {0}
    for e in entries:
        blocks = set(range(e['lba'], e['lba']+e['sectors']))
        if not blocks or min(blocks) < 1 or blocks & occupied:
            sys.exit(f"error: overlapping or invalid DAT extent: {e['file']}")
        occupied.update(blocks)
        payload = (build_dir/e['file']).read_bytes()
        if len(payload) > e['sectors']*512:
            sys.exit(f"error: resource exceeds its DAT extent: {e['file']}")
        dat[e['lba']*512:e['lba']*512+len(payload)] = payload
    (build_dir/'ELITE.DAT').write_bytes(dat)
    (build_dir/'STARTS.COM').write_bytes(
        b'SET TT SCOPE,QUIET\r\nSET USR SWAP\r\nSET EXIT SWAP\r\nR ELITE\r\n')
    manifest = {"format": "rt11", "base": "orig/rt11/RT11BASE.DSK",
                "geometry": {"size": 819200}, "entries": entries,
                "save_files": [f"ELSAV{i}.DAT" for i in range(1, 5)]}
    manifest_path = build_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    # Preserve commander files, migrating legacy raw slots if needed. The manifest
    # creates a pristine image for tests; make run uses saves/elite.dsk.
    pristine = build_dir / "elite-pristine.dsk"
    run_tool(["tools/dsk_build.py", manifest_path, pristine, "--force"],
             "disk build failed")
    from play_disk import refresh
    refresh(pristine, output, manifest_path)
    print(f"built {output}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", nargs="?", default="build/elite.dsk")
    ap.add_argument("--build-dir", default="build")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    build(args.output, args.build_dir, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
