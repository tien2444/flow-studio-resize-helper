import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from autoresize_tool.naming import asset_file_name, initial_asset_metadata


class NamingRuleTests(unittest.TestCase):
    def setUp(self):
        self.metadata = initial_asset_metadata(
            "Theme_APP_A1B2C3D4E5F6G7_EN_W2W42.mp4",
            datetime(2026, 10, 4),
        )

    def test_os_name(self):
        self.assertEqual(
            asset_file_name(self.metadata, "916", 30, "OS"),
            "Theme_APP_A1B2C3D4E5F6G7_EN_OS_916_30s_261004.mp4",
        )

    def test_auto_name(self):
        self.assertEqual(
            asset_file_name(self.metadata, "11", 15, "AUTO"),
            "Theme_APP_A1B2C3D4E5F6G7_EN_AT_11_15s_261004.mp4",
        )

    def test_w2w_variants(self):
        self.assertIn("_W2W42_916_30s_261004.mp4", asset_file_name(self.metadata, "916", 30, "W2W"))
        self.assertIn("_W2W42_OS_916_30s_261004.mp4", asset_file_name(self.metadata, "916", 30, "W2WOS"))


if __name__ == "__main__":
    unittest.main()
