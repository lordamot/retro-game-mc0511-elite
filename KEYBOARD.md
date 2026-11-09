# Keyboard and controls

These are the default UKNC bindings and their physical PC equivalents in
`bin/ukncbtl/uknc-play`. Changing the host language layout is unnecessary:
the emulator reads SDL key positions. The Russian printable references are
`control.pdf` and `controls-pc.pdf`, available as release assets or built
locally with `make docs`.

## Commands by context

Ordinary **ВВОД / Enter** and **numeric-block ВВОД / Right Ctrl or keypad
Enter** are different keys. Startup needs two separate ordinary Enter
presses, followed by ФИКС / Left Ctrl at the logo. Death and new-game
restarts go straight to that logo.

| УКНЦ key | PC key | Where | What it does |
|---|---|---|---|
| ← → | ← → | cockpit | roll |
| ↑ ↓ | ↑ ↓ | cockpit | pitch |
| ВВОД | Enter | startup welcome and controls | advance one page; the second Enter opens the Legend logo |
| ФИКС | Left Ctrl | title screen | start |
| ФИКС | Left Ctrl | cockpit | fire the laser (held; heats up and cuts out) |
| ФИКС | Left Ctrl | docked | launch - with ПОДТВЕРЖДЕНИЕ НА ВЗЛЕТ on in the pause menu, after НАЧАТЬ РАССТЫКОВКУ?: Н (PC Y) yes, Т (PC N) or СТОП no, Ф (PC A) yes and never ask again |
| АР2 | Tab | active game screens | the pause menu: the game and its clock stand still; see [The pause menu](#the-pause-menu) |
| ФИКС | Left Ctrl | either chart | hyperspace to the system under the cursor — or, with the cursor left on the system you are already in, or on a system of another galaxy the chart is showing, the galactic drive |
| space | Space | cockpit | lock on whatever is under the gunsight; again to let a missile go - or, with `8` on СБОР ГРУЗА, to have a locked canister fly itself into the scoop; with `8` on АБОРДАЖНЫЙ ДРОН, to send a drone at a locked wreck (a ship whose crew has ejected) and, on the roll, take it into a berth; with `8` on ЗАПРАВКА ИЗ БАКА, no lock needed: the extra tank fills the main one |
| ВВОД on the numpad | Right Ctrl, or keypad Enter | cockpit | step the throttle up, and round to a stop past full ahead |
| СТОП | Esc | normal game screens | cockpit → chart → short chart → data → market → outfitter → yard → commander's record → access menu → carrier market → cockpit |
| `1` | `1` | cockpit | look front → rear → left → right → front |
| `2` | `2` | cockpit | fire the ECM, if one is fitted |
| `3` | `3` | cockpit | activate the fitted energy bomb or Q-bomb, once |
| `6` | `6` | cockpit | eject in the escape capsule, once; unavailable in free space or without a rescuing station |
| `8` | `8` | cockpit | what the space bar does next, round the functions there is something for: РАКЕТА, ВОЕННАЯ РАКЕТА, ИНОПЛАНЕТНЫЙ ДРОН (the alien computer, with alien items in the hold; launches a Targlet at the locked ship), СБОР ГРУЗА (the auto-take, with the device), АБОРДАЖНЫЙ ДРОН (the boarding system, with a drone in the hold), ЗАПРАВКА ИЗ БАКА (the extra tank, with fuel in it), ДЕСАНТ (the war's assault troops aboard: the space bar sends them at a locked station the Targons hold) |
| `9` | `9` | cockpit | the cloaking device on (with the last bank full) and off |
| О | `J` | cockpit | HELD: the J-drive - every body and bay races towards you and past - while nothing mass-locks it; locked (a ship on the scanner, a bay within 4500, a world within 8000), the fuel injectors instead, if fitted: full speed and more, the stick dead, a tenth of fuel every 32 frames |
| М | `V` | cockpit | the advanced compass's next mode, if one is fitted: АВТО, СОЛНЦЕ, ПЛАНЕТА, СТАНЦИЯ, ВОЕННАЯ БАЗА, АСТЕРОИД, ЗАПРАВКА, КОЛЬЦО, СТОРОНЫ СВЕТА (horizontal north/south and vertical east/west markers; dash ahead, dot behind) |
| Ы | `S` | cockpit | the scanner's next mode: ВСЕ, КОРАБЛИ, ГРУЗ, ГРУЗ МИГАЕТ |
| А | `F` | cockpit | turn the laser turrets, if the ship has them (Legend's pause-menu A): with two the front and rear guns change places, with four every gun moves one mount round (left to front, front to right, right to rear, rear to left) |
| ← → | ← → | market | sell one / buy one |
| ФИКС | Left Ctrl | market | sell everything of this good in the hold, or if there is none, buy as much as the shelf, the hold and the purse allow |
| ↑ ↓ | ↑ ↓ | market, outfitter | pick the row; in the outfitter, past either end of the page turns it |
| ← → | ← → | outfitter | previous / next page of the list |
| ФИКС | Left Ctrl | outfitter | buy the row (a laser then asks which mount: ↑ ↓ and ФИКС again); at a service station, mend it |
| ↑ ↓ | ↑ ↓ | yard | pick the row, or on the berths' options, the option |
| ВВОД | Enter | yard | the other list: the ships for sale here, or the ones you own and where they are |
| → ← | → ← | yard, berths list | onto the two options (ПРОДАТЬ, and ВЫБРАТЬ or ДОСТАВИТЬ) and back |
| ФИКС | Left Ctrl | yard | buy the ship (your hold is sold, your ship berthed or, with no berth free, sold with its fittings); on the berths, do the option |
| ↑ ↓ | ↑ ↓ | access menu | pick the line; ← → go to the first and the last |
| ФИКС | Left Ctrl | access menu | choose: the load list, the save list, or exit; in a list, that slot - a save asks the name first (edit it, ВВОД), a load restarts the game as that commander |
| ВВОД | Enter | access menu, in a list | back to the menu |
| ↑ ↓ | ↑ ↓ | carrier market | pick the row; ← → go to the first and the last |
| ВВОД | Enter | carrier market | the other list: the station's offers (at the main station only) or your own contracts with the hours left on each |
| ФИКС | Left Ctrl | carrier market | open the row: what goes where within how long, what the trip takes, what it pays; then ↑ ↓ ← → pick a line and ФИКС does it - take the contract (or, in your own list, tear it up), or go back |
| ← → ↑ ↓ | ← → ↑ ↓ | either chart | walk the cursor (↑↓ move sixteen systems, ←→ one) |
| ВВОД | Enter | either chart | ПОИСК: name a system and the cursor goes to it |
| `9` | `9` | either chart | with the experimental galactic drive fitted and whole, the jump to Raxxla - no fuel, no interception, the drive kept (Legend's R held on the jump) |
| `1` `2` | `1` `2` | galaxy chart | look at the galaxy before or after, as far as the drive fitted reaches: none for the standard drive, three either way for the military one, all forty-eight for the experimental |
| `3` | `3` | galaxy chart | the list of the galaxy's systems, twenty a page, with the fuel to each, the travel time, the tech level and the government - with a navigation array, and for another galaxy the experimental one; again, the chart. In the list ↑↓ walk a system and ←→ a page |
| `1`..`4` | `1`..`4` | КАКОЙ КОМАНДИР? | pick a commander slot |
| letters, digits, space | see below | ИМЯ? and ПОИСК | type |
| забой | Backspace | ИМЯ? and ПОИСК | rub out the last character |
| ВВОД | Enter | ИМЯ? | that is the name — nothing typed gives ЯМЕСОН, the name every Elite starts with |
| ВВОД | Enter | ПОИСК | go and look for it |
| СТОП | Esc | ПОИСК | forget the whole thing |

The docking computer engages automatically at zero throttle with a station
in range. Docking and capsule rescue save the commander; the access menu
also supports explicit saves. Exit through АР2 then Ч (PC Tab then X)
does **not** save automatically.

## Pause menu

АР2 / Tab opens pause during gameplay. The sky and commander clock stop.
Press ПРОБЕЛ / Space or АР2 / Tab to resume. The displayed letters are
UKNC physical-key labels, with PC equivalents below.

| УКНЦ | PC | Option | What it does |
|---|---|---|---|
| Й | Q | НОВАЯ ИГРА | the game again from the title, with no question: the commander as the disk last had him |
| Ы | S | ЗВУКОВЫЕ ЭФФЕКТЫ | the effects and the tune on or off |
| И | B | ИНВЕРСИЯ УПРАВЛЕНИЯ | the stick inverted: ← rolls right, ↑ pitches down |
| Н | Y | ИНВЕРСИЯ КЛАВИШ ВВЕРХ/ВНИЗ | ↑ and ↓ swapped (with И as well: only the roll is inverted) |
| К | R | ИНЕРЦИОННОЕ УПРАВЛЕНИЕ | off: an opposite key stops a turn dead; on: it slows it through zero, a step a frame |
| В | D | ПОСТОЯННАЯ СКОРОСТЬ ПОВОРОТА | let go, a turn keeps its rate instead of springing back |
| У | E | АВТОВКЛЮЧЕНИЕ П.Р.О. | the auto-ECM armed or not (the bit flips with no device fitted, as in Legend; a bought one comes armed) |
| З | P | АВТОКАТАПУЛЬТИРОВАНИЕ | the auto-eject armed or not, the same way |
| А | F | ПЕРЕХВАТ ТАРГОНОВ | every hyperspace jump is intercepted into witchspace |
| С | C | УПРОЩЕННАЯ СТЫКОВКА | the slot need not be level to dock; still not rolling, still slow |
| Г | U | ПОДТВЕРЖДЕНИЕ НА ВЗЛЕТ | ФИКС in the station asks before launching |
| Ф | A | ПОВОРОТ ЛАЗЕРНЫХ ТУРЕЛЕЙ | the turrets turn, as А does in flight |
| Ч | X | ВЫХОД В ОС | restore the terminal and return to RT-11; save by docking or through the commander menu before exiting |

Options are session settings initialized from the key file, not saved
commander fields. Spectrum joystick, second-locator and General Sound
options are absent.

## Configuring flight bindings

`src/res/setup.txt` contains `COMMAND = KEY [KEY ...]` bindings and
`OPTION = 0|1` startup settings. Keys can be Cyrillic letters, digits,
names such as `ФИКС`, `ВВОД`, `ДОП.ВВОД`, `СТОП`, `АР2`, `ПРОБЕЛ`,
or octal scancodes. List names and check matrix conflicts with:

```sh
python3 tools/keyfile.py --names
python3 tools/keyfile.py src/res/setup.txt --check
```

The build generates four fixed-capacity PPU tables and DAT-relative block 2.
`KEY_INIT` checks the magic and copies valid disk settings over the compiled
defaults. To customize a disposable or backed-up disk:

```sh
cp src/res/setup.txt tmp/my-keys.txt
# Edit tmp/my-keys.txt, then:
python3 tools/keyfile.py tmp/my-keys.txt --check
python3 tools/keyfile.py tmp/my-keys.txt --disk tmp/custom.dsk
```

A refresh replaces DAT with the build's copy. Keep persistent defaults in
`src/res/setup.txt` or reapply disk customization after refresh. The splash
and PDF tables describe the default map; regenerate their text if shipping
changed defaults. Typing, pause letters and modal prompts use raw scancodes
and are not remapped by the flight key file.

## Typing Russian on a PC

| PC row | Russian output |
|---|---|
| `Q W E R T Y U I O P [ ]` | Й Ц У К Е Н Г Ш Щ З Х Ъ |
| `A S D F G H J K L ; '` | Ф Ы В А П Р О Л Д Ж Э |
| `Z X C V B N M , .` | Я Ч С М И Т Ь Б Ю |

Digits and Space type themselves. Ё is not mapped. Backspace deletes the
last character. Commander names allow **10 characters** (`NAME_MAX`);
system searches allow **8** (`FIND_MAX`) and match a prefix. Empty name
entry uses ЯМЕСОН. Enter finishes; Esc cancels a system search.

## Input protocol and matrix caveats

The keyboard IRQ on the PPU decodes make/release codes into two held words.
It accumulates press edges in acknowledged packets; `INPUT_POLL` consumes
each once. A press and release during native RT-11 I/O is retained until
publication resumes. CPU vectors remain RT-11's.

Typing reads changes in `PP_LASTKEY`, mapped by `NM_TAB` in `src/name.mac`.
A held key does not repeatedly type. Scripts must let modal screens draw
and send distinct press/release events; arbitrary text is not buffered as
a string by the edge-packet mechanism.

A make code equals the scancode. Release is `0200 | (code & 017)` and
clears **every held key in that matrix row**. Avoid adding a key in a row
used by a held control. Default compromises are right-arrow/Enter/Space
sharing row 013 and О/J sharing row 015 with capsule key 6. The latter is
acceptable because rescue ends that flight. The keyfile checker reports
conflicts; generated release tables must cover every assigned row.

The four consecutive published words in `src/ppu_keys.mac` and the
sequence/acknowledgement protocol must stay consistent with `input.mac`.
See [platform](docs/platform.md) for timing and shared-memory ownership.

## Scancodes

All values are octal. The authoritative PC mapping is `MapKey` in
`tools/uknc-headless/uknc-play.cpp`; raw name mapping is `NM_TAB` and flight
commands are `src/res/setup.txt`.

| Key | Code | Key | Code | Key | Code |
|---|---|---|---|---|---|
| ← | 0116 | Й | 0027 | Ф | 0047 |
| → | 0133 | Ц | 0050 | Ы | 0070 |
| ↑ | 0154 | У | 0051 | В | 0071 |
| ↓ | 0134 | К | 0052 | А | 0072 |
| ФИКС | 0107 | Е | 0033 | П | 0053 |
| ВВОД | 0153 | Н | 0054 | Р | 0074 |
| ВВОД (numpad) | 0166 | Г | 0055 | О | 0075 |
| СТОП | 0004 | Ш | 0036 | Л | 0056 |
| АР2 | 0006 | Щ | 0037 | Д | 0057 |
| space | 0113 | З | 0157 | Ж | 0137 |
| забой | 0132 | Х | 0156 | Э | 0136 |
| `1`..`3` | 0030 0031 0032 | Ъ | 0155 | Я | 0067 |
| `4`..`6` | 0013 0034 0035 | Ч | 0110 | С | 0111 |
| `7`..`9` | 0016 0017 0177 | М | 0112 | И | 0073 |
| `0` | 0176 | Т | 0114 | Ь | 0115 |
| | | Б | 0076 | Ю | 0077 |

## Headless input

The headless emulator takes UKNC scancodes, not PC key names:

```sh
python3 tools/uknc_control.py keys
python3 tools/uknc_control.py play --disk tmp/test.dsk FIRE1 1 ENTER
```

`play` boots through the startup pages to the logo before sending these
keys. Raw scripts use `press CODE`, `keydown CODE` and `keyup CODE` in
octal. For dependable test navigation use the startup boundaries and
`ui_ready()` described in [testing](docs/testing.md), with a disposable disk.
