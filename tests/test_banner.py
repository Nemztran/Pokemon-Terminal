import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from pokemon_welcome import banner
from pokemon_welcome import __main__ as app


class BannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, XDG_CONFIG_HOME=self.temp.name)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_import_and_narrow_fallback_keep_custom_name(self):
        art = '██╗██╗\n╚═╝╚═╝'
        file = Path(self.temp.name) / 'art.txt'
        file.write_text(art)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(banner.main(['--from-file', str(file), '--label', 'ASH']), 0)
        self.assertEqual(banner.load_custom_banner(), (art.splitlines(), 'ASH'))
        self.assertEqual([app.engine.ANSI.sub('', s) for s in app.shade_logo(72, 11)], art.splitlines())
        self.assertEqual(app.engine.ANSI.sub('', app.shade_logo(4, 7)[0]), 'ASH')

    def test_preview_does_not_save_and_reset_removes_override(self):
        with patch.object(banner.TaagClient, 'render', return_value='██ ASH ██'), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(banner.main(['ASH', '--preview']), 0)
            self.assertFalse(banner.config_path().exists())
            self.assertEqual(banner.main(['ASH']), 0)
            self.assertTrue(banner.config_path().exists())
            banner.main(['--reset'])
            self.assertFalse(banner.config_path().exists())

    def test_network_failure_preserves_existing_banner(self):
        banner.save_banner('ORIGINAL', 'Original')
        previous = banner.config_path().read_bytes()
        with patch.object(banner.TaagClient, 'render', side_effect=urllib.error.URLError('offline')), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(banner.main(['ASH']), 1)
        self.assertEqual(banner.config_path().read_bytes(), previous)

    def test_url_encodes_names(self):
        self.assertEqual(banner.editor_url('ASH & MISTY'),
                         'https://taag.fun/#f=ANSI+Shadow&t=ASH+%26+MISTY')

    def test_control_codes_are_rejected_before_save(self):
        banner.save_banner('ORIGINAL', 'Original')
        previous = banner.config_path().read_bytes()
        for art in ('', '\x1b[2Jhello', 'hello\tworld', '\x00'):
            with self.subTest(art=art), self.assertRaises(ValueError):
                banner.save_banner(art, 'ASH')
        self.assertEqual(banner.config_path().read_bytes(), previous)

    def test_mcp_json_and_sse(self):
        result = {'content': [{'type': 'text', 'text': '██ ASH ██'}]}
        message = {'jsonrpc': '2.0', 'id': 4, 'result': result}
        self.assertEqual(banner.decode_response(json.dumps(message), 'application/json', 4), result)
        stream = ': keepalive\n\nevent: message\ndata: ' + json.dumps(message) + '\n\n'
        self.assertEqual(banner.decode_response(stream, 'text/event-stream', 4), result)

    def test_mcp_http_handshake_session_schema_and_render(self):
        requests = []

        def response_for(request, timeout):
            data = json.loads(request.data)
            requests.append((data, dict(request.header_items())))
            results = {
                'initialize': {'protocolVersion': '2025-03-26'},
                'tools/list': {'tools': [{'name': 'render', 'inputSchema': {
                    'properties': {'text': {'type': 'string'}, 'font': {'type': 'string'}},
                    'required': ['text', 'font'],
                }}]},
                'tools/call': {'content': [{'type': 'text', 'text': '██ ASH ██'}]},
            }

            class Response(io.BytesIO):
                headers = {'Content-Type': 'application/json', 'Mcp-Session-Id': 'test-session'}

            body = json.dumps({'jsonrpc': '2.0', 'id': data.get('id'),
                               'result': results.get(data['method'], {})}).encode()
            return Response(body)

        with patch.object(banner.urllib.request, 'urlopen', side_effect=response_for):
            self.assertEqual(banner.TaagClient().render('ASH', 'ANSI Shadow'), '██ ASH ██')
        self.assertEqual([data['method'] for data, _ in requests],
                         ['initialize', 'notifications/initialized', 'tools/list', 'tools/call'])
        self.assertNotIn('id', requests[1][0])
        self.assertEqual(requests[-1][0]['params']['arguments'], {'text': 'ASH', 'font': 'ANSI Shadow'})
        self.assertIn('test-session', requests[-1][1].values())

    def test_cli_returns_nonzero_on_invalid_import(self):
        result = subprocess.run([sys.executable, '-m', 'pokemon_welcome', 'banner',
                                 '--from-file', str(Path(self.temp.name) / 'missing.txt')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Banner error:', result.stderr)

    def test_clipboard_failure_does_not_undo_save(self):
        with patch.object(banner.TaagClient, 'render', return_value='ASH'), \
                patch.object(banner, 'copy_art', return_value=False), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(banner.main(['ASH', '--copy']), 0)
        self.assertEqual(banner.load_custom_banner(), (['ASH'], 'ASH'))
