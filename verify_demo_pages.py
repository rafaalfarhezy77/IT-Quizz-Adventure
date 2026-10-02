"""Verify the standalone site under a repository subpath on a static server."""
import functools
import http.server
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            # Chromium may close an idle keep-alive connection during shutdown.
            pass


def main():
    subprocess.run(['node', '--test', str(ROOT / 'demo-pages/tests/engine.test.cjs'),
                    str(ROOT / 'demo-pages/tests/methods.test.cjs')], check=True)
    paths = [os.environ.get('DEMO_TEST_BROWSER', ''),
             r'C:\Program Files\Google\Chrome\Application\chrome.exe',
             r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe']
    browser = next((p for p in paths if p and Path(p).is_file()), None)
    if not browser:
        raise SystemExit('Set DEMO_TEST_BROWSER to a Chromium executable.')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        site = root / 'repository-name' / 'demo-pages'
        shutil.copytree(ROOT / 'demo-pages', site)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
                    functools.partial(QuietHandler, directory=str(root)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            subprocess.run(['node', str(ROOT / 'verify_demo_pages.cjs'), browser,
                            str(root / 'chrome-profile'),
                            f'http://127.0.0.1:{server.server_port}/repository-name/demo-pages/'],
                           cwd=ROOT, check=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    main()
