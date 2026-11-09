"""Exact integer and pixel models for renderer optimizations.

Called by the rules group. A disposable RAM probe runs from the existing
harness hook while docked, writes its results, then stops the CPU in a loop.
Docking keeps flight code out of the overlay window used by the probe; pixel
probes drain the PPU before taking their screenshots. It never patches a
source image or a player's disk.
"""
import math
import random
import struct
from PIL import Image
import syms

def check_render(v):
    print('renderer: exact arithmetic and filled-sun pixels')
    root = v.ROOT
    out = root / 'tmp/render-proof'
    out.mkdir(parents=True, exist_ok=True)
    t = syms.table()
    a = lambda k: int(t[k], 8)
    rng = random.Random(511)
    signed = lambda x: (x + 32768) % 65536 - 32768
    for routine in ('MATVEC', 'MATVEC_T', 'MAT_TURN_P', 'MAT_TURN_RP'):
        code = []
        expected = []
        entry = a('OVL_BASE')
        dest = entry + 4096

        # MOV immediate to absolute/register; JSR PC to absolute.
        def mov(addr, val):
            code.extend([0o012737, val & 65535, addr])

        def reg(r, val):
            code.extend([0o012700 + r, val & 65535])
        for case in range(24):
            m = [rng.randint(-16384, 16384) for _ in range(9)]
            if case == 0:
                m = [16384 if i in (0, 4, 8) else 0 for i in range(9)]
            for i, n in enumerate(m):
                mov(a('PMAT') + 2 * i, n)
            reg(5, a('PMAT'))
            if routine.startswith('MAT_TURN'):
                axis = case % 3
                sin = (512, -1536, 0, 2047)[case % 4]
                tan = (256, -769, 0, 1024)[case % 4]
                mov(a('RT_S'), sin)
                mov(a('RT_T'), tan)
                reg(1, 2 * axis)
                code.extend([0o004737, a(routine)])
                pair = ((0, 1), (1, 2), (0, 2))[axis]
                for k in range(3):
                    i, j = (3 * k + pair[0], 3 * k + pair[1]) if routine == 'MAT_TURN_P' else (3 * pair[0] + k, 3 * pair[1] + k)
                    m[i] = signed(m[i] - (tan * m[j] + 8192 >> 14))
                    m[j] = signed(m[j] + (sin * m[i] + 8192 >> 14))
                    m[i] = signed(m[i] - (tan * m[j] + 8192 >> 14))
                values = m
                source = a('PMAT')
            else:
                vec = [rng.randint(-32768, 32767) for _ in range(3)]
                for i, n in enumerate(vec):
                    mov(a('UN_TMP') + 2 * i, n)
                reg(4, a('UN_TMP'))
                code.extend([0o004737, a(routine)])
                shift = 14
                values = [(sum(((m[3 * j + i] if routine == 'MATVEC_T' else m[3 * i + j]) * vec[j] for j in range(3))) & 0xffffffff) >> shift & 65535 for i in range(3)]
                source = a('VOUT')
            for i, n in enumerate(values):
                code.extend([0o013737, source + 2 * i, dest + 2 * len(expected)])
                expected.append(n & 65535)
        mov(a('BENCH_RAM'), 1)
        code.append(0o000777)  # BR .: results stay stable until dumped
        assert len(code) * 2 < 4096
        disk = v.fresh_disk('render-' + routine)
        dump = out / (routine + '.bin')
        patch = [v.poke_at(entry + 2 * i, w) for i, w in enumerate(code)]
        patch += [v.poke_at(a('DRAW_HARNESS'), 0o000137), v.poke_at(a('DRAW_HARNESS') + 2, entry), v.poke_at(a('BENCH_RAM'), 0), v.poke_at(a('HARN_GO'), 1)]
        result = v.run_emu(list(v.BOOT) + ['run 20'] + patch + ['run 100', f"peekcpu {t['BENCH_RAM']}", f'dumpcpu {dest:o} {len(expected) * 2} {dump}', 'quit'], disk)
        got = list(struct.unpack('<' + 'H' * len(expected), dump.read_bytes()))
        v.check(routine + ' matches the integer model for 24 cases', got == expected and [int(n, 8) for n in v.PEEK.findall(result)] == [1], str([(i, x, y) for i, (x, y) in enumerate(zip(got, expected)) if x != y][:5]))
    cases = [[(320, 100, 40)], [(0, 100, 40)], [(639, 100, 40)], [(320, 0, 40)], [(320, 199, 40)], [(320, 100, 40), (340, 107, 40)], [(320, 100, 40), (320, 100, 70)], [(320, 100, 40), (900, 100, 40)], [(320, 100, 40), (320, -200, 40)], [(900, 100, 40), (320, 100, 40)], [(320, 100, 600)], [(0, 0, 100), (639, 199, 100)], [(320, 100, 40), (0, 0, 0)], [(320, 100, 40), (32767, 100, 40)], [(320, 100, 40), (320, -32768, 40)]]
    for ix, seq in enumerate(cases):
        code = []

        def call(k):
            code.extend([0o004737, a(k)])

        def mov(k, n):
            code.extend([0o012737, n & 65535, a(k)])
        call('SEG_RESET')
        call('CLS_SCREEN')
        for cx, cy, r in seq:
            for k, n in [('PL_CX', cx), ('PL_CY', cy), ('PL_R', r), ('PL_RX', r * 5 // 3)]:
                mov(k, n)
            call('SUN_FILL')
        call('RING_WAIT')
        code.append(0o000777)
        entry = a('OVL_BASE')
        patch = [v.poke_at(entry + 2 * i, w) for i, w in enumerate(code)]
        patch += [v.poke_at(a('DRAW_HARNESS'), 0o000137), v.poke_at(a('DRAW_HARNESS') + 2, entry), v.poke_at(a('HARN_GO'), 1)]
        disk = v.fresh_disk('sun-pixels')
        bmp = out / f'{ix}.bmp'
        script = list(v.BOOT) + ['run 20'] + patch + ['run 60', f'screenshot {bmp}', 'quit']
        v.run_emu(script, disk)
        im = Image.open(bmp).convert('RGB').crop((0, 0, 640, 200))
        im.save(out / f'{ix}.png')
        cx, cy, r = seq[-1]
        rx = r * 5 // 3
        expected = Image.new('RGB', (640, 200))
        px = expected.load()
        if r:
            for y in range(200):
                dy = abs(y - cy)
                if dy > r:
                    continue
                q = dy * 256 // r
                width = 0 if q == 256 else round(255 * math.sqrt(1 - (q / 256) ** 2)) * rx // 255
                for x in range(max(0, cx - width), min(639, cx + width) + 1):
                    px[x, y] = (255, 255, 255)
        v.check(f'filled sun pixels after transition {ix}', im.tobytes() == expected.tobytes(), str(seq))

    check_vertex_projection(v, t, out)
    check_walk_pairs(v, t, out)
    check_system_font(v, t, out)


def check_vertex_projection(v, t, out):
    """Check wrapped matrix sums, near rejection, DIV overflow and SP balance."""
    a = lambda key: int(t[key], 8)
    signed = lambda n: (n + 32768) % 65536 - 32768
    identity = [16384 if i in (0, 4, 8) else 0 for i in range(9)]
    cases = []
    for z in (-1, 0, a('ZNEAR') - 1, a('ZNEAR'), a('ZNEAR') + 1, 32767):
        for x, y in ((0, 0), (-32768, 0), (32767, 0), (0, -32768), (0, 32767)):
            cases.append((identity, [0, 0, 0], [x, y, z]))
    rng = random.Random(512)
    while len(cases) < 96:
        cases.append(([rng.randint(-32768, 32767) for _ in range(9)],
                      [rng.randrange(-8192, 8192) * 4 for _ in range(3)],
                      [rng.randint(-32768, 32767) for _ in range(3)]))

    def model(matrix, vertex, offset):
        xyz = [signed(signed((sum(matrix[3*i+j] * vertex[j] for j in range(3))
                             & 0xffffffff) >> 16) + offset[i]) for i in range(3)]
        if xyz[2] < a('ZNEAR'):
            return None
        projected = []
        for n, scale in zip(xyz[:2], (a('PROJ_DX'), a('PROJ_D'))):
            q = abs(n * scale) // xyz[2]
            if n < 0:
                q = -q
            if not -32768 <= q <= 32767:
                return None
            projected.append(q)
        return ((projected[0] + a('VIEW_XC')) & 65535,
                (a('VIEW_YC') - projected[1]) & 65535)

    for batch in range(4):
        code = []
        expected = []
        entry, dest = a('OVL_BASE'), a('OVL_BASE') + 4096

        def mov(address, value):
            code.extend([0o012737, value & 65535, address])

        for i, (matrix, vertex, offset) in enumerate(cases[batch*24:(batch+1)*24]):
            for j, value in enumerate(matrix):
                mov(a('PMAT') + 2*j, value)
            for j, value in enumerate(vertex):
                mov(a('UN_TMP') + 2*j, value)
            for axis, value in zip(('X', 'Y', 'Z'), offset):
                mov(a('SD_' + axis), value)
            result = dest + 10*i
            code.extend([0o010637, result + 6])  # SP before CALL
            code.extend([0o012704, a('UN_TMP'), 0o012705, a('PMAT'),
                         0o004737, a('VERT_PROJECT')])
            # MOV preserves C; ADC converts the returned carry to 0/1.
            code.extend([0o012702, 0, 0o005502])
            code.extend([0o010037, result, 0o010137, result+2,
                         0o010237, result+4, 0o010637, result+8])
            expected.append(model(matrix, vertex, offset))
        mov(a('BENCH_RAM'), 1)
        code.append(0o000777)
        assert 2*len(code) < 4096
        patch = [v.poke_at(entry + 2*i, word) for i, word in enumerate(code)]
        patch += [v.poke_at(a('DRAW_HARNESS'), 0o000137),
                  v.poke_at(a('DRAW_HARNESS')+2, entry),
                  v.poke_at(a('BENCH_RAM'), 0), v.poke_at(a('HARN_GO'), 1)]
        dump = out / f'projection-{batch}.bin'
        log = v.run_emu(list(v.BOOT) + ['run 20'] + patch + [
            'run 100', f"peekcpu {t['BENCH_RAM']}",
            f'dumpcpu {dest:o} {24*10} {dump}', 'quit'],
            v.fresh_disk('projection-model'))
        words = struct.unpack('<120H', dump.read_bytes())
        errors = []
        for i, want in enumerate(expected):
            x, y, carry, before, after = words[5*i:5*i+5]
            if before != after or carry != int(want is None) or (want is not None and (x, y) != want):
                errors.append((batch*24+i, (x, y, carry, before, after), want))
        v.check(f'fused vertex projection: exact results and stack, cases {batch*24}..{batch*24+23}',
                not errors and [int(n, 8) for n in v.PEEK.findall(log)] == [1], str(errors[:3]))


def check_walk_pairs(v, t, out):
    """A long paired stream must survive full-ring waits and several wraps."""
    a = lambda key: int(t[key], 8)
    code, labels, branches = [], {}, []
    entry, records = a('OVL_BASE'), a('BENCH_BUF')

    def mov(address, value):
        code.extend([0o012737, value & 65535, address])

    def call(name):
        code.extend([0o004737, a(name)])

    def branch(opcode, label):
        branches.append((len(code), opcode, label))
        code.append(0)

    call('SEG_RESET')
    call('CLS_SCREEN')
    mov(a('RING_STALL'), 0)
    mov(a('HARN_GO'), 511)
    mov(a('HARN_TICKS'), 0)
    for i, word in enumerate((639, 0, a('VRAM'), 639, 0, a('VRAM')+80)):
        mov(records + 2*i, word)
    labels['loop'] = len(code)
    code.extend([0o012704, records, 0o012705, records+6])
    call('RING_PUT2')
    code.extend([0o062737, 80, records+4, 0o062737, 80, records+10])
    code.extend([0o023727, records+4, a('VRAM')+199*80])
    branch(0o103400, 'next')  # BLO
    mov(records+4, a('VRAM'))
    mov(records+10, a('VRAM')+80)
    labels['next'] = len(code)
    code.extend([0o005337, a('HARN_GO')])
    branch(0o001000, 'loop')  # BNE
    call('RING_WAIT')
    mov(a('HARN_TICKS'), 1)
    code.append(0o000777)
    for i, opcode, label in branches:
        delta = labels[label] - i - 1
        assert -128 <= delta < 128
        code[i] = opcode | (delta & 255)
    patch = [v.poke_at(entry+2*i, word) for i, word in enumerate(code)]
    patch += [v.poke_at(a('DRAW_HARNESS'), 0o000137),
              v.poke_at(a('DRAW_HARNESS')+2, entry), v.poke_at(a('HARN_GO'), 1)]
    bmp = out / 'paired-wrap.bmp'
    keys = ('HARN_GO', 'HARN_TICKS', 'RING_HEAD', 'RING_TAIL', 'RING_STALL')
    log = v.run_emu(list(v.BOOT) + ['run 20'] + patch + ['run 400'] +
                   [f'peekcpu {t[key]}' for key in keys] + [f'screenshot {bmp}', 'quit'],
                   v.fresh_disk('paired-wrap'))
    values = [int(n, 8) for n in v.PEEK.findall(log)]
    im = Image.open(bmp).convert('RGB').crop((0, 0, 640, 200))
    im.save(out / 'paired-wrap.png')
    expected = Image.new('RGB', (640, 200))
    # 511 pairs over 199 starting rows cancel every intermediate row.
    for y in (0, 511 % 199):
        for x in range(640):
            expected.putpixel((x, y), (255, 255, 255))
    v.check('paired walks preserve pixels through full-ring waits and wraps',
            values[:2] == [0, 1] and values[2] == values[3] and values[4] > 0 and
            im.tobytes() == expected.tobytes(), str(values))


def check_system_font(v, t, out):
    """Check authentic ROM pixels at all three scales and page restoration."""
    from font_gen import read_font
    from elite_re import KOI7
    import re
    a = lambda key: int(t[key], 8)
    rom = v.ROM.read_bytes()
    bank = {}
    for c in range(32, 96):
        index = KOI7.get(chr(c), chr(c)).encode('koi8-r')[0]
        offset = 0o20170 + (index - 32) * 11
        bank[c] = rom[offset:offset + 11]
    resource = read_font(v.ROOT / 'src/res/font/uknc11.txt')
    converted = {c: bytes(sum((ch == '#') << x for x, ch in enumerate(row))
                         for row in rows) for c, rows in resource.items()}
    v.check('all 64 system glyphs retain the ROM rows and KOI-7 mapping',
            converted == bank and a('FONT_H') == 11)
    code = []
    def call(name):
        code.extend([0o004737, a(name)])
    def mov(name, value):
        code.extend([0o012737, value, a(name)])
    def reg(r, value):
        code.extend([0o012700 + r, value])
    call('SEG_RESET')
    call('CLS_SCREEN')
    expected = Image.new('RGB', (640, 288))
    pixels = expected.load()
    def glyph(c, col, row, sx, sy, routine):
        mov('TX', col)
        mov('TY', row)
        reg(0, c)
        call(routine)
        for y, b in enumerate(bank[c]):
            for x in range(8):
                if b & (1 << x):
                    for dy in range(sy):
                        for dx in range(sx):
                            pixels[col*8+x*sx+dx, row+y*sy+dy] = (255,255,255)
    for c in range(32, 96):
        i = c - 32
        glyph(c, i % 32, i // 32 * 12, 1, 1, 'PUTC')
        glyph(c, i % 16 * 2, 30 + i // 16 * 12, 2, 1, 'PUTC2')
    for i, ch in enumerate('ЙДЦЩ'):
        c = ord(next(k for k, value in KOI7.items() if value == ch))
        glyph(c, i * 4, 92, 4, 4, 'PUTBIG')
    # Exercise the final legal row and prove TEXT_CLEAR removes descenders.
    c = ord(next(k for k, value in KOI7.items() if value == 'Щ'))
    glyph(c, 79, 277, 1, 1, 'PUTC')
    reg(0,79); reg(1,277); reg(2,1); call('TEXT_CLEAR')
    for y in range(277,288):
        for x in range(632,640): pixels[x,y]=(0,0,0)
    call('RING_WAIT')
    mov('BENCH_RAM',1)
    code.append(0o000777)
    assert len(code)*2 < 5120
    entry = a('OVL_BASE')
    patch = [v.poke_at(entry+2*i,w) for i,w in enumerate(code)]
    patch += [v.poke_at(a('DRAW_HARNESS'),0o000137),
              v.poke_at(a('DRAW_HARNESS')+2,entry),v.poke_at(a('HARN_GO'),1),
              v.poke_at(a('BENCH_RAM'),0)]
    bmp = out/'system-font.bmp'
    result = v.run_emu(list(v.BOOT)+['run 20']+patch+
                      ['run 200',f"peekcpu {t['BENCH_RAM']}",f'screenshot {bmp}','quit'],
                      v.fresh_disk('system-font'))
    actual = Image.open(bmp).convert('RGB')
    actual.save(out/'system-font.png')
    v.check('system font pixels at normal, double and quadruple size; full-height erase',
            [int(n,8) for n in v.PEEK.findall(result)] == [1] and
            actual.tobytes() == expected.tobytes())

    # All mission coordinates must fit the expanded row height, including
    # the one-row top margin. The binary tokens contain zero-valued coords.
    data = (v.ROOT/'build/mistext.bin').read_bytes()
    offsets = [int(n,8) for n in re.findall(r'^MT_\w+ = ([0-7]+)$',
               (v.ROOT/'build/mistext.mac').read_text(),re.M)]
    bad = []
    for start in offsets:
        pos = start
        while pos < len(data) and data[pos]:
            token = data[pos];pos+=1
            if token == 1:
                x,y=data[pos:pos+2];pos+=2
                if (y+1)*11+11 > 288 or x+14 >= 80:bad.append((start,x,y))
    v.check('all mission text coordinates fit the authentic font height',not bad,str(bad))
    script = list(v.BOOT)+['run 30']+['press 004','run 160']*4
    script += [f"peekcpu {t['SCREEN']}",f"peekcpu {t['DASH_CK']}"]
    script += ['press 004','run 160']*6
    script += [f"peekcpu {t['SCREEN']}",f"peekcpu {t['DASH_CK']}",
               f"peekcpu {t['CKV_NUM']}",'quit']
    result = v.run_emu(script,v.fresh_disk('font-pages'))
    got=[int(n,8) for n in v.PEEK.findall(result)]
    v.check('full-height pages invalidate the dashboard and returning restores it',
            len(got)==5 and got[:3]==[4,65535,0] and got[3]==got[4],str(got))
