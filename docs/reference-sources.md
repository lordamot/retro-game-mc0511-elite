# Reference sources and formats

The UKNC implementation is native MACRO-11. Original game inputs establish
data and rule semantics; they are not CPU code to execute on the target.
Normal builds use readable extracted resources under `src/res/`.
Originals, third-party binaries and optional external checkouts are not
tracked. [Checkout setup](setup.md) lists their local paths and requirements.

## Elite Legend

The expanded game's primary reference is Elite Legend 128K v1.09 under
`orig/legend/EliteLegend_v1_09_source/`. The source is Z80/sjasmplus with
Russian CP866 comments. Use `rg -a` to search and decode CP866 when reading;
a binary-file warning or mojibake is not evidence that a symbol is absent.
The Russian reference manual is `orig/legend/elitelegend_info.pdf`.
The port's adapted manual is built from [manual sources](manual/README.md).

The source includes banked engine/menu code, 55 hull geometries with role
headers, cockpit variables/artwork and design notes. `tools/legend_build.py`
builds a runnable ZEsarUX reference snapshot using the supplied assembler.
A table or comment should be checked against executable source and, where
necessary, reference behavior before claiming exact equivalence.

| Legend location | What to check | UKNC owner |
|---|---|---|
| `INCLUDE/Ships/d_*D.a80`, `d_*H.a80` | Geometry and role statistics | Text blueprints, `ships_gen.py`, hull/ship modules |
| `Info/SlotInfo.txt`, `INCLUDE/Engine/` | Object flags, movement, targets and AI | Universe records and flight overlay |
| `INCLUDE/Pilot.var.a80` | Commander fields and device packing | `pilot.mac`, `save.mac` |
| `INCLUDE/InfoShips.a80`, `Cocpits/Cocpit_Var/` | Ship sales, fit masks and limits | Catalogue/cockpit resources and generators |
| `INCLUDE/Menu/priceEquip.a80`, `Info/Equip.txt` | Equipment names, gates and prices | Equipment resources and outfitter |
| `INCLUDE/Galaxy/` | Seeds, market and carrier generation | Galaxy, market and contract modules |
| `INCLUDE/Menu/Missions.a80`, mission messages, `Info/war*.txt` | Mission gates, state and text | Resident mission hooks and mission overlay |
| `Info/Objects.txt` | Bases, stations and gates | `bases.mac`, flight portal handling |
| `Library/LibSFX`, `INCLUDE/Main/Sound.a80` | Effects engine and requests | `ppu_sfx.mac`, `sound.mac`, effect resources |

### Object and hull formats

Legend's object slot is 51 bytes and its universe has sixteen slots.
Coordinates are three 24-bit values; orientation has nine 16-bit components.
Subsequent bytes hold speed, rotation, energy, header address, flags,
targets, counters and type. The port uses its own aligned slot layout,
32-bit coordinates and Q14 matrices; read `U.*` definitions, not Spectrum
offsets, when touching a live UKNC object.

The Legend hull header is 24 bytes. Geometry uses six-byte vertices
(magnitude coordinates, signs/cull and face pairs), four-byte edges
(cull, two vertex indices, face pair) and four-byte normals. Multiple
headers can share geometry while assigning different roles/statistics.
The extracted port roster includes 69 headers on 55 unique hulls.

The header's type low bits distinguish trader, police, pirate, hunter,
Targon, asteroid, missile and static kinds; higher bits include boardable
and missile-proof. Legend's cargo bit 6 denotes a fixed commodity, bit 7 a
mission container. The generator converts ordinary cargo to the port's
packed drop representation; mission containers are handled by type in
mission logic. Legacy `SH_*` names and tier lists remain compatibility
aliases; they are not the full AI spawn policy.

Legend's axis/cosine semantics use a scale of 63, not 127, and
`ScalarMultVectors` negates its dot product: bit 7 set denotes an acute
angle. Reproduce these rule decisions deliberately when translating them
to the port's matrix representation.

### Commander and content

The port preserves Legend's fields and values while aligning some fields
and widening others. Device bytes keep absent bit 7, broken bit 6 and
low type/mode bits. A fitted type-zero device is represented by zero.
The 772-byte port record is not a Spectrum save-file image.

The catalogue has twenty rows including the non-purchasable entry and
nineteen purchasable ships, twenty cockpit blocks, 49 equipment rows and
38 goods. Carrier offers use twelve station slots and six player slots;
the port aligns contract records to 14 bytes. Use the extracted tables
and generators for exact prices, probabilities and fit masks.

Mission state covers the nova, cloaked Asp, Targon station, alien computer,
Constrictor, plans, the eight-rank war, Confrontation, Retribution, portals
and Raxxla, plus related generation-ship/platform and pirate-base behavior.
Do not infer implementation from the source manual alone: known deviations
and inactive catalogue devices are listed in [compatibility](compatibility.md).

Legend's sound build defines `OnlySFX`. It uses 29 table entries referring
to 26 effect files, not PT3 music. An effect is a loop offset followed by
frame flags: noise present (bit 0), tone present (bit 1), loop (bit 2), end
(bit 3), and volume (bits 4–7), with the indicated operands. General Sound
samples are separate and not used by the port.

## Russian 1985 Spectrum disk

`orig/ELITE.SCL` supplies the original Russian world vocabulary and a
second reference for the underlying Elite formats. `elite_re.load_image()`
reconstructs `elitr1` at **0x5B00** and `elitr2` at **0x7000–0xFFFF**.
The BASIC loader's printed address 16384 is not the load destination: its
machine-code REM loader specifies 0x5B00.

nzeemin's [SkoolKit disassembly](https://github.com/nzeemin/skoolkit-game-revs/tree/master/elite128-zx)
is an annotated secondary map. Its object table at 0x6180 matches 76 bytes
at offset 0x680 of the disk's `elitr1`; this confirms the load address and
image correspondence. Check annotations against local bytes before using
them as evidence.

### Text and galaxy generation

| Location / range | Meaning |
|---|---|
| Literal bytes 0x20–0x7F | KOI-7 Cyrillic |
| 0xFD9B, twelve pairs | Separate short syllable table; not the text-token base |
| 0xFDB3, 32 pairs | Digrams used for text tokens and the port's system-name generation |
| Bytes 0x80+k and 0xE4+k | Both refer to digram k |
| Bytes 0xA0–0xE3 | Phrase tokens, indexed from the terminated-string run at 0xF11A |
| 0xF2FE onward | Species tables: three sizes, six colours, six traits, eight kinds |

The localized Spectrum font places Ч at Latin J and Э at digit 3.
`planet_extract.py` applies those fixups. One colour entry at 0xF322 is
empty; preserve it. Resource rows retain both the source stem and displayed
Russian form, because the port does not copy the original suffix engine.

Galaxy generation steps three 16-bit words as `(w1, w2, w0+w1+w2)`, four
steps per system. Pair indexing is `2 * ((w2 >> 8) & 31)`, not
`(2 * (w2 >> 8)) & 31`. Host checks use the English table's canonical
Lave case as an algorithm reference; it does not imply that the Russian
startup screen must display “Lave.”

### Original blueprint and table decoding

The nineteen-entry table at 0x6180 has four-byte records: a skipped 0xC3
opcode, a two-byte blueprint pointer and a class byte. The **1985** header
is 23 bytes, distinct from Legend's 24-byte header:

| Byte offset | Meaning |
|---:|---|
| 0, 1, 2 | Cargo, collision distance, laser accuracy |
| 3, 4, 5 | Vertex, edge and normal counts |
| 6, 7 | Speed and energy |
| 8–9 | Bounty in tenths |
| 10, 11 | Launch flags/count and dot-distance size |
| 12–17 | Vertex, edge and normal offsets from the header base |
| 18–20 | Flags and reserved fields |
| 21–22 | Combat rating points |

Coordinates use magnitude plus sign, so mirrored vertices may have the
same magnitude bytes. Edge/vertex cull thresholds use five bits; 31 means
always visible. Edge face nibbles support backface culling. A zero-normal
object is visible from both sides. The port projects endpoints selected
by visible edges rather than trusting the vertex's four-face membership.

The original cargo high nibble is one less than the fixed market index;
zero denotes mixed cargo. Its low nibble is the number of dropped canisters.
The launch low three bits are the launch count; upper bits must not be
assigned semantics without evidence. Active Legend missions and launch
rules use their own translated type/state handling.

The 1985 market is seventeen four-byte entries at 0x701B: price, packed
gradient/unit/sign, quantity and fluctuation mask. It is a reference format,
not the port's active 38-good market. Its rating is a weighted three-byte
counter, not an unweighted kill count; Legend's extended fields and
thresholds govern the current port.

## UKNC and RT-11 references

Vlad Zhigalov's manuscript [Ресурсы УКНЦ](https://emuverse.ru/wiki/Ресурсы_УКНЦ)
provides firmware and video context. Treat unmeasured book descriptions as
reference claims. The implementation uses CPU video address register
`176640`, despite the book's `177640` printing. Current register ownership,
line tables and native lifecycle are documented in [platform](platform.md)
and [RT-11](rt11.md), not inferred from a bare-metal example.

UKNCBTL by Nikita Zimin supplies the emulator core and ROM; Richard
Krehbiel's macro11 supplies the assembler, with project crash-fix patches.
RT-11 base volume and macro library provenance is in
[orig/rt11/README.md](../orig/rt11/README.md). Builds use these local inputs;
no sibling checkout is needed for the game build. ZEsarUX runs the Spectrum
reference. Retain their upstream licences and attribution.

## scr256db

The optional local `external/scr256db` is ilynxy's wireframe demo from
[the upstream repository](https://gitlab.com/ilynxy/scr256db), referenced at
`b45e1ba031aa8bd194644b0110a4c291baefb0cd`. It has no repository licence file;
the operator received the author's permission to use it on 2026-09-27.
Credit ilynxy wherever its code or ideas are used; that permission does not
establish a general upstream licence.

It uses 256×128 orthographic geometry, byte vertices, PPU transformation,
CPU drawing and two 4 KiB CPU-RAM buffers. Palette selection displays
alternating plane bytes as separate doubled rows. Unrolled DDA and its
single-writer synchronization are useful references, but this is not a
replacement renderer for a 640×200 perspective world. The author's cycle
counts are source claims; the demo has not been validated as a current
port benchmark. No predicted offload speedup is a measured port result.
