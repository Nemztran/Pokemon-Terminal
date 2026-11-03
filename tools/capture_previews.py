#!/usr/bin/env python3
"""Capture real VTE terminal widgets running the application on this machine.

Ubuntu/Debian preview dependencies: python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91.
Requires a graphical session. No desktop-wide capture or image reconstruction.
Hostnames are hidden in public demos; private shell startup files are not read.
"""
import argparse
import os
from pathlib import Path
import socket
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def capture(output, pokemon, columns, rows, trainer):
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    gi.require_version('Vte', '2.91')
    from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte

    if not Gtk.init_check([])[0]:
        raise RuntimeError('A graphical display is required to capture a real terminal.')
    window = Gtk.OffscreenWindow()
    terminal = Vte.Terminal()
    terminal.set_font(Pango.FontDescription('DejaVu Sans Mono 12'))
    terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)
    background, foreground = Gdk.RGBA(), Gdk.RGBA()
    background.parse('#1e1e2e')
    foreground.parse('#cdd6f4')
    terminal.set_color_background(background)
    terminal.set_color_foreground(foreground)
    window.add(terminal)
    window.show_all()
    # VTE needs realization before its font cell dimensions are available.
    terminal.set_size_request(columns * terminal.get_char_width() + 2,
                              rows * terminal.get_char_height() + 2)
    failures = []
    completed = False
    with tempfile.TemporaryDirectory(prefix='pokemon-terminal-demo-') as temporary:
        env = dict(os.environ, XDG_STATE_HOME=temporary + '/state',
                   XDG_CONFIG_HOME=temporary + '/config', POKEMON_HIDE_HOST='1',
                   POKEMON_TRAINER=trainer, TERM='xterm-256color',
                   SHELL='/bin/bash', PYTHONPATH=str(ROOT))
        # Only the Pokémon selection is fixed. System values and rendering are
        # produced by the application running in the terminal's actual PTY.
        script = ('from pokemon_welcome import __main__ as app; '
                  f'app.secrets.choice = lambda candidates: {pokemon}; app.main()')

        def save():
            nonlocal completed
            try:
                if terminal.get_column_count() != columns or terminal.get_row_count() != rows:
                    raise RuntimeError('The terminal did not allocate the requested grid size.')
                if hasattr(terminal, 'get_text_format'):
                    text = terminal.get_text_format(Vte.Format.TEXT)
                else:
                    stream = Gio.MemoryOutputStream.new_resizable()
                    terminal.write_contents_sync(stream, Vte.WriteFlags.DEFAULT, None)
                    stream.close(None)
                    text = stream.steal_as_bytes().get_data().decode('utf-8')
                if socket.gethostname() in text:
                    raise RuntimeError('Refusing to publish a capture containing the hostname.')
                if 'POKÉMON TRAINER' not in text or 'Traceback' in text:
                    raise RuntimeError('The terminal did not render the expected application output.')
                pixels = window.get_pixbuf()
                if pixels is None:
                    raise RuntimeError('GTK did not return a terminal image.')
                pixels.savev(str(output), 'png', [], [])
            except Exception as error:
                failures.append(str(error))
            completed = True
            Gtk.main_quit()
            return False

        def exited(_terminal, status):
            if status:
                failures.append(f'The demo exited with wait status {status}.')
                Gtk.main_quit()
            else:
                GLib.timeout_add(150, save)

        terminal.connect('child-exited', exited)

        def start():
            terminal.spawn_async(Vte.PtyFlags.DEFAULT, str(ROOT),
                                 [sys.executable, '-c', script],
                                 [f'{key}={value}' for key, value in env.items()],
                                 GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)
            return False

        def timeout():
            if not completed:
                failures.append('Terminal capture timed out.')
                Gtk.main_quit()
            return False

        GLib.timeout_add(200, start)
        deadline = GLib.timeout_add_seconds(15, timeout)
        Gtk.main()
        if completed:
            GLib.source_remove(deadline)
        window.destroy()
    if failures:
        raise RuntimeError('; '.join(failures))
    print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/screenshots')
    parser.add_argument('--trainer', default=os.environ.get('USER', 'Trainer'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, ident, columns, rows in (
        ('pikachu-wide', 25, 150, 42),
        ('gengar-wide', 94, 150, 42),
        ('lucario-compact', 448, 84, 26),
    ):
        capture(args.output / (name + '.png'), ident, columns, rows, args.trainer)


if __name__ == '__main__':
    main()
