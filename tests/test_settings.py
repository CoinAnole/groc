from __future__ import annotations

import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from groc.settings import DEFAULT_BACKEND_BASE_URL, DEFAULT_REFRESH_URL, settings_from_env, validate_trusted_endpoints


class SettingsTests(unittest.TestCase):
    def test_defaults_are_local_and_trusted(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = settings_from_env()

        self.assertEqual(settings.bridge_host, "127.0.0.1")
        self.assertEqual(settings.default_model, "gpt-5.6-sol")
        self.assertEqual(settings.reasoning_effort, "high")
        self.assertEqual(settings.upstream_model, "gpt-5.6-sol")
        self.assertEqual(settings.grok_bin, "grok")
        self.assertEqual(settings.auth_file, Path("~/.codex/auth.json").expanduser())
        self.assertEqual(settings.backend_base_url, DEFAULT_BACKEND_BASE_URL)
        self.assertEqual(settings.refresh_url, DEFAULT_REFRESH_URL)
        validate_trusted_endpoints(settings)

    def test_backend_override_requires_explicit_unsafe_opt_in(self) -> None:
        settings = replace(settings_from_env(), backend_base_url="https://example.invalid")

        with self.assertRaises(ValueError):
            validate_trusted_endpoints(settings)

        validate_trusted_endpoints(replace(settings, allow_untrusted_backend=True))

    def test_model_and_reasoning_defaults_remain_overridable(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GROC_MODEL": "gpt-5.6-terra",
                "GROC_REASONING_EFFORT": "medium",
                "GROC_UPSTREAM_MODEL": "gpt-5.6-luna",
            },
            clear=True,
        ):
            settings = settings_from_env()

        self.assertEqual(settings.default_model, "gpt-5.6-terra")
        self.assertEqual(settings.reasoning_effort, "medium")
        self.assertEqual(settings.upstream_model, "gpt-5.6-luna")

    def test_grok_binary_remains_overridable(self) -> None:
        with patch.dict(os.environ, {"GROC_GROK_BIN": "/opt/grok/bin/grok"}, clear=True):
            settings = settings_from_env()

        self.assertEqual(settings.grok_bin, "/opt/grok/bin/grok")

    def test_refresh_override_requires_explicit_unsafe_opt_in(self) -> None:
        settings = replace(settings_from_env(), refresh_url="https://example.invalid/oauth/token")

        with self.assertRaises(ValueError):
            validate_trusted_endpoints(settings)

        validate_trusted_endpoints(replace(settings, allow_untrusted_backend=True))


if __name__ == "__main__":
    unittest.main()
