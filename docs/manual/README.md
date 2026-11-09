# Russian player documentation

The maintained outputs at the repository root are `manual.pdf`,
`control.pdf` and `controls-pc.pdf`. The manual adapts the original Russian
`orig/legend/elitelegend_info.pdf` for the v0.8.0 UKNC port. The original
reference PDF is an ignored optional local input. Generated root PDFs are
also ignored and published as release assets; this source directory stays
in Git and rebuilds without that original PDF.

## Sources

| File | Purpose |
|---|---|
| `guide.html` | Startup, controls, screens, saving, contracts and port differences |
| `reference.json` | 49 equipment entries including fuel, seven station entries, nine mission descriptions and three legends |
| `controls.json` | Shared UKNC/PC command descriptions for the manual and both keyboard references |
| `img/` | Sixteen 640×288 captures from the actual port |
| `keyboard-uknc.png`, `keyboard-pc.png` | Offline keyboard artwork with attribution below |

Preserve the original equipment/story sections where they apply, but
validate instructions against the port. Authoritative controls are
`src/res/setup.txt`, raw handlers and the PC player's `MapKey` in
`tools/uknc-headless/uknc-play.cpp`. Commander names allow ten characters;
chart searches allow eight. Default bindings are documented, not inferred
from a user's customized DAT file.

## Rebuild

```sh
make docs
```

Generation is offline with Python, Pillow and Chrome/Chromium. All temporary
HTML, PDF and browser-profile output stays under `tmp/pdfs/manual`.
To build the game, recapture its screens on a disposable disk and rebuild:

```sh
make docs-capture
```

The capture drives real menu keys and leaves player disks untouched.
Individual commands are:

```sh
python3 tools/manual_pdf.py --out manual.pdf
python3 tools/manual_pdf.py --capture --out manual.pdf
python3 tools/control_pdf.py --board uknc --out control.pdf
python3 tools/control_pdf.py --board pc --out controls-pc.pdf
```

## Content constraints and review

The capsule restores a basic Cobra rather than its previous fittings. The
collector works during J-drive; military injectors have higher speed at
the same consumption interval. `P_EJECT`, `P_OREPROC` and `P_TARGETLOCK`
have no distinct gameplay action beyond catalogue/record handling. Keep
these limits explicit; see [compatibility](../compatibility.md).

The manual is 29 A4 portrait pages; each keyboard reference is two A4
landscape pages. After edits, render affected pages with Poppler and inspect
all changed layouts. Check searchable Cyrillic, catalogue headings, section
coverage, page counts and text bounds. A successful browser exit alone does
not establish a usable PDF. Recapture images after visible game changes.

## Artwork attribution

- UKNC keyboard: UKNCBTL, Nikita Zimin (nzeemin),
  https://nzeemin.github.io/ukncbtl-wasm/keyboard.png .
- PC keyboard: “ANSI Keyboard Layout Diagram with Form Factor”, Rumudiez,
  Wikimedia Commons, CC BY-SA 3.0,
  https://commons.wikimedia.org/wiki/File:ANSI_Keyboard_Layout_Diagram_with_Form_Factor.svg .
  The generator crops the form-factor legend and overlays UKNC labels.
  The adapted illustration remains under
  [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).

The project's MIT grant excludes these illustrations and underlying game
and manual content. See [licensing assessment](../licensing.md) before
distributing the PDFs; keep artwork credits and license information with
the distributed adaptations.

Source dates and credits establish provenance; they are not a change log.
