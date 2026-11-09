# Elite Legend compatibility and limits

The port uses Legend's expanded data and rules, with a native УКНЦ engine
and screens. Implemented scope is summarized in [the index](README.md).
This page records differences that matter to players or maintainers.

## Unimplemented or inapplicable features

| Feature | Current behavior |
|---|---|
| Attract demo | Deferred by the operator |
| Cargo discard, `P_EJECT` | Catalogue and record field only; the pilot page is read-only and there is no jettison action |
| Ore processor, `P_OREPROC` | Catalogue and record field only; scooped ore is not enriched |
| Target-lock enhancement, `P_TARGETLOCK` | No separate gameplay improvement; ordinary missile locking works without it |
| Joystick option, second locator, General Sound | Spectrum-specific pause options are absent |
| General geometry on the PPU | Not implemented; geometry remains on the CPU |

Do not describe the three catalogue-only devices as functional merely
because they can be listed, fitted or damaged. Their limits are explicit
in the Russian manual.

## Controls, screens and persistence

The game uses UKNC keys and the port's `setup.txt`, not Spectrum
`setup.ini`. See [KEYBOARD.md](../KEYBOARD.md). Flight bindings are
configurable; typing and pause letters use raw physical scancodes.

The welcome and controls pages are startup-only additions. The logo still
requires ФИКС. The dashboard is parametric with Legend scanner dishes;
the 640×288 layout and 8×11 font are native to this target. The chart's
galaxy selector replaces a separate galaxy-list page.

The outfitter uses text status columns instead of Spectrum row attributes.
Carrier pages use row marks for reputation and affordability, explain
refusals, and show distance rather than an embedded destination chart.
Contracts compare both galaxy and planet on delivery; their port records
are 14 bytes. Names are generated from contract state, not Spectrum text
addresses, and loading regenerates offers from saved state.

Commander files preserve the port's 772-byte record, not Spectrum binary
packing. Exit does not save. Docking, rescue and explicit access-menu saves
write the selected RT-11 file. Pause options are session settings initialized
from the key file, outside the commander record.

## Flight and equipment

- Steering uses Q14 matrices and 32-bit positions rather than Legend's
  byte shears and 24-bit coordinates. `ROT2` uses three shears to avoid
  cumulative scale growth.
- Ships collide. Drops are placed below their parent and launches beside
  it to avoid immediate self-collision; Legend ships pass through each other.
- NPC fire at the commander requires steering at the commander. A kill by
  another ship pays the player nothing. Far nonpersistent ships are culled
  according to `AI_GONE` and near-range rules.
- The docking computer activates at zero throttle with a station in range;
  there is no separate engagement key.
- Capsule rescue requires normal space and a rescuing station. It restores
  a basic Cobra Mk III, not the previous equipment. Cash, rating and mission
  progress survive; cargo/equipment are reset, legal status is reduced,
  passenger contracts are refused, and the result is saved.
- The fuel collector works during J-drive travel. Military injectors are
  faster than ordinary ones at the same fuel-consumption interval.
- All laser types participate in the port's heat behavior. Naval ECM defeats
  both missile types; no separate enemy-ECM suppression effect is implemented.
- A lost boarding drone is spent. A player Targlet that loses its target
  becomes alien cargo to collect; it does not instantly return to the hold.

## Presentation and sound

The sun is filled and there is a twelve-star field, rendered with the
port's own geometry and differencing. Dashboard lamps show ECM, cloak and
danger; danger flashes its lamp while the view palette remains readable.
ECM-blocked missile attempts report why. Spectrum colour-attribute effects
are not reproduced pixel for pixel.

Legend supplies 26 AY effects. Its `OnlySFX` build has no PT3 music; the
port adds the Blue Danube on a second AY chip for title and docking.
There is no music in flight. General Sound samples are not used.

An economy simulated by traffic and coordinated tactical packs are outside
the current scope; they are not missing Legend features.
