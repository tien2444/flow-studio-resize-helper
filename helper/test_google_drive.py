import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from google_drive import GoogleDriveUploader


def drive_error(reason="userRateLimitExceeded", message="User rate limit exceeded."):
    body = json.dumps({
        "error": {
            "code": 403,
            "message": message,
            "errors": [{"reason": reason, "message": message}],
        }
    }).encode()
    return urllib.error.HTTPError(
        "https://www.googleapis.com/drive/v3/files",
        403,
        "Forbidden",
        {},
        io.BytesIO(body),
    )


class GoogleDriveRetryTests(unittest.TestCase):
    def test_user_rate_limit_retries_then_succeeds(self):
        response = mock.MagicMock(status=200)
        with mock.patch(
            "google_drive.urllib.request.urlopen",
            side_effect=[drive_error(), drive_error(), response],
        ) as urlopen, mock.patch("google_drive.time.sleep") as sleep:
            result = GoogleDriveUploader()._open(mock.sentinel.request)

        self.assertIs(result, response)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])

    def test_exhausted_rate_limit_has_safe_friendly_message(self):
        with mock.patch(
            "google_drive.urllib.request.urlopen",
            side_effect=[drive_error() for _ in range(5)],
        ), mock.patch("google_drive.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "giới hạn tốc độ") as raised:
                GoogleDriveUploader()._open(mock.sentinel.request)

        self.assertIn("file vẫn an toàn trên máy", str(raised.exception))
        self.assertNotIn("userRateLimitExceeded", str(raised.exception))

    def test_permission_error_is_not_retried(self):
        error = drive_error("insufficientFilePermissions", "The user does not have permission.")
        with mock.patch(
            "google_drive.urllib.request.urlopen", side_effect=error
        ) as urlopen, mock.patch("google_drive.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                GoogleDriveUploader()._open(mock.sentinel.request)

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
