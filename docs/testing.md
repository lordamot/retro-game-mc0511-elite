# Verification

## Commands and coverage

Prepare the local inputs in [checkout setup](setup.md). Full and host-only
runs require the ignored Legend sources for resource round trips; a fresh
checkout alone cannot perform those comparisons. Missing Legend sources
fail explicitly. Runtime-focused groups use the built port and emulator.

```sh
make verify
```

This builds the game and runs host resource/model checks plus every entry
in `GROUPS` in `tools/verify_build.py`. The source dispatch list and `--help`
are authoritative; do not maintain a second group list or a fixed assertion
count in documentation.

For a narrower development loop, build first and run the relevant group:

```sh
make build
python3 -u tools/verify_build.py --only palette
python3 -u tools/verify_build.py --only rt11
python3 -u tools/verify_build.py --only splash
python3 -u tools/verify_build.py --only rules
python3 -u tools/verify_build.py --skip-emu
```

| Group or family | Main coverage |
|---|---|
| `rt11` | Real save/overwrite/load, invalid and full-disk failures, SAV/DAT pairing and relocation, legacy migration, cold reboot, exit/relaunch, stack and vector ownership |
| `palette` | Default/explicit GRB and RGB, real title keys, selection underline and Latin/version glyphs, both hardware palettes, full-screen pixel comparison, restart and relaunch lifetime |
| `splash`, `title`, `presentation` | Enter boundaries, logo/audio, font and screen rendering |
| `saving`, `access`, `commanders` | Commander persistence, chooser and access menu behavior |
| `keyfile`, `pause`, `sound`, `ppu` | Bindings/options, sound, cache and PPU integration |
| `completion` | Save preservation and input-driven completion features |
| `rules` | Controlled rule boundaries and exact renderer proofs |
| Other `GROUPS` entries | Combat, markets, travel, hulls, bases, contracts and missions |
| `--skip-emu` | Resource round trips and host-side models only |

The rules group calls `verify_render.py` for exact matrix cases, fused
projection (including signed overflow and near-plane rejection), filled-sun
pixels, font/layout and queue wraparound/full-ring stress. It also checks
all sixteen tunnel rotations against closed polygons and exact XOR pixels,
both station models from front, rear and oblique views, and clipped slot
and tunnel outlines against independently submitted edges. Those proofs
complement screenshots; none alone establishes all rendering behavior.
Hull-copy probes check all 55 bank records, all eight remainder lengths,
unused destination bytes, cached repeats, preserved registers and stack
balance. Face probes compare signed, wrapped dot products with an integer
model; packed-line probes check every octant and start bit against XOR pixels.

## Isolation and sequencing

Run emulator suites sequentially: some groups share a disposable disk.
Do not build while a suite is running. Symbols, native SAV/DAT and the disk
under test must belong to the same build. `syms.check_fresh()` rejects stale
inputs; parsed listings are cached by file version.

`keep_pristine()` reconstructs images from the manifest; `fresh_disk()`
provides a private test disk. `run_emu()` starts from a fresh image by
default; pass an explicit disk path to retain saves across a reboot.
Never copy a potentially played build image
and call it pristine. No test should save into `saves/elite.dsk`. Disk
refresh tests use independent fixtures, including distinct records in all
four slots and backup checks.

The native lifecycle probes use real monitor file calls, not simulated
writes. They check failure preservation, keyboard edges during I/O, cache
read avoidance, physical relocation of DAT, cold boots after swap writes,
and repeated clean exit/relaunch with reused allocation addresses.

## Driving startup and screens

Reuse the boundaries in `verify_build.py`:

| Sequence | End state |
|---|---|
| `POWER_ON` | First welcome page |
| `SPLASH_KEYS` after power-on | Logo after two separate Enter presses |
| `TITLE_BOOT` | Complete boot to logo |
| `CHOOSE_KEYS` after logo | Commander chooser |
| `COMMANDER_KEYS` after chooser | Default commander ready |
| `BOOT` | Combined launch sequence |

`uknc_control.py boot` ends at the logo; it does not select a commander.
Do not duplicate old fixed boot waits in new tests. Nonmodal navigation
uses `ui_ready(t)` to wait for main-loop progress after I/O and the
25-frame screen-switch lockout. Name and mission prompts are modal and
use bounded waits for `NAME_READY` or `mission_ready(t)` after their
overlay is loaded. `waitcpu` observes state transitions; `runpc` stops at
a known instruction; `runrel` counts completed loop progress. A timeout
is a failure. When a key appears lost, inspect CPU
registers and current page before attributing the problem to a crash.

Flight edges survive I/O in acknowledged packets. Raw scancode prompts
are not a queue of arbitrary typed characters; allow each prompt to draw,
and send separate press/release events.

## Controlled probes

Use the current helper routines to initialize complete ship state, both
position words and deterministic random inputs. A fixture's scene must be
proved by reads rather than inferred from a screenshot or a slot number.
Sample transient events across their active interval. Read completed frame
counters and correct byte halves. Recharge batches are compared at
`RECHARGE` boundaries using `RC_LAST`, not an unrelated clock sample;
automatic repair inputs are seeded at `PILOT_JUMP`, after tunnel random
draws. Keep a portal outside docking range when testing its appearance;
wait for a completed jump when testing entry. The [caveats](caveats.md)
reference lists common errors.

Rule probes patch only disposable emulator RAM. Renderer probes use the
flight-overlay window through the harness hook while docked, so they do
not overwrite live executing code. Drain the PPU before pixel inspection
and preserve final results until read. They do not modify gameplay source
or player disks.

A nonzero emulator exit, missing reply or zero-assertion group is a failure,
not a skip. Never weaken an assertion just because a speed or I/O change
moved the observation window; establish the event and correct the fixture.

## Reporting results

Record the build identity, command, exit status, actual assertion count,
failures and any skipped comparisons. Distinguish a full suite from focused
reruns and host-only checks. Do not combine earlier passing groups into a
claim that one complete run passed. Disposable logs in `tmp/` are evidence
for a local session, not enduring dependencies of the project documentation.

The v0.8.2 build with renderer speed optimizations passed `make build` on
2026-11-13. Completed focused runs of `python3 -u tools/verify_build.py`
passed with `--only rules` (180 assertions, including the station/tunnel
checks and seven hull-copy, face-sign and packed-line checks), `--only hulls`
(11 assertions) and `--only ppu` (9 assertions), all exit 0. Local logs are
`tmp/render-speed/verify-{rules,hulls,ppu}.log`. Before/after
`seg_snapshot.py --scenes 12` captures matched all 287 segments across the
eleven scenes frozen in both builds; scene 0 was skipped because it did not
freeze. Exact pixel checks passed separately in the rules group. The full
suite was not rerun for this build. Build identities:

- `ELITE.SAV` SHA-256: `f1a3f741786a77a291d83bd3786cedb298f1605fdc5308e65165880d427fb99e`
- `ELITE.DAT` SHA-256: `06377cb0de783dd1b782dd59eded83a862660358b5441d884e9c93ae4f8bb6ba`

The preceding v0.8.1 build passed one complete `make verify` run on 2026-11-11:
**713 assertions passed, zero failed, exit status 0**. Build identities:

- `ELITE.SAV` SHA-256: `f1c99532db75afd5451b6c69302750e7739eaedc51a9de51162f345f755066e4`
- `ELITE.DAT` SHA-256: `378617c624cff253354015c96b3fee7af89aac1ccfb8d5d8576217eeb7861dd9`

This includes all 87 palette assertions, 29 native RT-11 assertions and
145 rule/renderer assertions (28 exact renderer subchecks). The retired
1985 commodity-table comparison was skipped because that table is no
longer a maintained resource; Legend resource round trips passed.
The local full-run log is `tmp/verify-0.8.1-fixed.log`.

A documentation-only change does not require another long gameplay run;
validate its paths, commands and generated outputs. A runtime release
should establish a clean full result for its own build.

## Visual and performance checks

The emulator toolchain build runs `check-audio` before installing its
executables. This uses the real player loop and core with a deterministic
SDL sink to check PCM silence, sample production versus elapsed time,
buffer priming, render jitter and recovery from a 200 ms host stall.
It fails against the old 40 ms player loop with the current 50 Hz core.
It does not establish subjective sound quality on the host audio device.

Use [rendering](rendering.md) for fixed/sparse benchmarks and segment
comparisons. Check memory bounds from the assembled listing and manifest.
A timing improvement must retain the intended scene and visual features.

For PDFs, `make docs` builds all three from maintained sources;
`make docs-capture` first builds the game and captures real screens on a
private disk. Render affected pages with Poppler, inspect layout and glyphs,
and check searchable Russian text, section coverage and page bounds.
See [manual sources](manual/README.md).
