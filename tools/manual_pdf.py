#!/usr/bin/env python3
"""Build the Russian UKNC manual from editable sources and current screenshots.

python3 tools/manual_pdf.py --capture --out manual.pdf
python3 tools/manual_pdf.py --out manual.pdf
"""
import argparse
import base64
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / 'docs/manual'
WORK = ROOT / 'tmp/pdfs/manual'

CSS = '''
@page { size: A4; margin: 16mm 16mm 17mm;
 @bottom-left { content: "ELITE LEGEND / УКНЦ / v0.8.0"; font: 8pt "DejaVu Sans"; color: #68717a; }
 @bottom-right { content: counter(page); font: 9pt "DejaVu Sans"; color: #68717a; }
}
* { box-sizing: border-box; }
body { font: 10.3pt/1.43 "DejaVu Sans", sans-serif; color: #18232d; margin: 0; }
h1 { font-size: 29pt; line-height: 1.15; margin: 0 0 8mm; color: #17384d; }
h2 { font-size: 20pt; line-height: 1.2; margin: 0 0 6mm; color: #17384d; }
h3 { font-size: 12pt; line-height: 1.3; margin: 5mm 0 2mm; color: #17384d; break-after: avoid; }
p { margin: 0 0 3mm; } ul,ol { padding-left: 6mm; margin: 2mm 0 4mm; }
li { margin-bottom: 1.5mm; }
a { color: #245a76; text-decoration: none; }
.chapter { break-before: page; }
.cover { padding-top: 13mm; }
.kicker { color: #65717b; letter-spacing: 1.4pt; font-size: 9pt; margin-bottom: 6mm; }
.subtitle { font-size: 16pt; margin: 0 0 8mm; }
.meta { color: #5e6972; font-size: 9pt; }
.note { background: #edf3f6; border-left: 3pt solid #39718c; padding: 3mm 4mm; margin: 4mm 0; break-inside: avoid; }
figure { margin: 4mm 0 5mm; break-inside: avoid; }
figure img { width: 100%; display: block; image-rendering: pixelated; border: .5pt solid #7e8e98; }
figcaption { font-size: 8.5pt; line-height: 1.35; color: #586873; margin-top: 2mm; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; line-height: 1.3; margin: 3mm 0 5mm; }
th { text-align: left; background: #e5eef3; color: #17384d; }
th, td { padding: 2mm 2.5mm; border-bottom: .5pt solid #c9d3d9; vertical-align: top; }
tr { break-inside: avoid; } thead { display: table-header-group; }
.key { font-weight: bold; white-space: nowrap; }
.item { break-inside: avoid; margin: 0 0 5mm; }
.item h3 { margin-top: 0; }
.item p { break-inside: avoid; }
.en { font-size: 9pt; color: #65717b; margin-bottom: 2mm; }
.toc li { margin-bottom: 3mm; }
.small { font-size: 9pt; }
#pause th, #pause td { padding-top: 1.4mm; padding-bottom: 1.4mm; }
#start table { font-size: 8.5pt; margin-bottom: 2mm; }
#start th, #start td { padding: 1.5mm 2mm; }
'''


def data_uri(path):
    return 'data:image/png;base64,' + base64.b64encode(Path(path).read_bytes()).decode('ascii')


def figure(name, caption):
    path = DOC / 'img' / f'{name}.png'
    if not path.exists():
        raise FileNotFoundError(f'{path}: capture current screens with --capture')
    return f'<figure><img src="{data_uri(path)}"><figcaption>{html.escape(caption)}</figcaption></figure>'


def controls():
    return json.loads((DOC / 'controls.json').read_text())


def control_table(group, board=None):
    rows = controls()[group]
    headings = ['Клавиша УКНЦ', 'На ПК', 'Действие'] if board is None else ['Клавиша', 'Действие']
    result = '<table><thead><tr>' + ''.join(f'<th>{x}</th>' for x in headings) + '</tr></thead><tbody>'
    for uk, pc, action in rows:
        keys = [uk, pc] if board is None else [uk if board == 'uknc' else pc]
        result += '<tr>' + ''.join(f'<td class="key">{html.escape(k)}</td>' for k in keys)
        result += f'<td>{html.escape(action)}</td></tr>'
    return result + '</tbody></table>'


def print_pdf(document, output, stem):
    chrome = next((shutil.which(x) for x in ('google-chrome', 'chromium', 'chromium-browser') if shutil.which(x)), None)
    if not chrome:
        raise SystemExit('Chrome/Chromium is needed to print the PDF')
    WORK.mkdir(parents=True, exist_ok=True)
    src = WORK / f'{stem}.html'
    src.write_text(document, encoding='utf-8')
    output = Path(output).resolve()
    pending = WORK / f'{stem}.pdf'
    pending.unlink(missing_ok=True)
    subprocess.run([chrome, '--headless', '--disable-gpu', '--no-sandbox', '--no-pdf-header-footer',
                    '--allow-file-access-from-files', '--disable-dev-shm-usage',
                    f'--user-data-dir={WORK / (stem + "-chrome")}',
                    f'--print-to-pdf={pending}', src.as_uri()],
                   check=True, capture_output=True, text=True, timeout=180)
    if not pending.exists() or pending.stat().st_size < 1000:
        raise RuntimeError('PDF output is missing or empty')
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pending, output)
    print(f'Wrote {output} ({output.stat().st_size:,} bytes)')


def capture():
    import verify_build as v
    from PIL import Image
    v.syms.check_fresh()
    v.keep_pristine()
    (DOC / 'img').mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    names = []
    def shot(name):
        names.append(name)
        return [f'screenshot {WORK / (name + ".bmp")}']
    t = v.syms.table()
    script = list(v.POWER_ON) + shot('welcome') + ['press 153', 'run 150'] + shot('controls')
    script += ['press 153', 'run 300'] + shot('title') + v.CHOOSE_KEYS + v.COMMANDER_KEYS + shot('docked')
    for name in ('chart', 'local', 'system', 'market', 'equipment', 'yard', 'pilot', 'save', 'carrier'):
        script += ['press 004', v.ui_ready(t)] + shot(name)
    script += ['press 107', 'run 160'] + shot('contract')
    # Return to the cockpit through the same nonmodal screen cycle.
    script += ['press 004', v.ui_ready(t), 'press 107', 'run 160'] + shot('flight')
    script += ['press 006', 'run 100'] + shot('pause') + ['quit']
    log = v.run_emu(script, v.fresh_disk('manual'))
    (WORK / 'capture.log').write_text(log)
    for name in names:
        with Image.open(WORK / f'{name}.bmp') as im:
            im.save(DOC / 'img' / f'{name}.png')
    print(f'Captured {len(names)} current screens on a disposable disk')


def build_html():
    body = (DOC / 'guide.html').read_text()
    body = re.sub(r'\{\{image:([a-z]+)\|([^}]+)\}\}', lambda m: figure(m[1], m[2]), body)
    body = re.sub(r'\{\{controls:([a-z]+)\}\}', lambda m: control_table(m[1]), body)
    content = json.loads((DOC / 'reference.json').read_text())
    for section in ('equipment', 'stations', 'missions', 'legends'):
        parts = []
        for item in content[section]:
            parts.append('<div class="item"><h3>' + html.escape(item['title']) + '</h3>')
            if item.get('english'):
                parts.append('<div class="en">' + html.escape(item['english']) + '</div>')
            for p in item['paragraphs']:
                parts.append('<p>' + html.escape(p) + '</p>')
            parts.append('</div>')
        body = body.replace('{{reference:' + section + '}}', '\n'.join(parts))
    if '{{' in body:
        raise ValueError('Unexpanded manual placeholder')
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Elite Legend - руководство УКНЦ v0.8.0</title><style>' + CSS + '</style><body>' + body + '</body></html>'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture', action='store_true', help='recapture screens from the current built disk')
    ap.add_argument('--out', type=Path, default=ROOT / 'manual.pdf')
    args = ap.parse_args()
    if args.capture:
        capture()
    print_pdf(build_html(), args.out, 'manual')


if __name__ == '__main__':
    main()
