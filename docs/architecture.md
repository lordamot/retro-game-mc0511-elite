# Architecture

## Target and source of truth

Elite Legend's rules and Russian content are adapted to the УКНЦ rather
than emulating the Spectrum or copying its screen layout. The CPU performs
simulation, fixed-point geometry and screen composition; the PPU owns
rasterization, keyboard interrupts and AY playback. RT-11 remains resident.

Readable inputs are under `src/`: MACRO-11 modules and text resources.
`src/elite.list` is the resident's assembly and memory order;
`src/ovl.list` defines overlay numbers and their constituent modules.
`tools/build_elite.py` generates tables, assembles the resident, exports its
symbols, assembles overlays and packages a native RT-11 volume. Build outputs
are reproducible from these inputs, not patched game binaries.

## Launch and restart

1. RT-11 loads `ELITE.SAV` and enters `RT_ENTRY`. It requests memory through
   `146400` octal and verifies the paired header in `DK:ELITE.DAT`.
2. `MAIN_START` allocates/uploads the PPU program, saves firmware state,
   loads overlay metadata, key settings, effects and the hull bank, and
   initializes text.
3. The commander overlay's startup entry displays the welcome and control
   pages. Each requires a distinct ВВОД press; holding the key cannot skip
   both. Latin credits use an overlay-local ROM glyph bank.
4. The title overlay displays the logo, music and version. Fixed keys 1/2
   select GRB/RGB physical palette wiring; an underline marks the choice.
   ФИКС opens the four-slot commander chooser; an empty slot prompts for a name.
5. Flight and docked screens use the resident main loop and screen overlays.

`MAIN_RESTART` reuses the running PPU and loaded banks, resets the stack and
returns to the logo after death or a new-game request. A successful load
from the access menu uses `FLY_LOADED` to resume the selected commander
without repeating the logo. Neither path may upload the dead CPU copy of
the PPU program again. A new `R ELITE` after exit is a fresh launch.

## Module responsibilities

| Area | Source |
|---|---|
| Startup, main loop, views, hyperspace | `main.mac`, `rt11.mac` |
| Universe, movement, geometry and line records | `space.mac`, `math3d.mac`, `ship.mac`, `gfx.mac` |
| Planet, filled sun, stars and beams | `sun.mac`, `stars.mac`, `beams.mac`, body routines in `space.mac` |
| Hull selection and working-model cache | `hull.mac` |
| Commander, equipment, jump effects | `pilot.mac`, `cockpit.mac`, `jump_ship.mac` |
| Lasers, missiles, damage, collisions | `combat.mac`, `cargo.mac` |
| Docking, bases and distant fields | `dock.mac`, `bases.mac`, `asteroids.mac` |
| AI, drive, boarding and portals | resident entry helpers plus `ai_fly.mac`, `jdrive_fly.mac`, `drone_fly.mac`, `portal_fly.mac` in the flight overlay |
| Player Targlets and targeting | `alien.mac`, `drone.mac`, flight entries |
| Galaxies, markets and carrier records | `galaxy.mac`, `market.mac`, `contract.mac` |
| Mission state and flight hooks | `mission.mac`, `mission_fly.mac` |
| HUD, gauges, compass and indicators | `hud.mac`, `navigation.mac`, `indicators.mac` |
| Screen pages | `ovl_*.mac`, `title.mac`, `splash.mac` |
| Saving and overlay loading | `save.mac`, `ovl.mac`, `rt11.mac` |
| Text, names and keyboard | `text.mac`, `name.mac`, `nameask.mac`, `input.mac` |
| PPU lifecycle, clock, drawing and sound | `ppucomm.mac`, `ppu.mac`, `ppu_keys.mac`, `sync.mac`, `sound.mac`, `ppu_sfx.mac` |
| Controlled drawing measurement | `harness.mac` |

All source paths in this table are relative to `src/`.

## Overlay ownership

The CPU has one 5120-byte overlay window. Only resident code loads an
entry; an overlay returns to the resident before another replaces it.
The flight overlay must be loaded before calls through `FV_*`. Persistent
state belongs in resident data, never in a reloadable overlay.

The cache reserves PPU RAM for flight and other entries. The outfitter and
carrier market use plane 0 above the displayed screen. Title and commander
pages are not cached. Entries are cached before execution, so a reload
restores the built image. Cache allocation is bounded and does not evict
entries during a screen cycle. The SFX entry is exceptional: its PPU copy
is live mutable engine state and must never be copied back to the CPU.

A table included in an overlay occupies space even if that overlay reads
only one column. Generators emit `--part` subsets, and text sections name
which overlays own them. Preserve that separation when adding content.

## Data representation

- Sixteen universe slots use signed 32-bit positions and Q14 orientation
  matrices. Near-range routines explicitly validate 16-bit coordinates.
- The hull bank holds 55 geometries shared by 69 role headers. Its vertices
  are scaled by four; edge vertex indices are doubled word offsets.
  Readable blueprints retain their original units.
- The per-system roster has a logical 5120-byte selection budget, with
  aliases sharing geometry. `SHIP_TABLE` stores video-bank addresses;
  `HULL_FETCH` supplies one CPU working model, not a persistent CPU pointer
  for every selected hull.
- `pilot.mac` stores Legend's fields in PDP-11-friendly packing: 32-bit
  values are low word then high, byte runs are aligned, and several fields
  are words. This is not a binary-compatible Spectrum save file.
- The commander is 772 bytes; the disk file is two 512-byte blocks.
  Device bytes use bit 7 for absent and bit 6 for broken. A fitted type-zero
  device is valid. Contracts have 14-byte port records and six player slots.
- Ship limits come from cockpit blocks. Dashboards are parametric layouts
  using Legend's scanner artwork, rather than twenty copied Spectrum panels.

## Presentation and timing

The cockpit view is 640×200 above an 88-line dashboard. Text pages can use
all 288 lines; returning to flight restores an invalidated dashboard.
Normal body text uses the 8×11 UKNC ROM font; `PUTS2` is double width.

The CPU maintains two previous/current line-record lists and emits only
changed XOR walks. The PPU consumes a 256-record ring. The filled sun has
its own span differencing; stars use a private deterministic state rather
than advancing gameplay randomness. See [rendering](rendering.md).

The PPU publishes the 50 Hz clock and acknowledged input-edge packets.
No CPU interrupt vector is replaced. `VSYNC_PACE` caps a fast flight loop
at the clock rate but does not impose another tick on a frame that already
outlasted one. AI decisions remain frame-based. Clock-driven gameplay must
use `FRAMES`, not docked loop iterations.

Legend's 26 AY effects run on the first chip. The port's Blue Danube plays
on the second at the title and during docking; there is no flight music
or PT3 player. CPU requests go through `SFX_PLAY` and `TUNE`.
