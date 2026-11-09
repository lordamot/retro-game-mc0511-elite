#!/usr/bin/env python3
"""Refresh a playable disk's program while preserving all four commanders.

The manifest selects RT-11 files or the legacy reserved save area. A player disk belongs
under saves/, outside make clean's build directory.  Publishing is atomic;
the previous complete image is retained as .bak before an update.
"""
import argparse
import json
import os
from pathlib import Path


def refresh(source, output, manifest):
    source, output = Path(source), Path(output)
    layout = json.loads(Path(manifest).read_text())
    image = bytearray(source.read_bytes())
    if len(image) != layout["geometry"]["size"]:
        raise ValueError("invalid disk size")
    old = output.read_bytes() if output.exists() else None
    if layout.get('format') == 'rt11':
        from rt11_disk import slot_files, install_slots
        from rt11fs import Volume
        if old is not None:
            slots = slot_files(output)
            volume = Volume(source)
            install_slots(volume, slots, source.parent)
            image = volume.img
    else:
        area = layout['save_area']
        start, size = area['lba']*512, area['sectors']*512
        if start+size > len(image):
            raise ValueError('invalid save area')
        if old is not None:
            if len(old) != len(image):
                raise ValueError('existing player disk has a different size; left untouched')
            image[start:start+size] = old[start:start+size]
    if old == image:
        output.touch()
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    if old is not None:
        output.with_suffix(output.suffix + ".bak").write_bytes(old)
    pending = output.with_suffix(output.suffix + ".new")
    with pending.open("wb") as stream:
        stream.write(image)
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(output)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source")
    ap.add_argument("output")
    ap.add_argument("--manifest", default="build/manifest.json")
    args = ap.parse_args()
    refresh(args.source, args.output, args.manifest)


if __name__ == "__main__":
    main()
