"""Native RT-11 lifecycle, filesystem safety and legacy-save migration checks."""
from pathlib import Path
import struct
from rt11fs import Volume
from rt11_disk import slot_files, SLOTS, LEGACY_PREFIX
import play_disk
import syms

LETTERS = {'A':'072','B':'076','C':'050','D':'057','E':'033','F':'047','G':'055',
           'H':'156','I':'073','J':'027','K':'052','L':'056','M':'112','N':'054',
           'O':'075','P':'053','Q':'067','R':'074','S':'111','T':'114','U':'051',
           'V':'137','W':'071','X':'115','Y':'070','Z':'157',' ':'113'}

def command(text, wait=500):
    lines=[]
    for c in text:
        lines += [f'press {LETTERS[c]}', 'run 3']
    return lines+['press 153',f'run {wait}']


def files(path):
    v=Volume(path)
    return {e.name: bytes(v.img[e.block*512:(e.block+e.length)*512])
            for e in v.read_dir()[1] if e.status & 0o2000}


def check_rt11(v):
    print('RT-11 files, migration, native writes and clean exit/relaunch')
    t=syms.table(); a=lambda n:int(t[n],8)
    work=v.ROOT/'tmp/rt11-proof';work.mkdir(exist_ok=True)
    disk=v.fresh_disk('rt11-files')
    protected=files(disk)
    v.check('SAV, DAT and unmodified RT-11 boot/system files are present',
            all(n in protected for n in ('ELITE.SAV','ELITE.DAT','RT11SJ.SYS','SWAP.SYS'))
            and disk.read_bytes()[:512]==(v.ROOT/'orig/rt11/RT11BASE.DSK').read_bytes()[:512])
    sav=protected['ELITE.SAV'];dat=protected['ELITE.DAT']
    v.check('SAV entry and DAT pairing header are correct',
            struct.unpack_from('<H',sav,0o40)[0]==a('RT_ENTRY')
            and sav[a('RT_HEADER'):a('RT_HEADER')+32]==dat[:32])
    v.check('stack and PPU mailboxes are below the USR swap region',
            a('STACK_TOP')<=0o136000 and a('PP_END')<=0o136000 and a('MEM_TOP')<=0o146400)

    # Use the existing emulator-only harness entry from a docked frame.
    # No disk image patches and no CPU-vector hooks. All four files round-trip.
    entry=a('OVL_BASE');code=[]
    def mov(addr,value):code.extend([0o012737,value & 65535,addr])
    def call(name):code.extend([0o004737,a(name)])
    def carry(dest):code.extend([0o012700,0,0o005500,0o010037,dest])
    for i in range(4):
        mov(a('CMDR_SLOT'),i);mov(a('CASH_L'),1111+i);call('SAVE_CMDR')
        carry(a('BENCH_BUF')+2*i)
    # Replace an existing permanent slot; the old file must become free.
    mov(a('CMDR_SLOT'),2);mov(a('CASH_L'),7777);call('SAVE_CMDR')
    carry(a('BENCH_BUF')+8)
    for i in range(4):
        mov(a('CMDR_SLOT'),i);mov(a('CASH_L'),0);call('LOAD_CMDR')
        carry(a('BENCH_BUF')+10+2*i)
        code.extend([0o013737,a('CASH_L'),a('BENCH_BUF')+18+2*i])
    # A request beginning inside DAT but extending past EOF must fail
    # before changing the destination (the last block is only a guard).
    mov(a('SAVE_BUFFER'),0xBEEF)
    code.extend([0o012700,len(dat)//512-1,0o012701,a('SAVE_BUFFER'),0o012702,512])
    call('DATA_READ');carry(a('BENCH_BUF')+26)
    code.extend([0o013737,a('SAVE_BUFFER'),a('BENCH_BUF')+28])
    call('INPUT_FLUSH')
    code.extend([0o013700,a('KB_FLUSH'),0o020037,a('KB_FLUSHED'),0o001375])
    mov(a('KEYS_ACC'),0);mov(a('RT_IOBUSY'),1)
    mov(a('BENCH_RAM'),1);code.append(0o000777)
    patch=[v.poke_at(entry+2*i,w) for i,w in enumerate(code)]
    patch += [v.poke_at(a('DRAW_HARNESS'),0o000137),v.poke_at(a('DRAW_HARNESS')+2,entry),
              v.poke_at(a('BENCH_RAM'),0),v.poke_at(a('HARN_GO'),1)]
    dump=work/'files.bin'
    out=v.run_emu(list(v.BOOT)+patch+['run 1800',f'peekcpu {t["BENCH_RAM"]}',
        f'dumpcpu {t["BENCH_BUF"]} 30 {dump}',f'dumpcpu {t["PROG_SIZE"]} 128 {work/"stack.bin"}',
        'press 107','run 10',f'peekcpu {t["KEYS_ACC"]}',v.poke_at(a('RT_IOBUSY'),0),
        'run 5',f'peekcpu {t["KEYS_ACC"]}','quit'],disk)
    results=struct.unpack('<15H',dump.read_bytes())
    v.check('four files save, overwrite and load through native RT-11 calls',
            results[:9]==(0,)*9 and results[9:13]==(1111,1112,7777,1114)
            and [int(x,8) for x in v.PEEK.findall(out)][:1]==[1],str(results))
    keys=[int(x,8) for x in v.PEEK.findall(out)][1:]
    v.check('a complete short key press survives the RT-11 I/O pause',
            keys==[0,a('K_FIRE')],str(keys))
    v.check('a resource read crossing EOF fails without touching its buffer',results[13:]==(1,0xBEEF),str(results[13:]))
    after=files(disk)
    v.check('every slot is two blocks with the expected commander record',
            all(len(after.get(name,b''))==1024 and struct.unpack_from('<H',after[name],a('CASH_L')-a('PILOT'))[0]==cash
                for name,cash in zip(SLOTS,(1111,1112,7777,1114))))
    v.check('saving preserves system, executable and resource files',
            all(after.get(n)==b for n,b in protected.items() if n!='SWAP.SYS'))
    v.check('no tentative save files remain after CLOSE',
            not any(e.status & 0o400 for e in Volume(disk).read_dir()[1]))

    # Stack watermark covers file calls and their monitor/interrupt nesting.
    # The pattern is installed before switching off the initial low stack.
    stack=work/'stack.bin'
    v.check('native file calls retain the bottom 128 bytes of stack reserve',stack.read_bytes()==struct.pack('<H',0o125252)*64)

    saved_disk=work/'saved.dsk';saved_disk.write_bytes(disk.read_bytes())
    def failure_probe(disk, routine):
        program=[0o012737,4321,a('CASH_L'),0o012737,0,a('CMDR_SLOT'),
                 0o004737,a(routine),0o012700,0,0o005500,
                 0o010037,a('BENCH_BUF'),0o000777]
        patch=[v.poke_at(entry+2*i,w) for i,w in enumerate(program)]
        patch += [v.poke_at(a('DRAW_HARNESS'),0o000137),v.poke_at(a('DRAW_HARNESS')+2,entry),v.poke_at(a('HARN_GO'),1)]
        out=v.run_emu(list(v.BOOT)+patch+['run 600',f'peekcpu {t["BENCH_BUF"]}',f'peekcpu {t["CASH_L"]}','quit'],disk)
        return [int(x,8) for x in v.PEEK.findall(out)]

    full=work/'full.dsk';full.write_bytes(saved_disk.read_bytes());volume=Volume(full)
    for i,e in enumerate(list(volume.read_dir()[1])):
        if e.status & 0o1000 and e.length:
            payload=work/'fill.bin';payload.write_bytes(bytes(e.length*512))
            volume.put(f'F{i}.DAT',payload)
    volume.save(full);old=slot_files(full)
    r=failure_probe(full,'SAVE_CMDR')
    v.check('a full disk rejects replacement and preserves the old commanders',
            r==[1,4321] and slot_files(full)==old,str(r))

    # The actual save-menu failure must also retain the current slot.
    # Once names are read, moving its cursor should not do directory I/O.
    menu=['press 004',v.ui_ready(t)]*(a('NSCREENS')-2)
    script=list(v.BOOT)+menu+['press 134',v.ui_ready(t),'press 107',v.ui_ready(t),
        f'peekcpu {t["CPU_VSYNC"]}','press 134',v.ui_ready(t,2),
        f'peekcpu {t["CPU_VSYNC"]}',f'peekcpu {t["SV_SEL"]}',
        'press 107','run 40','press 153',v.ui_ready(t),
        f'peekcpu {t["CMDR_SLOT"]}',f'peekcpu {t["SV_MSG"]}',f'peekcpu {t["CASH_L"]}','quit']
    values=[int(x,8) for x in v.PEEK.findall(v.run_emu(script,full))]
    v.check('cached save-menu cursor movement completes within one second',
            len(values)==6 and values[2]==1 and 0<((values[1]-values[0])&65535)<=50,str(values[:3]))
    v.check('a full-disk save from the menu keeps the current slot and commander files',
            len(values)==6 and values[3:]==[0,a('S_V_DISKERR'),1111] and slot_files(full)==old,str(values[3:]))

    # Automatic docking saves must report failure too, not merely the
    # explicit save menu. This is a real launch/dock on the filled volume.
    shot=work/'full-dock.bmp'
    script=list(v.BOOT)+[v.poke_dev(t,'P_DOCKCOMP'),'press 107','run 50']
    script+=['press 166','run 20']*4+['run 1000',f'peekcpu {t["DOCKED"]}',
        f'peekcpu {t["SAVE_STATUS"]}',f'screenshot {shot}','quit']
    values=[int(x,8) for x in v.PEEK.findall(v.run_emu(script,full))]
    from PIL import Image
    picture=Image.open(shot).convert('RGB')
    picture.save(work/'full-dock.png')
    banner=picture.crop((32,170,400,181)).convert('L').getbbox()
    v.check('failed automatic docking save shows a warning and preserves the commander files',
            values==[1,1] and banner is not None and slot_files(full)==old,str(values))

    for kind in ('missing','truncated','bad-header'):
        bad=work/(kind+'.dsk');bad.write_bytes(saved_disk.read_bytes());volume=Volume(bad)
        volume.rm('ELSAV1.DAT')
        if kind!='missing':
            payload=work/'bad.dat'
            payload.write_bytes(after['ELSAV1.DAT'][:512] if kind=='truncated' else bytes(1024))
            volume.put('ELSAV1.DAT',payload)
        volume.save(bad)
        r=failure_probe(bad,'LOAD_CMDR')
        v.check(kind+' save is rejected without replacing the current commander',r==[1,4321],str(r))

    reboot=v.run_emu(list(v.BOOT)+[f'peekcpu {t["PP_ACTIVE"]}',f'peekcpu {t["DOCKED"]}',f'peekcpu {t["CASH_L"]}','quit'],saved_disk)
    values=[int(x,8) for x in v.PEEK.findall(reboot)]
    v.check('a cold reboot after real swap and save writes loads the commander',values==[1,1,1111],str(values))

    relocated=work/'relocated.dsk';relocated.write_bytes(v.PRISTINE.read_bytes())
    volume=Volume(relocated);oldblock=volume.find('ELITE.DAT').block
    payload=work/'relocate.dat';payload.write_bytes(protected['ELITE.DAT'])
    volume.rm('ELITE.DAT');volume.put('PAD.DAT',payload);volume.put('ELITE.DAT',payload)
    newblock=volume.find('ELITE.DAT').block;volume.save(relocated)
    out=v.run_emu(list(v.BOOT)+['press 107','run 100',f'peekcpu {t["DOCKED"]}',f'peekcpu {t["HULL_FILL"]}','quit'],relocated)
    values=[int(x,8) for x in v.PEEK.findall(out)]
    v.check('moving ELITE.DAT to different physical blocks still loads flight and hulls',
            oldblock!=newblock and len(values)==2 and values[0]==0 and 0<values[1]<=5120,str(values))
    for kind in ('missing-data','mismatched-data','truncated-data'):
        bad=work/(kind+'.dsk');bad.write_bytes(v.PRISTINE.read_bytes());volume=Volume(bad)
        if kind=='missing-data':volume.rm('ELITE.DAT')
        elif kind=='mismatched-data':
            e=volume.find('ELITE.DAT');volume.img[e.block*512+16]^=1
        else:
            payload=work/'short.dat';payload.write_bytes(dat[:512])
            volume.put('ELITE.DAT',payload)
        volume.save(bad)
        out=v.run_emu(list(v.POWER_ON)+[f'peekcpu {t["PP_ACTIVE"]}',f'peekcpu {t["RT_OLDSP"]}',f'screenshot {work/kind}.bmp','quit'],bad)
        values=[int(x,8) for x in v.PEEK.findall(out)]
        v.check(kind+' returns with the PPU inactive',values==[0,0o1000],str(values))

    # A legacy raw disk migrates all record bytes without touching its backup.
    legacy=work/'legacy.dsk';raw=bytearray(819200);raw[:len(LEGACY_PREFIX)]=LEGACY_PREFIX
    records={name:after[name] for name in SLOTS}
    for i,name in enumerate(SLOTS):raw[(100+2*i)*512:(102+2*i)*512]=records[name]
    legacy.write_bytes(raw)
    play_disk.refresh(v.PRISTINE,legacy,v.ROOT/'build/manifest.json')
    v.check('legacy raw commanders migrate into all four normal files',slot_files(legacy)==records)
    v.check('migration retains the exact original disk as backup',legacy.with_suffix('.dsk.bak').read_bytes()==raw)

    unknown=work/'unknown.dsk'
    original=(v.ROOT/'orig/rt11/RT11BASE.DSK').read_bytes()
    unknown.write_bytes(original)
    try:
        play_disk.refresh(v.PRISTINE,unknown,v.ROOT/'build/manifest.json')
    except ValueError:
        pass
    v.check('a non-Elite RT-11 disk is not mistaken for the legacy NOP loader',
            unknown.read_bytes()==original and not unknown.with_suffix('.dsk.bak').exists())

    # Three native exits and launches: restored CPU vectors, reusable PPU
    # allocations, command processor input, and restored terminal display.
    disk=v.fresh_disk('rt11-exit')
    before=work/'before.bin';aftercpu=work/'after.bin'
    lines=list(v.BOOT)+[f'dumpcpu 0 512 {before}']
    for i in range(3):
        if i==2:
            lines += ['press 107','run 200',f'dumpcpu {t["PROG_SIZE"]} 128 {work/"flight-stack.bin"}']
        lines += [f'peekcpu {t["PP_ACTIVE"]}',f'peekcpu {t["OC_BASE"]}',
                  'press 006','run 160','press 110','run 400',f'peekcpu {t["PP_ACTIVE"]}']
        if i<2:
            lines += command('DIR')+command('R ELITE',1600)
            lines += v.SPLASH_KEYS + v.CHOOSE_KEYS + v.COMMANDER_KEYS
    lines += [f'dumpcpu 0 512 {aftercpu}']+command('DIR')
    lines += [f'screenshot {work/"monitor.bmp"}','quit']
    out=v.run_emu(lines,disk);p=[int(x,8) for x in v.PEEK.findall(out)]
    v.check('three launches allocate PPU memory and each exit releases it',
            len(p)==9 and all(p[i]==1 and p[i+1]!=0 and p[i+2]==0 for i in (0,3,6)),str(p))
    v.check('PPU allocation address is reused after each exit',len(p)==9 and p[1]==p[4]==p[7])
    v.check('flight retains the bottom 128 bytes of stack reserve',
            (work/'flight-stack.bin').read_bytes()==struct.pack('<H',0o125252)*64)
    # Vector words 4, 100, 300 and EMT 30 were never installed by Elite.
    b=before.read_bytes();e=aftercpu.read_bytes()
    v.check('CPU trap, timer, EMT and console vectors survive unchanged',
            all(b[n:n+4]==e[n:n+4] for n in (0o4,0o30,0o100,0o300)))
    from PIL import Image
    Image.open(work/'monitor.bmp').save(work/'monitor.png')
