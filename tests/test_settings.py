from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from groc.errors import GrocError
from groc.settings import (
    DEFAULT_BACKEND_BASE_URL,
    DEFAULT_REFRESH_URL,
    LAUNCHER_CONFIG_TEMPLATE,
    ensure_launcher_file,
    settings_from_env,
    validate_trusted_endpoints,
)


class SettingsTests(unittest.TestCase):
    def test_defaults_are_local_and_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"GROC_HOME": directory}, clear=True
        ):
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
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"GROC_HOME": directory}, clear=True
        ):
            settings = replace(settings_from_env(), backend_base_url="https://example.invalid")

        with self.assertRaises(ValueError):
            validate_trusted_endpoints(settings)

        validate_trusted_endpoints(replace(settings, allow_untrusted_backend=True))

    def test_model_and_reasoning_defaults_remain_overridable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "GROC_HOME": directory,
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
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"GROC_HOME": directory, "GROC_GROK_BIN": "/opt/grok/bin/grok"},
            clear=True,
        ):
            settings = settings_from_env()

        self.assertEqual(settings.grok_bin, "/opt/grok/bin/grok")

    def test_refresh_override_requires_explicit_unsafe_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"GROC_HOME": directory}, clear=True
        ):
            settings = replace(settings_from_env(), refresh_url="https://example.invalid/oauth/token")

        with self.assertRaises(ValueError):
            validate_trusted_endpoints(settings)

        validate_trusted_endpoints(replace(settings, allow_untrusted_backend=True))

    def test_launcher_file_is_loaded_before_environment_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "groc.toml").write_text(
                'bridge_port = 12000\ndefault_model = "gpt-5.4"\nbridge_log = "logs/bridge.log"\n'
                'grok_bin = "bin/grok"\n',
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"GROC_HOME": directory, "GROC_BRIDGE_PORT": "13000"},
                clear=True,
            ):
                settings = settings_from_env()

        self.assertEqual(settings.bridge_port, 13000)
        self.assertEqual(settings.default_model, "gpt-5.4")
        self.assertEqual(settings.bridge_log, home / "logs" / "bridge.log")
        self.assertEqual(settings.grok_bin, str(home / "bin" / "grok"))

    def test_relative_environment_paths_resolve_from_groc_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "GROC_HOME": directory,
                "GROC_BRIDGE_LOG": "logs/bridge.log",
                "GROC_GROK_BIN": "bin/grok",
            },
            clear=True,
        ):
            settings = settings_from_env()

        self.assertEqual(settings.bridge_log, Path(directory) / "logs" / "bridge.log")
        self.assertEqual(settings.grok_bin, str(Path(directory) / "bin" / "grok"))

    def test_launcher_file_rejects_unknown_and_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "groc.toml"
            path.write_text("surprise = true\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {"GROC_HOME": directory}, clear=True),
                self.assertRaisesRegex(GrocError, "unknown setting"),
            ):
                settings_from_env()

            path.write_text('bridge_port = "not-a-port"\n', encoding="utf-8")
            with (
                patch.dict(os.environ, {"GROC_HOME": directory}, clear=True),
                self.assertRaisesRegex(GrocError, "bridge_port must be an integer"),
            ):
                settings_from_env()

    def test_launcher_template_is_created_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"GROC_HOME": directory}, clear=True):
                settings = settings_from_env()
            ensure_launcher_file(settings)
            self.assertEqual(settings.launcher_file.read_text(encoding="utf-8"), LAUNCHER_CONFIG_TEMPLATE)

            settings.launcher_file.write_text("bridge_port = 12000\n", encoding="utf-8")
            ensure_launcher_file(settings)
            self.assertEqual(settings.launcher_file.read_text(encoding="utf-8"), "bridge_port = 12000\n")

    def test_install_launcher_template_matches_runtime_template(self) -> None:
        static_template = (Path(__file__).parents[1] / "config" / "groc.toml").read_text(encoding="utf-8")

        self.assertEqual(static_template, LAUNCHER_CONFIG_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
