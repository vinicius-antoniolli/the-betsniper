from __future__ import annotations

import unittest

from config import settings
from src.collectors.betfair_auth import betfair_context_options, betfair_credentials, betfair_geolocation


class BetfairAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = {
            "betfair_username": settings.betfair_username,
            "betfair_password": settings.betfair_password,
            "betfair_allow_geolocation": settings.betfair_allow_geolocation,
            "betfair_geolocation_latitude": settings.betfair_geolocation_latitude,
            "betfair_geolocation_longitude": settings.betfair_geolocation_longitude,
            "betfair_geolocation_accuracy": settings.betfair_geolocation_accuracy,
            "betfair_geolocation_jitter_meters": settings.betfair_geolocation_jitter_meters,
        }

    def tearDown(self) -> None:
        for key, value in self.original.items():
            setattr(settings, key, value)

    def test_credentials_require_user_and_password(self) -> None:
        settings.betfair_username = "user@example.com"
        settings.betfair_password = ""
        self.assertIsNone(betfair_credentials())

        settings.betfair_password = "secret"
        self.assertEqual(betfair_credentials(), ("user@example.com", "secret"))

    def test_geolocation_uses_configured_coordinates(self) -> None:
        settings.betfair_geolocation_latitude = "-23,55"
        settings.betfair_geolocation_longitude = "-46.63"
        settings.betfair_geolocation_accuracy = 50
        settings.betfair_geolocation_jitter_meters = 0

        self.assertEqual(
            betfair_geolocation(),
            {"latitude": -23.55, "longitude": -46.63, "accuracy": 50.0},
        )

    def test_geolocation_requires_valid_pair(self) -> None:
        settings.betfair_geolocation_latitude = "-23.55"
        settings.betfair_geolocation_longitude = ""
        with self.assertLogs("src.collectors.betfair_auth", level="WARNING"):
            self.assertIsNone(betfair_geolocation())

        settings.betfair_geolocation_longitude = "-190"
        with self.assertLogs("src.collectors.betfair_auth", level="WARNING"):
            self.assertIsNone(betfair_geolocation())

    def test_context_grants_geolocation_permission(self) -> None:
        settings.betfair_allow_geolocation = True
        settings.betfair_geolocation_latitude = "-23.55"
        settings.betfair_geolocation_longitude = "-46.63"
        settings.betfair_geolocation_jitter_meters = 0

        options = betfair_context_options()

        self.assertEqual(options["permissions"], ["geolocation"])
        self.assertEqual(options["geolocation"]["latitude"], -23.55)
        self.assertEqual(options["geolocation"]["longitude"], -46.63)

    def test_geolocation_jitter_stays_within_30_meters(self) -> None:
        settings.betfair_geolocation_latitude = "-27.236033"
        settings.betfair_geolocation_longitude = "-48.626439"
        settings.betfair_geolocation_jitter_meters = 30

        point = betfair_geolocation()

        self.assertIsNotNone(point)
        assert point is not None
        lat_meters = (point["latitude"] + 27.236033) * 111_320
        lon_meters = (point["longitude"] + 48.626439) * 111_320 * 0.889
        self.assertLessEqual((lat_meters**2 + lon_meters**2) ** 0.5, 31)


if __name__ == "__main__":
    unittest.main()
