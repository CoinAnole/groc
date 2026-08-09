from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class InstallTests(unittest.TestCase):
    def test_reinstall_preserves_both_configuration_files(self) -> None:
        repo = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            env = {**os.environ, "HOME": str(home)}
            subprocess.run([str(repo / "bin" / "install")], check=True, env=env, capture_output=True, text=True)

            grok_config = home / ".groc" / "config.toml"
            launcher_config = home / ".groc" / "groc.toml"
            grok_config.write_text("[ui]\ncompact_mode = true\n", encoding="utf-8")
            launcher_config.write_text("bridge_port = 12000\n", encoding="utf-8")

            subprocess.run([str(repo / "bin" / "install")], check=True, env=env, capture_output=True, text=True)

            self.assertEqual(grok_config.read_text(encoding="utf-8"), "[ui]\ncompact_mode = true\n")
            self.assertEqual(launcher_config.read_text(encoding="utf-8"), "bridge_port = 12000\n")


if __name__ == "__main__":
    unittest.main()
