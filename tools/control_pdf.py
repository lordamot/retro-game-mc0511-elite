#!/usr/bin/env python3
"""Build current two-page keyboard references for UKNC and the PC player.

python3 tools/control_pdf.py --board uknc --out control.pdf
python3 tools/control_pdf.py --board pc --out controls-pc.pdf

Offline keyboard images, original attribution and physical key rectangles
are retained. Searchable text and shared control data replace tiny raster
callouts. Sources: docs/manual/controls.json, KEYBOARD.md, src/res/setup.txt.
"""
import argparse
import html
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from manual_pdf import CSS, WORK, controls, data_uri, print_pdf

ROOT = Path(__file__).resolve().parent.parent
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# the УКНЦ letter rows, by physical position under QWERTY
ROWS_RU = ["ЙЦУКЕНГШЩЗХЪ", "ФЫВАПРОЛДЖЭ", "ЯЧСМИТЬБЮ"]

BOARDS = {
    "uknc": dict(
        url="https://nzeemin.github.io/ukncbtl-wasm/keyboard.png",
        cache=ROOT / "docs/manual/keyboard-uknc.png",
        crop=None,
        out=ROOT / "control.pdf",
        title="Elite — УКНЦ (Электроника МС-0511): управление / controls",
        subtitle=("Клавиатура УКНЦ; на ПК под make run: ФИКС = левый Ctrl, ВВОД (цифровой) = "
                  "правый Ctrl или Enter на цифровом блоке, СТОП = Esc, забой = Backspace, буквы — по "
                  "положению клавиш QWERTY.  UKNC keyboard; on a PC under make run: ФИКС = Left Ctrl, "
                  "numpad ВВОД = Right Ctrl or keypad Enter, СТОП = Esc, забой = Backspace, letters by "
                  "QWERTY position."),
        credit="Рисунок клавиатуры / keyboard picture: UKNCBTL (nzeemin), nzeemin.github.io/ukncbtl-wasm.",
        # key rectangles in the picture's own pixels (the page's image map)
        keys={
            "STOP": [(551, 15, 593, 42)],
            "1": [(77, 56, 104, 83)], "2": [(106, 56, 134, 83)],
            "3": [(136, 56, 163, 83)], "6": [(224, 56, 252, 83)],
            "BS": [(431, 56, 473, 83)],
            "ENTER": [(446, 86, 473, 142)],
            "FIX": [(77, 174, 111, 201)],
            "SPACE": [(114, 174, 325, 201)],
            "LEFTRIGHT": [(387, 145, 414, 201), (446, 145, 473, 201)],
            "UPDOWN": [(416, 145, 444, 201)],
            "NENTER": [(565, 174, 593, 201)],
            "LETTERS": [(62, 86, 414, 172)],
            "89": [(283, 56, 310, 83), (312, 56, 340, 83)],
            "AR2": [(19, 56, 46, 83)],
            "FLY": [(247, 116, 275, 143), (175, 145, 202, 172),
                    (100, 116, 127, 143), (160, 116, 187, 143)],
        },
        heads={"1": "1", "2": "2", "3": "3", "6": "6", "BS": "забой",
               "89": "8, 9", "AR2": "АР2", "FLY": "О М Ы А",
               "ENTER": "ВВОД", "STOP": "СТОП", "FIX": "ФИКС",
               "SPACE": "пробел / space", "LETTERS": "буквы, цифры / letters, digits",
               "LEFTRIGHT": "← →", "UPDOWN": "↑ ↓", "NENTER": "ВВОД (цифровой)"},
        overlays=[],
    ),
    "pc": dict(
        url=("https://commons.wikimedia.org/wiki/Special:FilePath/"
             "ANSI_Keyboard_Layout_Diagram_with_Form_Factor.svg?width=1920"),
        cache=ROOT / "docs/manual/keyboard-pc.png",
        crop=(0, 0, 1920, 585),          # the form-factor legend under it goes
        out=ROOT / "controls-pc.pdf",
        title="Elite — УКНЦ: управление на клавиатуре ПК (make run) / controls on a PC keyboard",
        subtitle=("Так bin/ukncbtl/uknc-play отображает клавиши ПК на клавиатуру УКНЦ (MapKey в "
                  "tools/uknc-headless/uknc-play.cpp); красным — что клавиша даёт на УКНЦ.  Буквы — по "
                  "положению: где у QWERTY Q, там Й.  How the player maps PC keys onto the УКНЦ "
                  "keyboard; in red, what each key is there.  Letters by position: the key where "
                  "QWERTY has Q types Й."),
        credit=("Рисунок клавиатуры / keyboard picture: \"ANSI Keyboard Layout Diagram with Form "
                "Factor\", Rumudiez, Wikimedia Commons, CC BY-SA 3.0."),
        # key rectangles in the picture's pixels, found by flood-filling
        # the keys off the grey plate (scratch script, not kept)
        keys={
            "STOP": [(35, 37, 106, 108)],
            "1": [(116, 144, 187, 214)], "2": [(197, 144, 268, 214)],
            "3": [(278, 144, 349, 214)], "6": [(521, 144, 592, 214)],
            "BS": [(1089, 144, 1231, 214)],
            "ENTER": [(1089, 307, 1231, 378)],
            "FIX": [(35, 471, 124, 542)],
            "SPACE": [(334, 471, 830, 542)],
            "LEFTRIGHT": [(1283, 471, 1353, 542), (1445, 471, 1515, 542)],
            "UPDOWN": [(1364, 389, 1434, 542)],
            "NENTER": [(1140, 471, 1229, 542), (1813, 389, 1884, 542)],
            "LETTERS": [(152, 225, 1113, 460)],
            "89": [(683, 144, 754, 214), (764, 144, 835, 214)],
            "AR2": [(35, 225, 141, 296)],
            "FLY": [(679, 307, 750, 378), (461, 389, 532, 460),
                    (270, 307, 341, 378), (434, 307, 505, 378)],
        },
        heads={"1": "1", "2": "2", "3": "3", "6": "6", "BS": "Backspace = забой",
               "89": "8, 9", "AR2": "Tab = АР2", "FLY": "J V S F = О М Ы А",
               "ENTER": "Enter = ВВОД", "STOP": "Esc = СТОП", "FIX": "Left Ctrl = ФИКС",
               "SPACE": "Space = пробел", "LETTERS": "Q..] A..' Z.. = ЙЦУКЕН, цифры / digits",
               "LEFTRIGHT": "← →", "UPDOWN": "↑ ↓",
               "NENTER": "Right Ctrl, keypad Enter = ВВОД (цифровой)"},
        # red text written on a key: (x0, y0, x1, y1, text) - what the
        # key IS on the УКНЦ
        overlays=(
            [(35, 37, 106, 108, "СТОП"), (1089, 144, 1231, 214, "забой"),
             (35, 225, 141, 296, "АР2"), (1089, 307, 1231, 378, "ВВОД"),
             (35, 471, 124, 542, "ФИКС"), (1140, 471, 1229, 542, "ВВОД#"),
             (1813, 389, 1884, 542, "ВВОД#")]
            + [(x, 225, x + 71, 296, ch) for x, ch in
               zip([152, 233, 314, 395, 476, 557, 638, 719, 800, 881, 962, 1043], ROWS_RU[0])]
            + [(x, 307, x + 71, 378, ch) for x, ch in
               zip([188, 270, 352, 434, 516, 598, 679, 761, 843, 925, 1007], ROWS_RU[1])]
            + [(x, 389, x + 71, 460, ch) for x, ch in
               zip([223, 303, 382, 461, 540, 619, 699, 778, 857], ROWS_RU[2])]
        ),
    ),
}


def keyboard(board, name):
    with Image.open(board['cache']) as source:
        rgba = source.convert('RGBA')
        im = Image.alpha_composite(Image.new('RGBA', rgba.size, 'white'), rgba).convert('RGB')
    if board['crop']:
        im = im.crop(board['crop'])
    draw = ImageDraw.Draw(im)
    width = max(1, round(im.width / 610))
    for group, rects in board['keys'].items():
        if group == 'LETTERS':
            continue
        for rect in rects:
            draw.rectangle(rect, outline='#b72531', width=width)
    font = ImageFont.truetype(FONT_B, round(im.width / 90))
    for x0, y0, x1, y1, text in board['overlays']:
        box = draw.textbbox((0, 0), text, font=font)
        w, h = box[2]-box[0], box[3]-box[1]
        x, y = x1-w-3, y1-h-3
        draw.rectangle((x-2,y-2,x+w+2,y+h+2), fill='white')
        draw.text((x,y-box[1]),text,font=font,fill='#b72531')
    WORK.mkdir(parents=True,exist_ok=True)
    path = WORK / f'keyboard-{name}.png'
    im.save(path)
    return path


def table(group, board, indices=None):
    data = controls()
    indices = range(len(data[group])) if indices is None else indices
    out = '<table><thead><tr><th>Клавиша</th><th>Действие</th></tr></thead><tbody>'
    for i in indices:
        uk,pc,_ = data[group][i]
        key = uk if board=='uknc' else pc
        action = data['quick'][group][i]
        if board == 'pc':
            action = action.replace('ФИКС', 'Left Ctrl').replace('ВВОД', 'Enter')
        out += '<tr><td class="key">'+html.escape(key)+'</td><td>'+html.escape(action)+'</td></tr>'
    return out+'</tbody></table>'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--board', choices=['uknc','pc'], default='uknc')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--png', type=Path, help='render the first PDF page as a PNG preview')
    args=ap.parse_args(); board=BOARDS[args.board]
    output=args.out or board['out']
    image=keyboard(board,args.board)
    title='Клавиатура УКНЦ' if args.board=='uknc' else 'Клавиатура ПК в эмуляторе УКНЦ'
    mapping=('ФИКС - огонь и выбор. Обычный ВВОД - меню; ВВОД цифрового блока - газ.' if args.board=='uknc' else
             'Left Ctrl = ФИКС · Enter = ВВОД · Right Ctrl / Num Enter = ВВОД цифрового блока · Esc = СТОП · Tab = АР2.')
    css=CSS+'''
@page { size: A4 landscape; margin: 10mm 12mm 12mm; }
body { font-size: 9pt; line-height: 1.25; }
h1 { font-size: 19pt; margin: 0 0 2mm; } h2 {font-size: 17pt; margin:0 0 3mm;}
h3 {font-size:11pt; margin:0 0 2mm;}
p {margin:0 0 2mm;} .board { width:78%; max-height:76mm; object-fit:contain; display:block; margin:2mm auto 3mm; }
.columns {display:flex; gap:5mm; align-items:flex-start;} .columns > div {flex:1; min-width:0;}
table {font-size:8.7pt; line-height:1.2; margin:0 0 2mm;}
th,td {padding:1.3mm 1.5mm;} td.key {white-space:normal; width:28%;}
.notes {font-size:8pt; color:#4c5b64; margin-top:2mm;}
.reference table {font-size:8.4pt;} .reference td {padding:1.45mm 1.5mm;}
'''
    body=f'<h1>Elite Legend v0.8.0 / {title}</h1><p>{mapping}</p>'
    body+=f'<img class="board" src="{data_uri(image)}">'
    body+='<div class="columns"><div>'+table('flight',args.board,range(9))+'</div><div>'+table('flight',args.board,range(9,17))
    start_keys = 'обычный ВВОД; затем ФИКС' if args.board == 'uknc' else 'Enter; затем Left Ctrl'
    body+='<p class="notes"><b>Старт:</b> '+start_keys+'. Два отдельных нажатия ВВОД / Enter проходят заставки, ФИКС / Left Ctrl открывает выбор командира. Слот: 1...4; имя: ВВОД / Enter.</p></div></div>'
    body+='<p class="notes"><b>Без отдельной клавиши:</b> стыковочный компьютер включается при нулевом газе у станции. Сохранение - при стыковке, спасении или через меню доступа. Клавиши по умолчанию, 9 ноября 2026.</p>'
    body+='<p class="notes">'+html.escape(board['credit'])+'</p>'
    body+='<section class="chapter reference"><h2>Меню, карты и пауза</h2><div class="columns">'
    for group,section_title in [('menus','На станции и в меню'),('charts','На картах'),('pause','В меню паузы')]:
        body+='<div><h3>'+section_title+'</h3>'+table(group,args.board)
        if group=='charts':
            body+='<p class="notes">Для гиперпрыжка сначала выйдите со станции. Галактический переход требует исправного привода. Перелет в другую галактику расторгает контракты.</p>'
        if group=='pause':
            exitkeys='АР2, затем Ч' if args.board=='uknc' else 'Tab, затем X'
            body+='<p class="notes"><b>Выход: '+exitkeys+'.</b> Перед выходом сохранитесь. Игра не сохраняется автоматически при возвращении в RT-11.</p>'
        body+='</div>'
    body+='</div><p class="notes">Имя: до 10 символов; поиск: до 8, по началу имени. На ПК буквы вводятся по физическим позициям ЙЦУКЕН: Q → Й, A → Ф, Z → Я. Подробности и описание оборудования - в manual.pdf.</p></section>'
    document='<!doctype html><html lang="ru"><meta charset="utf-8"><title>'+html.escape(title)+' - Elite Legend v0.8.0</title><style>'+css+'</style><body>'+body+'</body></html>'
    print_pdf(document,output,'control-'+args.board)
    if args.png:
        import subprocess
        prefix=args.png.with_suffix('')
        args.png.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['pdftoppm','-f','1','-l','1','-singlefile','-scale-to','1800','-png',str(output),str(prefix)],check=True)

if __name__=='__main__':main()
