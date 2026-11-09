# Licensing and third-party rights

Assessment of the v0.8.0 tree, 9 November 2026. The grant is in
[LICENSE.md](../LICENSE.md), in English and Russian.

## Decision

MIT covers Sergey's original contributions only, to the extent he holds
the copyright. It permits commercial use of those contributions; the
project's non-commercial purpose is not an extra MIT condition. The
[standard MIT terms](https://opensource.org/license/mit) are reproduced
unchanged in English, apart from the copyright holder and year.

The complete game cannot be represented as wholly MIT-licensed. It
contains extracted content and translated implementations, not just
independently written platform code. Rewriting Z80 as MACRO-11 does not
by itself establish permission to relicense the underlying work. The
[US Copyright Office's explanation of derivative works](https://www.copyright.gov/eco/help-limitation.html)
distinguishes new authorship from pre-existing material and the owner's
right to authorize adaptations. This is a provenance review, not a legal
opinion or a determination under every applicable jurisdiction.

## Material and evidence

| Material | Evidence and licensing position |
|---|---|
| Elite and its Russian Spectrum version | Original credits name David Braben, Ian Bell and Torus/Firebird. `src/res/text/planet.txt`, `pairs.txt` and parts of `strings.txt` are extracted or adapted. No grant establishing MIT relicensing of that material was found locally. Attribution does not establish current ownership or permission. |
| Elite Legend by PLM | `src/res/legend/` contains extracted models, artwork, text, tables and effects. Assembly modules translate Legend routines. The local v1.09 source tree has no general LICENSE/COPYING file or explicit MIT grant found in the reviewed notices. |
| Reported Legend permission | [The source-release report](https://idpixel.ru/news/3284-opublikovany-ishodniki-elite-legend-ultimativnoj-versii-elity/ru/) says the author permits redistribution and reuse in other projects. This is useful secondary evidence, not an MIT license. The linked [release thread](https://zx-pk.ru/threads/33861-elite-legend-128k.html) was accessible, but the later source-release post could not be retrieved in this review. Preserve the exact author's statement before relying on its scope. It would not by itself settle other authors' underlying rights. |
| LibSFX | `src/ppu_sfx.mac` explicitly ports `Library/LibSFX/LibSFX.asm1.a80`. The upstream main files credit `(C) 2001-2020 LoneWolf`. No separate general license grant was found in the local library. Excluded underlying material remains subject to its author's rights. |
| UKNC font and firmware | Both `src/res/font/uknc11.txt` and `latin11.txt` identify ROM extraction. Being bundled with an emulator does not establish that the firmware or extracted font has the emulator's license. No separate grant was established here. |
| RT-11 | The disk build copies a supplied RT-11 base volume and uses `SYSMAC.SML`. [Input provenance](../orig/rt11/README.md) asserts no redistribution rights. MIT for port code does not license the monitor, bootstrap, system files or macro library. |
| Adapted manual and screenshots | `docs/manual/reference.json` and parts of the manual adapt Legend's manual. Images in `docs/manual/img/` and `output/` depict game content. Newly written explanations and capture/generation code do not relicense the material they reproduce. |
| PC keyboard artwork | Rumudiez's [original illustration](https://commons.wikimedia.org/wiki/File:ANSI_Keyboard_Layout_Diagram_with_Form_Factor.svg) offers CC BY-SA 3.0, the option used here. Keep credit, source, license link and a description of changes with distributed adaptations. Those adaptations remain under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). |
| UKNC keyboard artwork | `docs/manual/keyboard-uknc.png` comes from UKNCBTL; [manual attribution](manual/README.md#artwork-attribution) records its source. The image's specific licensing scope needs confirmation; do not assume it is MIT. |
| Emulator and assembler | UKNCBTL's [license](https://github.com/nzeemin/ukncbtl-qt/blob/master/LICENSE) is LGPL v3; macro11's [license](https://github.com/shattered/macro11/blob/master/LICENSE) is BSD-style with three conditions. Their code, patch context and linked binaries are not relicensed by this project. Building the game with these tools does not alone transfer their licenses to the game's original code. |
| Sibling-project code and scr256db | Platform code, emulator runners and RT-11 tools have [recorded provenance](reference-sources.md). Verify ownership or the applicable grants before treating inherited portions as MIT. The recorded scr256db permission allows use but is not a documented MIT relicensing grant. |

## Distribution limits

The MIT grant is usable for the original contributions it covers. It does
not certify that the whole source tree, disk image, screenshots or player
PDFs may be distributed without additional permissions. Excluding original
archives and binaries from Git does not remove extracted material still
present in tracked resources, code or documentation.

For a release, retain the applicable third-party notices and establish the
rights to distribute and adapt the included original-game content, Legend
material, LibSFX, ROM/font material and RT-11 system software. Record the
actual permission and its scope, or replace/omit material whose rights
cannot be established. Free distribution and preservation intent do not
by themselves resolve those questions. A qualified legal review is needed
for a definitive clearance of the combined release.

No upstream material has been declared public domain or relicensed by this
assessment. Credits remain acknowledgments, not transfers of copyright.
