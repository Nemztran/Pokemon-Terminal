import contextlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pokemon_welcome import prompt


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pokemon prompt ')
        self.home = Path(self.temp.name)
        self.environment = patch.dict(os.environ, HOME=str(self.home),
                                      XDG_CONFIG_HOME=str(self.home / 'config'),
                                      ZDOTDIR=str(self.home / 'zsh'), SHELL='/bin/bash')
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def run_prompt(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return prompt.main(list(args))

    def test_install_reinstall_and_remove_preserve_greeting_and_global_theme(self):
        rc = self.home / '.bashrc'
        old = '# >>> pokemon-welcome >>>\necho greeting\n# <<< pokemon-welcome <<<\n'
        rc.write_text(old)
        global_config = self.home / 'config/starship.toml'
        global_config.parent.mkdir()
        global_config.write_text('original global theme\n')
        with patch.object(prompt.shutil, 'which', return_value='/usr/bin/starship'):
            self.assertEqual(self.run_prompt('--install'), 0)
            installed = rc.read_text()
            subprocess.run(['bash', '-n', str(rc)], check=True)
            # The configuration path contains spaces, so verify shell quoting too.
            env = subprocess.check_output(['bash', '--noprofile', '--rcfile', '/dev/null', '-ic',
                'function starship() { :; }; source "$1" >/dev/null; printf "%s" "$STARSHIP_CONFIG"',
                'check', str(rc)], text=True, stderr=subprocess.DEVNULL)
            self.assertEqual(env, str(prompt.config_path()))
            prompt.config_path().write_text('customized theme\n')
            self.assertEqual(self.run_prompt('--install'), 0)
        self.assertEqual(rc.read_text(), installed)
        self.assertEqual(installed.count(prompt.START), 1)
        self.assertEqual(installed.count('starship init bash'), 1)
        self.assertTrue(list(self.home.glob('.bashrc.pokemon-prompt-*.bak')))
        self.assertIn(old, installed)
        self.assertEqual(global_config.read_text(), 'original global theme\n')
        self.assertEqual(prompt.config_path().read_text(), 'customized theme\n')
        self.assertEqual(self.run_prompt('--uninstall'), 0)
        self.assertNotIn(prompt.START, rc.read_text())
        self.assertIn(old, rc.read_text())
        self.assertTrue(prompt.config_path().exists())

    def test_existing_starship_init_is_not_duplicated(self):
        rc = self.home / '.bashrc'
        rc.write_text('eval "$(starship init bash)"\n')
        with patch.object(prompt.shutil, 'which', return_value='/usr/bin/starship'):
            self.assertEqual(self.run_prompt('--install'), 0)
        self.assertEqual(rc.read_text().count('starship init bash'), 1)
        self.assertIn('export STARSHIP_CONFIG=', rc.read_text())

    def test_missing_dependency_does_not_change_files(self):
        rc = self.home / '.bashrc'
        rc.write_text('original\n')
        with patch.object(prompt.shutil, 'which', return_value=None):
            self.assertEqual(self.run_prompt('--install'), 1)
        self.assertEqual(rc.read_text(), 'original\n')
        self.assertFalse(prompt.config_path().exists())

    def test_zsh_and_uninstall_both_shells(self):
        with patch.object(prompt.shutil, 'which', return_value='/usr/bin/starship'):
            self.assertEqual(self.run_prompt('--install', '--shell', 'bash'), 0)
            self.assertEqual(self.run_prompt('--install', '--shell', 'zsh'), 0)
        zsh_rc = self.home / 'zsh/.zshrc'
        self.assertIn('starship init zsh', zsh_rc.read_text())
        self.assertEqual(self.run_prompt('--uninstall'), 0)
        for rc in (self.home / '.bashrc', zsh_rc):
            self.assertNotIn(prompt.START, rc.read_text())

    def test_print_config_does_not_require_starship_or_write_files(self):
        with patch.object(prompt.shutil, 'which', return_value=None):
            self.assertEqual(self.run_prompt('--print-config'), 0)
        self.assertEqual(list(self.home.iterdir()), [])

    @unittest.skipUnless(shutil.which('starship'), 'Starship not installed')
    def test_real_directory_and_git_branch_changes(self):
        repo = self.home / 'sample-project'
        repo.mkdir()
        subprocess.run(['git', 'init', '-b', 'main'], cwd=repo, check=True, capture_output=True)
        environment = dict(os.environ, STARSHIP_CONFIG=str(prompt.PRESET), STARSHIP_SHELL='plain', TERM='xterm-256color')

        def render(directory):
            result = subprocess.run(['starship', 'prompt', '--path', str(directory),
                                     '--logical-path', str(directory)], cwd=directory,
                                    env=dict(environment, PWD=str(directory)),
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stderr, '')
            return re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)

        outside = render(self.home)
        self.assertNotIn('main', outside)
        inside = render(repo)
        self.assertIn('sample-project', inside)
        self.assertIn('main', inside)
        self.assertEqual(inside.count(''), 1)
        self.assertNotIn('', inside)
        subprocess.run(['git', 'checkout', '-b', 'feature/new-ui'], cwd=repo,
                       check=True, capture_output=True)
        (repo / 'new.txt').write_text('new file\n')
        updated = render(repo)
        self.assertIn('feature/new-ui', updated)
        self.assertIn('?1', updated)


if __name__ == '__main__':
    unittest.main()
