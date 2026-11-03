#!/usr/bin/env python3
"""Install a standalone copy; no sudo, pip or network required."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

START = '# >>> pokemon-welcome >>>'
END = '# <<< pokemon-welcome <<<'
PATTERN = re.compile(r'(?m)^' + re.escape(START) + r'\n.*?^' + re.escape(END) + r'\n?', re.S)


def paths():
    home = Path.home()
    data = Path(os.environ.get('XDG_DATA_HOME') or home / '.local/share')
    return data / 'pokemon-welcome', home / '.local/bin/pokemon-welcome'


def update_rc(rc, block):
    original = rc.read_text() if rc.exists() else ''
    updated = PATTERN.sub('', original)
    if block:
        updated = updated.rstrip('\n') + '\n\n' + block
    if updated != original:
        if rc.exists():
            backup = rc.with_name(rc.name + '.pokemon-welcome-' + datetime.now().strftime('%Y%m%d%H%M%S%f') + '.bak')
            shutil.copy2(rc, backup)
            print(f'Backup: {backup}')
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text(updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true')
    parser.add_argument('--shell', choices=('bash', 'zsh', 'none'), help='Shell to configure; default: current shell')
    args = parser.parse_args()
    target, command = paths()
    home = Path.home()
    zsh_rc = Path(os.environ.get('ZDOTDIR') or home) / '.zshrc'
    if args.uninstall:
        for rc in dict.fromkeys((home / '.bashrc', zsh_rc)):
            if rc.exists():
                update_rc(rc, '')
        if target.exists():
            shutil.rmtree(target)
        if command.exists() or command.is_symlink():
            command.unlink()
        print('Uninstalled pokemon-welcome. Selection history in XDG_STATE_HOME is retained.')
        return

    source = Path(__file__).resolve().parent / 'pokemon_welcome'
    if not source.is_dir():
        parser.error('Run install.py from the project checkout.')
    if source.resolve() == (target / 'pokemon_welcome').resolve():
        parser.error('Run install.py from the project checkout, outside the installation directory.')
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target / 'pokemon_welcome', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text('#!/bin/sh\n' + 'export PYTHONPATH=' + shlex.quote(str(target)) + '\n' +
                       'exec ' + shlex.quote(sys.executable) + ' -m pokemon_welcome "$@"\n')
    command.chmod(0o755)

    shell = args.shell or Path(os.environ.get('SHELL', 'bash')).name
    if shell in ('bash', 'zsh'):
        rc = home / '.bashrc' if shell == 'bash' else zsh_rc
        old = rc.read_text() if rc.exists() else ''
        if 'NEMZCHAN_POKEMON_V8' in old:
            print(f'Existing NEMZCHAN welcome detected in {rc}; keeping its startup hook. Use the new command manually.')
        else:
            block = (START + '\n'
                     'if [[ $- == *i* ]] && [[ -t 1 ]] && [[ -z "${POKEMON_HIDE_WELCOME:-}" ]]; then\n'
                     '    ' + shlex.quote(str(command)) + '\n'
                     'fi\n' + END + '\n')
            update_rc(rc, block)
    elif shell != 'none':
        print(f'Shell {shell!r} is not configured automatically. Supported: Bash, Zsh.')

    print(f'Installed: {command}')
    if not shutil.which('chafa'):
        try:
            import PIL  # noqa: F401
        except ImportError:
            print('Install Pillow or Chafa to display Pokémon images; see README.md.')
    print('Open a new terminal or run the installed command above.')


if __name__ == '__main__':
    main()
