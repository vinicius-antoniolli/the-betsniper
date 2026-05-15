from __future__ import annotations

import unittest

from src.integrations.x_api import XCredentials, XPostError, XPostResult, publish_x_posts


class XApiTests(unittest.TestCase):
    def test_credentials_report_missing_env_names(self) -> None:
        credentials = XCredentials(None, "secret", "", "token-secret")

        self.assertEqual(credentials.missing_fields(), ["X_API_KEY", "X_ACCESS_TOKEN"])

    def test_publish_posts_waits_between_successful_posts(self) -> None:
        credentials = XCredentials("key", "secret", "token", "token-secret")
        sent: list[str] = []
        sleeps: list[float] = []

        def sender(text: str, _credentials: XCredentials, _base_url: str) -> XPostResult:
            sent.append(text)
            return XPostResult(post_id=f"id-{len(sent)}", text=text)

        results = publish_x_posts(
            ["post 1", "post 2", "post 3"],
            credentials,
            delay_seconds=60,
            post_fn=sender,
            sleep_fn=sleeps.append,
        )

        self.assertEqual([result.post_id for result in results], ["id-1", "id-2", "id-3"])
        self.assertEqual(sent, ["post 1", "post 2", "post 3"])
        self.assertEqual(sleeps, [60, 60])

    def test_publish_rejects_posts_over_limit_before_sending(self) -> None:
        credentials = XCredentials("key", "secret", "token", "token-secret")

        with self.assertRaisesRegex(XPostError, "acima do limite"):
            publish_x_posts(["123456"], credentials, max_chars=5, post_fn=lambda *_args: None)


if __name__ == "__main__":
    unittest.main()
