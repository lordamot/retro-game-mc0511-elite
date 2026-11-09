# Implementation caveats

These are active constraints, grouped by failure mode. Read the called
routine's clobber list and the assembled listing as well as this reference.

## MACRO-11 and VM2 arithmetic

- Default radix is octal. Write decimal values with a trailing dot,
  especially values containing 8 or 9. Invalid bare digits can assemble
  incorrectly or stall the assembler. Confirm values in the listing.
- Expressions evaluate left-to-right without normal operator precedence.
  Bracket a product as a whole; `A+<B-1>*2` is not `A+((B-1)*2)`.
- Branch immediately from the instruction whose flags matter. `MOV` can
  overwrite condition codes, including the overflow from a subtraction.
- `MUL` is signed. An even destination overwrites the next register with
  the low half; an odd destination keeps only the low half. `DIV` needs
  an even pair and an explicit policy for quotient overflow.
- `ASR` sign-extends. A mask shifted down from `0100000` never reaches zero;
  use a positive mask or `CLC`/`ROR` when logical shifting is required.
- `MOVB` sign-extends into a register. Clear the high byte for unsigned
  counts such as a ship energy of 250. `SXT` also changes its destination;
  do not expect a type number to survive there.
- A global label ends the local-label scope. `.BLKW` needs its count in
  pass one; include generated size definitions before buffer declarations.
- `SYMBOL = value` can silently reassign a constant. Search before naming
  one; gameplay kinds use `KD_*`, keyboard bits use `K_*`/`KB_*`.
- An equate based on a later label is not reliable before its own line in
  pass two. Use the original label expression or indexed addressing where
  necessary. Export overlay symbols only from the resident listing.
- `.+4` is a byte displacement, not “skip one instruction.” Use labels.
  `SOB` has a shorter backward range than a general branch; use `DEC`, a
  short exit branch and `JMP` for long loops.
- This assembler rejects register-indirect `JMP` forms used in some PDP-11
  assemblers. Push the destination and `RETURN` when that convention is needed.
- A terse assembler error can be a symbol defined twice with different
  addresses. Check stale exported overlay labels before chasing code.

## Registers and shared temporaries

`RND` clobbers R1–R3 and R5; `U_NEAR` clobbers R0. A ship pointer or type
must be saved or reread after those calls. Follow all helpers' actual
contracts, not a caller's assumption. Read `KEYS_EDGE` from memory when a
previous handler call may have changed the working register.

A memory temporary belongs to one routine's live operation. Nested name,
price, contract or random helpers need separate scratch if values survive
the call. PPU interrupt code must preserve every register its callees use;
`SX_TICK` saves R2–R5, but a helper may still destroy a loop counter kept in
one of them by its immediate caller.

## Coordinates, records and collision rules

- Positions have low and high words. Only use the low word after a
  successful `U_NEAR`; a 16-bit write requires `U_SXT` or explicit high words.
- Two individually near positions can differ by more than 32767. Check
  overflow immediately after their 16-bit subtraction and treat it as far.
- `ROT2` uses three shears. Simultaneous small-angle updates inflate the
  matrix and eventually overflow positions.
- Blueprint radii are not strict bounds. The Coriolis radius field is 160
  while vertices reach 226; culling uses a conservative allowance.
- `U.BR` is body-renderer state and `BODY_FORGET` clears it. Aliases such as
  `U.BCX`/`U.BCY` carry AI state; inspect the current slot layout before
  reusing any word.
- Spawned drops and launches need separation from their parent because
  ships collide. A stationary test target also needs a valid mind, matrix,
  speed, energy and high position words, not merely a type and location.
- Device bits 7/6 mean absent/broken. Test `BITB #DEV_OFF,P_x`; zero can
  mean a fitted type-zero device. Use `DEV_ON`/`DEV_NONE` for state changes.
- Hull bank vertices are fourfold and edge indices are word offsets.
  `SHIP_TABLE` is a bank-address table, not a list of CPU model pointers.

## Memory, overlays and graphics

- Plane addresses below `100000` are ordinary RAM. Drawing there corrupts
  code/stack; drawing above `154777` overwrites bank/cache storage.
- PPU code is relocated. PC-relative operands are valid; absolute local
  addresses need relocation. This applies to the SFX overlay too.
- Preserve all four consecutive PPU published words. Buffers over the
  uploaded CPU copy are uninitialized instruction bytes until their own
  initializer runs. Check `PP_OVER_END` against `PP_KEYS_DATA` after growth.
- `MAIN_START` uploads the PPU once. Death/new-game restarts use
  `MAIN_RESTART`; loaded commanders use `FLY_LOADED`.
- Only the resident may replace the CPU overlay window. Flight calls go
  through `FV_*` with the flight overlay loaded. Persistent state cannot
  live in a cache-restored screen image. SFX's PPU cache is live mutable
  state and is never copied back into the CPU window.
- Ring data must precede publication. Preserve a single owner per shared
  counter/flag; cross-processor read/modify/write is not atomic. Paired
  enqueue tests space from one tail snapshot.
- CPU drawing, screen clears and save staging drain the PPU first.
  `CLIP_LINE` edits endpoints; keep original curve vertices separately.
  XOR segments include both endpoints, including zero-length segments.
- Keep body-list indices consistent when a body is behind the viewer.
  A skipped draw must not attach the sun's previous-frame state to a planet.
- `PUTS2` is double-width heading text. Body columns use `PUTS`. Preserve
  all eleven font rows and restore the dashboard after full-height pages.

## RT-11 and keyboard

Keep the stack and asynchronous state below the swapped USR area. Both
USR and EXIT swapping are required. Preserve `RT_IOBUSY` around native
file calls and retain firmware motor service while longer PPU work is
deferred. K2 copy does not provide the allocator's completion status.

Keyboard release identifies a row. Generate make and release tables from
`src/res/setup.txt`; do not patch generated tables by hand. If table
capacities change, change the key-file magic/layout together. Flight edges
are acknowledged packets; raw typing still depends on observed scancode
changes. Modal prompts need distinct press/release events and time to draw.

## Reliable emulator fixtures

- `peekcpu`, `pokecpu` and `dumpcpu` addresses are octal. `dumpcpu` length
  is decimal. An invalid address can stop the script before later replies.
- Peeking an odd-address byte reads it in the high half of its aligned word.
  Shift by address parity. Check the number of returned values explicitly.
- `SEGCNT` is a partial current frame; read `SEGPREV` for completed geometry.
  Brief flags or damage pulses need tick-by-tick observation, not one peek.
- Resolve symbols from the matching listing. A failed build can leave an
  old disk/listing; use `syms.check_fresh()` and do not rebuild during tests.
- `fresh_disk()` must start from a manifest-reconstructed pristine image.
  Emulator disk writes need not update mtime, so file timestamps cannot
  prove a previously played disk is pristine.
- A longer boot or screen read changes timing and random state. Initialize
  the scene you assert; do not assume the arrival stock or traffic roll.
  `ui_ready(t)` handles nonmodal redraw and the 25-frame switch lockout.
- Clear/disable ambient traffic and bay launches in isolated combat tests.
  Locking selects the lowest suitable slot; place controlled targets
  accordingly and find new objects by type rather than guessed slot.
- Use `ship_pokes`, `ai_pokes`/`mind` and position helpers rather than partial
  slot writes. Verify spawned energy as well as the eventual kill.
- Count cargo by goods, not only free tonnage: kilogram/gram goods do not
  consume a tonne in the same way. Keep banks/fuel/devices sufficient at
  the exact moment a tested action occurs.
- Whole-game AI is frame-based; faster code changes observation timing.
  Verify the event rather than relaxing its rule to fit a stale delay.
- Controlled probes must not overwrite an executing overlay. Renderer RAM
  probes run docked, drain the queue and hold final results stable.

See [testing](testing.md) for commands and [rendering](rendering.md) for
benchmark fixture requirements.
