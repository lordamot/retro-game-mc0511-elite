# Ship blueprints, one file per header

These are EXTRACTED FROM ELITE LEGEND by `tools/legend_ships.py`, which
reads `INCLUDE/Ships/d_*D.a80` (the geometry) and `d_*H.a80` (the
headers) under `orig/legend/EliteLegend_v1_09_source`, and
`AdrDataShips` for the numbering.  `make extract-legend` rewrites every
`.txt` here, so hand edits are lost unless you mean to diverge from
Legend on purpose.  (This README is not generated; keep it.)

`tools/ships_gen.py` turns the directory into the resident's tables
(`build/ships.mac`) and the hull bank (`build/hulls.bin`); see
`src/hull.mac` for how the bank reaches the game.

Format (blank lines and `#` comments ignored):

    name     <key, upper case>
    index    <its number in AdrDataShips; 64.. for the headers not in it>
    class    <spawn tier 0..4 - DERIVED, see below>
    speed    <max speed along its nose>
    energy   <what it takes to break it up>
    bounty   <credits for killing it, in tenths>
    laser    <its chance of hitting an Elite pilot, 0..255>
    collide  <collision distance>
    cargo    <Legend's cargo byte: bit 6 + market index for a fixed load,
              bit 7 for the two mission containers, 0 a random load;
              ships_gen.py translates it to what src/cargo.mac reads>
    launch   <what it can launch: the low three bits are how many>
    dot      <distance past which it is drawn as a dot - kept here, not
              in the resident's table: nothing reads it, and its byte
              carries shipnum instead>
    rating   <combat rating points a kill is worth>
    flags    <the header's flag byte>
    flags2   <the byte after it>
    laservert <the vertex its laser fires from>
    type     <bits 0-2 the kind: 0 trader, 1 police, 2 pirate, 3 hunter,
              4 Targon, 5 asteroid, 6 missile, 7 static; 8 boardable,
              16 missile-proof>
    objflags <the object flags byte>
    shipnum  <its number in the ship yard, which a boarding captures
              (src/drone.mac); 64 and up the Targon spy and cruiser>
    radius   <bounding radius, in the same units as the coordinates>
    vertex   <x> <y> <z>                  one per line
    edge     <v0> <v1> <cull> <f1> <f2>   indices, cull, two faces
    normal   <x> <y> <z>                  one per face, outward
    geometry <key>                        instead of geometry: borrow a hull

Axes are x right, y up, z forward - a ship's nose points at +z.

`class` is not Legend's: it is the port's own spawn tier, worked out
from `type`, `objflags` and `energy` by `shiplib.legend_tier`.  Since
2026-09-24 the sky is spawned by Legend's own tables (`src/ai.mac`) and
the record `SHIP_STATS` no longer carries it; it still sorts the tier
lists `HULL_SYSTEM` fills the hull area from, and the missions' "any of
a class".  `type`, `objflags` and `flags` are in the record instead:
they are the ship's mind.

A `NOTE:` at the top of a file says its header's counts disagree with
its data (the Adder claims 15 normals and has 13); the port draws the
data.
