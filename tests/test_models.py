from __future__ import annotations

import unittest

from groc.models import DEFAULT_MODEL, DEFAULT_UPSTREAM_MODEL, MODEL_CATALOG, upstream_model


class ModelTests(unittest.TestCase):
    def test_catalog_matches_current_codex_model_ids(self) -> None:
        ids = [model.id for model in MODEL_CATALOG]

        self.assertEqual(
            ids,
            [
                "gpt-5.6-sol",
                "gpt-5.6-terra",
                "gpt-5.6-luna",
                "gpt-5.5",
                "gpt-5.4",
                "gpt-5.4-mini",
                "gpt-5.2",
                "grok-build",
            ],
        )
        self.assertTrue(all(model.context_window == 272_000 for model in MODEL_CATALOG))
        self.assertTrue(all(model.supports_reasoning_effort for model in MODEL_CATALOG))

    def test_defaults_and_upstream_fallback_use_gpt_5_6_sol(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "gpt-5.6-sol")
        self.assertEqual(DEFAULT_UPSTREAM_MODEL, "gpt-5.6-sol")
        self.assertEqual(upstream_model("grok-build"), "gpt-5.6-sol")
        self.assertEqual(upstream_model("grok-build", fallback="gpt-5.6-terra"), "gpt-5.6-terra")
        self.assertEqual(upstream_model("gpt-5.4"), "gpt-5.4")
        self.assertEqual(upstream_model("gpt-5.3"), "gpt-5.3")


if __name__ == "__main__":
    unittest.main()
