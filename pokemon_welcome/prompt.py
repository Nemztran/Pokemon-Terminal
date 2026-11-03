"""Opt-in Starship directory/Git prompt; terminal fonts are left untouched."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

START = '# >>> pokemon-welcome prompt >>>'
END = '# <<< pokemon-welcome prompt <<<'
PATTERN = re.compile(r'(?m)^' + re.escape(START) + r'\n.*?^' + re.escape(END) + r'\n?', re.S)
PRESET = Path(__file__).resolve().parent / 'assets/starship.toml'


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'pokemon-welcome/starship.toml'


def shell_rc(shell):
    home = Path.home()
    return home / '.bashrc' if shell == 'bash' else Path(os.environ.get('ZDOTDIR') or home) / '.zshrc'


def write_with_backup(path, content):
    if path.exists():
        if path.read_text() == content:
            return
        backup = path.with_name(path.name + '.pokemon-prompt-' + datetime.now().strftime('%Y%m%d%H%M%S%f') + '.bak')
        shutil.copy2(path, backup)
        print(f'Backup: {backup}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def uninstall():
    for rc in dict.fromkeys((shell_rc('bash'), shell_rc('zsh'))):
        if rc.exists():
            original = rc.read_text()
            updated = PATTERN.sub('', original)
            if updated != original:
                write_with_backup(rc, updated)


def install(shell):
    if not shutil.which('starship'):
        raise ValueError('Starship is required. Install it from https://starship.rs/guide/#installation and retry.')
    rc = shell_rc(shell)
    original = rc.read_text() if rc.exists() else ''
    remaining = PATTERN.sub('', original)
    # Respect an existing Starship initialization instead of adding another one.
    has_init = any(not line.lstrip().startswith('#') and
                   re.search(r'\bstarship\s+init\s+' + shell + r'\b', line)
                   for line in remaining.splitlines())
    config = config_path()
    # Preserve user edits on reinstall. The global Starship config is untouched.
    if not config.exists():
        write_with_backup(config, PRESET.read_text())
    lines = [START, 'if [[ $- == *i* ]]; then',
             '    export STARSHIP_CONFIG=' + shlex.quote(str(config))]
    if not has_init:
        lines.append('    eval "$(starship init ' + shell + ')"')
    lines.extend(['fi', END, ''])
    # Keep the managed block in place so repeated installs are byte-for-byte stable.
    block = '\n'.join(lines)
    updated = PATTERN.sub(lambda match: block, original) if PATTERN.search(original) else remaining.rstrip('\n') + '\n\n' + block
    write_with_backup(rc, updated)
    print(f'Enabled directory/Git prompt in {rc}. Open a new terminal to apply it.')
    print('Powerline symbols need a compatible terminal font. No fonts or greeting settings were changed.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--install', action='store_true', help='Enable the prompt in your shell startup file')
    action.add_argument('--uninstall', action='store_true', help='Remove prompt hooks; keep the theme and greeting')
    action.add_argument('--print-config', action='store_true', help='Print the bundled Starship theme without changing files')
    parser.add_argument('--shell', choices=('bash', 'zsh'), help='Default: current shell')
    args = parser.parse_args(argv)
    try:
        if args.print_config:
            print(PRESET.read_text(), end='')
        elif args.uninstall:
            uninstall()
            print('Removed prompt hooks. Open a new terminal to restore your previous prompt.')
        else:
            shell = args.shell or Path(os.environ.get('SHELL', 'bash')).name
            if shell not in ('bash', 'zsh'):
                parser.error('Choose --shell bash or --shell zsh.')
            install(shell)
    except (OSError, ValueError) as error:
        print(f'Prompt error: {error}', file=sys.stderr)
        return 1
    return 0
