# Project tools

Run Python 3 CLIs from the repository root; use each tool's `--help` for
its exact options. Most use the standard library. Image tools need Pillow;
PDF generation also needs Chrome/Chromium, and previews use Poppler.
`bin/` is an ignored local installation of the assembler, firmware and
emulator runners. See [checkout setup](setup.md) for required RT-11 inputs
and optional reference originals.

## Build and disk operations

| Tool / target | Purpose |
|---|---|
| `make build`, `build_elite.py` | Generate resources, assemble resident/overlays, link SAV and package DAT on a bootable RT-11 volume |
| `savlink.py` | Resolve MACRO-11 object relocation and write the RT-11 SAV job header |
| `obj2bin.py` | Link overlay objects to flat images |
| `dsk_build.py` | Construct a disk from a manifest; use for pristine disks, not player refresh |
| `rt11_disk.py` | Package native files, read commander files and recognize legacy raw slot data |
| `rt11fs.py` | Inspect and edit the RT-11 filesystem with RAD50 names |
| `rt11_home.py` | Inspect/set disk naming metadata |
| `play_disk.py` | Refresh code/resources while preserving commanders and a complete previous-image backup |
| `make run` | Build, refresh `PLAY_DSK` (default `saves/elite.dsk`) and start SDL |
| `make clean` | Remove `build/`; leave `saves/` intact |

```sh
python3 tools/rt11fs.py ls build/elite.dsk
python3 tools/rt11fs.py get build/elite.dsk ELITE.SAV tmp/ELITE.SAV
python3 tools/play_disk.py build/elite.dsk saves/elite.dsk --manifest build/manifest.json
make run PLAY_DSK=saves/another.dsk
```

The RT-11 base and macro library must be supplied locally; they are not
tracked or fetched by the toolchain. The build reads `src/elite.list` and `src/ovl.list`, uses
`orig/rt11/SYSMAC.SML`, and installs `ELITE.SAV`, `ELITE.DAT` and
`STARTS.COM` on the supplied base volume. Generated overlay symbols come
only from the resident listing. File offsets in `build/manifest.json`
are DAT-relative, not physical sectors. The paired identity header catches
mismatched SAV/DAT builds.

Refresh is not a general filesystem merge: it retains the four commander
files and replaces other contents with the build volume. Native invalid
records are preserved; unrecognized legacy records fail safely. See
[RT-11](rt11.md) for backup, migration and swap requirements.

## Resource generators

The build invokes the generators automatically. Editable resources remain
under `src/res/`; generated `.mac` and binary output goes under `build/`.

| Tools | Input and result |
|---|---|
| `ships_gen.py`, `shiplib.py` | Legend text blueprints → resident statistics/type/alias tables and `hulls.bin`; validate model limits and geometry sharing |
| `market_gen.py` | 38 Legend goods → market records and KOI-7 names |
| `legend_gen.py` | 49 equipment rows → names, fit-device mapping, tech/gating and prices; `--part names` / `--part price` avoid unused overlay columns |
| `catalog_gen.py` | Ship catalogue → prices, fit masks, dates, cockpit/hull mappings and availability; `--part fit` serves the outfitter |
| `cockpit_gen.py` | Cockpit blocks/catalogue → missile, energy, fuel, turret, scanner and tonnage limits |
| `text_gen.py` | Russian strings/pairs → resident strings and `@overlay`-selected sections |
| `planet_gen.py` | Extracted world vocabulary → description pointer tables |
| `font_gen.py` | Readable 8×11 UKNC ROM glyphs → KOI-7 font; `--prefix SPLAT` builds the startup/title Latin bank |
| `mission_text.py` | Legend mission messages → `mistext.bin` and label/offset tables |
| `logo_gen.py`, `scanner_gen.py` | Editable pixel text → title/scanner run-length streams |
| `music_gen.py` | `NOTE FRAMES` score → period/volume/duration table for the second AY |
| `sfx_gen.py` | Editable effect frames → position-independent SFX data; `--check` compares against Legend |
| `keyfile.py` | Binding/options text → four fixed-capacity PPU tables and DAT key block |

Hull bank vertices are scaled by four and edge indices by two; the text
blueprints are not. `HULL_OFF` and `SHIP_TABLE` describe the video bank,
with runtime selection and fetching handled by `hull.mac`.

Mission text converts Legend controls to the port's cursor/system/galaxy/
pause controls, expands submessages and writes KOI-7. Each message fits
within the two blocks read by the mission overlay. DAT ends with a zero
guard block for the final read.

The normal font resource is `src/res/font/uknc11.txt`; `height 11` and
`FONT_H` must agree. All accent/descender rows are retained. The generated
filename `build/font8.mac` does not imply an eight-row font. Reproduce the
ROM extraction without modifying the maintained source:

```sh
python3 tools/font_gen.py bin/ukncbtl/uknc_rom.bin --uknc-rom --out tmp/uknc11.txt
```

The Latin bank is `src/res/font/latin11.txt`, assembled separately in the
startup and title overlays. Their `<ASCII>` spans use `src/latin.mac`;
ordinary game text retains KOI-7.

A score uses `R` for rest; `#` begins a comment only at line start or after
whitespace so `F#4` remains a note. Periods target the AY module's 1.77 MHz
clock; emulator chip timing can produce a different pitch.

## Keyboard configuration

```sh
python3 tools/keyfile.py --names
python3 tools/keyfile.py src/res/setup.txt --check
python3 tools/keyfile.py tmp/my-keys.txt --disk tmp/custom.dsk
```

`--disk` locates `ELITE.DAT` in the RT-11 directory and atomically replaces
its key block while preserving other bytes. `KEY_INIT` validates the magic
before copying settings over the PPU tables. A layout/capacity change needs
a matching magic change. A normal player-disk refresh restores the build's
DAT, so maintain desired default bindings in `src/res/setup.txt` or reapply
customization after refresh. [KEYBOARD.md](../KEYBOARD.md) explains row
release conflicts and raw typing.

## Extraction and reference tools

Extraction rewrites maintained resources; use deliberately and review diffs.

| Command / tools | Purpose |
|---|---|
| `make extract` | Extract only world-description vocabulary from `orig/ELITE.SCL` |
| `make extract-legend` | Run `legend_ships.py`, `legend_tables.py`, `legend_text.py` into Legend resources |
| `ships_extract.py`, `tables_extract.py` | Inspect/extract the 1985 roster and commodity/name tables; not the active Legend roster generators |
| `planet_extract.py` | Decode original species/description vocabulary; `--raw` omits localization glyph fixups |
| `logo_gen.py --extract`, `scanner_gen.py --extract`, `sfx_gen.py --extract` | Recreate readable artwork/effects from original assets |
| `elite_re.py` | Read SCL catalogue, rebuild the Spectrum memory image and decode text |
| `z80_trace.py`, `z80dis.py`, `z80_disasm.py` | Reachability tracing and disassembly |
| `zx_view.py` | Render Spectrum memory/graphics |
| `tap_extract.py` | Extract tape blocks |
| `basiclib.py`, `basic_detokenize.py` | Spectrum BASIC tokens, hidden numbers and loader listing |
| `ship_render.py` | Render blueprints with the port's projection/culling model; `--sheet` and `--no-cull` aid inspection |

```sh
python3 tools/elite_re.py catalogue
python3 tools/elite_re.py strings --from 0xF120 --to 0xF600
python3 tools/elite_re.py image tmp/spectrum.bin
```

`legend_build.py` copies reference sources under `tmp/legend-build` and
uses the bundled author's sjasmplus 1.07 through Wine. `--run` launches
the resulting 128K snapshot in ZEsarUX; `--shot` captures it. `make legend`
is this reference workflow, not the UKNC build. A different assembler
version is not assumed equivalent. `zx_control.py` drives ZEsarUX keys,
memory and screenshots through its remote protocol. Sources, formats and
provenance are in [reference sources](reference-sources.md).

## Emulator and symbols

```sh
python3 tools/uknc_control.py boot --disk build/elite.dsk --shot tmp/logo.png
python3 tools/uknc_control.py keys
python3 tools/uknc_control.py script tmp/check.script --disk tmp/test.dsk
```

`boot` ends at the Elite logo after passing the two startup pages. `play`
adds named keys after that; `script` executes a supplied raw script.
`make shot` builds and captures a logo proof of life. The headless emulator
is `bin/ukncbtl/uknc-headless`; the interactive one is `uknc-play`.
The player uses the core's `FRAMERATE` (currently 50 Hz) and `SAMPLERATE`
(22050 Hz) together. It queues zero-valued silence without a fixed offset,
primes three frames before playback, and re-primes after an underrun.
`python3 tools/build_toolchain.py --only headless` rebuilds both runners
and checks the real player loop against a deterministic audio sink before
installing them. No audio hardware or player disk is used by that check.

The raw command parser is in `tools/uknc-headless/main.cpp`. Common commands:

```text
timing
run N
runrel OCTAL_ADDRESS DECIMAL_COUNT [DECIMAL_LIMIT]
waitcpu OCTAL_ADDRESS OCTAL_VALUE DECIMAL_LIMIT
runpc OCTAL_ADDRESS DECIMAL_LIMIT
press CODE [HOLD]
keydown CODE
keyup CODE
screenshot tmp/screen.bmp
peekcpu OCTAL
pokecpu OCTAL B B ...
dumpcpu OCTAL DECIMAL_LENGTH tmp/ram.bin
regs
wavstart
wavstop tmp/audio.wav
quit
```

Scancodes and CPU addresses are octal; dump lengths are decimal. `run N`
uses core frames: `timing` reports frames per second. The current core uses
1/50-second ticks; older builds used 1/25 second. Prefer `verify_build` startup constants and
`ui_ready` over hard-coded old delays. Screenshots are native 640×288 BMPs;
the wrapper converts to PNG through Pillow.

`runrel` waits for a CPU word counter to advance by at least the requested
count; `waitcpu` waits for a word value; `runpc` stops at a CPU instruction
address. All three fail with a nonzero exit on timeout. Limits are emulator
ticks. For overlay breakpoints, establish the loaded overlay first because
different overlays share instruction addresses.

`keymap.py` sweeps actual make/release codes. `syms.py` resolves labels and
assignments from the matching listing and supplies `check_fresh()`. A
failed build may leave old outputs; do not bypass the freshness guard.

## Verification and measurement

| Tool | Use |
|---|---|
| `verify_build.py` | Single dispatch list for full, selected and host-only checks |
| `verify_rt11.py` | Native lifecycle checks, invoked through `--only rt11` |
| `verify_completion.py` | Input-driven feature and save-preservation checks |
| `verify_rules.py` | Controlled gameplay boundary probes |
| `verify_render.py` | Exact integer and pixel proofs, invoked by the rules group |
| `bench.py` | Whole-game fixed or sparse workload, counters and final screenshot |
| `harness.py` | Drawing-only frames timed by 50 Hz interrupts |
| `seg_snapshot.py` | Capture frozen wireframe records and compare common frozen scenes |
| `prof.py` | PC-sampling profile with labels from the current listing and shared boot sequence |
| `wav_analyze.py` | Tone activity in captured audio windows |

```sh
python3 tools/bench.py --fixed --ticks 1200 --turning --peek RING_STALL --shot tmp/turn.png
python3 tools/harness.py --turning --draw-frames 100
python3 tools/seg_snapshot.py --scenes 12 --out tmp/segments-new.txt
python3 tools/seg_snapshot.py --compare tmp/segments-old.txt tmp/segments-new.txt
```

See [testing](testing.md) for safe fixtures and result reporting, and
[rendering](rendering.md) for workload comparability and measurement limits.

## Player PDFs

```sh
make docs
make docs-capture
```

`manual_pdf.py` builds the Russian manual from `docs/manual/guide.html`,
`reference.json`, shared `controls.json` and real game screenshots.
`--capture` drives a fresh disposable disk and updates those images.
`control_pdf.py --board uknc|pc` builds a two-page landscape keyboard
reference; `--out` selects the output, and `--png` renders its first page.

Normal generation is offline using bundled artwork and captured screens.
`docs-capture` builds the game first. Temporary HTML, browser profiles and
PDF renders stay under `tmp/pdfs/manual`. Sources and artwork attribution
are in [manual/README.md](manual/README.md).

## Toolchain

`make toolchain` runs `build_toolchain.py`; `--only macro11|headless`
selects a component. Sources are fetched/copied under `tmp/`, compiled
there, and resulting executables/firmware/licenses copied under `bin/`.
It needs host build tools and the SDL2 runtime; the player uses the bundled
minimal SDL declarations, not an SDL development-header dependency.
The builder does not install host packages. Follow [AGENTS.md](../AGENTS.md)
if a dependency is missing. Normal game/PDF builds use existing tools and
do not fetch reference material.
