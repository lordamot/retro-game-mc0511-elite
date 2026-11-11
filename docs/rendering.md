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

The ship pipeline rejects distant/outside objects, computes visible face
masks, then marks the endpoints of surviving edges. `VERT_MARK` also builds
a compact edge list so unused vertices need not be transformed. Model-space
face testing transforms the eye/centre once through the transpose matrix;
zero-face geometry remains visible. A blueprint radius is not a strict
bounding sphere; `SHIP_CONE` allows twice the recorded radius.

`VERT_PROJECT` combines the scaled transform and projection. It computes
depth first, rejecting near-plane failures before the other row products,
and returns projected coordinates in registers. NPC beam muzzles use the
same path. Signed division, coordinate wrapping, overflow handling and
stack balance are part of its contract.

`ROT2` uses three shears. Replacing it with the two simultaneous small-angle
updates introduces scale growth. Matrix optimizations must retain the
exact integer results, not merely visually similar positions.

## Queue and pixels

`LINE_SETUP` packs three-word walks into a 256-record queue. The PPU runs
byte-accumulating Bresenham and span paths, including a rightward horizontal
shortcut. `RING_PUT2` publishes a replacement and its erase record together
when room permits, taking one tail snapshot. Both paired and fallback paths
keep new-before-old ordering.

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

## Applicable baseline

The latest measured RT-11 runtime baseline is from 2026-11-08, before the
startup-only splash addition. It is retained as a workload reference,
not a claim that the current tree was rebenchmarked during documentation.
The recorded rates below used the older 25 Hz tick conversion; do not
apply them to the updated core or reinterpret them as new measurements.

| Sixteen-slot workload | Completed frames in 1200 ticks | FPS |
|---|---:|---:|
| Still | 451 | 9.40 |
| Moving | 355 | 7.40 |
| Turning | 308 | 6.42 |

Roster checks passed and ending screenshots were inspected. Local evidence
is under `tmp/rt11-port/` (`*-final.log`, `*-final.png`). These are disposable
artifacts, not required repository inputs. Seven frozen comparison scenes
contained 196 identical wireframe segments; one unfrozen scene was excluded.
That comparison says nothing about filled pixels, fonts or effects.

There is no retained current sparse or drawing-only baseline for this
RT-11 layout. Run those workloads when needed rather than importing rates
from a different memory layout or fixture. One-frame differences in a
48-second window are too small to support a strong speed claim.

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
