# УКНЦ platform

Addresses and register values are octal unless explicitly marked otherwise.
The CPU is a КМ1801ВМ2 at 8 MHz; the PPU is a КМ1801ВМ2 at 6.25 MHz.
The PPU owns keyboard, floppy firmware, video tables and AY access.
The implementation is checked with the bundled UKNCBTL core. Hardware
claims inferred only from a reference or emulator are not physical-machine
measurements.

## Memory and plane access

| Region | Direct access | Plane-register access |
|---|---|---|
| CPU RAM | CPU | Planes 1 and 2 below plane address `100000` |
| PPU RAM, 32 KiB | PPU | Plane 0 below `100000` |
| Video RAM, three 32 KiB planes | Neither CPU as ordinary RAM | Plane addresses `100000` … `177777` |

CPU word address `A` is plane byte address `A/2`; its low byte is plane 1
and high byte plane 2. A video-window write below `100000` therefore
corrupts CPU RAM. The display occupies `100000` … `154777`, 80 bytes per
line for 288 lines. Above it, each plane has 9728 undisplayed bytes.
Planes 1/2 hold the hull bank there; plane 0 holds overlay cache entries.
Do not draw into either region.

| Processor | Address register | Data register |
|---|---|---|
| CPU | `176640` | `176642`: planes 1/2 |
| PPU | `177010` | `177012`: plane 0; `177014`: planes 1/2 |

Writing the address latches that plane byte for read/modify/write. Data
access does **not** advance the address. The CPU cannot directly access
plane 0. PPU sprite helpers are `177016` (point colour), `177020`/`177022`
(background octet), `177024` (pixel octet read/merge/write) and `177026`
(plane write mask). `CLS_SCREEN_PP` uses the sprite helpers.

The CPU drawing inks are 0/2/4/6: plane 0 supplies pixel bit 0, plane 1
bit 1, plane 2 bit 2. Plane 0 is normally black in the displayed game.

## Line table and colour

Firmware starts the line-table walk at `270`/`272` in PPU RAM. An ordinary
entry is a plane byte address followed by the next-entry pointer. A tagged
entry has two control words before those words. Pointer bit 1 denotes a
four-word next entry; bit 2 selects palette rather than display control.
Bit 0 controls the cursor. Tagged entries must be eight-byte aligned.

The display control's scale field is bits 5..4. Mode word `7` selects
640 pixels, `27` selects 320. At 640×288 the hardware still combines three
planes into eight colours; palette entries map them to eight of sixteen
YRGB colours. A YRGB nibble is bright/red/green/blue in bits 3/2/1/0.
Two palette words contain entries 0–3 and 4–7, low nibble first.

`NEW_TABLE` in `src/ppu.mac` builds the user table at `2410`. The first
200 lines use the space-view palette. A palette element at line 200
selects the dashboard's colours for the remaining 88 lines. Text pages
reuse the full height. Firmware row count and scrolling state are restored
on exit along with the table.

Canonical palette constants remain YRGB. `COMMAND_4` exchanges the red and
green bits of every nibble in both screen palettes when `PALETTE_MODE=0`
(default GRB); mode 1 writes unchanged RGB words. The display-mode word,
bitplanes, cached art and rendering inks stay unchanged. Title keys 1/2
select the layout and reapply the palettes immediately. The resident choice
survives screen changes and restarts; a fresh RT-11 launch resets it to GRB.

Both local emulator runners default to physical GRB output and accept
`--palette grb|rgb`. Their shared `palette.h` swaps decoded red and green,
including attenuated colors and the hardware cursor. The SDL window is
named **Elite УКНЦ МС-0511**. Matching game and emulator choices preserves
the canonical colors; real hardware should use its connector's layout.

The table permits split screens and page flipping, but memory capacity
rules out a second full space-view bitmap in this layout. See
[rendering](rendering.md) for the retained buffering decision.

## CPU/PPU channels

| Channel | CPU transmitter status/data | CPU receiver status/data |
|---|---|---|
| K0 terminal | `177564` / `177566` | `177560` / `177562` |
| K1 game commands | `176664` / `176666` | `176660` / `176662` |
| K2 firmware requests | `176674` / `176676` | — |

K2 carries a pointer to a firmware request block. `ppucomm.mac` uses the
firmware allocator, copy and execution services for reversible takeover.
PPU program and cache addresses are allocated, not hard-coded. K2 request
20 copies without the usual completion-status update; do not wait on that
byte. [RT-11](rt11.md) describes the lifecycle.

K1 commands used by the game are:

| Value | Action |
|---:|---|
| 0 | Clear screen and apply `CPU_MODE` |
| 1 | Restore firmware display/state |
| 2 | Copy overlay words between CPU window and PPU cache |
| 3 | Tune control: stop, once or loop via `MUS_MODE` |
| 4 | Reload palettes/mode without clearing |
| 6 | Fill complete scanlines |
| 7 | Run the PPU memory benchmark |
| -1 | Reset machine |

Command 5 currently dispatches to the clear handler; it is not an active
bitmap-blit interface despite the reserved `CMD_BLIT` name in `defs.mac`.
Long screen fills lower interrupt priority so keyboard releases can arrive.

## Drawing queue and synchronization

The CPU prepares three-word walk records in `gfx.mac`; `RING_PUT` and
`RING_PUT2` publish them to a ring of 256 records. The PPU starts draining
from its timer handler when no drain is already active. It drops priority
while drawing so keyboard, channel and timer interrupts continue.

The CPU owns `RING_HEAD`; the PPU owns `RING_TAIL`. Data is written before
publishing the head. A paired submission takes one tail snapshot when
checking space, preserves new-before-old order, and falls back to single
submissions at wraparound or when two slots are unavailable. A full queue
waits for the consumer. `RING_WAIT` establishes completion before direct
CPU drawing, command dispatch and buffer reuse.

Do not rely on an atomic read/modify/write across processors: the memory
arbiter may interleave the other processor's access. Design single-writer
flags and explicit request/acknowledgement handshakes. A shared ready flag
is not a substitute for publishing data in the correct order.

The PPU program and SFX overlay are position independent. Plain label
operands are PC-relative; immediate `#label` or `label(Rn)` references need
explicit relocation. The CPU copy is reused after upload, except the
published words and other live state identified in `tail.mac`.

## Input and clocks

The PPU hooks its own keyboard, timer and K1 vectors; CPU vectors remain
RT-11's. The four CPU-copy words `PP_KEYS_DATA`, `PP_VSYNC_READY`,
`PP_LASTKEY`, `PP_KEYS2_DATA` must remain consecutive. Held state is also
published to `KEYS`/`KEYS2`; pending edges enter immutable packets in
`KEYS_ACC`/`KEYS2_ACC`. The PPU publishes `KB_SEQ` after the packet, and
`INPUT_POLL` consumes it once and writes `KB_ACK`. Flushes have their own
request/acknowledgement. Edges accumulate while publication is paused.

A keyboard make code is the scancode. Release is `0200 | (code & 017)`:
it names a matrix row, not a key. A release clears all held keys in that
row. `tools/keyfile.py --check` reports conflicts. Text input reads raw
scancode changes, with physical ЙЦУКЕН mapping; see [KEYBOARD.md](../KEYBOARD.md).

The PPU's 50 Hz handler publishes `CPU_VSYNC` and advances `FRAMES` during
normal service. Native I/O defers this work under `RT_IOBUSY` while
retaining firmware motor service. Do not install a separate CPU clock ISR.
`VSYNC_PACE` avoids waiting a whole additional tick after a long frame.
The current emulator core runs one 50 Hz interrupt per `run` tick:
**1/50 second**. Older cores used two interrupts per tick (1/25 second).
The headless `timing` command reports the installed core's frame rate.
Clock counters and game frames are different quantities.

## Arithmetic

The VM2 provides signed `MUL`, `DIV`, `ASH` and `ASHC`. An even-register
`MUL` returns the high/low pair and overwrites both registers; an odd-register
one retains only the low word. `DIV` requires an even pair and signals
quotient overflow. `UMUL` in `rnd.mac` corrects the high word for unsigned
operands. Preserve exact wrapping and signed division when changing geometry.

Shift cost depends on the shift count. A two-bit left shift followed by
selecting the high word can replace a fourteen-bit right shift only where
the required sixteen bits and overflow semantics agree. Instruction counts
alone do not predict cost; use the measurement procedures in
[rendering](rendering.md).
