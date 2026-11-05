# -*- coding: utf-8 -*-
"""Security regression tests for the SPA static-file fallback route."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from api.app import create_app


class SpaStaticFallbackSecurityTestCase(unittest.TestCase):
    """The catch-all route must never escape the configured static directory."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.static_dir = self.root / "static"
        self.static_dir.mkdir()
        (self.static_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
        (self.static_dir / "app.js").write_text("console.log('ok')", encoding="utf-8")
        # A file outside the static root, standing in for the real project
        # files (.env, database, source code) that must stay private.
        self.secret = self.root / "secret.env"
        self.secret.write_text("API_KEY=super-secret", encoding="utf-8")

        app = create_app(static_dir=self.static_dir)
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", None) == "/{full_path:path}"
        )
        self.serve_spa = route.endpoint

    def _request(self, full_path: str):
        return asyncio.run(self.serve_spa(None, full_path))

    def test_parent_directory_traversal_is_rejected(self) -> None:
        response = self._request("../secret.env")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"super-secret", response.body)

    def test_nested_traversal_is_rejected(self) -> None:
        response = self._request("assets/../../secret.env")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"super-secret", response.body)

    def test_absolute_path_is_rejected(self) -> None:
        response = self._request("/secret.env")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"super-secret", response.body)

    @unittest.skipUnless(os.name == "nt", "backslash is only a path separator on Windows")
    def test_windows_separator_traversal_is_rejected(self) -> None:
        response = self._request("..\\secret.env")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"super-secret", response.body)

    def test_regular_static_file_is_served(self) -> None:
        response = self._request("app.js")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(str(response.path).endswith("app.js"))

    def test_unknown_client_route_falls_back_to_index(self) -> None:
        response = self._request("dashboard/settings")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(str(response.path).endswith("index.html"))

    def test_api_paths_still_return_json_404(self) -> None:
        response = self._request("api/v1/unknown")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"api/v1/unknown", response.body)


if __name__ == "__main__":
    unittest.main()
