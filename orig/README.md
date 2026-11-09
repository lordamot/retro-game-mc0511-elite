# Local original/reference inputs

Only the setup/provenance READMEs in this directory belong in Git. Game
originals and binary build inputs are supplied locally and ignored.

- `rt11/RT11BASE.DSK` and `rt11/SYSMAC.SML` are required for the native build.
- `ELITE.SCL` is the original Russian Spectrum disk, used for extraction
  and optional source comparison.
- `legend/EliteLegend_v1_09_source/` supplies Legend re-extraction and
  full resource round-trip verification.
- `legend/elitelegend_info.pdf` is a reference manual, not needed to
  regenerate the port's player PDFs.

See [checkout setup](../docs/setup.md), [RT-11 input provenance](rt11/README.md)
and [reference formats](../docs/reference-sources.md). Normal port builds
use the maintained readable resources in `src/res/`; do not replace them
with copied original binaries.
