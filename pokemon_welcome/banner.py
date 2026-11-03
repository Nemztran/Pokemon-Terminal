"""Personal banners and a small standard-library client for TAAG's public MCP."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ENDPOINT = 'https://taag.fun/mcp'
MAX_RESPONSE = 2 * 1024 * 1024


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'pokemon-welcome/banner.json'


def validate_art(art):
    if not isinstance(art, str) or not art.strip():
        raise ValueError('The banner is empty.')
    art = art.replace('\r\n', '\n').rstrip('\n')
    if len(art) > 100000 or len(art.splitlines()) > 100:
        raise ValueError('The banner is too large (maximum 100 rows / 100000 characters).')
    if any(not char.isprintable() and char != '\n' for char in art):
        raise ValueError('The banner contains control characters. Use plain UTF-8 text without tabs or ANSI escapes.')
    return art


def load_custom_banner():
    try:
        data = json.loads(config_path().read_text(encoding='utf-8'))
        return validate_art(data['art']).splitlines(), clean_name(data['name'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clean_name(name):
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError('Use a name between 1 and 80 characters.')
    if not all(char.isprintable() for char in name):
        raise ValueError('Names cannot contain control characters.')
    return name.strip()


def save_banner(art, name):
    data = {'name': clean_name(name), 'art': validate_art(art)}
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.banner-', delete=False) as temp:
        temporary = Path(temp.name)
        json.dump(data, temp, ensure_ascii=False, indent=2)
        temp.write('\n')
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def editor_url(name, font='ANSI Shadow'):
    return 'https://taag.fun/#' + urllib.parse.urlencode({'f': font, 't': clean_name(name)})


def decode_response(body, content_type, request_id):
    if 'text/event-stream' in content_type:
        messages = []
        for event in body.replace('\r\n', '\n').split('\n\n'):
            data = '\n'.join(line[5:].lstrip(' ') for line in event.splitlines()
                             if line.startswith('data:'))
            if data:
                messages.append(json.loads(data))
    else:
        messages = [json.loads(body)]
    for message in messages:
        if isinstance(message, dict) and message.get('id') == request_id:
            if 'error' in message:
                raise ValueError('TAAG MCP error: ' + str(message['error']))
            if 'result' not in message:
                raise ValueError('TAAG returned a response without a result.')
            return message['result']
    raise ValueError('TAAG returned no matching response.')


class TaagClient:
    def __init__(self):
        self.session = None
        self.request_id = 0
        self.protocol = None

    def request(self, method, params=None, notification=False):
        self.request_id += 1
        payload = {'jsonrpc': '2.0', 'method': method}
        if not notification:
            payload['id'] = self.request_id
        if params is not None:
            payload['params'] = params
        headers = {'Content-Type': 'application/json',
                   'Accept': 'application/json, text/event-stream',
                   'User-Agent': 'pokemon-welcome/1.0'}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        if self.protocol:
            headers['MCP-Protocol-Version'] = self.protocol
        request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                         headers=headers, method='POST')
        with urllib.request.urlopen(request, timeout=20) as response:
            self.session = response.headers.get('Mcp-Session-Id', self.session)
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise ValueError('TAAG response exceeded 2 MiB.')
            if notification:
                return None
            return decode_response(body.decode('utf-8'), response.headers.get('Content-Type', ''),
                                   self.request_id)

    def render(self, name, font):
        initialized = self.request('initialize', {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'pokemon-welcome', 'version': '1.0.0'},
        })
        self.protocol = initialized['protocolVersion']
        if self.protocol != '2025-03-26':
            raise ValueError(f'TAAG negotiated an unsupported MCP version: {self.protocol}')
        self.request('notifications/initialized', notification=True)
        catalog = self.request('tools/list')
        tool = next((tool for tool in catalog.get('tools', []) if tool.get('name') == 'render'), None)
        if not tool:
            raise ValueError('TAAG does not advertise a render tool.')
        schema = tool.get('inputSchema', {})
        properties = schema.get('properties', {})
        if not {'text', 'font'}.issubset(properties):
            raise ValueError('The TAAG render schema has changed; use the website and --from-file.')
        if set(schema.get('required', [])) - {'text', 'font'}:
            raise ValueError('TAAG requires new render options; use the website and --from-file.')
        result = self.request('tools/call', {'name': 'render', 'arguments': {'text': name, 'font': font}})
        if result.get('isError'):
            raise ValueError('TAAG could not render this name/font: ' + str(result.get('content', '')))
        # Prefer structured output when available; some MCP servers return a
        # JSON object in their text content, others return the artwork directly.
        structured = result.get('structuredContent')
        if isinstance(structured, dict):
            for key in ('art', 'output', 'result', 'text'):
                if isinstance(structured.get(key), str):
                    return validate_art(structured[key])
        parts = [item['text'] for item in result.get('content', []) if item.get('type') == 'text']
        text = '\n'.join(parts)
        try:
            decoded = json.loads(text)
        except ValueError:
            decoded = None
        if isinstance(decoded, dict):
            for key in ('art', 'output', 'result', 'text'):
                if isinstance(decoded.get(key), str):
                    return validate_art(decoded[key])
            raise ValueError('TAAG returned unrecognized JSON instead of artwork.')
        if text.startswith('```'):
            lines = text.splitlines()
            if lines[-1] == '```':
                text = '\n'.join(lines[1:-1])
        return validate_art(text)


def copy_art(art):
    candidates = []
    if os.environ.get('WAYLAND_DISPLAY'):
        candidates.append(['wl-copy'])
    if os.environ.get('DISPLAY'):
        candidates.extend((['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']))
    if sys.platform == 'darwin':
        candidates.append(['pbcopy'])
    for command in candidates:
        if shutil.which(command[0]):
            subprocess.run(command, input=art, text=True, check=True, timeout=5)
            return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate a personal banner using TAAG, or import copied artwork.')
    parser.add_argument('name', nargs='?', help='Name to render using TAAG (network required)')
    parser.add_argument('--font', default='ANSI Shadow')
    parser.add_argument('--from-file', type=Path, help='Import UTF-8 artwork without a network request')
    parser.add_argument('--label', help='Compact fallback name when importing artwork')
    parser.add_argument('--url', metavar='NAME', help='Print the TAAG editor link without calling its API')
    parser.add_argument('--preview', action='store_true', help='Print artwork without saving it')
    parser.add_argument('--copy', action='store_true', help='Also copy artwork to the system clipboard')
    parser.add_argument('--reset', action='store_true', help='Remove the personal banner and use the bundled default')
    args = parser.parse_args(argv)
    if sum(bool(item) for item in (args.name, args.from_file, args.url, args.reset)) != 1:
        parser.error('Choose a name, --from-file, --url, or --reset.')
    try:
        if args.url:
            print(editor_url(args.url, args.font))
            return
        if args.reset:
            config_path().unlink(missing_ok=True)
            print('Personal banner removed; the bundled banner will be used.')
            return
        if args.from_file:
            name = clean_name(args.label or args.from_file.stem)
            art = validate_art(args.from_file.read_text(encoding='utf-8'))
        else:
            name = clean_name(args.name)
            art = TaagClient().render(name, args.font)
        print(art)
        if not args.preview:
            print(f'\nSaved: {save_banner(art, name)}', file=sys.stderr)
        if args.copy:
            try:
                copied = copy_art(art)
            except (OSError, subprocess.SubprocessError) as error:
                print(f'Clipboard unavailable: {error}', file=sys.stderr)
            else:
                print('Copied to clipboard.' if copied else
                      'Clipboard helper unavailable. Install wl-clipboard (Wayland) or xclip (X11).', file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Banner error: {error}\nUse the TAAG website and import with --from-file if the API is unavailable.', file=sys.stderr)
        return 1
    return 0
