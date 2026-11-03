#!/usr/bin/env python3
"""Offline Pokémon greeting with a responsive two-column layout."""
from datetime import datetime
from pathlib import Path
import fcntl
import os
import secrets
import shutil
import sys

from . import engine

BASE = Path(__file__).resolve().parent / 'assets'
STATE = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state') / 'pokemon-welcome'
TRAINER = os.environ.get('POKEMON_TRAINER', os.environ.get('USER', 'Trainer'))
TRAINER = ''.join(c for c in TRAINER if c.isprintable())[:40] or 'Trainer'

RST = engine.RST
WHITE = '\033[1;38;2;230;231;241m'
DIM = engine.DIM
CYAN = engine.CYAN
YELLOW = engine.YELLOW
SHADES = ' ░▒▓█'
DENSITY = {c: i for i, c in enumerate(SHADES)}

# Built-in pool: id -> name, types (all available in generation-v sprites).
POKEMON = {
    1: ('BULBASAUR', 'GRASS / POISON'),
    4: ('CHARMANDER', 'FIRE'),
    6: ('CHARIZARD', 'FIRE / FLYING'),
    7: ('SQUIRTLE', 'WATER'),
    25: ('PIKACHU', 'ELECTRIC'),
    37: ('VULPIX', 'FIRE'),
    38: ('NINETALES', 'FIRE'),
    39: ('JIGGLYPUFF', 'NORMAL / FAIRY'),
    94: ('GENGAR', 'GHOST / POISON'),
    133: ('EEVEE', 'NORMAL'),
    134: ('VAPOREON', 'WATER'),
    135: ('JOLTEON', 'ELECTRIC'),
    136: ('FLAREON', 'FIRE'),
    143: ('SNORLAX', 'NORMAL'),
    149: ('DRAGONITE', 'DRAGON / FLYING'),
    150: ('MEWTWO', 'PSYCHIC'),
    196: ('ESPEON', 'PSYCHIC'),
    197: ('UMBREON', 'DARK'),
    448: ('LUCARIO', 'FIGHTING / STEEL'),
    570: ('ZORUA', 'DARK'),
}


def choose_pokemon():
    """Choose from pre-downloaded sprites without repeating the previous one.

    The lock keeps independent terminal instances from selecting against a
    stale last-used value. Bundled images are never modified.
    """
    folder = BASE / 'pokemon-cache'
    usable = [n for n in POKEMON if (folder / str(n) / 'pokemon.png').is_file()]
    if not usable:
        return 25, folder / '25'
    lockpath = STATE / 'pokemon.lock'
    statepath = STATE / 'last-pokemon.txt'
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        with lockpath.open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                last = int(engine.read_file(statepath, '-1'))
            except ValueError:
                last = -1
            candidates = [n for n in usable if n != last] or usable
            n = secrets.choice(candidates)
            statepath.write_text(str(n) + '\n', encoding='ascii')
            return n, folder / str(n)
    except OSError:
        n = secrets.choice(usable)
        return n, folder / str(n)


def shade_logo(max_w, height):
    """Preserve outlined banners; resample shading-only banners when needed."""
    from .banner import load_custom_banner
    custom = load_custom_banner()
    raw = custom[0] if custom else (BASE / 'banner.txt').read_text(encoding='utf-8').splitlines()
    if not raw:
        return [WHITE + 'NEMZCHAN' + RST]
    sw = max(len(x) for x in raw)
    sh = len(raw)
    if any(char not in SHADES for line in raw for char in line):
        # Box-drawing characters are structural: averaging them into shade
        # density erases their outlines. Keep their original rows and columns.
        if sw <= max_w:
            return [WHITE + line + RST for line in raw]
        return [WHITE + engine.clip(custom[1], max_w) + RST] if custom else engine.pixel_name(max_w)
    width = min(sw, max(1, max_w))
    height = max(7, height)
    raw = [line.ljust(sw) for line in raw]
    result = []
    for y in range(height):
        # Replicate whole raster rows to keep its original distinctive shape;
        # any horizontal downsampling still averages adjacent shade glyphs.
        sy = min(sh - 1, int((y + .5) * sh / height))
        src = raw[sy]
        chars = []
        for x in range(width):
            a = x * sw / width
            b = (x + 1) * sw / width
            index = int(a)
            density = 0.0
            while index < b:
                overlap = min(index + 1, b) - max(index, a)
                density += overlap * DENSITY.get(src[index], 0)
                index += 1
            level = max(0, min(4, round(density / (b - a) + .15)))
            chars.append(SHADES[level])
        result.append(WHITE + ''.join(chars).rstrip() + RST)
    return result


def clip_line(text, width):
    """Clip plain descriptive text, preserving common terminal glyphs."""
    if engine.cells(text) <= width:
        return text
    return text[:max(0, width - 1)] + '…'


def info_panel(width, max_rows, pk_id, name, ptype):
    ram, ratio = engine.mem()
    if width < 39 or max_rows < 20:
        info = [
            WHITE + TRAINER + RST,
            CYAN + clip_line('✦ POKÉMON TRAINER', width) + RST,
            '',
            engine.value_row('OS', engine.read_pretty_os(), width),
            engine.value_row('CPU', engine.cpu_name(), width),
            engine.value_row('RAM', ram, width),
            engine.value_row('UPTIME', engine.uptime(), width),
            clip_line(f'#{pk_id:03d} {name}', width),
        ]
        return info[:max_rows]
    compact = max_rows < 28
    logo_h = 7 if compact else (11 if max_rows >= 36 else 10)
    sep = DIM + '─' * width + RST
    info = [
        f'{DIM}✦ POKÉMON TRAINER  /  {WHITE}{TRAINER}{RST}',
        '',
        *shade_logo(width, logo_h),
        '',
        f'{CYAN}✧ Welcome back, {TRAINER}!{RST}',
        sep,
        engine.value_row('OS', engine.read_pretty_os(), width),
        engine.value_row('HOST', '[hidden]' if os.environ.get('POKEMON_HIDE_HOST') else os.uname().nodename, width),
        engine.value_row('CPU', engine.cpu_name(), width),
    ]
    if not compact:
        gpu = engine.gpu_name()
        if gpu:
            info.append(engine.value_row('GPU', gpu, width))
    info.append(engine.value_row('RAM', ram, width))
    if not compact:
        try:
            disk = shutil.disk_usage(str(Path.home()))
            disk_text = f'{(disk.total - disk.free)/1024**3:.0f} / {disk.total/1024**3:.0f} GiB'
        except OSError:
            disk_text = 'Unknown'
        info.append(engine.value_row('DISK', disk_text, width))
    info.append(engine.value_row('UPTIME', engine.uptime(), width))
    if not compact:
        info.extend([
            engine.value_row('SHELL', os.path.basename(os.environ.get('SHELL', 'bash')), width),
            engine.value_row('DATE', datetime.now().strftime('%d/%m/%Y %H:%M'), width),
        ])
    info.extend([
        sep,
        engine.memory_meter(ratio, width),
        clip_line(f'✦ #{pk_id:03d} {name}  /  {ptype}', width),
    ])
    # Ensure terminal prompt isn't overwritten by clipping lower lines.
    if len(info) > max_rows:
        info = info[:max_rows - 1] + [info[-1]]
    return info


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'prompt':
        from .prompt import main as prompt_main
        return prompt_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == 'banner':
        from .banner import main as banner_main
        return banner_main(sys.argv[2:])
    if '--help' in sys.argv or '-h' in sys.argv:
        print('pokemon-welcome: offline Pokémon terminal greeting\n'
              'pokemon-welcome banner --help: generate or import a custom banner\n'
              'pokemon-welcome prompt --help: enable a directory/Git prompt with Starship\n'
              'Configure: POKEMON_TRAINER, POKEMON_HIDE_WELCOME, POKEMON_HIDE_HOST, XDG_STATE_HOME, XDG_CONFIG_HOME')
        return
    if not sys.stdout.isatty():
        return
    size = shutil.get_terminal_size((140, 42))
    cols, rows = size.columns, size.lines
    if cols < 40 or rows < 12:
        print(CYAN + f'✦ {TRAINER}  /  POKÉMON TRAINER' + RST)
        return

    pk_id, folder = choose_pokemon()
    name, ptype = POKEMON[pk_id]
    # The renderer reads the chosen sprite from this folder.
    engine.BASE = folder

    margin, gap = 2, 3
    usable = cols - 2 * margin - gap
    left_w = usable // 2
    right_w = usable - left_w
    content_h = rows - 4

    # Render the right-hand panel first, so the Pokemon sprite can match its
    # actual height instead of a fraction of the total terminal height.
    right = info_panel(right_w, content_h, pk_id, name, ptype)

    # Sprite + blank separator + Pokemon name occupy about the same height as
    # the entire right panel. engine.sprite_lines preserves the image aspect ratio.
    target_sprite_h = max(8, min(len(right) - 2, content_h - 2))
    sprite = engine.sprite_lines(max(8, left_w - 2), target_sprite_h)
    if not sprite:
        sprite = [YELLOW + '◈ POKÉMON' + RST]

    sprite_width = max(map(engine.cells, sprite), default=0)
    sprite_pad = max(0, (left_w - sprite_width) // 2)
    left = [' ' * sprite_pad + line for line in sprite]
    caption = f'#{pk_id:03d} {name} ▸ {ptype}'
    caption = clip_line(caption, left_w)
    caption_pad = max(0, (left_w - engine.cells(caption)) // 2)
    left.extend(['', ' ' * caption_pad + YELLOW + caption + RST])

    # Crucial: right pane starts at row 1, NOT in the middle of the window.
    # Center the Pokemon only *within the content panel*, not the whole screen.
    left_top = max(0, (len(right) - len(left)) // 2)
    h = max(len(right), left_top + len(left))

    print('\033[2J\033[H', end='')
    for index in range(h):
        li = index - left_top
        l = left[li] if 0 <= li < len(left) else ''
        r = right[index] if index < len(right) else ''
        pad = max(0, left_w - engine.cells(l))
        print(' ' * margin + l + RST + ' ' * pad + ' ' * gap + r + RST)
    print()



if __name__ == '__main__':
    sys.exit(main())

