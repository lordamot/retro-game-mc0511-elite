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
from pathlib import Path
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
    check_docking_geometry(v, t, out)
    check_hull_fetch(v, t, out)
    check_face_visibility(v, t, out)
    check_walk_pixels(v, t, out)
    check_span_pixels(v, t, out)


def check_hull_fetch(v, t, out):
    """All bank hulls: exact copy length, cached repeat, registers and stack."""
    import shiplib
    from ships_gen import bank_layout, record_bytes
    a = lambda key: int(t[key], 8)
    ships = shiplib.read_dir(v.ROOT / 'src/res/legend/ships')
    _, offsets = bank_layout(ships)
    cases = [(ship.key, a('HBANK_ADDR') + offset, record_bytes(ship))
             for ship, offset in zip(ships, offsets) if not ship.geometry]
    errors, register_errors = [], []
    for batch in range(0, len(cases), 20):
        subset = cases[batch:batch+20]
        entry, dest = a('OVL_BASE'), a('OVL_BASE') + 4096
        code, stops = [], []
        for _, bank, _ in subset:
            code += [0o012737, 0, a('HULL_CACHED'),
                     0o012701, a('HULL_BASE'), 0o012702, 256,
                     0o012700, 0xa55a, 0o010021, 0o077202]
            for reg in range(1, 6):
                code += [0o012700 + reg, 1000 + reg]
            code += [0o010637, dest+12, 0o012700, bank, 0o004737, a('HULL_FETCH'),
                     0o012700, bank, 0o004737, a('HULL_FETCH')]
            for reg in range(6):
                code += [0o010037 + (reg << 6), dest+2*reg]
            code += [0o010637, dest+14]
            stops.append(entry + len(code)*2)
            code.append(0o000777)
        assert len(code)*2 < 4096
        script = list(v.BOOT) + ['run 20']
        script += [v.poke_at(entry+2*i, word) for i, word in enumerate(code)]
        script += [v.poke_at(a('DRAW_HARNESS'), 0o000137),
                   v.poke_at(a('DRAW_HARNESS')+2, entry), v.poke_at(a('HARN_GO'), 1)]
        for i, stop in enumerate(stops):
            prefix = out / f'hull-fetch-{batch+i}'
            script += [f'runpc {stop:o} 100', f"peekcpu {t['HULL_CACHED']}",
                       f"dumpcpu {t['HULL_BASE']} 512 {prefix}.bin",
                       f'dumpcpu {dest:o} 16 {prefix}-regs.bin']
            if i+1 < len(stops):
                script.append(v.poke_at(stop, 0o000240))
        log = v.run_emu(script + ['quit'], v.fresh_disk('hull-fetch'))
        cached = [int(n, 8) for n in v.PEEK.findall(log)]
        for i, (key, bank, record) in enumerate(subset):
            prefix = out / f'hull-fetch-{batch+i}'
            got = prefix.with_suffix('.bin').read_bytes()
            expected = record + b'\x5a\xa5' * ((512-len(record))//2)
            if got != expected or cached[i] != bank:
                errors.append(key)
            regs = struct.unpack('<8H', Path(str(prefix)+'-regs.bin').read_bytes())
            if regs[:6] != (a('HULL_BASE'), 1001, 1002, 1003, 1004, 1005) or regs[6] != regs[7]:
                register_errors.append((key, regs))
    v.check('all 55 hull fetches and cached repeats preserve exact bytes and unused tail',
            len(cases) == 55 and not errors, str(errors))
    v.check('all hull fetches preserve R1..R5 and stack balance',
            not register_errors, str(register_errors[:3]))


def check_face_visibility(v, t, out):
    """Check face-dot signs with signed products, zero normals and wrapping."""
    a = lambda key: int(t[key], 8)
    signed = lambda n: (n + 32768) % 65536 - 32768
    rng = random.Random(514)
    for batch in range(3):
        code, expected = [], []
        entry, dest = a('OVL_BASE'), a('OVL_BASE')+4096
        def mov(addr, value):
            code.extend([0o012737, value & 65535, addr])
        for case in range(8):
            matrix = [rng.randint(-16384, 16384) for _ in range(9)]
            pos = [rng.randint(-32768, 32767) for _ in range(3)]
            normals = [[rng.randint(-32768, 32767) for _ in range(3)] for _ in range(16)]
            normals[:3] = [[0, 0, 0], [0, 0, 160], [0, 0, -160]]
            if case == 0:
                matrix = [16384 if j in (0, 4, 8) else 0 for j in range(9)]
                pos = [(-32768, 0, 32767)[batch]] * 3
            if batch == case == 0:
                normals = []
            for j, value in enumerate(matrix):
                mov(a('PMAT')+2*j, value)
            for key, value in zip(('SD_X', 'SD_Y', 'SD_Z'), pos):
                mov(a(key), value)
            for j, value in enumerate(n for normal in normals for n in normal):
                mov(a('HULL_BASE')+2*j, value)
            mov(a('SD_MAT'), a('PMAT'))
            mov(a('SD_NP'), a('HULL_BASE'))
            mov(a('SD_NF'), len(normals))
            code += [0o004737, a('FACE_VIS'), 0o013737, a('SD_VIS'), dest+2*case]
            centre = [signed((sum(matrix[3*j+i]*pos[j] for j in range(3)) & 0xffffffff) >> 14)
                      for i in range(3)]
            mask = sum(1 << i for i, normal in enumerate(normals)
                       if (sum(x*y for x, y in zip(normal, centre)) & 0xffffffff) >= 0x80000000)
            expected.append(mask if normals else 65535)
        mov(a('BENCH_RAM'), 1)
        code.append(0o000777)
        assert len(code)*2 < 4096
        patch = [v.poke_at(entry+2*i, word) for i, word in enumerate(code)]
        patch += [v.poke_at(a('DRAW_HARNESS'), 0o000137),
                  v.poke_at(a('DRAW_HARNESS')+2, entry),
                  v.poke_at(a('BENCH_RAM'), 0), v.poke_at(a('HARN_GO'), 1)]
        dump = out / f'face-visibility-{batch}.bin'
        log = v.run_emu(list(v.BOOT) + ['run 20'] + patch + [
            'run 100', f"peekcpu {t['BENCH_RAM']}", f'dumpcpu {dest:o} 16 {dump}', 'quit'],
            v.fresh_disk('face-visibility'))
        got = list(struct.unpack('<8H', dump.read_bytes()))
        v.check(f'face visibility matches signed 32-bit model, batch {batch}',
                got == expected and [int(n, 8) for n in v.PEEK.findall(log)] == [1], str(got))


def check_walk_pixels(v, t, out):
    """Packed line decoding and XOR pixels for every octant and start bit."""
    lines = []
    for bit in range(8):
        for dx, dy in ((0, 0), (0, 63), (1, 0), (1, 1), (2, 1),
                       (7, 0), (8, 0), (127, 0), (63, 63), (63, 64),
                       (63, 31), (63, 32), (63, 15), (63, 16),
                       (63, 7), (63, 8), (7, 63), (8, 63)):
            for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
                lines.append(((320+bit, 100), (320+bit+sx*dx, 100+sy*dy)))
    lines += [((0, 0), (639, 0)), ((639, 199), (0, 199)),
              ((0, 0), (639, 199)), ((639, 199), (0, 0))]
    lines = list(dict.fromkeys(lines))  # duplicate XOR walks would hide errors
    check_walk_image(v, t, out, lines, 'walk-octants',
                     'packed walks match exact XOR pixels in all octants')


def check_span_pixels(v, t, out):
    """Each horizontal span gets its own row, so overlaps cannot hide errors."""
    lengths = (0, 1, 7, 8, 9, 15, 16, 17, 23, 24, 25, 31, 32, 33,
               63, 64, 65, 127, 128, 129, 255, 256, 257, 511, 512, 513)
    lines = []
    for bit in range(8):
        for direction in (1, -1):
            x = bit if direction > 0 else 632 + bit
            limit = 639 - x if direction > 0 else x
            for length in lengths + (limit,):
                y = len(lines) % 200
                lines.append(((x, y), (x + direction * length, y)))
    check_walk_image(v, t, out, lines, 'walk-spans',
                     'horizontal spans preserve every byte boundary and tail')


def check_walk_image(v, t, out, lines, name, description):
    """Compare queued records with an independent per-pixel Bresenham model."""
    a = lambda key: int(t[key], 8)
    for batch in range(0, len(lines), 200):
        subset = lines[batch:batch+200]
        entry, records = a('OVL_BASE'), a('OVL_BASE')+1024
        code = [0o004737, a('SEG_RESET'), 0o004737, a('CLS_SCREEN'),
                0o012704, records, 0o012705, len(subset),
                0o004737, a('RING_PUTR'), 0o077503,
                0o004737, a('RING_WAIT'), 0o012737, 1, a('BENCH_RAM'), 0o000777]
        patch = [v.poke_at(entry+2*i, word) for i, word in enumerate(code)]
        pixels = set()
        for i, ((x, y), (ex, ey)) in enumerate(subset):
            dx, dy = abs(ex-x), abs(ey-y)
            sx, sy = (1 if ex >= x else -1), (1 if ey >= y else -1)
            packed = (dx | ((x & 7) << 10) | (32768 if sx < 0 else 0),
                      dy | (32768 if sy < 0 else 0), a('VRAM')+80*y+x//8)
            patch += [v.poke_at(records+6*i+2*j, word) for j, word in enumerate(packed)]
            major, minor = max(dx, dy), min(dx, dy)
            error = major//2
            for step in range(major+1):
                pixels.symmetric_difference_update([(x, y)])
                if step == major:
                    break
                if dx >= dy:
                    x += sx
                else:
                    y += sy
                error -= minor
                if error < 0:
                    error += major
                    if dx >= dy:
                        y += sy
                    else:
                        x += sx
        patch += [v.poke_at(a('DRAW_HARNESS'), 0o000137),
                  v.poke_at(a('DRAW_HARNESS')+2, entry),
                  v.poke_at(a('BENCH_RAM'), 0), v.poke_at(a('HARN_GO'), 1)]
        bmp = out / f'{name}-{batch}.bmp'
        log = v.run_emu(list(v.BOOT) + ['run 20'] + patch + [
            'run 200', f"peekcpu {t['BENCH_RAM']}", f'screenshot {bmp}', 'quit'],
            v.fresh_disk(name))
        im = Image.open(bmp).convert('RGB')
        im.save(bmp.with_suffix('.png'))
        expected = Image.new('RGB', (640, 288))  # dashboard must remain clear
        for point in pixels:
            expected.putpixel(point, (255, 255, 255))
        v.check(f'{description}, batch {batch//200}',
                im.tobytes() == expected.tobytes() and
                [int(n, 8) for n in v.PEEK.findall(log)] == [1])


def geometry_frames(v, t, out, name, frames):
    """Run docked RAM probes in sequence, stopping after each queue drain."""
    a = lambda key: int(t[key], 8)
    entry = a('OVL_BASE')
    code, stops = [], []
    for setup in frames:
        # Use a known current buffer so each completed frame has one dump.
        code += [0o004737, a('SEG_RESET'), 0o004737, a('CLS_SCREEN')]
        for key, value in [('SEGNEW', a('SEGBUF')), ('SEGOLD', a('SEGBUFB')),
                           ('NOCLIP', 0), ('CLIPX1', 639)]:
            code += [0o012737, value, a(key)]
        code += [0o004737, a('SEG_RESET'), 0o004737, a('CLIP_VIEW')]
        code += setup
        code += [0o004737, a('SEG_FLUSH'), 0o004737, a('RING_WAIT')]
        stops.append(entry + 2*len(code))
        code.append(0o000777)  # BR .; patched to NOP after inspection
    assert len(code)*2 <= a('OVL_END') - entry
    patch = [v.poke_at(entry + 2*i, word) for i, word in enumerate(code)]
    patch += [v.poke_at(a('DRAW_HARNESS'), 0o000137),
              v.poke_at(a('DRAW_HARNESS')+2, entry), v.poke_at(a('HARN_GO'), 1)]
    script = list(v.BOOT) + ['run 20'] + patch
    for i, stop in enumerate(stops):
        script += [f'runpc {stop:o} 300', f"peekcpu {t['SEGPREV']}",
                   f"peekcpu {t['SD_VIS']}", f"peekcpu {t['HARN_TICKS']}",
                   f"dumpcpu {t['SEGBUF']} {a('MAXSEG')*6} {out / f'{name}-{i}.bin'}",
                   f"screenshot {out / f'{name}-{i}.bmp'}"]
        if i + 1 < len(stops):
            script += [v.poke_at(stop, 0o000240)]  # NOP
    log = v.run_emu(script + ['quit'], v.fresh_disk(name))
    values = [int(n, 8) for n in v.PEEK.findall(log)]
    results = []
    for i in range(len(frames)):
        count, visible, hull_count = values[3*i:3*i+3]
        raw = (out / f'{name}-{i}.bin').read_bytes()
        segments = []
        for j in range(count):
            dx, dy, addr = struct.unpack_from('<3H', raw, 6*j)
            y, byte = divmod(addr - a('VRAM'), 80)
            x = byte*8 + ((dx >> 10) & 7)
            segments.append(((x, y), (x + (dx & 1023)*(-1 if dx & 32768 else 1),
                                      y + (dy & 511)*(-1 if dy & 32768 else 1))))
        im = Image.open(out / f'{name}-{i}.bmp').convert('RGB').crop((0, 0, 640, 200))
        im.save(out / f'{name}-{i}.png')
        results.append((segments, visible, hull_count, im))
    return results


def check_docking_geometry(v, t, out):
    """Closed tunnel polygons and station slots hidden by their own hull."""
    a = lambda key: int(t[key], 8)
    def mov(key, value):
        return [0o012737, value & 65535, a(key)]
    def call(key):
        return [0o004737, a(key)]
    def quotient(n, d):
        return abs(n)//abs(d) * (-1 if (n < 0) != (d < 0) else 1)

    # Independent cyclic polygon: four distinct edges, including closure.
    trig = [(round(256*math.cos((i+1)*math.pi/8)),
             round(256*math.sin((i+1)*math.pi/8))) for i in range(16)]
    frames, expected = [], []
    for angle in range(16):
        radius = (22, 60, 96)[angle % 3]
        frames.append(mov('DT_RAD', radius) + mov('DT_ANG', angle) + call('DT_SQUARE'))
        corners = [(320 + quotient((trig[i % 16][0]*radius >> 8)*5, 3),
                    100 + (trig[i % 16][1]*radius >> 8))
                   for i in (angle, angle+12, angle+8, angle+4)]
        expected.append(list(zip(corners, corners[1:] + corners[:1])))
    for i, ((segments, _, _, im), edges) in enumerate(zip(
            geometry_frames(v, t, out, 'tunnel', frames), expected)):
        # Independent XOR Bresenham image, including shared endpoint parity.
        pixels = set()
        for (x, y), (ex, ey) in edges:
            dx, dy = abs(ex-x), abs(ey-y)
            sx, sy = (1 if ex >= x else -1), (1 if ey >= y else -1)
            major, minor = max(dx, dy), min(dx, dy)
            error = major//2
            for step in range(major+1):
                pixels.symmetric_difference_update([(x, y)])
                if step == major:
                    break
                if dx >= dy:
                    x += sx
                else:
                    y += sy
                error -= minor
                if error < 0:
                    error += major
                    if dx >= dy:
                        y += sy
                    else:
                        x += sx
        actual = {(x, y) for y in range(200) for x in range(640)
                  if im.getpixel((x, y)) != (0, 0, 0)}
        v.check(f'tunnel rotation {i}: four closed edges and exact pixels',
                segments == edges and actual == pixels, str(segments) if segments != edges else '')

    import shiplib
    from ships_gen import bank_layout
    ships = shiplib.read_dir(v.ROOT / 'src/res/legend/ships')
    _, offsets = bank_layout(ships)
    frames, wants = [], []
    # Each station is checked from both faces and at oblique/edge-on angles.
    for ship in ('SH_CORIOLIS', 'SH_DODOH'):
        for angle in (0, 45, 90, 135, 180):
            c, s = round(16384*math.cos(math.radians(angle))), round(16384*math.sin(math.radians(angle)))
            matrix = [c, 0, s, 0, 16384, 0, -s, 0, c]
            setup = mov('SD_MODEL', a('HBANK_ADDR') + offsets[a(ship)-1])
            setup += mov('SD_MAT', a('PMAT'))
            for j, value in enumerate(matrix):
                setup += [0o012737, value & 65535, a('PMAT')+2*j]
            for key, value in [('SD_X', 0), ('SD_Y', 0), ('SD_Z', 1600), ('SD_SH', 0)]:
                setup += mov(key, value)
            setup += call('SHIP_DRAW') + [0o013737, a('SEGCNT'), a('HARN_TICKS')]
            setup += call('STATION_SLOT')
            frames.append(setup)
            wants.append((ship, angle, 4 if angle < 90 else 0, angle > 90))
    for (segments, visible, hull_count, _), (ship, angle, extra, native) in zip(
            geometry_frames(v, t, out, 'station', frames), wants):
        v.check(f'{ship} at {angle} degrees: only the facing entrance is visible',
                len(segments)-hull_count == extra and bool(visible & 1) == native and
                not (native and len(segments) > hull_count),
                f'{hull_count} hull edges, {len(segments)-hull_count} added slot edges')

    # Compare clipped outlines with four separately submitted original edges.
    # This catches a clipped endpoint being reused as the next polygon corner.
    frames = []
    slot_setup = mov('SD_MAT', a('PMAT'))
    for j in range(9):
        slot_setup += [0o012737, 16384 if j in (0, 4, 8) else 0, a('PMAT')+2*j]
    for key, value in [('SD_X', 0), ('SD_Y', 40), ('SD_Z', 300), ('SD_SH', 0)]:
        slot_setup += mov(key, value)
    slot_corners = [(320 + quotient(x*640, 140), 100 - quotient((40+y)*384, 140))
                    for x, y in [(-60, -18), (60, -18), (60, 18), (-60, 18)]]
    tunnel_corners = [(320 + quotient((trig[i][0]*96 >> 8)*5, 3),
                       100 + (trig[i][1]*96 >> 8)) for i in (0, 12, 8, 4)]
    for setup, corners in [(slot_setup + call('STATION_SLOT'), slot_corners),
                           (mov('DT_RAD', 96) + mov('DT_ANG', 0) + call('DT_SQUARE'),
                            tunnel_corners)]:
        clip = mov('CLIPY1', 120) + mov('CLIPYD', 120)
        frames.append(clip + setup)
        reference = list(clip)
        for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
            for key, value in [('LX0', x0), ('LY0', y0), ('LX1', x1), ('LY1', y1)]:
                reference += mov(key, value)
            reference += call('SEG_LINE')
        frames.append(reference)
    results = geometry_frames(v, t, out, 'clipped-outline', frames)
    for i, name in enumerate(('station slot', 'tunnel square')):
        actual, reference = results[2*i:2*i+2]
        v.check(f'clipped {name} preserves each original polygon edge',
                actual[0] == reference[0] and actual[3].tobytes() == reference[3].tobytes())


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
    im = Image.open(bmp).convert('RGB')
    im.save(out / 'paired-wrap.png')
    expected = Image.new('RGB', (640, 288))
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
