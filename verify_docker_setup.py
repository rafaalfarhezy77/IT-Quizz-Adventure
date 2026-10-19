"""Verification script for Docker containerization setup."""
import os
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class TestDockerSetup(unittest.TestCase):
    def test_dockerfile_exists_and_valid(self):
        df_path = BASE_DIR / "Dockerfile"
        self.assertTrue(df_path.exists(), "Dockerfile must exist")
        content = df_path.read_text(encoding="utf-8")
        self.assertIn("FROM python:3.11-slim", content)
        self.assertIn("ENTRYPOINT", content)
        self.assertIn("HEALTHCHECK", content)
        self.assertIn("EXPOSE 5000", content)

    def test_docker_compose_exists_and_valid(self):
        dc_path = BASE_DIR / "docker-compose.yml"
        self.assertTrue(dc_path.exists(), "docker-compose.yml must exist")
        content = dc_path.read_text(encoding="utf-8")
        self.assertIn("services:", content)
        self.assertIn("quiz-app:", content)
        self.assertIn("./instance:/app/instance", content)
        self.assertIn("5000", content)

    def test_dockerignore_exists(self):
        di_path = BASE_DIR / ".dockerignore"
        self.assertTrue(di_path.exists(), ".dockerignore must exist")
        content = di_path.read_text(encoding="utf-8")
        self.assertIn("venv/", content)
        self.assertIn(".git/", content)
        self.assertIn("instance/*.db", content)

    def test_entrypoint_exists(self):
        ep_path = BASE_DIR / "entrypoint.sh"
        self.assertTrue(ep_path.exists(), "entrypoint.sh must exist")
        content = ep_path.read_text(encoding="utf-8")
        self.assertIn("#!/bin/sh", content)
        self.assertIn("python seed.py", content)
        self.assertIn("exec gunicorn", content)

    def test_requirements_includes_gunicorn(self):
        req_path = BASE_DIR / "requirements.txt"
        content = req_path.read_text(encoding="utf-8")
        self.assertIn("gunicorn", content)

    def test_documentation_guides_exist(self):
        doc_path = BASE_DIR / "docs" / "docker_deployment_guide.md"
        nginx_path = BASE_DIR / "docs" / "nginx_reverse_proxy_sample.conf"
        self.assertTrue(doc_path.exists())
        self.assertTrue(nginx_path.exists())


if __name__ == "__main__":
    unittest.main()
