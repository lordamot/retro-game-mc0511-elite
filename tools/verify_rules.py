"""Focused emulator rule checks.  Invoke through verify_build --only rules.

The probe replaces only the unused window benchmark on a disposable disk's
running RAM. It is entered from the existing drawing benchmark hook, so a
routine executes with the real stack/PPU/overlay and then returns normally.
These are routine-level checks, complementary to the input-driven suite.
"""
import syms


def check_rules(v):
    print("Legend rule boundaries and presentation")
    t = syms.table()
    a = lambda k: int(t[k], 8)
    fly = list(v.BOOT) + ["press 107", "run 60"] + v.clear_traffic(t)
    fly += [v.poke_at(a("PSPEED"), 0)]

    def word(slot, key):
        return int(v.slot_field(t, slot, key), 8)

    def run(script, name):
        return [int(x, 8) for x in v.PEEK.findall(v.run_emu(
            script + ["quit"], v.fresh_disk("rules-" + name)))]

    def call(name, setup=(), regs=None, reads=(), boot=None, overlay=None, result_reg=0, at_call=(), capture=False):
        # PDP-11 CLR @#HARN_GO; MOV #value,Rn; CALL @#routine;
        # MOV R0,@#BENCH_BUF; RETURN.  No patched gameplay instruction.
        code = [0o005037, a("HARN_GO")]
        if overlay is not None:
            code += [0o012700, a(overlay), 0o004737, a("OVL_LOAD")]
        for reg, value in (regs or {}).items():
            code += [0o012700 + reg, value]
        for address, value in at_call:
            code += [0o012737, value, address]
        code += [0o004737, a(name), 0o010037 + result_reg*0o100, a("BENCH_BUF")]
        if capture:
            assert len(reads) <= 15
            for i, address in enumerate(reads):
                code += [0o013737, address, a("BENCH_BUF")+2+2*i]
            reads = [a("BENCH_BUF")+2+2*i for i in range(len(reads))]
        code += [0o012737, 1, a("BENCH_RAM"), 0o000207]
        assert len(code) * 2 <= a("FLY") - a("BENCH")
        patch = [v.poke_at(a("BENCH") + 2*i, w) for i, w in enumerate(code)]
        patch += [v.poke_at(a("DRAW_HARNESS"), 0o000137),
                  v.poke_at(a("DRAW_HARNESS") + 2, a("BENCH")),
                  v.poke_at(a("BENCH_RAM"), 0), v.poke_at(a("HARN_GO"), 1), "run 1"]
        # Overlay loads may take hundreds of ticks. Observe the completion
        # flag with a bounded wait before reading the captured results.
        script = list(fly if boot is None else boot) + list(setup) + patch
        keys = [a("BENCH_RAM"), a("BENCH_BUF")] + list(reads)
        script += [f"waitcpu {t['BENCH_RAM']} 1 1200"]
        script += [f"peekcpu {x:o}" for x in keys]
        values = run(script, name)
        v.check(f"{name} probe returns", len(values) == len(keys) and values[0] == 1)
        return values[1:] if len(values) == len(keys) and values[0] == 1 else []

    # Life on a distant asteroid field, with both signs and exact boundary.
    for x, y, z, expected in ((0, 0, 0, 0), (65535, 0, 0, 0),
                              (65536, -65536, 0, 2), (-65537, 0, 0, 1),
                              (127*65536, 65536, 0, 128), (300*65536, 0, 0, 255)):
        setup = []
        for axis, n in zip(("X", "Y", "Z"), (x, y, z)):
            setup += [v.poke_at(word(0, "U."+axis), n),
                      v.poke_at(word(0, "U."+axis+"H"), n >> 16)]
        got = call("AST_DISTANCE", [v.poke_at(word(0,"U.TYPE"),1)] + setup,
                   {5: a("UNIV")}, boot=list(v.BOOT))
        v.check(f"distant-body magnitude {x,y,z}", got and got[0] == expected, str(got))

    # The front's shortages are specific, while an occupied world does
    # not get the front's market rule applied a second time.
    for x, shortages in ((100, True), (10, False), (240, False)):
        setup = [v.poke_byte(t, "P_WAR", 40), v.poke_byte(t, "P_WAR", 0, 1),
                 v.poke_byte(t, "P_GALAXY", 0), v.poke_at(a("WAR_Y"), 128),
                 v.poke_byte(t, "P_PLANETDATA", x, 3), v.poke_byte(t, "P_PLANETDATA", 128, 1)]
        setup += [v.poke_at(a("P_PRODUCT")+2*g, 17) for g in range(38)]
        got = call("MS_WARMKT", setup, reads=[a("P_PRODUCT")+2*g for g in range(38)])[1:]
        absent = {0,32,37,10,22,26,28,33} if shortages else set()
        v.check(f"war market x={x}: only front-line shortages", got == [0 if g in absent else 17 for g in range(38)])

    # Naval ECM in mission 3 cannot be fired by the commander; ordinary
    # ECM, and the same naval device outside that mission, can.
    for mission, device, fires in ((4,1,False),(4,0,True),(0,1,True),(4,0x41,False)):
        got = call("ECM_START", [v.poke_byte(t,"P_M3",mission),v.poke_byte(t,"P_ECM",device),
                    v.poke_at(a("ECM_TIME"),0)], reads=[a("ECM_TIME")])
        v.check(f"mission {mission}, ECM {device}: station jamming gate", bool(got and got[1]) == fires, str(got))

    # Cardinal bearings follow a turn, without drifting with speed.
    base = [v.poke_at(a("PROLL"),0),v.poke_at(a("PPITCH"),0)]
    got = call("NAV_TURN", base, reads=[a("PMAT")+2*i for i in range(9)])
    v.check("cardinal bearings do not rotate at rest", got[1:] == [16384,0,0,0,16384,0,0,0,16384], str(got))

    # Far-field generation preserves the original group size.  No bay or
    # ordinary traffic participates in this routine-level fixture.
    setup = [v.poke_at(word(k,"U.TYPE"),0) for k in range(16)]
    for slot, distance in ((0,128),(1,8)):
        setup += [v.poke_at(word(slot,"U.TYPE"),a("SH_CORIOLIS")),
                  v.poke_at(word(slot,"U.X"),0),v.poke_at(word(slot,"U.Y"),0),
                  v.poke_at(word(slot,"U.Z"),0),v.poke_at(word(slot,"U.XH"),0),
                  v.poke_at(word(slot,"U.YH"),0),v.poke_at(word(slot,"U.ZH"),distance)]
    got = call("AST_FIELD",setup+[v.poke_at(a("WITCH"),1)],reads=[word(k,"U.TYPE") for k in range(2,16)])
    rocks = [ty for ty in got[1:] if ty]
    v.check("far from the world and sun, a field contains two to four asteroids",
            2 <= len(rocks) <= 4 and all(ty in (a("SH_ASTEROIDHA"),a("SH_ASTEROIDBIGHA")) for ty in rocks),str(rocks))
    v.check("a distant field contains at most one large asteroid",rocks.count(a("SH_ASTEROIDBIGHA")) <= 1)

    for key, spent in (("DRONEH",True),("TARGLETH",False)):
        setup = v.ship_pokes(t,3,key,z=3000,hostile=False,hyper=False,still=True)
        kind = v.ship_stats(key)["type"] | a("KB_PLAYER")
        if spent:
            kind |= a("KB_DRONE")
        setup += [v.poke_at(word(3,"U.KIND"),kind)]
        got = call("DRONE_LOST",setup,{5:word(3,"U.TYPE")},reads=[word(3,"U.TYPE"),word(3,"U.FLAGS")])
        v.check(f"lost {key}: {'spent' if spent else 'returned as alien cargo'}",
                (got[1] == 0) if spent else (got[1] == a("SH_TARGLETH") and got[2] & a("UF_ALIENITEM")),str(got))
    setup = v.ship_pokes(t,3,"TARGLETH",z=3000,hostile=False,hyper=False,still=True,
                          **{"U.FLAGS":a("UF_DROP")|a("UF_DERELICT")|a("UF_ALIENITEM")})
    cargo = a("P_CARGO")+2*a("G_ALIEN")
    got = call("SCOOP_TAKE",setup+[v.poke_at(cargo,0),v.poke_at(a("P_FREECARGO"),10)],
               {5:word(3,"U.TYPE")},reads=[cargo,a("P_FREECARGO"),word(3,"U.TYPE")])
    v.check("a returned Targlet scoops as exactly one alien item",got[1:] == [1,9,0],str(got))

    # The occupied world's side bases must disappear, irrespective of
    # its normal technology/government combination.
    got = call("SYS_BASES_SET",[v.poke_byte(t,"P_M7",3),v.poke_byte(t,"P_M7",255,1),
                v.poke_at(a("P_GALAXY"),254),v.poke_at(a("P_PLANET"),0),v.poke_at(a("SYS_BASES"),255)],
               reads=[a("SYS_BASES")])
    v.check("a Targon-held world has no service/military/hermit/ring bases",got[1:] == [0],str(got))

    # The very last pirate frees the station, and ordinary kills cannot
    # underflow the completed tally.
    pirate = v.ship_pokes(t,3,"KRAITH",z=3000,hostile=True,hyper=False,still=True)
    for tally, expected in ((1,0),(0,0),(2,1)):
        got = call("MS_KILLED",pirate+[v.poke_at(a("PIRATE_ON"),tally),v.poke_at(a("STN_NEAR"),3)],
                   {5:word(3,"U.TYPE")},reads=[a("PIRATE_ON")],boot=list(v.BOOT))
        v.check(f"pirate station tally {tally} resolves to {expected}",got[1:] == [expected],str(got))

    # Every legal boundary on the pilot page, including unsigned 32768+.
    legal_names = ["S_LS_CLEAN","S_LS_OFFENDER","S_LS_FUGITIVE","S_LS_OUTLAW","S_LS_ROGUE"]
    limits = [1,a("LEGAL_FUGITIVE"),256,8192]
    for n in sorted({0,65535,*limits,*(x-1 for x in limits)}):
        got = call("PI_BAND", regs={0:n,2:a("LEGALTAB"),4:a("LEGALNAMES")},
                   boot=list(v.BOOT),overlay="OVL_PILOT",result_reg=1)
        expected = a(legal_names[sum(n >= x for x in limits)])
        v.check(f"pilot page legal band at {n}",got == [expected],str(got))
    for n, expected in ((8,0),(9,1),(16,1),(17,2),(32,2),(33,3),(64,3),(65,4),
                        (128,4),(129,5),(767,5),(768,6),(2815,6),(2816,7),
                        (6655,7),(6656,8),(65536,9)):
        score = n << 8
        got = call("PI_RATING", [v.poke_at(a("RATING_L"),score),v.poke_at(a("RATING_H"),score>>16)],
                   boot=list(v.BOOT),overlay="OVL_PILOT",result_reg=1)
        v.check(f"pilot page rating band at {n}",got == [a(f"S_RT_{expected}")],str(got))

    # Mission text's disk bank: compare every byte with the resource
    # generator, then check every declared offset is a terminated message.
    import json
    import re
    layout = json.loads((v.ROOT/"build/manifest.json").read_text())
    entry = next(e for e in layout["entries"] if e["file"] == "mistext.bin")
    bank = (v.ROOT/"build/mistext.bin").read_bytes()
    from rt11fs import Volume
    disk = v.PRISTINE.read_bytes()
    data = Volume(v.PRISTINE).find('ELITE.DAT')
    start = (data.block + entry['lba'])*512
    v.check("the disk contains the complete mission text bank",
            disk[start:start+len(bank)] == bank)
    offsets = [int(x,8) for x in re.findall(r"^MT_\w+ = ([0-7]+)$",(v.ROOT/"build/mistext.mac").read_text(),re.M)]
    v.check("every mission text label points to a terminated message in the bank",
            len(offsets)>30 and all(0 <= x < len(bank) and b"\x00" in bank[x:] for x in offsets),str(len(offsets)))

    # A rich high-tech world's outfitter must expose the reference list
    # across page boundaries, not just Lave's first page.
    rows = v.legend_equip()
    want = [c for c in range(len(rows)) if v.legend_sale(rows,c,1,15,0,0,0,255,40) is not None]
    script = list(v.BOOT)+[v.poke_byte(t,"P_TECH",15),v.poke_byte(t,"P_ECO",0),
            v.poke_byte(t,"P_MCOMPLETE",255),v.poke_at(a("P_LEGAL"),0),v.poke_at(a("PFUEL"),30)]
    script += ["press 004","run 90"]*5
    script += [f"peekcpu {t['EQ_LAST']}",f"peekcpu {t['EQ_NPAGES']}"]
    script += [f"peekcpu {a('EQ_ROWITEM')+2*i:o}" for i in range(15)]
    got = run(script,"high-tech")
    v.check("high-tech outfitter lists the reference items and page count",
            got[0] == min(15,len(want)) and got[1] == (len(want)+14)//15 and got[2:2+got[0]] == want[:15],str(got[:2]))
    second = run(script + ["press 133", "run 60", f"peekcpu {t['EQ_PAGE']}",
                 f"peekcpu {t['EQ_LAST']}"] +
                 [f"peekcpu {a('EQ_ROWITEM')+2*i:o}" for i in range(15)], "high-tech-page2")[-17:]
    v.check("the outfitter's second page continues the reference list",
            second[0] == 1 and second[1] == min(15,len(want)-15) and
            second[2:2+second[1]] == want[15:30],str(second[:2]))

    # Load a multi-government system's real hull set, then approach its
    # hermit through the normal docking loop rather than forcing DOCKED.
    script = list(v.BOOT) + [v.poke_at(a("SYS_GOVT"),2), "press 107", "run 80"]
    script += v.clear_traffic(t)
    script += v.ship_pokes(t,3,"ASTEROIDSTH",z=600,hostile=False,speed=0,
                          hyper=False,still=True,**{"U.FLAGS":a("UF_BASE")})
    script += [v.poke_at(a("PSPEED"),0), "run 300",
               f"peekcpu {t['DOCKED']}", f"peekcpu {t['DOCKED_AT']}"]
    got = run(script,"hermit-dock")
    v.check("a hermit's bay docks and retains its service identity",
            got == [1,a("BK_HERMIT")],str(got))

    # A held world's barrier becomes stronger as fewer worlds remain.
    for held, expected in ((256,0),(128,32),(1,63)):
        setup = [v.poke_at(a("P_GALAXY"),254),v.poke_at(a("P_PLANET"),0),
                 v.poke_byte(t,"P_M7",3),v.poke_byte(t,"P_RND",0)]
        bits = [0]*32
        for i in range(held):
            bits[i//8] |= 128 >> (i%8)
        setup += [v.poke_byte(t,"P_M7",b,i+1) for i,b in enumerate(bits)]
        setup += [v.poke_byte(t,"P_PLANETDATA",int(i==2),i) for i in (2,3,4,5)]
        got = call("MS_SETM7",setup,reads=[a("M7_BAR")],boot=list(v.BOOT))
        v.check(f"Retribution barrier with {held} occupied worlds",got[1:] == [expected],str(got))

    # Raxxla's guard appears once, at the approach distance, and is
    # peaceful to a clean record.  Both possible hulls are in the core.
    setup = [v.poke_at(word(2,"U.TYPE"),0),v.poke_at(a("WITCH"),0),
             v.poke_at(a("PT_GUARD"),0),v.poke_byte(t,"P_RND",208),
             v.poke_byte(t,"P_PLANETDATA",191,1),v.poke_byte(t,"P_PLANETDATA",64,3),
             v.poke_byte(t,"P_MCOMPLETE",63),v.poke_at(a("RATING_H"),32),
             v.poke_at(a("P_DESTR"),1800),v.poke_at(a("P_LEGAL"),0),
             v.poke_at(word(1,"U.X"),0),v.poke_at(word(1,"U.Y"),0),v.poke_at(word(1,"U.Z"),4*a("BASE_U"))]
    got = call("FV_PORTAL",setup,reads=[a("PT_GUARD")]+[word(k,"U.TYPE") for k in range(2,16)])
    v.check("the Raxxla approach produces one guard",got[1] == 1 and
            sum(ty in (a("SH_ASPH"),a("SH_FERDELANCEH")) for ty in got[2:]) == 1,str(got))

    # A shot between ships records its actual target for the subsequent
    # muzzle-vertex draw pass; it is not an unrelated screen flash.
    target = v.ship_pokes(t,3,"KRAITH",z=3000,hostile=False,energy=4000,hyper=False,still=True)
    shooter = v.ship_pokes(t,4,"TARGLETH",x=500,z=3000,hostile=False,energy=96,hyper=False,still=True)
    shooter += [v.poke_at(word(4,"U.KIND"),v.ship_stats("TARGLETH")["type"] | a("KB_PLAYER"))]
    got = call("FV_ATTACK",target+shooter+[v.poke_at(a("AI_I"),4),v.poke_at(a("AI_SELF"),5)],
               {0:4,5:word(4,"U.TYPE")},reads=[word(3,"U.ENERGY"),a("NPSHOT")+8],
               at_call=[(a("AI_I"),4),(a("AI_SELF"),5)],capture=True)
    v.check("an NPC hit does damage and records the beam's target",got[1:] == [3977,word(3,"U.TYPE")],str(got))

    protected = v.ship_pokes(t,3,"COBRAMK3HT1",z=3000,hostile=False,energy=4000,hyper=False,still=True)
    st = v.ship_stats("COBRAMK3HT1")
    protected += [v.poke_at(word(3,"U.KIND"),(st["flags"]<<8)|st["type"]|a("KB_MISSPROOF"))]
    ordinary = v.ship_pokes(t,4,"COBRAMK3HT1",x=2500,z=3000,hostile=False,energy=4000,hyper=False,still=True)
    got = call("BOMB_FIRE",protected+ordinary+[v.poke_dev(t,"P_EBOMB")],
               reads=[word(3,"U.EXPL"),word(4,"U.EXPL")]+[a("SX_Q")+2*i for i in range(8)])
    v.check("bombs spare protected hulls and destroy ordinary hulls",got[1] == 0 and got[2] > 0,str(got[:3]))
    v.check("the bomb event requests its own AY effect",a("FX_BOMB") in got[3:])

    missile = v.ship_pokes(t,4,"MISSILEH",z=3010,hostile=False,hyper=False,still=True,
                          **{"U.FLAGS":a("UF_MISSILE"),"U.TARGET":4})
    # Capture at the routine boundary: the next flight frame can reuse
    # the spent missile's slot before an emulator tick ends.
    got = call("MISSILE_STEP",protected+missile,
               reads=[word(3,"U.ENERGY"),word(4,"U.TYPE")],capture=True)
    v.check("a missile is spent without damaging a protected hull",got[1:] == [4000,0],str(got))

    import verify_render
    verify_render.check_render(v)
