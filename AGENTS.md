# Working on MC-0511 Elite

## Read first

Read [docs/README.md](docs/README.md) for current scope, then the topic
needed for the change. Read [architecture](docs/architecture.md),
[memory map](docs/memory-map.md) and [caveats](docs/caveats.md) before
changing assembly. Read [platform](docs/platform.md) and
[rendering](docs/rendering.md) before changing drawing or PPU code.
[Testing](docs/testing.md) defines verification and measurement rules.

The target is a Russian Elite Legend port for Электроника МС-0511 (УКНЦ):
640×288, hardware MUL/DIV, readable MACRO-11 and text resources, normal
RT-11 SAV/DAT files, persistent commanders and a clean return to RT-11.
Preserve these decisions. Known differences from Legend are explicit in
[compatibility](docs/compatibility.md); a catalogue entry alone does not
prove an implemented feature.

## Work rules

- Discuss work in English. Code and comments are English; game strings
  and player PDFs are Russian.
- Work inside this repository. Compile toolchains under `tmp/`, then
  install their results under `bin/`. Game build artifacts go in `build/`.
- Ask before installing anything on the host; the operator installs it
  or suggests an alternative. If a required screenshot cannot be obtained,
  ask before researching an alternative.
- Prefer reusable Python CLIs under `tools/` for project workflows.
  Ask before creating a new skill file. The existing project skill is
  [.agents/skills/elite-tools/SKILL.md](.agents/skills/elite-tools/SKILL.md).
- Working on the user's current branch is allowed. `main` is the ready
  solution; feature branches use `feat/<short-kebab-name>`.
- Ask before committing. Never push. Commit subjects are short English
  imperatives, under 72 characters, without a final period.
- Preserve unrelated working changes. Do not commit original game files,
  third-party binaries/reference checkouts, RT-11 input binaries, generated
  PDFs/disks, `build/`, `tmp/`, player disks or host caches. See
  [checkout setup](docs/setup.md) for the tracking policy.

## Data safety

`make run` refreshes and plays `saves/elite.dsk`. Use `tools/play_disk.py`
to update a player disk while retaining all four commander files and a
backup. Do not regenerate a player's disk with `dsk_build.py`.
Verification uses disposable disks under `tmp/`; never test saving on the
player's image. Refresh replaces files other than the four commander
files, so it is not a general-purpose filesystem merge.

Keep both `SET USR SWAP` and `SET EXIT SWAP` on the supplied monitor.
Keep `RT_IOBUSY` around native file calls. Exit is АР2 then Ч (PC Tab,
then X), without autosave. See [RT-11](docs/rt11.md).

## Assembly essentials

- MACRO-11 defaults to octal: decimal literals need a trailing dot.
  Expressions are left-to-right; bracket products explicitly.
- Check register clobbers and branch directly from the flags being tested.
  `MUL` is signed; an even destination also overwrites the next register.
- Positions are 32-bit. `U_NEAR` gates 16-bit reads; `U_SXT` accompanies
  16-bit writes. Device flags are bytes, with absent/broken bits.
- The PPU code is relocated. Keep it position independent, preserve the
  four consecutive published words, and respect buffer lifetimes in
  `src/tail.mac`. Each cross-processor handshake needs clear ownership.
- Drain the drawing ring before direct CPU drawing or shared-buffer reuse.
  The flight overlay owns the CPU overlay window during flight work.
- `MAIN_START` is a once-per-launch entry. Restarts use `MAIN_RESTART`.
- Measure memory from assembled listings and the manifest. The resident
  and largest overlays have very little spare space.

## Validation and documentation

Use a narrow relevant verification group during development and the full
suite when the scope requires it. Run emulator suites sequentially; do not
rebuild underneath them. A missing result, failed emulator or group with
zero assertions is a failure. Never present focused checks as a full pass.

Benchmark identical fixtures; one emulator tick is 1/25 second. Inspect
the scene and verify the roster. Geometry-preserving changes need segment
comparison; that does not establish filled-pixel or text equivalence.

Maintain documentation as current behavior, final decisions, constraints
and reproducible procedures. Replace superseded statements; do not append
dated work logs, plans marked done, or session handovers. Keep provenance
and measurement dates where they establish what evidence applies. Use
`docs/` for technical references and `docs/manual/` for player PDF sources.

## Source preferences

For web research, browsing, source selection and downloads, apply the
available `avoid-blocked-sources` skill. Exclude `remont-aud.net`,
`lineage-os.ru`, all their subdomains and known mirrors. Do not visit,
download, cite, recommend or use their snippets as evidence. Add
`-site:remont-aud.net -site:lineage-os.ru` to searches where supported.
This preference persists across projects unless the user changes it.
