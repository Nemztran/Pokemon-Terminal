import fcntl
import importlib
import os
from pathlib import Path
import pty
import struct
import subprocess
import sys
import tempfile
import termios
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
app = importlib.import_module('pokemon_welcome.__main__')


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pokemon welcome ')
        self.home = Path(self.temp.name)
        self.env = dict(os.environ, HOME=str(self.home), SHELL='/bin/bash',
                        XDG_DATA_HOME=str(self.home / 'data'),
                        XDG_STATE_HOME=str(self.home / 'state'),
                        XDG_CONFIG_HOME=str(self.home / 'config'),
                        ZDOTDIR=str(self.home / 'zsh'), USER='test-trainer')

    def tearDown(self):
        self.temp.cleanup()

    def install(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'install.py'), *args],
                              env=self.env, check=True, text=True, capture_output=True)

    def test_install_reinstall_and_uninstall(self):
        rc = self.home / '.bashrc'
        rc.write_text('export KEEP_ME=yes\n')
        self.install()
        self.install()
        self.assertEqual(rc.read_text().count('# >>> pokemon-welcome >>>'), 1)
        self.assertIn('export KEEP_ME=yes', rc.read_text())
        self.assertTrue(list(self.home.glob('.bashrc.pokemon-welcome-*.bak')))
        command = self.home / '.local/bin/pokemon-welcome'
        # The clone is unnecessary at runtime: execute installed files elsewhere.
        result = subprocess.run([str(command), '--help'], env=self.env, cwd='/tmp',
                                check=True, text=True, capture_output=True)
        self.assertIn('offline Pokémon', result.stdout)
        link = subprocess.run([str(command), 'banner', '--url', 'ASH'], env=self.env,
                              cwd='/tmp', check=True, text=True, capture_output=True)
        self.assertEqual(link.stdout.strip(), 'https://taag.fun/#f=ANSI+Shadow&t=ASH')
        preset = subprocess.run([str(command), 'prompt', '--print-config'], env=self.env,
                                cwd='/tmp', check=True, text=True, capture_output=True)
        self.assertIn('[directory]', preset.stdout)
        # Enabling the optional prompt and uninstalling the entire application
        # must remove both startup hooks while retaining the user's theme.
        fake_starship = self.home / '.local/bin/starship'
        fake_starship.write_text('#!/bin/sh\nexit 0\n')
        fake_starship.chmod(0o755)
        prompt_env = dict(self.env, PATH=str(fake_starship.parent) + os.pathsep + os.environ['PATH'])
        subprocess.run([str(command), 'prompt', '--install'], env=prompt_env,
                       cwd='/tmp', check=True, capture_output=True)
        self.assertIn('# >>> pokemon-welcome prompt >>>', rc.read_text())
        self.install('--uninstall')
        self.assertFalse(command.exists())
        self.assertNotIn('# >>> pokemon-welcome >>>', rc.read_text())
        self.assertNotIn('# >>> pokemon-welcome prompt >>>', rc.read_text())
        self.assertTrue((self.home / 'config/pokemon-welcome/starship.toml').exists())
        self.assertIn('export KEEP_ME=yes', rc.read_text())
        self.assertFalse((self.home / 'data/pokemon-welcome').exists())

    def test_legacy_hook_and_no_shell(self):
        rc = self.home / '.bashrc'
        old = '# >>> NEMZCHAN_POKEMON_V8 >>>\nlegacy\n'
        rc.write_text(old)
        self.install()
        self.assertEqual(rc.read_text(), old)
        self.install('--shell', 'none')
        self.assertEqual(rc.read_text(), old)

    def test_zsh(self):
        self.install('--shell', 'zsh')
        rc = self.home / 'zsh/.zshrc'
        self.assertIn('# >>> pokemon-welcome >>>', rc.read_text())
        self.install('--uninstall')
        self.assertNotIn('# >>> pokemon-welcome >>>', rc.read_text())

    def test_all_sprites_and_no_repeat(self):
        from unittest.mock import patch
        with patch.object(app, 'STATE', self.home / 'state'):
            previous = None
            for _ in range(50):
                ident, folder = app.choose_pokemon()
                self.assertNotEqual(previous, ident)
                self.assertTrue((folder / 'pokemon.png').is_file())
                previous = ident
        for ident in app.POKEMON:
            self.assertTrue((app.BASE / 'pokemon-cache' / str(ident) / 'pokemon.png').is_file())

    def test_missing_sprites_fall_back_without_legacy_files(self):
        from unittest.mock import patch
        with patch.object(app, 'BASE', self.home):
            ident, folder = app.choose_pokemon()
        self.assertEqual(ident, 25)
        self.assertEqual(app.POKEMON[ident], ('PIKACHU', 'ELECTRIC'))
        with patch.object(app.engine, 'BASE', folder):
            self.assertEqual(app.engine.sprite_lines(40, 20), [])

    def test_render_real_terminal_sizes(self):
        for columns, rows in ((140, 42), (80, 24), (40, 12), (30, 8)):
            with self.subTest(columns=columns, rows=rows):
                master, slave = pty.openpty()
                try:
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
                    process = subprocess.Popen([sys.executable, '-m', 'pokemon_welcome'],
                                               cwd=ROOT, env=self.env, stdout=slave,
                                               stderr=subprocess.PIPE)
                    os.close(slave)
                    slave = -1
                    chunks = []
                    while True:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError:
                            break
                        if not chunk:
                            break
                        chunks.append(chunk)
                    _, error = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 0, error.decode())
                    output = b''.join(chunks).decode()
                    self.assertIn('POKÉMON TRAINER', output)
                    self.assertNotIn('Traceback', output)
                    if columns >= 80:
                        self.assertIn('test-trainer', output)
                        self.assertIn('RAM', output)
                        self.assertTrue('48;2;' in output or '38;2;' in output)
                finally:
                    os.close(master)
                    if slave >= 0:
                        os.close(slave)

    def test_pipe_is_quiet(self):
        result = subprocess.run([sys.executable, '-m', 'pokemon_welcome'],
                                cwd=ROOT, env=self.env, capture_output=True, check=True)
        self.assertEqual(result.stdout, b'')

    def test_outlined_banner_preserves_shape_and_fits(self):
        original = (app.BASE / 'banner.txt').read_text().splitlines()
        rendered = [app.engine.ANSI.sub('', line) for line in app.shade_logo(72, 11)]
        self.assertEqual(rendered, original)
        self.assertIn('╔', ''.join(rendered))
        for width in (39, 47, 67, 71, 72):
            with self.subTest(width=width):
                self.assertTrue(all(app.engine.cells(line) <= width
                                    for line in app.shade_logo(width, 7)))

    def test_hostname_can_be_hidden_for_public_screenshots(self):
        from unittest.mock import patch
        with patch.dict(os.environ, POKEMON_HIDE_HOST='1'):
            panel = '\n'.join(app.info_panel(72, 38, 25, 'PIKACHU', 'ELECTRIC'))
        self.assertIn('[hidden]', panel)
        self.assertNotIn(os.uname().nodename, panel)


if __name__ == '__main__':
    unittest.main()
