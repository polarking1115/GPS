"""Exercise the hosted-preview entry point in disposable child processes."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


class Deployment(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='festival-deployment-')
        self.addCleanup(self.directory.cleanup)
        self.env = os.environ.copy()
        # Tests must never use the developer's DB or provider credentials.
        for key in ['FESTIVAL_TRANSLATION_API_KEY', 'FESTIVAL_KMA_API_KEY']:
            self.env.pop(key, None)
        self.env.update(FESTIVAL_DATA=self.directory.name, HOST='127.0.0.1',
                        FESTIVAL_ADMIN_EMAIL='preview-owner@example.test',
                        FESTIVAL_ADMIN_PASSWORD='preview-test-password-2026',
                        FESTIVAL_SECURE_COOKIE='1', FESTIVAL_ALLOW_SETUP='1')
        self.process = None
        self.addCleanup(self.stop)

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.communicate(timeout=5)
            self.process = None

    def start(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.env['PORT'] = str(sock.getsockname()[1])
        self.base = 'http://127.0.0.1:' + self.env['PORT']
        self.process = subprocess.Popen([sys.executable, str(ROOT/'deploy_demo.py')],
                                        cwd=ROOT, env=self.env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail('Preview stopped: ' + self.process.communicate()[0])
            try:
                return self.request('/api/status')[1]
            except URLError:
                time.sleep(0.05)
        self.fail('Preview did not become ready')

    def request(self, path, data=None, token=None, cookie=None):
        headers = {}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if cookie:
            headers['Cookie'] = cookie
        request = Request(self.base + path, headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            body = json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw
            return response.status, body, response.headers

    def login(self, password=None):
        status, result, _ = self.request('/api/login', {
            'email': 'preview-owner@example.test',
            'password': password or 'preview-test-password-2026'})
        self.assertEqual(status, 200)
        return result['token']

    def test_public_preview_login_and_qr_workflow(self):
        status = self.start()
        self.assertFalse(status['setup_required'])
        self.assertEqual(status['integrations']['translation'], 'not_configured')
        for path in ['/', '/e/youth-expo', '/manage', '/booth', '/register?event=youth-expo']:
            code, html, _ = self.request(path)
            self.assertEqual(code, 200)
            self.assertIn('실제 개인정보를 입력하지 마세요.'.encode(), html)
        self.assertEqual(self.request('/api/setup', {'email': 'intruder@example.test',
                                                   'name': 'Intruder', 'password': 'invalid-password-2026'})[0], 409)
        self.assertEqual(self.request('/api/events/youth-expo/admin')[0], 401)
        token = self.login()
        me = self.request('/api/me', token=token)[1]
        self.assertIn({'event': '*', 'role': 'owner'}, me['access'])
        self.assertEqual(self.request('/api/login', {'email': 'preview-owner@example.test',
                                                    'password': 'incorrect-password'})[0], 401)
        self.assertNotIn(b'test-deployment', self.request('/assets/favicon.svg')[1])
        access = self.request('/api/events/youth-expo/booth-access', {'booth': 'booth-1'}, token)[1]
        code, _, headers = self.request('/api/events/youth-expo/pass', {})
        self.assertEqual(code, 200)
        self.assertIn('Secure', headers['Set-Cookie'])
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('/api/events/youth-expo/certify',
                                      {'qr': access['qr']}, cookie=cookie)[0], 200)
        admin = self.request('/api/events/youth-expo/admin', token=token)[1]
        self.assertEqual(next(b['total'] for b in admin['booths'] if b['id'] == 'booth-1'), 1)
        with sqlite3.connect(Path(self.directory.name)/'festival.sqlite3') as db:
            saved = db.execute('SELECT password FROM users').fetchone()[0]
            self.assertNotEqual(saved, self.env['FESTIVAL_ADMIN_PASSWORD'])

    def test_restart_keeps_existing_owner_and_event_data(self):
        self.start()
        token = self.login()
        self.assertEqual(self.request('/api/events/youth-expo/settings',
                                      {'primary': '#334455'}, token)[0], 200)
        self.stop()
        self.env['FESTIVAL_ADMIN_EMAIL'] = 'different@example.test'
        self.env['FESTIVAL_ADMIN_PASSWORD'] = 'different-password-2026'
        self.start()
        self.login()
        self.assertEqual(self.request('/api/events/youth-expo/admin', token=token)[1]
                         ['event']['settings']['primary'], '#334455')
        with sqlite3.connect(Path(self.directory.name)/'festival.sqlite3') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 1)

    def test_missing_or_invalid_owner_fails_before_serving(self):
        for email, password in [('', ''), ('not-an-email', 'sensitive-test-password'),
                                ('preview-owner@example.test', 'short')]:
            with self.subTest(email=email):
                self.env.update(FESTIVAL_ADMIN_EMAIL=email, FESTIVAL_ADMIN_PASSWORD=password)
                result = subprocess.run([sys.executable, str(ROOT/'deploy_demo.py')],
                                        cwd=ROOT, env=self.env, capture_output=True,
                                        text=True, timeout=12)
                self.assertEqual(result.returncode, 1)
                self.assertIn('FESTIVAL_ADMIN_', result.stderr)
                if password:
                    self.assertNotIn(password, result.stderr + result.stdout)
                with sqlite3.connect(Path(self.directory.name)/'festival.sqlite3') as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
