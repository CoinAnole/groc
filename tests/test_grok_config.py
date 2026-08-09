from __future__ import annotations

import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

from groc.errors import GrocError
from groc.grok_config import (
    BEGIN_MANAGED_MODELS,
    END_MANAGED_MODELS,
    reconcile_grok_config,
    render_grok_config,
    write_grok_config,
)
from groc.models import MODEL_CATALOG
from groc.settings import Settings


def settings(port: int = 11435, model: str = "gpt-5.6-sol") -> Settings:
    root = Path(tempfile.gettempdir()) / "groc-config-tests"
    return Settings(
        home=root / "home",
        bridge_host="127.0.0.1",
        bridge_port=port,
        bridge_log=root / "bridge.log",
        grok_bin="/usr/local/bin/grok",
        default_model=model,
        reasoning_effort="high",
        auth_home=root / "auth",
        codex_bin="codex",
        repo_url="https://github.com/matrixtsex/groc.git",
        update_dir=root / "src",
        upstream_model="gpt-5.6-sol",
        backend_base_url="https://chatgpt.com/backend-api/codex",
        refresh_url="https://auth.openai.com/oauth/token",
        auto_login=True,
        device_auth=False,
        raw_stderr=False,
        allow_untrusted_backend=False,
    )


class GrokConfigTests(unittest.TestCase):
    def test_render_uses_runtime_bridge_port_and_default_model(self) -> None:
        rendered = render_grok_config(settings(port=11436, model="gpt-5.4"))

        self.assertIn('default = "gpt-5.4"', rendered)
        self.assertIn('base_url = "http://127.0.0.1:11436/v1"', rendered)
        self.assertIn('fork_secondary_model = "gpt-5.4"', rendered)

    def test_render_matches_current_grok_and_codex_config_contracts(self) -> None:
        rendered = render_grok_config(settings())

        self.assertIn('[subagents]\nenabled = true\n\n[features]', rendered)
        self.assertNotIn("default_model =", rendered)
        self.assertNotIn("gpt-5.3", rendered)
        self.assertIn('[model."gpt-5.6-sol"]', rendered)
        self.assertIn('[model."gpt-5.6-terra"]', rendered)
        self.assertIn('[model."gpt-5.6-luna"]', rendered)
        self.assertEqual(rendered.count(BEGIN_MANAGED_MODELS), 1)
        self.assertEqual(rendered.count(END_MANAGED_MODELS), 1)
        self.assertEqual(rendered.count("context_window = 272000"), len(MODEL_CATALOG))
        self.assertEqual(rendered.count("supports_reasoning_effort = true"), len(MODEL_CATALOG))

    def test_install_time_config_matches_runtime_defaults(self) -> None:
        static_config = (Path(__file__).parents[1] / "config" / "groc.config.toml").read_text(
            encoding="utf-8"
        )

        self.assertIn('default = "gpt-5.6-sol"', static_config)
        self.assertIn('fork_secondary_model = "gpt-5.6-sol"', static_config)
        self.assertNotIn("default_model =", static_config)
        self.assertNotIn("gpt-5.3", static_config)
        self.assertEqual(static_config.count(BEGIN_MANAGED_MODELS), 1)
        self.assertEqual(static_config.count(END_MANAGED_MODELS), 1)
        self.assertEqual(static_config.count("context_window = 272000"), len(MODEL_CATALOG))
        self.assertEqual(
            static_config.count("supports_reasoning_effort = true"),
            len(MODEL_CATALOG),
        )

    def test_write_grok_config_creates_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_settings = settings()
            config_settings = replace(config_settings, home=Path(directory) / "missing" / "home")

            write_grok_config(config_settings)

            self.assertTrue((config_settings.home / "config.toml").is_file())

    def test_new_config_escapes_control_characters_and_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_settings = replace(
                settings(),
                home=Path(directory),
                default_model="model\nwith-control-character",
            )

            write_grok_config(config_settings)

            with (config_settings.home / "config.toml").open("rb") as handle:
                parsed = tomllib.load(handle)
            self.assertEqual(parsed["models"]["default"], "model\nwith-control-character")

    def test_invalid_generated_config_is_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_settings = replace(settings(), home=Path(directory), default_model="\ud800")

            with self.assertRaisesRegex(GrocError, "file not created"):
                write_grok_config(config_settings)

            self.assertFalse((config_settings.home / "config.toml").exists())

    def test_reconcile_preserves_user_settings_and_custom_models(self) -> None:
        original = """# personal comment
[models]
default = "gpt-5.4"

[model."gpt-5.6-sol"]
base_url = "http://old.invalid/v1"

[model."my-model"]
base_url = "https://example.invalid/v1"

[ui]
screen_mode = "minimal"

[hints]
new_session_worktree_mode = "always"
"""

        reconciled = reconcile_grok_config(original, settings(port=12000))

        self.assertIn("# personal comment", reconciled)
        self.assertIn('default = "gpt-5.4"', reconciled)
        self.assertIn('[model."my-model"]\nbase_url = "https://example.invalid/v1"', reconciled)
        self.assertIn('screen_mode = "minimal"', reconciled)
        self.assertIn('new_session_worktree_mode = "always"', reconciled)
        self.assertIn('base_url = "http://127.0.0.1:12000/v1"', reconciled)
        self.assertNotIn("old.invalid", reconciled)

    def test_reconcile_migrates_all_historical_model_tables(self) -> None:
        original = """[models]
default = "gpt-5.6-sol"

[model."gpt-5.3"]
base_url = "http://old.invalid/v1"

[model."gpt-5.3-spark"]
base_url = "http://old.invalid/v1"

[model.grok-build]
base_url = "http://old.invalid/v1"

[ui]
compact_mode = true
"""

        reconciled = reconcile_grok_config(original, settings())

        self.assertNotIn("gpt-5.3", reconciled)
        self.assertNotIn("old.invalid", reconciled)
        self.assertIn('[model."grok-build"]', reconciled)
        self.assertIn("compact_mode = true", reconciled)
        self.assertEqual(reconciled.count(BEGIN_MANAGED_MODELS), 1)

    def test_legacy_migration_preserves_comments_before_unrelated_tables(self) -> None:
        original = """[model."gpt-5.4"]
base_url = "http://old.invalid/v1"

# IMPORTANT USER COMMENT FOR UI
[ui]
compact_mode = true
"""

        reconciled = reconcile_grok_config(original, settings())

        self.assertIn("# IMPORTANT USER COMMENT FOR UI\n[ui]", reconciled)
        self.assertNotIn("old.invalid", reconciled)

    def test_reconcile_preserves_multiline_values_with_structural_text(self) -> None:
        original = "\n".join(
            [
                "[notes]",
                'basic = """',
                "basic prefix",
                '[model."gpt-5.4"]',
                BEGIN_MANAGED_MODELS,
                'two quotes: ""',
                'escaped delimiter: \\""" still basic',
                END_MANAGED_MODELS,
                'basic closing quote""""',
                "literal = '''",
                "literal prefix",
                '[model."gpt-5.3"]',
                BEGIN_MANAGED_MODELS,
                "two quotes: ''",
                END_MANAGED_MODELS,
                "literal closing quotes'''''",
                "",
            ]
        )
        parsed_original = tomllib.loads(original)

        reconciled = reconcile_grok_config(original, settings())

        self.assertTrue(reconciled.startswith(original))
        self.assertEqual(tomllib.loads(reconciled)["notes"], parsed_original["notes"])
        self.assertEqual(reconcile_grok_config(reconciled, settings()), reconciled)

    def test_real_markers_coexist_with_marker_text_inside_multiline_string(self) -> None:
        original = (
            render_grok_config(settings())
            + "\n[notes]\nmarkers = \"\"\"\n"
            + BEGIN_MANAGED_MODELS
            + "\n"
            + END_MANAGED_MODELS
            + '\n\"\"\"\n'
        )

        reconciled = reconcile_grok_config(original, settings(port=12003))

        self.assertEqual(reconciled.count(BEGIN_MANAGED_MODELS), 2)
        self.assertEqual(reconciled.count(END_MANAGED_MODELS), 2)
        self.assertEqual(tomllib.loads(reconciled)["notes"]["markers"], tomllib.loads(original)["notes"]["markers"])
        self.assertIn('base_url = "http://127.0.0.1:12003/v1"', reconciled)
        self.assertEqual(reconcile_grok_config(reconciled, settings(port=12003)), reconciled)

    def test_marker_text_in_single_line_strings_and_prose_comments_is_user_content(self) -> None:
        original = "\n".join(
            [
                f"# marker documentation: {BEGIN_MANAGED_MODELS}",
                "[notes]",
                f'basic = "{BEGIN_MANAGED_MODELS}"',
                f"literal = '{END_MANAGED_MODELS}'",
                f"enabled = true  {BEGIN_MANAGED_MODELS} with inline context",
                "",
            ]
        )
        parsed_original = tomllib.loads(original)

        reconciled = reconcile_grok_config(original, settings())

        self.assertTrue(reconciled.startswith(original))
        self.assertEqual(tomllib.loads(reconciled)["notes"], parsed_original["notes"])

    def test_legacy_owned_multiline_value_is_removed_as_one_value(self) -> None:
        original = "\n".join(
            [
                '[model."gpt-5.4"]',
                'description = """',
                "owned model text",
                '[model."my-model"]',
                'base_url = "https://must-not-survive.invalid/v1"',
                '"""',
                "literal = '''",
                "[ui.fake]",
                "'''",
                "matrix = [",
                "  [1, 2]",
                "]",
                'base_url = "http://old.invalid/v1"',
                "",
                "# IMPORTANT USER COMMENT FOR UI",
                "[ui]",
                "compact_mode = true",
                "",
            ]
        )

        reconciled = reconcile_grok_config(original, settings())

        self.assertNotIn("owned model text", reconciled)
        self.assertNotIn("must-not-survive.invalid", reconciled)
        self.assertNotIn("[ui.fake]", reconciled)
        self.assertNotIn("[1, 2]", reconciled)
        self.assertNotIn("old.invalid", reconciled)
        self.assertIn("# IMPORTANT USER COMMENT FOR UI\n[ui]", reconciled)
        self.assertTrue(tomllib.loads(reconciled)["ui"]["compact_mode"])

    def test_reconcile_replaces_only_existing_managed_block(self) -> None:
        original = render_grok_config(settings()) + "\n[marketplace]\nupdated = true\n"

        reconciled = reconcile_grok_config(original, settings(port=12001))
        second = reconcile_grok_config(reconciled, settings(port=12001))

        self.assertIn('base_url = "http://127.0.0.1:12001/v1"', reconciled)
        self.assertIn("[marketplace]\nupdated = true", reconciled)
        self.assertEqual(second, reconciled)

    def test_invalid_toml_and_markers_are_rejected_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_settings = replace(settings(), home=Path(directory))
            path = config_settings.home / "config.toml"
            invalid = "[ui\ncompact_mode = true\n"
            path.write_text(invalid, encoding="utf-8")

            with self.assertRaisesRegex(GrocError, "refusing to overwrite"):
                write_grok_config(config_settings)

            self.assertEqual(path.read_text(encoding="utf-8"), invalid)

            bad_markers = f"{BEGIN_MANAGED_MODELS}\n[ui]\nyolo = false\n"
            path.write_text(bad_markers, encoding="utf-8")
            with self.assertRaisesRegex(GrocError, "managed-model markers"):
                write_grok_config(config_settings)
            self.assertEqual(path.read_text(encoding="utf-8"), bad_markers)

    def test_malformed_reserved_marker_comments_are_rejected_without_writing(self) -> None:
        malformed_markers = [
            f"  {BEGIN_MANAGED_MODELS} extra text \t\n[ui]\nyolo = false\n",
            f"\t{END_MANAGED_MODELS}# extra text\n[ui]\nyolo = false\n",
            f"values = [\n  {BEGIN_MANAGED_MODELS} extra text\n  1,\n]\n",
        ]
        for malformed in malformed_markers:
            with self.subTest(
                marker=malformed.splitlines()[0]
            ), tempfile.TemporaryDirectory() as directory:
                config_settings = replace(settings(), home=Path(directory))
                path = config_settings.home / "config.toml"
                path.write_text(malformed, encoding="utf-8")

                with self.assertRaisesRegex(GrocError, "malformed") as caught:
                    write_grok_config(config_settings)

                self.assertEqual(caught.exception.status, 2)
                self.assertEqual(path.read_text(encoding="utf-8"), malformed)

    def test_duplicate_and_reversed_exact_markers_are_rejected(self) -> None:
        invalid_markers = {
            "duplicate": "\n".join(
                [BEGIN_MANAGED_MODELS, BEGIN_MANAGED_MODELS, END_MANAGED_MODELS, ""]
            ),
            "reversed": "\n".join([END_MANAGED_MODELS, BEGIN_MANAGED_MODELS, ""]),
        }
        for error, original in invalid_markers.items():
            with self.subTest(error=error), self.assertRaisesRegex(GrocError, error) as caught:
                reconcile_grok_config(original, settings())

            self.assertEqual(caught.exception.status, 2)

    def test_indented_markers_with_trailing_horizontal_whitespace_are_exact(self) -> None:
        original = "\n".join(
            [
                f" \t{BEGIN_MANAGED_MODELS}\t ",
                '[model."gpt-5.4"]',
                'base_url = "http://old.invalid/v1"',
                f"\t{END_MANAGED_MODELS} \t",
                "[ui]",
                "yolo = false",
                "",
            ]
        )

        reconciled = reconcile_grok_config(original, settings(port=12004))

        self.assertNotIn("old.invalid", reconciled)
        self.assertIn('base_url = "http://127.0.0.1:12004/v1"', reconciled)
        self.assertIn("[ui]\nyolo = false", reconciled)

    def test_write_preserves_config_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "shared.toml"
            target.write_text(render_grok_config(settings()), encoding="utf-8")
            home = root / "home"
            home.mkdir()
            link = home / "config.toml"
            link.symlink_to(target)
            config_settings = replace(settings(), home=home, bridge_port=12002)

            write_grok_config(config_settings)

            self.assertTrue(link.is_symlink())
            self.assertIn('base_url = "http://127.0.0.1:12002/v1"', target.read_text(encoding="utf-8"))

    def test_write_atomically_replaces_config_and_preserves_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_settings = replace(settings(), home=Path(directory))
            path = config_settings.home / "config.toml"
            path.write_text(render_grok_config(settings()), encoding="utf-8")
            path.chmod(0o640)
            original_inode = path.stat().st_ino
            config_settings = replace(config_settings, bridge_port=12005)

            write_grok_config(config_settings)

            self.assertNotEqual(path.stat().st_ino, original_inode)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertIn('base_url = "http://127.0.0.1:12005/v1"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
