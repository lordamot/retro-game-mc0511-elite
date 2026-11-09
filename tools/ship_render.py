#!/usr/bin/env python3
"""ship_render.py - draw a ship blueprint to a PNG, the way the port does.

Runs the same pipeline as src/math3d.mac and src/ship.mac in Python -
rotate, perspective-project with the 5/3 stretch that the УКНЦ's tall
narrow pixels need, draw the edges - so a shape can be checked by eye
without building a disk and booting the emulator.

    python3 tools/ship_render.py src/res/legend/ships/cobramk3ht1.txt out.png
    python3 tools/ship_render.py src/res/legend/ships --sheet out.png
"""

import argparse
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shiplib                                    # noqa: E402

PROJ_D = 384.0
XASP = 5.0 / 3.0


def rotate(v, yaw, pitch, roll):
    x, y, z = v
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, z = x * cy + z * sy, -x * sy + z * cy
    cp, sp = math.cos(pitch), math.sin(pitch)
    y, z = y * cp - z * sp, y * sp + z * cp
    cr, sr = math.cos(roll), math.sin(roll)
    x, y = x * cr - y * sr, x * sr + y * cr
    return x, y, z


def visible_faces(ship, yaw, pitch, roll, dist):
    """Which faces point at the eye, the way src/ship.mac decides it.

    The eye is the origin and the hull's centre is at P, so the vector
    from a face to the eye is -P and an outward normal N faces us when
    N . P < 0.  Rather than rotate every normal into camera space, the
    ship's position is rotated into MODEL space once - the matrix is
    orthonormal, so that is its transpose - and the normals are used as
    they are stored.  Three multiplies a face instead of twelve.
    """
    if not ship.normals:
        return None                     # no normals: everything is visible
    # P in camera space is (0, 0, dist); the transpose of the rotation
    # takes it back into model space.
    px, py, pz = untransform((0.0, 0.0, dist), yaw, pitch, roll)
    return [nx * px + ny * py + nz * pz < 0 for nx, ny, nz in ship.normals]


def untransform(v, yaw, pitch, roll):
    """The inverse of rotate(): the same turns, backwards and negated."""
    x, y, z = v
    cr, sr = math.cos(-roll), math.sin(-roll)
    x, y = x * cr - y * sr, x * sr + y * cr
    cp, sp = math.cos(-pitch), math.sin(-pitch)
    y, z = y * cp - z * sp, y * sp + z * cp
    cy_, sy_ = math.cos(-yaw), math.sin(-yaw)
    x, z = x * cy_ + z * sy_, -x * sy_ + z * cy_
    return x, y, z


def draw_ship(ship, img, cx, cy, dist, yaw, pitch, roll, scale=1.0,
              cull=True):
    d = ImageDraw.Draw(img)
    pts = []
    for v in ship.vertices:
        x, y, z = rotate(v, yaw, pitch, roll)
        z += dist
        if z < 24:
            pts.append(None)
            continue
        pts.append((cx + x * PROJ_D / z * XASP * scale,
                    cy - y * PROJ_D / z * scale))
    vis = visible_faces(ship, yaw, pitch, roll, dist) if cull else None
    for a, b, _, f1, f2 in ship.edges:
        if vis is not None and not (vis[f1] or vis[f2]):
            continue                    # both its faces point away
        if pts[a] and pts[b]:
            d.line([pts[a], pts[b]], fill=255, width=1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("source", help="a blueprint file, or the directory")
    ap.add_argument("out")
    ap.add_argument("--sheet", action="store_true",
                    help="render every ship in the directory")
    ap.add_argument("--dist", type=float, default=900.0)
    ap.add_argument("--yaw", type=float, default=35.0)
    ap.add_argument("--pitch", type=float, default=20.0)
    ap.add_argument("--roll", type=float, default=0.0)
    ap.add_argument("--no-cull", action="store_true",
                    help="draw the far side too, as the port used to")
    args = ap.parse_args(argv)

    rad = math.radians
    if os.path.isdir(args.source) or args.sheet:
        ships = shiplib.read_dir(args.source)
        cols = 3
        rows = (len(ships) + cols - 1) // cols
        cw, ch = 213, 144
        img = Image.new("L", (cols * cw, rows * ch), 0)
        d = ImageDraw.Draw(img)
        for i, s in enumerate(ships):
            cx = (i % cols) * cw + cw // 2
            cy = (i // cols) * ch + ch // 2
            s = shiplib.hull_of(s, ships)   # a borrowed hull draws as itself
            dist = args.dist * max(1.0, s.radius / 110.0)
            draw_ship(s, img, cx, cy, dist,
                      rad(args.yaw), rad(args.pitch), rad(args.roll),
                      cull=not args.no_cull)
            d.text((cx - cw // 2 + 4, cy - ch // 2 + 4), ships[i].key,
                   fill=160)
        img.save(args.out)
        print(f"-> {args.out}: {len(ships)} ships")
    else:
        s = shiplib.read_ship(args.source)
        img = Image.new("L", (640, 400), 0)
        draw_ship(s, img, 320, 200, args.dist,
                  rad(args.yaw), rad(args.pitch), rad(args.roll), scale=2.0,
                  cull=not args.no_cull)
        img.save(args.out)
        print(f"-> {args.out}: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
