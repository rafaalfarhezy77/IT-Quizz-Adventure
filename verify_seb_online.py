"""Verification test suite for Safe Exam Browser (SEB) integration and Online Exam settings."""
import unittest
import xml.etree.ElementTree as ET

from app import app
from services.seb_service import (
    build_seb_plist,
    is_seb_user_agent,
    is_seb_request,
    is_seb_enforced,
    set_seb_enforced,
    reset_seb_runtime_toggle,
)


class TestSafeExamBrowser(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        reset_seb_runtime_toggle()

    def tearDown(self):
        reset_seb_runtime_toggle()

    def test_build_seb_plist_valid_xml(self):
        start_url = "http://127.0.0.1:5000/participant/access"
        quit_url = "http://127.0.0.1:5000/"
        xml_content = build_seb_plist(start_url=start_url, quit_url=quit_url, quit_password="secretpassword")

        # Must parse as valid XML
        root = ET.fromstring(xml_content)
        self.assertEqual(root.tag, "plist")
        dict_elem = root.find("dict")
        self.assertIsNotNone(dict_elem)

        # Check critical keys exist in plist
        keys = [k.text for k in dict_elem.findall("key")]
        self.assertIn("startURL", keys)
        self.assertIn("quitURL", keys)
        self.assertIn("allowQuit", keys)
        self.assertIn("hashedQuitPassword", keys)
        self.assertIn("enableAltTab", keys)
        self.assertIn("enableDeveloperConsole", keys)
        self.assertIn("kioskMode", keys)
        self.assertIn("hookKeys", keys)

    def test_is_seb_user_agent(self):
        self.assertTrue(is_seb_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 SEB/3.4.1"))
        self.assertTrue(is_seb_user_agent("SEB_Win_3.4.0"))
        self.assertTrue(is_seb_user_agent("SafeExamBrowser/3.1"))
        self.assertFalse(is_seb_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"))
        self.assertFalse(is_seb_user_agent(""))

    def test_seb_download_endpoint(self):
        resp = self.client.get("/seb/download")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/x-seb", resp.content_type)
        self.assertIn('attachment; filename="IT_Quizz_Adventure.seb"', resp.headers.get("Content-Disposition", ""))
        self.assertIn(b"<plist", resp.data)
        self.assertIn(b"<key>startURL</key>", resp.data)

    def test_seb_config_file_endpoint(self):
        resp = self.client.get("/seb/config.seb")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/x-seb", resp.content_type)
        self.assertIn('inline; filename="IT_Quizz_Adventure.seb"', resp.headers.get("Content-Disposition", ""))
        self.assertIn(b"<plist", resp.data)

    def test_seb_instruction_endpoint(self):
        resp = self.client.get("/seb/instruction")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Safe Exam Browser", resp.get_data(as_text=True))
        self.assertIn("BUKA LANGSUNG DI SEB", resp.get_data(as_text=True))

    def test_participant_access_when_seb_flexible(self):
        set_seb_enforced(False)
        # Normal browser request succeeds
        resp = self.client.get(
            "/participant/access",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_participant_access_when_seb_enforced(self):
        set_seb_enforced(True)

        # Standard browser should be blocked with 403 and SEB required template
        resp_chrome = self.client.get(
            "/participant/access",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"},
        )
        self.assertEqual(resp_chrome.status_code, 403)
        self.assertIn("SAFE EXAM BROWSER", resp_chrome.get_data(as_text=True))
        self.assertIn("DIPERLUKAN", resp_chrome.get_data(as_text=True))

        # SEB User-Agent should be allowed through
        resp_seb = self.client.get(
            "/participant/access",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 SEB/3.4.1"},
        )
        self.assertEqual(resp_seb.status_code, 200)

        # SEB Header (e.g. RequestHash) should also be allowed through
        resp_header = self.client.get(
            "/participant/access",
            headers={
                "User-Agent": "CustomBrowser",
                "X-SafeExamBrowser-RequestHash": "dummy-hash-abc",
            },
        )
        self.assertEqual(resp_header.status_code, 200)

    def test_landing_page_decorations(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        text = resp.get_data(as_text=True)

        # Check offline text was removed
        self.assertNotIn("OFFLINE LAN", text)

        # Check online & SEB badges exist
        self.assertIn("ONLINE EXAM", text)
        self.assertIn("SEB SECURED", text)
        self.assertIn("PANDUAN SEB", text)


if __name__ == "__main__":
    unittest.main()
