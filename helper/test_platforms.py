import ntpath
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from autoresize_tool.platform_paths import (
    configured_path_for_platform,
    default_resize_output_root,
    local_shared_drives_root,
)


class PlatformPathTests(unittest.TestCase):
    def test_windows_output_stays_in_current_users_videos_folder(self):
        self.assertEqual(
            default_resize_output_root("win32", r"C:\Users\Editor"),
            ntpath.join(r"C:\Users\Editor", "Videos", "Flow Studio", "Exports"),
        )

    def test_windows_drive_discovery_is_not_fixed_to_g_drive(self):
        shared = ntpath.join("Z:\\", "Bộ nhớ dùng chung")
        canonical = ntpath.join(
            shared, "iKame Apps - Creative", "Creative Asset - MKT"
        )

        def exists(path):
            return path == shared or path == canonical

        with mock.patch("autoresize_tool.platform_paths.safe_is_dir", side_effect=exists):
            self.assertEqual(local_shared_drives_root("win32"), shared)

    def test_windows_catalog_path_uses_discovered_drive_mount(self):
        self.assertEqual(
            configured_path_for_platform(
                r"G:\Shared drives\iKame Apps - Creative\Creative Asset - MKT\Clean",
                "win32",
                r"Z:\Bộ nhớ dùng chung",
            ),
            r"Z:\Bộ nhớ dùng chung\iKame Apps - Creative\Creative Asset - MKT\Clean",
        )


if __name__ == "__main__":
    unittest.main()
