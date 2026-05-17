from __future__ import annotations

from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
STREAMLIT_APP = ROOT_DIR / "streamlit_app.py"


class StreamlitAppStaticTests(unittest.TestCase):
    def test_streamlit_app_uses_current_iframe_api(self) -> None:
        source = STREAMLIT_APP.read_text(encoding="utf-8")

        self.assertNotIn("streamlit.components.v1", source)
        self.assertNotIn("components.html", source)

    def test_streamlit_app_does_not_import_missing_bool_helper(self) -> None:
        source = STREAMLIT_APP.read_text(encoding="utf-8")

        self.assertNotIn("from src.db.models import bool_from_db", source)


if __name__ == "__main__":
    unittest.main()
