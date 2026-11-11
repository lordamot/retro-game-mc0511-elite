"""Regression cases for the November completion work; run via --only completion."""
import json
from pathlib import Path

import play_disk
import syms


def check_completion(v):
    print("save workflow and remaining Legend rules")
    t = syms.table()
    a = lambda name: int(t[name], 8)
    work = v.ROOT / "tmp/completion"
    work.mkdir(parents=True, exist_ok=True)
    manifest = v.ROOT / "build/manifest.json"
    layout = json.loads(manifest.read_text())
    from rt11fs import Volume
    from rt11_disk import slot_files, install_slots
    source, player = work / "source.dsk", work / "player.dsk"
    pristine = v.PRISTINE.read_bytes()
    source.write_bytes(pristine)
    player.write_bytes(pristine)
    slots = {f'ELSAV{i+1}.DAT': bytes([i+1])*1024 for i in range(4)}
    volume = Volume(player)
    install_slots(volume, slots, work)
    volume.save(player)
    original = player.read_bytes()
    updated = bytearray(pristine)
    exe = Volume(source).find('ELITE.SAV')
    offset = exe.block*512+512
    updated[offset] ^= 1
    source.write_bytes(updated)
    play_disk.refresh(source, player, manifest)
    got = player.read_bytes()
    v.check("refreshing the game preserves all four complete commander files",
            slot_files(player) == slots)
    v.check("refreshing also installs new code and retains a recoverable old disk",
            got[offset] == updated[offset]
            and player.with_suffix(".dsk.bak").read_bytes() == original)
    play_disk.refresh(source, player, manifest)
    v.check("a second launch preserves the same commanders", player.read_bytes() == got)
    player.write_bytes(b"not a disk")
    try:
        play_disk.refresh(source, player, manifest)
    except ValueError:
        pass
    v.check("an invalid existing disk is left untouched", player.read_bytes() == b"not a disk")

    def run(script, name):
        return [int(x, 8) for x in v.PEEK.findall(v.run_emu(
            script + ["quit"], v.fresh_disk("completion-" + name)))]

    jump = ["press 004", v.ui_ready(t)] + ["press 154", v.ui_ready(t, frames=1)] * 3
    jump += [v.poke_at(a("HYP_NOROLL"), 1), "press 107", v.ui_ready(t, frames=1)]
    for support in (0x80, 0x40, 0):
        script = list(v.BOOT) + [v.poke_byte(t, "P_LIFESUPPORT", support),
                  v.poke_byte(t, "P_AUTOREPAIR", 0x80), v.poke_byte(t, "P_WEAR", 254)]
        for good, qty in ((3, 3), (31, 5), (24, 7), (20, 11)):
            script += [v.poke_at(a("P_CARGO") + 2 * good, qty)]
        script += [v.poke_at(a("P_FREECARGO"), 12)] + jump
        script += [f"peekcpu {t['P_JUMPS']}", v.peek_byte(t, "P_WEAR")]
        script += [f"peekcpu {a('P_CARGO') + 2 * g:o}" for g in (3, 31, 24, 20)]
        script += [f"peekcpu {t['P_FREECARGO']}"]
        got = run(script, f"life-{support}")
        want = [3, 5, 7, 11] if support == 0 else [0, 0, 10, 16]
        v.check(f"life support {support:o}: jump converts only unprotected living cargo",
                got[0] == 1 and got[2:6] == want and got[6] == 12, str(got))
        v.check("jump wear saturates at 255", v.byte_of(t, "P_WEAR", got[1]) == 255)

    # Seed at the actual jump-effect call, after the tunnel's random draws
    # and key entropy. These fixtures exercise no repair, each eligible
    # device, and the absent/broken repair system without a probabilistic pass.
    repaired = 0
    for seed, repair, expected in ((0, 0, (0x41, 0x40)),
                                    (1, 0, (0x41, 0)),
                                    (7, 0, (1, 0x40)),
                                    (7, 0x40, (0x41, 0x40)),
                                    (7, 0x80, (0x41, 0x40))):
        script = list(v.BOOT) + [v.poke_byte(t, "P_AUTOREPAIR", repair),
            v.poke_byte(t, "P_WEAR", 0), v.poke_byte(t, "P_ENERGYUNIT", 0x41),
            v.poke_byte(t, "P_GALDRIVE", 0xC1), v.poke_byte(t, "P_ECM", 0x40)]
        script += jump[:-1] + [f"runpc {t['PILOT_JUMP']} 1200",
            v.poke_at(a("RNDSEED"), 0), v.poke_at(a("RNDSEED") + 2, seed),
            v.ui_ready(t, frames=1)]
        script += [v.peek_byte(t, k) for k in ("P_WEAR", "P_ENERGYUNIT", "P_GALDRIVE", "P_ECM")]
        got = run(script, "repair")
        wear, unit, drive, ecm = [v.byte_of(t, k, w) for k, w in zip(
            ("P_WEAR", "P_ENERGYUNIT", "P_GALDRIVE", "P_ECM"), got)]
        n = (unit == 1) + (ecm == 0)
        repaired += n
        v.check(f"repair {repair:o}, seed {seed}: exact mend, no wear underflow or absent-device repair",
                0 <= wear <= 2 and drive == 0xC1 and n <= 1 and (unit, ecm) == expected,
                str((wear, unit, drive, ecm)))
    v.check("working automatic repair actually mends a broken device", repaired == 2, str(repaired))

    fly = list(v.BOOT) + ["press 107", "run 60"] + v.clear_traffic(t) + [v.poke_at(a("PSPEED"), 0)]
    got = run(fly + [v.poke_dev(t, "P_ESCPOD"), v.poke_at(a("WITCH"), 1),
                    "press 035", "run 40", f"peekcpu {t['DOCKED']}", v.peek_dev(t, "P_ESCPOD")], "pod")
    v.check("free-space ejection leaves the ship flying and capsule fitted",
            got[0] == 0 and v.byte_of(t, "P_ESCPOD", got[1]) == 0, str(got))

    got = run(fly + [v.poke_dev(t, "P_ADVCOMPASS")] + ["press 112", "run 8"] * 8 +
              [f"peekcpu {t['CO_MODE']}", f"peekcpu {t['CO_M']}", "press 112", "run 8",
               f"peekcpu {t['CO_MODE']}"], "compass")
    v.check("the advanced compass reaches cardinal mode and wraps after nine modes",
            got[0] == 8 and got[1] > 0 and got[2] == 0, str(got))

    for key, expected in (("TARGONSPYH", 96), ("TARGONINTH", 48)):
        armed = [v.poke_byte(t, "P_DRONE", 1), v.poke_at(a("CARGO") + 2*a("G_DRONE"), 2),
                 v.poke_at(a("BD_FREE"), 0), v.poke_at(a("BD_C"), 0), "press 017", "run 8"]
        target = v.ship_pokes(t, 3, key, z=3000, hostile=False, hyper=False, still=True,
                             **{"U.FLAGS": a("UF_DERELICT")})
        # These mission hulls need not be loaded in Lave.  Test the
        # boarding rule with an explicit lock; ordinary lock acquisition
        # has its own full flight regression in check_drone.
        target += [v.poke_at(int(v.slot_field(t, 3, "U.KIND"), 8),
                    (v.ship_stats(key)["flags"] << 8) | v.ship_stats(key)["type"] | a("KB_BOARD"))]
        script = fly + armed + target + [v.poke_at(a("MISS_LOCK"), 4), "press 113", "run 8"]
        script += ["run 5", f"peekcpu {t['BD_C']}"] * 60
        got = run(script, "boarding")
        v.check(f"{key} uses Legend's distinct naval boarding threshold",
                expected in got and set(got) <= {0, expected}, str(sorted(set(got))))

    # Player alien item: launch from the real function key, then damage
    # the chosen ship.  Keep the victim still and well away from the bay.
    target = v.ship_pokes(t, 3, "KRAITH", z=3000, hostile=False, energy=4000,
                          hyper=False, still=True)
    script = fly + target + [v.poke_dev(t,"P_ALIENCOMP"),
        v.poke_at(a("P_CARGO")+2*a("G_ALIEN"),2), v.poke_at(a("MISS_KIND"),a("MF_ALIEN")),
        v.poke_at(a("MISS_LOCK"),4), "press 113", "run 8",
        f"peekcpu {a('P_CARGO')+2*a('G_ALIEN'):o}"]
    script += [f"peekcpu {v.slot_field(t,k,'U.TYPE')}" for k in range(4,16)]
    script += ["run 180", f"peekcpu {v.slot_field(t,3,'U.ENERGY')}"]
    got = run(script,"alien-launch")
    v.check("alien function spends one item and launches a Targlet at the chosen ship",
            got[0] == 1 and a("SH_TARGLETH") in got[1:13], str(got))
    v.check("the player's Targlet actually attacks its target", 0 < got[-1] < 4000, str(got[-1]))

    # Weak lasers bounce off a protected hull; only the Targoid laser reaches 51 damage.
    for gun, hurts in (("LAS_PULSE",False),("LAS_NAVAL",False),("LAS_MINING",False),("LAS_TARGOID",True)):
        target = v.ship_pokes(t,3,"KRAITH",z=1200,hostile=False,energy=4000,hyper=False,still=True)
        st = v.ship_stats("KRAITH")
        target += [v.poke_at(int(v.slot_field(t,3,"U.KIND"),8),
                             (st["flags"]<<8) | st["type"] | a("KB_MISSPROOF"))]
        script = fly + target + [v.poke_at(a("PLASERS"),a(gun)),v.poke_at(a("PLASTEMP"),0),
            "run 10", "keydown 107", "run 20", "keyup 107",
            f"peekcpu {v.slot_field(t,3,'U.ENERGY')}"]
        got = run(script,"immune-laser")
        v.check(f"{gun} respects the protected-hull damage threshold",
                (got[0] < 4000) == hurts and got[0] > 0, str(got))
