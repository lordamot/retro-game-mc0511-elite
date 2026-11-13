# Rendering and performance

## Retained architecture

The CPU simulates the sky, transforms and clips geometry, and compares
line records. The PPU draws pixel walks through the plane window. General
geometry is not offloaded to the PPU. The display is 640×288, with a
640×200 space view; projection stretches x by 5/3 for the pixel aspect.

A bitmap back buffer is excluded by memory capacity. One space view needs
16,000 plane bytes; only 9728 remain above the displayed screen per plane,
and those areas already hold hulls and overlays. Putting a display in CPU
RAM consumes space needed by the resident and RT-11. A line-table flip is
possible in hardware but does not create storage for the second image.

The renderer instead retains previous/current six-byte walk records and
XORs changes. General lists hold 160 records each; planet lists hold 48.
The sun uses cached scanline widths and changed edge spans. Stars have
private deterministic positions. Direct CPU text and HUD drawing first
drain the PPU queue, and full-height pages invalidate the dashboard.

## Hull pipeline

`HULL_FETCH` resolves a model from the immutable video bank into a 512-byte
CPU workspace, caching the last model. Hull records store vertices at four
times blueprint scale and doubled vertex indices in four-byte edge records.
Do not interpret the bank with the readable blueprint's units.
Cache misses copy eight words per loop and then the exact remaining words.
Incrementing the CPU video-address port refreshes its read latch; the copy
does not maintain a second address cursor. `HULL_FETCH` preserves R1–R5.

The ship pipeline rejects distant/outside objects, computes visible face
masks, then marks the endpoints of surviving edges. `VERT_MARK` also builds
a compact edge list so unused vertices need not be transformed. Model-space
face testing transforms the eye/centre once through the transpose matrix;
zero-face geometry remains visible. A blueprint radius is not a strict
bounding sphere; `SHIP_CONE` allows twice the recorded radius.
Each face's first signed product initializes the 32-bit dot-product sum;
the other two products retain the same carry and wrapping arithmetic.
The edge pass retains its list cursor on the stack across `SEG_LINE`,
avoiding a PC-relative address word on each cursor load/store. It releases
that word after the last edge; an empty list never pushes it.

`POS_NARROW` finds the smallest common arithmetic right shift that fits
all three signed 32-bit coordinates into signed 16-bit words. Its unrolled
high-word checks avoid loop setup in the common near case. Input positions
remain unchanged; the six result words and shared shift retain exact
integer behavior.

The station's added docking rectangle lies on the negative-z face, opposite
the entrance in the Legend blueprint. `STATION_SLOT` transforms the camera
position into model space and draws the added rectangle only when the eye
is outside its face. It cannot show through the hull beside the blueprint
entrance. Chained slot edges retain their original projected corners after
clipping. The docking/hyperspace tunnel draws four distinct edges per square,
including the closing edge, at each of its sixteen rotation steps.

`VERT_PROJECT` combines the scaled transform and projection. It computes
depth first, rejecting near-plane failures before the other row products,
and returns projected coordinates in registers. NPC beam muzzles use the
same path. Signed division, coordinate wrapping, overflow handling and
stack balance are part of its contract.

`ROT2` uses three shears. Replacing it with the two simultaneous small-angle
updates introduces scale growth. Matrix optimizations must retain the
exact integer results, not merely visually similar positions.
`TURN_SET` accepts the game's Q14 angles in -2000..2000. It computes the
original rounded Q14 sine and half-angle tangent, then multiplies those
coefficients by four for Q16 storage in `RT_S`/`RT_T` and the per-frame
`US_*` caches. The rounded multiply's high word then supplies each shear
without four shifts for a 16-bit value or eight for a 32-bit position.
The coefficients retain their original precision; matrices remain Q14,
positions remain signed 32-bit, and every shear retains its own rounding
and wrapping before the next one.

## Queue and pixels

`LINE_SETUP` packs three-word walks into a 256-record queue. The PPU runs
byte-accumulating Bresenham and span paths, including a rightward horizontal
shortcut. `RING_PUT2` publishes a replacement and its erase record together
when room permits, taking one tail snapshot. Both paired and fallback paths
keep new-before-old ordering.
Ring cursors are window word addresses, avoiding an offset conversion on
every record. The decoder passes the address, mask, deltas and row stride
in registers, writing only the state needed by the selected walker. An
eight-word mask table avoids byte sign extension, including start bit 7.
Rightward horizontal lines bypass the general walker. Both major-axis
walkers select the x direction once per line; x-major loops start with the
first pixel pending and count the remaining steps with `SOB`. They test
the row change before shifting x, so the old byte always has pending
pixels when flushed. The next pixel replaces that mask without a separate
clear, including simultaneous row and byte crossings.
Both ordinary walkers advance the video-address port directly, with R0
pointing at the port instead of copying a software cursor before each XOR.
Port writes refresh the data latch; timer and command interrupts preserve
the selected address. Long spans split whole bytes from the tail once,
then advance the same port directly for each full-byte XOR.
Span division loads the divisor into R2 before `DIV`. Sun scanline-width
calculations similarly stage immediate and memory operands in R2 for EIS
instructions. On the emulator's processor model, a separate load followed
by register `MUL`/`DIV` costs less than those instructions' memory modes.
The arithmetic and integer rounding are unchanged.

Every segment draws both endpoints: a point segment draws one pixel, and
shared XOR endpoints can cancel. `CLIP_LINE` mutates its input endpoints;
chained curves must retain their original vertices separately. A body
behind the viewer still advances body-list bookkeeping. The sun rejects a
wholly offscreen ellipse while erasing any previous visible spans.

Read `SEGPREV` for the last complete frame, not a mid-frame `SEGCNT`.
Queue drain completion is required before reading final pixels or reusing
segment storage for save I/O.

## Reproducible measurement

```sh
make build
python3 tools/bench.py --fixed --ticks 1200 --shot tmp/still.png
python3 tools/bench.py --fixed --ticks 1200 --moving --shot tmp/moving.png
python3 tools/bench.py --fixed --ticks 1200 --turning --shot tmp/turning.png
python3 tools/bench.py --sparse --ticks 1200 --turning --shot tmp/sparse.png
python3 tools/harness.py --turning
```

An emulator `run` tick follows the installed core's frame rate, reported
by `timing` and used by `bench.py`. The current 50 Hz core takes 24 emulated
seconds for 1200 ticks; older 25 Hz cores took 48 seconds. Count completed
game frames, not interrupts. `PPB_BUSY` counts 50 Hz drawing activity;
its denominator is elapsed emulated seconds times 50.
Native I/O can defer published CPU clocks, so do not use those clocks to
infer disk latency.

The fixed workload has the world, sun, station, Cobra and Viper plus eleven
inert distant fillers. Moving/turning runs reset the scene every hundred
ticks to keep it in range. Both fixed and sparse benchmarks check the slot
roster and fail if it changes. Sparse leaves spare slots empty, disables
ambient traffic and makes the station unmanned. Report it separately.

The drawing harness measures a fixed frame count using **50 Hz interrupts**
with the PPU drained at both ends. It excludes normal AI/HUD/input work;
its fps is not whole-game fps. `--no-stars` and `--no-bodies` are ablations,
not the shipped scene. The harness does not run at boot.
`bench.py` stops at its entry after a normal flight frame, then installs
the complete universe, identity player matrix and initial star data.
A disposable 26-byte RAM prelude clears old geometry before measurement
and freezes the CPU immediately after the requested frames. Setup and
completion PCs, frame count and roster are checked. The prelude uses free
resident reserve without changing the SAV or overwriting the flight overlay.

Earlier drawing measurements installed the scene before a fixed tick
warm-up. Builds could enter the harness with different positions and
orientations, making those figures unsuitable for exact A/B comparisons.
Use the corrected harness on both builds. Its whole-game scripts are
unchanged, so the whole-game baseline remains applicable.

## Applicable baseline

The unrolled position checks and register-operand sun/span arithmetic were
measured on 2026-11-13 against the PPU walker build (`876ebbb`). Both builds
used identical whole-game `bench.py --ticks 6000` scripts and the same 50 Hz
emulator: 120 emulated seconds per run. The first three rows use `--fixed`;
the last uses `--sparse --turning`, with only five occupied slots.

| Workload | Before: frames / FPS | Optimized: frames / FPS | Change |
|---|---:|---:|---:|
| Still | 1163 / 9.692 | 1167 / 9.725 | 0.3% |
| Moving | 912 / 7.600 | 921 / 7.675 | 1.0% |
| Turning | 713 / 5.942 | 718 / 5.983 | 0.7% |
| Sparse turning | 904 / 7.533 | 919 / 7.658 | 1.7% |

Roster checks passed and ending screenshots were inspected. Local logs and
images are `tmp/render-speed4/long-port-{still,moving,turning,sparse}` for
the baseline and `tmp/render-speed5/long-verified-{still,moving,turning,sparse}`
for the optimized build, with `.log`/`.png` suffixes. These are small gains;
individual intermediate changes did not improve every workload.

Both builds were also measured with the corrected drawing-only harness.
Its 100-frame still workload changes from 340 to 338 interrupts
(68.0 → 67.6 ms/frame), and turning from 572 to 569
(114.4 → 113.8 ms/frame). The whole universe, player matrix, star data and
speed/turn inputs match byte for byte at entry; all 640×288 final screen
pixels match after the 100-frame turning run. Local evidence is
`tmp/render-speed5/ready-{base,verified}` and `harness-{base,verified}-*.log`.
Harness rates exclude gameplay and are not flight FPS.

Before/after segment captures match all 287 segments across eleven frozen
scenes. One of the twelve requested scenes did not freeze and was skipped.
The rules group independently verifies exact rotation arithmetic, pixels,
face signs, hull-copy contents, stack/register preservation and the
station/tunnel regressions; see
[testing](testing.md) for the completed groups and build identities.

The changes add 28 resident bytes, leaving 302 bytes free. Overlay sizes
are unchanged (the largest is 4959 bytes, leaving 161). The PPU program occupies
3424 bytes; 88 bytes remain between reused buffers and published words.
These are emulator measurements, with frame-count boundary and fixture limits;
they are not physical-hardware timing or a uniform speed guarantee.

## Acceptance criteria for renderer changes

- Compare the same fixture, benchmark revision, options and measurement
  duration. Check the roster and inspect the final screenshots.
- Use turning as well as straight flight. A straight-moving scene does
  not exercise all matrix work. Use sparse to expose dependence on fillers.
- Capture before/after `seg_snapshot.py` results for changes intended to
  preserve geometry. Compare only scenes frozen in both runs.
- Run the rules group's exact matrix/projection, filled-sun and queue pixel
  proofs. Geometry records alone cannot validate text or filled effects.
- Record resident, overlay and PPU memory costs alongside elapsed time.
  Read measured costs; instruction count and PC profiles alone are not
  timing models. Use controlled ablation to attribute work.
- Keep gameplay timing implications visible: AI rolls per frame, so a
  faster renderer can change combat and traffic frequency per second.

## Constraints on further optimization

The sibling `retro-game-mc0511-dizzy` at `f6c66a7` was reviewed for applicable
techniques, especially `PP_CPU_COPY` in `src/ppu_anim.mac` and address-port
increments in `src/cpu_prepare.mac`. Its unrolled window transfers apply to
Elite's immutable hull copy. Its other major gains have different prerequisites:

- Dizzy's 320-pixel, 173-row composition fits small framebuffer banks. Elite's
  640×200 view needs 16,000 bytes per plane, exceeding the 9728-byte offscreen
  space, which also holds hulls and overlay caches.
- Direct RAM0 painting applies to Dizzy's plane-zero mappings. Elite's XOR
  geometry uses plane 1 through the video port; changing that requires a new
  plane/palette layout and pixel proofs.
- Dizzy overlaps simulation with a pending bank flip. Elite already submits
  line records asynchronously; its current flight loop does not wait for a
  bank-flip acknowledgment.
- Prepared sprite caches reuse finite animation poses. Elite's projected
  vertices change with depth and orientation. Reusing per-object geometry
  would require explicit invalidation and a memory budget for retained state.

At the `876ebbb` baseline, 1200-tick turning samples placed 27–31% of
PPU time in the x-major walkers and 17–20% in queue decoding/draining.
The drawing drain was active for about 77% of the filled workload and 84%
of sparse turning. Still-flight CPU samples placed about 15% in vertex
projection and 5% in position narrowing. These samples identify costs,
not speed gains. Further improvements should target measured arithmetic
or raster costs while preserving pixels and buffer ownership.

Keep per-record tail publication. Trials publishing every four or eight
records, with an immediate publication at the cached head, did not produce
a consistent whole-game gain.

Keep register operands in the matrix multiply. Folding an operand load
into `MUL (R4)+` reduced instructions but slowed the `876ebbb` baseline's
6000-tick still workload from 1163 to 1127 frames and moving from 912 to
889. Exact projection tests passed; the processor model's more expensive
EIS memory addressing outweighed the removed loads.

Keep the eight-pixel-per-scanline span threshold. After staging the span
divisor in a register, thresholds 4, 6, 12 and 16 took 570, 570, 577 and 579
interrupts in the corrected 100-frame turning harness, compared with 569
at eight pixels. Their sparse-turning runs completed 907, 916, 902 and 907
frames, compared with 919 at eight pixels. Removing stars or bodies is
useful only as an ablation; their removal does not optimize the shipped
appearance.

General PPU geometry needs a new measurement and scheduling design before
implementation. The PPU has a lower clock, transfers geometry/results
through a window, already draws pixels and services firmware I/O. Any gain
requires useful overlap without using stale orientations or blocking the
CPU at each ship. Budget request/result storage, cache displacement,
relocation, queue latency and single-writer handshakes explicitly.

The `external/scr256db` demo demonstrates a different split and unrolled
DDA, but its 256×128 orthographic one-object workload and CPU double buffer
do not satisfy this port's display and world requirements. Its source cycle
counts are not measurements of this renderer. Keep the single-writer
synchronization lesson; do not adopt its frame-rate claims. Provenance and
permission are in [reference sources](reference-sources.md).
