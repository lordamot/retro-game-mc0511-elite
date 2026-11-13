# Project documentation

These references describe the v0.8.3 source tree. The game code and
generated listings are authoritative for behavior and addresses. Documents
record current decisions and constraints; they are not a development log.

## Start here

| Task | Reference |
|---|---|
| Prepare dependencies and optional reference inputs | [Checkout setup](setup.md) |
| Build, play or locate player PDFs | [Project README](../README.md) |
| Work in this repository | [AGENTS.md](../AGENTS.md) |
| Understand module boundaries and data flow | [Architecture](architecture.md) |
| Change graphics, input, timing or PPU ownership | [Platform](platform.md) |
| Allocate code, data or overlays | [Memory map](memory-map.md) |
| Change loading, saving, disk refresh or exit | [RT-11 lifecycle](rt11.md) |
| Change or measure the renderer | [Rendering and performance](rendering.md) |
| Avoid assembly, concurrency and fixture errors | [Caveats](caveats.md) |
| Select checks and interpret evidence | [Testing](testing.md) |
| Find a CLI or resource generator | [Tools](tools.md) |
| Check what differs from Elite Legend | [Compatibility and limits](compatibility.md) |
| Trace original data and third-party inputs | [Reference sources](reference-sources.md) |
| Check the MIT scope and third-party rights | [Licensing assessment](licensing.md) |
| Read keys and keyboard protocol | [KEYBOARD.md](../KEYBOARD.md) |
| Edit or regenerate the Russian PDFs | [Manual sources](manual/README.md) |

## Current scope

The port has 69 object headers on 55 hulls, sixteen universe slots,
nineteen purchasable ships, 38 commodities, 49 equipment rows, four saved
commanders, a carrier market, 48 galaxies and Legend's mission systems.
Combat includes eight lasers on four mounts, missiles, ECM, bombs,
cloaking, boarding and player Targlets. Jumps apply wear, repairs and cargo
life support. Screens use the full 640×288 display and the 8×11 УКНЦ font.

A native RT-11 launch shows welcome and controls pages, each advanced by
ВВОД, then the Legend logo waiting for ФИКС. The logo offers 1 — GRB
(default) and 2 — RGB; the palette choice lasts until exit. Restarts return
to the logo.
The game uses `ELITE.SAV`, paired `ELITE.DAT` and normal commander files.
Player disks live under `saves/`; tests use `tmp/`.

The attract demo is deferred. Cargo discard, ore processing and target-lock
enhancement are catalogue/record items without their own gameplay effect.
Platform-specific differences and capsule behavior are documented in
[compatibility](compatibility.md). General PPU geometry offload is not
implemented. These limitations must remain visible in player documentation.

## Evidence limits

The v0.8.3 release passed its build and all 783
assertions in one complete `tools/verify_build.py` run on 2026-11-13,
including palette, native RT-11, gameplay, presentation and exact renderer
checks. The v0.8.2 renderer optimization comparisons found 287 identical
segments across eleven frozen scenes; one scene was skipped because it did
not freeze.
[Testing](testing.md) records build identities and coverage limits.

The latest whole-game benchmark measures the RT-11 renderer at 9.725 fps
still, 7.675 moving and 5.983 turning with the sixteen-slot fixture and 50 Hz
emulator. Sparse turning reaches 7.658 fps with five occupied slots.
See [rendering](rendering.md) for the workload, comparison and limits.
Memory figures are a build snapshot, not a promise that later edits fit
unchanged.
