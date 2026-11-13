# Memory map

Snapshot of the v0.8.2 build with renderer speed optimizations, checked on
2026-11-13 against `src/defs.mac`,
`build/elite.lst` and `build/manifest.json`. Addresses are **octal**; sizes
and file-block numbers are decimal. End addresses are exclusive. Recheck
the listing after a rebuild; limits are enforced by `src/tail.mac`, the
generated hull tables and `tools/build_elite.py`.

## CPU address space

| Region | Start | End (exclusive) | Bytes |
|---|---|---|---:|
| RT-11 low memory, vectors and job header | 000000 | 001000 | 512 |
| Resident code/data | 001000 | 131722 | 45522 |
| Resident reserve | 131722 | 132400 | **302** |
| Downward game stack | 132400 | 133400 | 512 |
| One CPU working hull | 133400 | 134400 | 512 |
| Overlay window | 134400 | 146400 | 5120 |
| Monitor and transient USR | above requested limit | | |

`RT_ENTRY` starts at 001000, with the initial stack at 001000. `.SETTO`
requests 146400 (52,480 bytes), then startup changes to the game stack.
The supplied SJ monitor returned 146556..146616 with USR swapping enabled;
with USR NOSWAP it returned only 136556. Both `SET USR SWAP` **and**
`SET EXIT SWAP` are required. The stack, file-call argument areas and PPU
mailboxes must remain below the swapped USR region. The overlay window may
be swapped out temporarily during a monitor call; request state stays resident.
CPU interrupt vectors remain the monitor's throughout play.

The CPU keeps one 512-byte working hull.
`SHIP_TABLE` contains video-bank word addresses; `HULL_FETCH` resolves one
model into the CPU buffer and retains it until another model is needed.
The logical roster still has a 5120-byte budget, including alias sharing,
which bounds the set available to a system. The largest current record is 480 bytes.
The full bank is loaded once; fetching a working model never reads disk.

### Shared buffers and the dead PPU copy

The two contiguous segment buffers each use 960 bytes. Save I/O drains and
resets rendering, then uses their first 1024 bytes (`SAVE_BUFFER = SEGBUF`)
to stage the 772-byte commander plus zero padding. Loading validates file
length and record signature/version before replacing the live commander.
No save transfer buffer occupies the active overlay or USR swap region.

After `PP_MAIN_LOAD`, live buffers overwrite 113656..122246.
Published PPU words start at 122376: **88 bytes remain**.
Nothing may read these buffers before initialization; the SAV initially
contains PPU instructions there. The reused buffers are `UNIV`, `NPSHOT`,
`SVX`, `SVY`, `SVOK`/`SVNEED`/`CO_R`, `SVLIST`, `SLIST`, `EXPTAB`,
`BENCH_BUF`, `LREC`, `VIEW_MAT`, `OVL_DIR`/`OC_TAB`, `ST_PRICE`, `AST_QTY`,
`HUD_LAST`, `PLANET_CT`, `FPAIR` and the 400-byte sun span cache `SU_SPAN`.

`SCRATCH` aliases the first 256 bytes of the 334-byte geometry workspace
beginning at `SVX`; commander-name reads finish before a hull is drawn.
The PPU consumes copied ring records and does not read these geometry
buffers. `FPAIR` is initialized once per restart after the PPU copy is dead.

## Overlays and files

The disk is a normal 1600-block RT-11 volume with an unchanged system
bootstrap. RT-11 loads `ELITE.SAV`; the game opens `DK:ELITE.DAT` on
channel 0 and uses `.READW` with **file-relative** blocks. Constants with
`LBA` in their names and manifest entries now refer to these DAT offsets,
not physical disk sectors. The data file can be moved on the volume.
`elite.raw` is an internal debugger copy of the SAV, not a custom loader.

| # | Overlay | Bytes | Free in window | DAT block | Blocks |
|---:|---|---:|---:|---:|---:|
| 0 | title | 4352 | 768 | 3 | 9 |
| 1 | charts | 1977 | 3143 | 12 | 4 |
| 2 | info | 1725 | 3395 | 16 | 4 |
| 3 | trade | 1863 | 3257 | 20 | 4 |
| 4 | cmdr | 2764 | 2356 | 24 | 6 |
| 5 | pilot | 3425 | 1695 | 30 | 7 |
| 6 | equip | 4959 | 161 | 37 | 10 |
| 7 | yard | 3943 | 1177 | 47 | 8 |
| 8 | save | 1395 | 3725 | 55 | 3 |
| 9 | carrier | 4269 | 851 | 58 | 9 |
| 10 | ctgen | 2158 | 2962 | 67 | 5 |
| 11 | fly | 4844 | 276 | 72 | 10 |
| 12 | mission | 2020 | 3100 | 82 | 4 |
| 13 | dash | 2472 | 2648 | 86 | 5 |
| 14 | pause | 1004 | 4116 | 91 | 2 |
| 15 | sfx | 3622 | 1498 | 93 | 8 |

| Resource | DAT block | Blocks |
|---|---:|---:|
| SAV/DAT pairing header | 0 | 1 |
| Overlay directory | 1 | 1 |
| Key tables and options | 2 | 1 |
| Overlays | 3 | 98 |
| Hull bank (13,612 bytes) | 101 | 27 |
| Mission text | 128 | 15 |
| Zero guard for two-block message reads | 143 | 1 |

`ELITE.DAT` is 144 blocks. `ELSAV1.DAT`..`ELSAV4.DAT` are independent
two-block files, accessed on channel 1. Replacement uses ENTER/WRITW/CLOSE;
a failed tentative write is purged. The build/refresh tools migrate legacy
raw slots at physical blocks 100..107, preserving bytes and a full backup.
Those old addresses are used only by the host-side migration tool.

The commander overlay carries the two startup pages and their Latin ROM
glyphs. The title overlay carries its own copy of the Latin renderer and
glyph bank for GRB/RGB labels; neither adds a resident font bank.

The overlay window has one tenant. Resident code calls flight code only
through `FV_*` during the flight frame. Sound executes from its mutable
PPU cache, never from the CPU window.

## PPU and video planes

The copied PPU program is 3424 bytes, followed in its firmware allocation by a
2392-byte backup of the terminal line-table region (02300..07027).
This backup is allocated dynamically and is not stored in the CPU image.
Saved scalar state includes firmware row/scroll settings, receiver-enable
bits, drawing registers and interrupt vectors. `PP_RESTORE` reinstates
these, stops sound and publication; the CPU then frees the PPU program
and overlay cache and returns through RT-11 `.EXIT`.

The PPU overlay cache is **14 KiB** (7168 words). The firmware restore backup has a separate
allocation budget within the PPU program block. Plane 0 above the screen holds overflow
cache entries. Each displayed plane uses 23,040 bytes (640×288), leaving
9728 bytes above the screen. Planes 1 and 2 hold the interleaved 13,612-byte
hull bank there. CPU accesses below plane address 0100000 reach CPU RAM,
not video memory. Never draw below that boundary or past the screen end.

The PPU consumes a ring of 256 three-word walk records and publishes the
50 Hz clock and acknowledged keyboard-edge packets. It retains the Blue
Danube score and AY effect engine. Sound's cache is mutable engine state;
never copy it back into the CPU overlay window. A bitmap back buffer
does not fit; rendering differences line records and sun spans.

See [architecture](architecture.md) for ownership and [RT-11](rt11.md)
for file calls, failure handling and player-disk migration.
