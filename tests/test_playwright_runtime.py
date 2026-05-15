from __future__ import annotations

import sys
import unittest

from config import settings
from src.collectors.playwright_runtime import chromium_launch_options


class PlaywrightRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_chromium = settings.playwright_chromium_executable

    def tearDown(self) -> None:
        settings.playwright_chromium_executable = self.original_chromium

    def test_uses_configured_chromium_executable(self) -> None:
        settings.playwright_chromium_executable = sys.executable

        options = chromium_launch_options(headless=True)

        self.assertTrue(options["headless"])
        self.assertEqual(options["executable_path"], sys.executable)
        self.assertIn("--no-sandbox", options["args"])


if __name__ == "__main__":
    unittest.main()
