from __future__ import annotations

import unittest

from config import Settings


class SettingsTests(unittest.TestCase):
    def test_x_auto_publish_enabled_reads_env_alias(self) -> None:
        settings = Settings(_env_file=None, X_AUTO_PUBLISH_ENABLED="true")

        self.assertTrue(settings.x_auto_publish_enabled)

    def test_x_publish_password_reads_env_alias(self) -> None:
        settings = Settings(_env_file=None, X_PUBLISH_PASSWORD="secret")

        self.assertEqual(settings.x_publish_password, "secret")

    def test_public_viewer_mode_reads_env_alias(self) -> None:
        settings = Settings(_env_file=None, PUBLIC_VIEWER_MODE="true")

        self.assertTrue(settings.public_viewer_mode)


if __name__ == "__main__":
    unittest.main()
