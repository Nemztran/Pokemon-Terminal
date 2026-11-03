#!/usr/bin/env python3
"""Shared rendering helpers for the Pokémon terminal greeting.
Uses Pillow or Chafa to render sprites. A fallback pixel font is built in.
"""
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata

BASE = Path(__file__).resolve().parent / 'assets'
ESC = '\033['
RST = ESC + '0m'
PURPLE = ESC + '38;2;203;166;247m'
PINK = ESC + '38;2;245;194;231m'
CYAN = ESC + '38;2;148;226;213m'
GREEN = ESC + '38;2;166;227;161m'
DIM = ESC + '38;2;166;173;200m'
WHITE = ESC + '38;2;205;214;244m'
YELLOW = ESC + '38;2;249;226;175m'
BG = '#1e1e2e'  # Matches the screenshot's Catppuccin Mocha-style backdrop.
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

# True 5x7 pixel glyphs. No outline-style FIGlet font.
FONT = {
    'N': ('10001','11001','10101','10011','10001','10001','10001'),
    'E': ('11111','10000','10000','11110','10000','10000','11111'),
    'M': ('10001','11011','10101','10101','10001','10001','10001'),
    'Z': ('11111','00001','00010','00100','01000','10000','11111'),
    'C': ('01111','10000','10000','10000','10000','10000','01111'),
    'H': ('10001','10001','10001','11111','10001','10001','10001'),
    'A': ('01110','10001','10001','11111','10001','10001','10001'),
}
NAME = 'NEMZCHAN'
GRADIENT = ['#f5c2e7','#e5b5f0','#cba6f7','#b4befe',
            '#89b4fa','#89dceb','#94e2d5','#a6e3a1']


def rgb(hexcolor):
    c = hexcolor.lstrip('#')
    return f'\033[38;2;{int(c[0:2],16)};{int(c[2:4],16)};{int(c[4:6],16)}m'


def cells(text):
    s = ANSI.sub('', text)
    return sum(0 if unicodedata.combining(c) else
               2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in s)


def clip(s, limit):
    if limit < 1:
        return ''
    if cells(s) <= limit:
        return s
    r = ''
    for c in s:
        if cells(r) + cells(c) + 1 > limit:
            break
        r += c
    return r + '…'


def run(*cmd, timeout=2):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           check=False, timeout=timeout)
        return p.stdout.rstrip('\n') if p.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def read_file(path, fallback=''):
    try:
        return Path(path).read_text().strip() or fallback
    except OSError:
        return fallback


def read_pretty_os():
    for ln in read_file('/etc/os-release').splitlines():
        if ln.startswith('PRETTY_NAME='):
            return ln.partition('=')[2].strip('"\'')
    return 'Ubuntu Linux'


def cpu_name():
    for ln in read_file('/proc/cpuinfo').splitlines():
        if ln.startswith('model name'):
            return ln.partition(':')[2].strip()
    return 'CPU unknown'


def gpu_name():
    rows = run('lspci', '-nn', timeout=0.9).splitlines()
    for ln in rows:
        if 'VGA compatible controller' in ln or '3D controller' in ln:
            return ln.split(': ', 1)[-1]
    return ''


def mem():
    data = {}
    for ln in read_file('/proc/meminfo').splitlines():
        if ':' not in ln:
            continue
        key, val = ln.split(':',1)
        try:
            data[key] = int(val.strip().split()[0])
        except (ValueError, IndexError):
            continue
    if data.get('MemTotal') and data.get('MemAvailable') is not None:
        total = data['MemTotal'] / 1048576
        used = (data['MemTotal'] - data['MemAvailable']) / 1048576
        return f'{used:.1f} / {total:.1f} GiB', used / total
    return 'Unknown', 0


def uptime():
    try:
        sec = int(float(read_file('/proc/uptime').split()[0]))
        d, sec = divmod(sec, 86400)
        h, sec = divmod(sec, 3600)
        m = sec // 60
        return f'{d}d {h}h {m}m' if d else f'{h}h {m}m'
    except (ValueError, IndexError):
        return 'Unknown'


def pixel_name(max_width):
    # Render pixel glyphs in mono-width columns; 47 columns for NEMZCHAN.
    # Wide terminal can optionally show double-width square pixels.
    px = 2 if max_width >= 96 else 1
    required = len(NAME) * (5 * px + 1) - 1
    if required > max_width:
        return [f'{PURPLE}N E M Z C H A N{RST}']
    lines = []
    for y in range(7):
        parts = []
        for i, letter in enumerate(NAME):
            chars = ''.join(('█' * px) if bit == '1' else ' ' * px
                            for bit in FONT[letter][y])
            parts.append(rgb(GRADIENT[i]) + chars + RST)
        lines.append(' '.join(parts))
    return lines


def sprite_lines(max_width, max_height):
    image = BASE / 'pokemon.png'
    if not image.is_file():
        return []
    # Pixel-perfect sprite: NEAREST resize + upper/lower half-block per cell.
    # A font cell is roughly twice as tall as it is wide, hence 2*height.
    try:
        from PIL import Image
        im = Image.open(image).convert('RGBA')
        bbox = im.getchannel('A').getbbox()
        if not bbox:
            return []
        im = im.crop(bbox)
        scale = min(max_width / im.width, (2 * max_height) / im.height)
        w = min(max_width, max(1, round(im.width * scale)))
        h = min(2 * max_height, max(2, round(im.height * scale)))
        if h % 2:
            h = max(2, h - 1)
        im = im.resize((w, h), Image.Resampling.NEAREST)
        bg = Image.new('RGBA', (w, h), (30, 30, 46, 255))
        bg.alpha_composite(im)
        pix = bg.convert('RGB').load()
        lines = []
        for y in range(0, h, 2):
            parts = []
            for x in range(w):
                a, b = pix[x, y], pix[x, y + 1]
                parts.append(f'\033[38;2;{a[0]};{a[1]};{a[2]};'
                             f'48;2;{b[0]};{b[1]};{b[2]}m▀')
            lines.append(''.join(parts) + RST)
        return lines
    except (ImportError, OSError, ValueError):
        pass
    # Fallback to Chafa if Pillow is missing for any reason.
    if shutil.which('chafa'):
        out = run('chafa', '-f', 'symbols', '-c', 'full',
                  '--symbols', 'block', '-s', f'{max_width}x{max_height}',
                  '--scale', 'max', '--bg', BG, str(image), timeout=5)
        return out.splitlines() if out else []
    return []


def value_row(label, value, right_width):
    label_w = 8
    available = max(4, right_width - label_w - 3)
    return f'{PINK}{label:<{label_w}}{RST} {WHITE}{clip(value,available)}{RST}'


def memory_meter(fraction, right_width):
    n = max(7, min(22, right_width - 20))
    on = max(0, min(n, round(fraction * n)))
    return (f'{DIM}RAM {RST}{CYAN}' + '█' * on +
            f'{DIM}' + '░' * (n - on) + RST +
            f'  {YELLOW}{fraction*100:.0f}%{RST}')

