# -*- coding: utf-8 -*-
"""Security tests for the first-time admin password bootstrap token."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.auth as auth
from api.v1.endpoints import auth as auth_endpoint
from src.config import Config


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}
    auth._setup_token = None


def _build_request(host: str):
    return SimpleNamespace(
        headers={},
        url=SimpleNamespace(scheme="http"),
        cookies={},
        client=SimpleNamespace(host=host),
    )


class FirstLoginSetupTokenTestCase(unittest.TestCase):
    """A remote client must not be able to claim the admin account."""

    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.env_path.write_text(
            "STOCK_LIST=600519\nADMIN_AUTH_ENABLED=true\n",
            encoding="utf-8",
        )
        self._env_patcher = patch.dict(
            os.environ,
            {
                "ENV_FILE": str(self.env_path),
                "DATABASE_PATH": str(self.data_dir / "test.db"),
                "ADMIN_SETUP_TOKEN": "",
            },
        )
        self._env_patcher.start()
        Config.reset_instance()

        self._enabled_patcher = patch.object(auth, "_is_auth_enabled_from_env", return_value=True)
        self._enabled_patcher.start()
        self._data_dir_patcher = patch.object(auth, "_get_data_dir", return_value=self.data_dir)
        self._data_dir_patcher.start()

    def tearDown(self) -> None:
        self._enabled_patcher.stop()
        self._data_dir_patcher.stop()
        self._env_patcher.stop()
        Config.reset_instance()
        _reset_auth_globals()
        self.temp_dir.cleanup()

    def _login(self, host: str, *, token: str | None = None):
        body = auth_endpoint.LoginRequest(
            password="newpass123",
            passwordConfirm="newpass123",
            setupToken=token,
        )
        return asyncio.run(auth_endpoint.auth_login(_build_request(host), body))

    def test_remote_first_login_requires_setup_token(self) -> None:
        response = self._login("203.0.113.7")

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"setup_token_required", response.body)
        self.assertFalse(auth.has_stored_password())

    def test_remote_first_login_rejects_wrong_token(self) -> None:
        auth.get_setup_token()
        response = self._login("203.0.113.7", token="definitely-wrong")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(auth.has_stored_password())

    def test_remote_first_login_accepts_file_token(self) -> None:
        token = auth.get_setup_token()
        token_path = self.data_dir / auth.SETUP_TOKEN_FILENAME
        self.assertTrue(token_path.exists())

        response = self._login("203.0.113.7", token=token)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(auth.has_stored_password())
        self.assertFalse(token_path.exists())

    def test_loopback_first_login_keeps_zero_friction(self) -> None:
        response = self._login("127.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(auth.has_stored_password())

    def test_status_exposes_requirement_only_for_remote_clients(self) -> None:
        remote_status = asyncio.run(auth_endpoint.auth_status(_build_request("203.0.113.7")))
        loopback_status = asyncio.run(auth_endpoint.auth_status(_build_request("127.0.0.1")))

        self.assertTrue(remote_status["setupTokenRequired"])
        self.assertFalse(loopback_status["setupTokenRequired"])

    def test_settings_initial_password_requires_token_for_remote(self) -> None:
        body = auth_endpoint.AuthSettingsRequest(
            authEnabled=True,
            password="newpass123",
            passwordConfirm="newpass123",
        )
        response = asyncio.run(
            auth_endpoint.auth_update_settings(_build_request("203.0.113.7"), body)
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"setup_token_required", response.body)
        self.assertFalse(auth.has_stored_password())


if __name__ == "__main__":
    unittest.main()
