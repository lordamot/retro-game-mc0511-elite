---
name: elite-tools
description: Refresh an MC-0511 Elite player disk without losing commanders, run the project's regression checks, or measure its renderer with the fixed-scene and drawing-only tools.
---

# Elite disk and measurement tools

Run commands from the repository root. Read the current state in
[documentation index](../../../docs/README.md); consult
[tools.md](../../../docs/tools.md) for additional CLI options.

The original game references, RT-11 inputs and `bin/` installation are
local/ignored. Follow [checkout setup](../../../docs/setup.md) in a fresh
checkout; `make toolchain` does not supply the RT-11 base or macro library.

## Refresh a playable disk

`make run` builds the game, refreshes `saves/elite.dsk`, then opens SDL.
For a refresh without starting the emulator:

```sh
make build
python3 tools/play_disk.py build/elite.dsk saves/elite.dsk --manifest build/manifest.json
```

Use the user's chosen disk path when supplied. The refresh preserves the
four RT-11 commander files `ELSAV1.DAT` through `ELSAV4.DAT`, including
files whose records the game would reject. Legacy raw disks migrate their
four two-sector records without changing record bytes. The preceding full
image is retained as `.bak`, and publication uses a temporary `.new` file.
An unknown image, mismatched size or unrecognized legacy record raises an
error without replacing the disk. Investigate instead of deleting it.
The tool does not translate commander-record versions. Refresh replaces
other files with the build's base volume; preserve unrelated user files
separately if the player has added any.

Keep player disks outside `build/`, which `make clean` removes. Do not
reconstruct a player's image directly with `dsk_build.py`: that creates a
pristine disk. Verification reconstructs disposable images under `tmp/`.

The disk contains `ELITE.SAV` and `ELITE.DAT`; native RT-11 calls locate
all resources by filename and file-relative block. `STARTS.COM` sets both
`SET USR SWAP` and `SET EXIT SWAP`. Keep both settings: EXIT NOSWAP is unsafe for subsequent boots after
swap-file writes. The volume must be writable for
RT-11 swapping even when the player is only loading files. Tab then X (АР2 then Ч) exits to
RT-11 without saving. The `rt11` group checks real save/overwrite/load,
full disk and invalid records, DAT relocation and pairing, legacy migration,
cold reboot and repeated exit/relaunch with stable PPU allocations.
Keep `RT_IOBUSY` around native file operations: the long PPU sound/input
tick can cause firmware read errors without it. The keyboard IRQ queues edges
during I/O; a regression checks a complete short press across that pause.

## Verify rules and integration

`make verify` builds and runs the complete suite. After a relevant narrow
change, these groups exercise native I/O, save preservation and Legend rules:

```sh
python3 -u tools/verify_build.py --only rt11
python3 -u tools/verify_build.py --only completion
python3 -u tools/verify_build.py --only rules
```

For scripted nonmodal navigation use `verify_build.ui_ready(t)`: it waits
for the main loop after I/O and clears the 25-frame screen-switch lockout.
Name and mission prompts are modal and need their own waits. PPU-cache
checks observe `RT_BLOCK` to prove DAT reads are avoided; native RT-11
reads have variable monitor/rotational latency.

Run verification processes sequentially: some groups share a
disposable disk. Do not rebuild while an emulator suite is running; its
symbol addresses and disk must belong to the same build. A missing peek,
nonzero emulator exit or zero-assertion group is a failure, not a skip.

## Measure the renderer

The font resource is `src/res/font/uknc11.txt`, the unscaled 8x11 startup
font remapped to KOI-7. Reproduce it for comparison with
`python3 tools/font_gen.py bin/ukncbtl/uknc_rom.bin --uknc-rom --out tmp/uknc11.txt`.
Do not crop the extra rows: Cyrillic accents and descenders use them.
The rules group's renderer checks compare every glyph with the ROM and
check normal, double-width and quadruple-size pixels, full-height erasure,
mission row bounds and dashboard restoration after full-height text pages.

```sh
python3 tools/bench.py --fixed --ticks 1200 --shot tmp/still.png
python3 tools/bench.py --fixed --ticks 1200 --moving --shot tmp/moving.png
python3 tools/bench.py --fixed --ticks 1200 --turning --shot tmp/turning.png
python3 tools/harness.py --turning --no-stars
```

The ordinary benchmark measures whole-game frames. An emulator `run` tick
is **1/25 second**. The drawing harness measures 100 render frames by
**50 Hz interrupts**, draining the PPU at both ends; `--no-stars` is an
ablation, not the shipped appearance. Do not compare its fps directly to
whole-game fps. See [rendering reference](../../../docs/rendering.md).

Compare the same benchmark revision and fixed scene. Inspect the ending
screenshot when a rate changes unexpectedly: fillers that die or a scene
that runs away invalidate the comparison. For a change claiming unchanged
wireframe geometry, capture before/after snapshots with `seg_snapshot.py`
and compare them; this does not validate filled pixels, text or effects.

Use `bench.py --sparse` for a separate five-object workload with empty
spare slots, ambient traffic disabled and an unmanned station. The whole-game
benchmarks check the slot roster and fail if it changes. Report it separately from the filled
sixteen-slot benchmark; a gain from rejecting distant collision candidates
will be larger in the latter. The rules group includes exact integer
matrix and fused-projection cases, filled-sun pixel comparisons, and a
paired-queue wraparound/full-ring test (`verify_render.py`). These RAM
probes run while docked so they never replace an executing flight overlay.

Record the measured cost and remaining memory from the build. The
[memory map](../../../docs/memory-map.md) documents tight resident
and overlay bounds; predicted architectural gains are not measurements.
