# Checkout setup and repository contents

The repository contains the port's source, readable game resources,
project tools and documentation sources. Executables, ROMs, original game
files, third-party reference checkouts, generated PDFs and disk images are
local inputs/outputs, excluded from Git. Downloadable releases carry the
built disk and player PDFs separately.

## Build prerequisites

Use Python 3 and Pillow for the project tools. Building the local toolchain
requires Git, make, a C/C++ compiler, patch and the SDL2 runtime. The player
uses minimal bundled SDL declarations and does not require SDL development
headers. Install missing host dependencies separately; the project does
not install system packages.

```sh
make toolchain
```

This fetches/builds macro11 and UKNCBTL from the upstream repositories named
in `tools/build_toolchain.py`. It compiles under `tmp/` and installs the
assembler, headless/player runners, UKNC ROM and licences under ignored
`bin/`. Project runner source and macro11 patches remain tracked under
`tools/`. Do not copy executables back into Git.

The native RT-11 build also needs these separately supplied files:

| Local path | Required content |
|---|---|
| `orig/rt11/RT11BASE.DSK` | The supported bootable 819,200-byte RT-11 SJ V05.04 G base volume |
| `orig/rt11/SYSMAC.SML` | The matching RT-11 macro library |

Their provenance and known hashes are in
[orig/rt11/README.md](../orig/rt11/README.md). They are not downloaded by
`make toolchain`. Supply your local copies at those paths before building;
the build reports missing inputs explicitly. Substituting another monitor
requires its own memory, swapping and lifecycle validation.

```sh
make build
make run
```

The game builds entirely from `src/` plus the toolchain and RT-11 inputs.
It does **not** require the original Spectrum disk, Legend source archive,
ZEsarUX or scr256db for normal compilation/play. `build/elite.dsk` is an
output to attach to a release, not a tracked file. Player state is under
`saves/` and survives `make clean`.

## Optional reference inputs

| Local path | Needed for |
|---|---|
| `orig/ELITE.SCL` | Original Russian world-vocabulary extraction/comparison |
| `orig/legend/EliteLegend_v1_09_source/` | Legend re-extraction, resource round trips and reference build |
| `orig/legend/elitelegend_info.pdf` | Consulting the original Russian manual |
| `bin/zesarux/` | Running the Spectrum reference through `zx_control.py` |
| `external/scr256db/` | Consulting the separate renderer reference |

Original games and archives must be supplied separately. Keep their exact
expected layouts; the extraction tools name files within the Legend tree.
[Reference sources](reference-sources.md) records provenance and formats.
`make legend` additionally requires Wine and the author's sjasmplus from
that local Legend source tree. ZEsarUX is optional and is **not** built by
the current `make toolchain`; `zx_control.py` expects a working
`bin/zesarux/run.sh` launcher plus the emulator's own runtime/ROM files.

scr256db is not used by the game build. It can be obtained independently
from its upstream repository; use the revision documented in
[reference sources](reference-sources.md). Its entire checkout, including
any prebuilt SAV, belongs under ignored `external/`.

`make verify` and `--skip-emu` include Legend source comparisons and therefore
need the original Legend sources. Missing Legend sources are an explicit
failure, not a claimed passing round trip. The original SCL comparison is
explicitly skipped if that disk is absent. Selected emulator groups can
run from the built port without those source comparisons; see
[testing](testing.md). Check each group's prerequisites before interpreting
its result.

## Player PDFs and release files

```sh
make docs
```

Python/Pillow and Chrome/Chromium build `manual.pdf`, `control.pdf` and
`controls-pc.pdf` at the repository root. These generated files are ignored
and intended as release attachments. Sources, offline artwork and captured
screens remain tracked under `docs/manual/`, so regeneration does not need
the original manual or network access. Poppler is used for rendered QA.
`make docs-capture` additionally needs the game build inputs and emulator.

## Tracking policy

| Keep in Git | Keep local / release separately |
|---|---|
| `src/` assembly and readable resources | Original game disks, archives, manuals and reference sources in `orig/` |
| Project Python/C++ tooling and patches | Tool executables, libraries and firmware in `bin/` |
| `docs/`, `AGENTS.md`, README and keyboard guide | Downloadable third-party copies in `external/` |
| Manual text, control data, artwork and maintained screenshots | Generated root PDFs |
| Setup/provenance READMEs in `orig/` | RT-11 binary inputs and macro library |
| Makefiles and ignore rules | `build/`, `tmp/`, `saves/`, disk images and emulator/host caches |

The ignore rules protect local copies; removing a tracked file from the
index does not delete it from the working machine. This policy controls
future snapshots, not the contents of previous Git history.
