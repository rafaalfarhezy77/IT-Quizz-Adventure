"""Run real Chromium checks against a temporary app, without Playwright."""
import os
import subprocess
import tempfile
import threading
import logging
from pathlib import Path

from werkzeug.serving import make_server
from config import Config
from models import db, Admin
from werkzeug.security import generate_password_hash
from quiz_app import create_app


def main():
    browsers = [os.environ.get("DEMO_TEST_BROWSER", ""),
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    browser = next((path for path in browsers if path and Path(path).is_file()), None)
    if not browser:
        raise SystemExit("Set DEMO_TEST_BROWSER to a Chromium executable.")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        class BrowserConfig(Config):
            SECRET_KEY = "temporary-browser-verification"
            DEMO_ENABLED = True
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + (root / "official.db").as_posix()
            DEMO_DATABASE_PATH = str(root / "demo.db")
            UPLOAD_FOLDER = str(root / "uploads")
            SESSION_COOKIE_SECURE = False
        app = create_app(BrowserConfig)
        with app.app_context():
            db.session.add(Admin(username="guide-admin", password_hash=generate_password_hash("guide-test-password")))
            db.session.commit()
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            subprocess.run(["node", "verify_demo_browser.js", browser, str(root / "browser"),
                            f"http://127.0.0.1:{server.server_port}"], check=True)
        finally:
            server.shutdown()
            thread.join()
            with app.app_context():
                db.session.remove()
                db.engine.dispose()


if __name__ == "__main__":
    main()
