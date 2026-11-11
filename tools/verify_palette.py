"""Physical RGB/GRB output, title controls and session palette lifetime."""
import struct

from PIL import Image

from font_gen import read_font
from text_gen import to_koi7
from verify_rt11 import command


def check_palette(v):
    t = v.syms.table()
    canonical = [int(t[n], 8) for n in
                 ('PAL_VIEW1', 'PAL_VIEW2', 'PAL_DASH1', 'PAL_DASH2')]
    font = read_font(v.ROOT / 'src/res/font/uknc11.txt')
    latin = read_font(v.ROOT / 'src/res/font/latin11.txt')
    work = v.ROOT / 'tmp/palette'
    work.mkdir(exist_ok=True)
    dash = 0o2410 + 200 * 4
    mode = f'peekcpu {t["PALETTE_MODE"]}'

    for layout in (None, 'grb', 'rgb'):
        folder = work / (layout or 'default')
        folder.mkdir(exist_ok=True)
        shots = []

        def capture(name, selected, title=False):
            shots.append((name, selected, title))
            return [mode, f'dump 0 2400 4 {folder/name}.view',
                    f'dump 0 {dash:o} 4 {folder/name}.dash',
                    f'screenshot {folder/name}.bmp'] + [
                        f'dump {p} 100000 23040 {folder/name}.p{p}' for p in range(3)]

        script = list(v.TITLE_BOOT) + capture('title-default', 0, True)
        script += ['keydown 031', 'run 60'] + capture('title-rgb', 1, True)
        script += ['run 60', mode, 'keyup 031', 'run 10', 'press 030', 'run 60']
        script += capture('title-grb', 0, True)
        script += ['press 031', 'run 60'] + v.CHOOSE_KEYS + v.COMMANDER_KEYS
        script += capture('docked-rgb', 1)
        script += ['press 004', v.ui_ready(t)] + capture('chart-rgb', 1)
        script += ['press 006', 'run 100', 'press 027', 'run 200']
        script += capture('restart-rgb', 1, True)
        script += v.CHOOSE_KEYS + v.COMMANDER_KEYS
        script += ['press 006', 'run 160', 'press 110', 'run 400',
                   f'peekcpu {t["PP_ACTIVE"]}']
        script += command('R ELITE', 1600) + [mode, 'quit']
        out = v.run_emu(script, v.fresh_disk('palette'), palette=layout)
        (folder / 'emulator.log').write_text(out)
        values = [int(x, 8) for x in v.PEEK.findall(out)]
        v.check(f'{layout or "default GRB"}: selection, held key, screens, restart and fresh launch',
                values == [0, 1, 1, 0, 1, 1, 1, 0, 0], str(values))

        for name, selected, title in shots:
            words = struct.unpack('<4H', (folder / f'{name}.view').read_bytes() +
                                  (folder / f'{name}.dash').read_bytes())
            # Decode each component independently, not with the game's bit trick.
            expected_words = []
            for word in canonical:
                result = 0
                for i in range(4):
                    nibble = (word >> (4*i)) & 15
                    if selected == 0:
                        nibble = ((nibble & 9) | ((nibble & 2) << 1) |
                                  ((nibble & 4) >> 1))
                    result |= nibble << (4*i)
                expected_words.append(result)
            v.check(f'{name}/{layout}: both hardware palettes', list(words) == expected_words)

            im = Image.open(folder / f'{name}.bmp').convert('RGB')
            im.save(folder / f'{name}.png')
            planes = [(folder / f'{name}.p{p}').read_bytes() for p in range(3)]
            palettes = []
            for band in range(2):
                colors = []
                for index in range(8):
                    nibble = (canonical[2*band + index//4] >> (4*(index % 4))) & 15
                    intensity = 255 if nibble & 8 else 128
                    rgb = tuple(intensity if nibble & bit else 0 for bit in (4, 2, 1))
                    if (selected == 0) != (layout != 'rgb'):
                        rgb = rgb[1], rgb[0], rgb[2]
                    colors.append(rgb)
                palettes.append(colors)
            wrong = 0
            for y in range(288):
                colors = palettes[y >= 200]
                for x in range(640):
                    offset, bit = y*80 + x//8, 1 << (x % 8)
                    index = sum((1 << p) for p in range(3) if planes[p][offset] & bit)
                    wrong += im.getpixel((x, y)) != colors[index]
            v.check(f'{name}/{layout}: all screenshot pixels match physical wiring', wrong == 0,
                    f'{wrong} mismatched pixels')
            if not title:
                continue
            start = (37 + 9*selected)*8
            mark = [x for x in range(37*8, 52*8) if im.getpixel((x, 249)) == (255,)*3]
            v.check(f'{name}/{layout}: selected choice is underlined',
                    mark == list(range(start, start + 48)))
            for text, col, row, glyphs in (('0.8.2', 74, 272, font),
                                          ('GRB', 40, 236, latin),
                                          ('RGB', 49, 236, latin)):
                codes = list(text.encode('ascii')) if glyphs is latin else to_koi7(text, name)
                wrong = sum((im.getpixel((8*(col+i)+x, row+y)) == (255,)*3) != (pixel == '#')
                            for i, code in enumerate(codes)
                            for y, glyphrow in enumerate(glyphs[code])
                            for x, pixel in enumerate(glyphrow))
                v.check(f'{name}/{layout}: exact {text} glyphs', wrong == 0)
