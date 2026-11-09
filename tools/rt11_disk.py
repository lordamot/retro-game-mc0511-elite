#!/usr/bin/env python3
"""Build native RT-11 Elite disks and extract commanders for safe refresh."""
from pathlib import Path
import struct
import tempfile
from rt11fs import Volume

ROOT = Path(__file__).resolve().parent.parent
SLOTS = tuple(f'ELSAV{i}.DAT' for i in range(1, 5))
# Fixed NOP/branch/trap/K2-send instructions of Elite's previous bootstrap.
# A NOP alone also identifies ordinary RT-11 disks and is not sufficient.
LEGACY_PREFIX = bytes.fromhex(
    'a000110106000200f795ff008c00c215a400c315050002019f94befddf8bbcfdfd80')


def slot_files(path):
    """Return exact slot bytes from RT-11 or the previous raw Elite layout.

    Unknown images and damaged legacy records are rejected, never silently
    replaced. Files from RT-11 are preserved even when the game rejects them.
    """
    path = Path(path)
    data = path.read_bytes()
    if len(data) != 819200:
        raise ValueError('existing player disk has a different size; left untouched')
    # Both boot sectors begin with NOP. Recognize the RT-11 directory first.
    try:
        volume = Volume(path)
        native = volume.find('RT11SJ.SYS') and volume.find('ELITE.SAV')
    except (ValueError, IndexError, struct.error, SystemExit):
        native = False
    if native:
        return {name: bytes(volume.img[e.block*512:(e.block+e.length)*512])
                for name in SLOTS if (e := volume.find(name))}
    if data.startswith(LEGACY_PREFIX):
        slots = {}
        for i, name in enumerate(SLOTS):
            record = data[(100+i*2)*512:(102+i*2)*512]
            if not any(record):
                continue
            if struct.unpack_from('<HH', record) != (0o66153, 2):
                raise ValueError(f'legacy slot {i+1} is unrecognized; disk left untouched')
            slots[name] = record
        return slots
    raise ValueError('not a recognized Elite player disk; left untouched')


def install_slots(volume, slots, directory):
    directory = Path(directory)
    with tempfile.TemporaryDirectory(dir=directory) as scratch:
        for name, data in slots.items():
            p = Path(scratch)/name
            p.write_bytes(data)
            volume.put(name, p)


def build_image(manifest, directory, output):
    directory = Path(directory)
    volume = Volume(ROOT/manifest['base'])
    for name in ('ELITE.SAV', 'ELITE.DAT', 'STARTS.COM'):
        volume.put(name, directory/name)
    volume.save(output)
