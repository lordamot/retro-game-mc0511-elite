# RT-11 build inputs

Provenance: `retro-game-mc0511-darkroom`, supplied 2026-11-08. The game
build uses these local inputs and requires no sibling checkout:

- `RT11BASE.DSK`: the supplied bootable RT-11 SJ V05.04 G volume.
- `SYSMAC.SML`: the RT-11 macro library used by MACRO-11.

The sibling also supplied `tools/savlink.py` and `tools/rt11fs.py`.
These files are local reference/build inputs, not generated game assets.
The build copies the base volume and installs `ELITE.SAV`, `ELITE.DAT`
and `STARTS.COM`; it does not replace the monitor or bootstrap.
`STARTS.COM` enables both USR and EXIT swapping before `R ELITE`.
No additional rights to the RT-11 system software are asserted here.

See [RT-11 lifecycle](../../docs/rt11.md) for the supported monitor
configuration, memory requirements and save/exit behavior.

These two inputs are excluded from Git and must be supplied separately;
`make toolchain` does not download them. The known supported copies have
these SHA-256 hashes:

```text
834d11949ee97ba76429ec5e96175992555beb74dfeaf916cbecdee38fb5f5ff  RT11BASE.DSK
a9d716957163b53d86ddd4f9f65a172b9c4c456aaf6272509fb0ec7f4716485e  SYSMAC.SML
```

See [checkout setup](../../docs/setup.md) before building a fresh clone.
