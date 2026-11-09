#!/usr/bin/env python3
"""Build a UKNC disk image from a JSON manifest.

For format=rt11, copy the supplied base volume and install ELITE.SAV,
ELITE.DAT and STARTS.COM as normal files. Resource entries in that
manifest describe file-relative DAT blocks for inspection/rebuilding.

Legacy manifests without format retain the old raw layout support:
geometry.size gives the image size (default 819200 bytes); entries give
file paths relative to the manifest, physical lba and reserved sectors.
Omitted lba follows the previous entry, omitted sectors rounds file size
up to 512 bytes, and gaps are zero-filled. This compatibility path is
not the current game's loader or save mechanism.

Usage: python3 tools/dsk_build.py MANIFEST.json OUTPUT.dsk [--force]
"""

import argparse
import json
import sys
from pathlib import Path

SECTOR = 512


def build(manifest_path, output_path, force=False):
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    if output_path.exists() and not force:
        sys.exit(f"error: {output_path} exists (use --force to overwrite)")

    with open(manifest_path) as f:
        manifest = json.load(f)

    if manifest.get("format") == "rt11":
        from rt11_disk import build_image
        build_image(manifest, manifest_path.parent, output_path)
        return

    size = manifest.get("geometry", {}).get("size", 819200)
    image = bytearray(size)
    next_lba = 0

    for entry in manifest["entries"]:
        path = manifest_path.parent / entry["file"]
        data = path.read_bytes()
        lba = entry.get("lba", next_lba)
        sectors = entry.get("sectors", (len(data) + SECTOR - 1) // SECTOR)
        if len(data) > sectors * SECTOR:
            sys.exit(f"error: {path.name} is {len(data)} bytes, "
                     f"exceeds its {sectors}-sector budget "
                     f"({sectors * SECTOR} bytes)")
        start = lba * SECTOR
        end = start + sectors * SECTOR
        if end > size:
            sys.exit(f"error: {path.name} at LBA {lba} runs past the disk end")
        if any(image[start:start + len(data)]):
            sys.exit(f"error: {path.name} at LBA {lba} overlaps a previous entry")
        image[start:start + len(data)] = data
        print(f"  LBA {lba:4d} +{sectors:3d}  {path.name}  ({len(data)} bytes)")
        next_lba = lba + sectors

    output_path.write_bytes(image)
    print(f"wrote {output_path}: {size} bytes")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("output")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    build(args.manifest, args.output, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
