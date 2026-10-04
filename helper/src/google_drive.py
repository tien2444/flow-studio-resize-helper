"""Google Drive API fallback for macOS File Provider copy failures."""
import json
import mimetypes
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from autoresize_tool.platform_paths import application_data_dir


FOLDER_MIME = "application/vnd.google-apps.folder"
SUPPORT = Path(application_data_dir())
CLIENT_FILE = Path(os.environ.get("GOOGLE_OAUTH_CLIENT_FILE", SUPPORT / "oauth_client.json"))
TOKEN_FILE = Path(os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", SUPPORT / "drive_oauth_token.json"))
DRIVE_NAME = "iKame Apps - Creative"
CREATIVE_ROOT_NAME = "Creative Asset - MKT"
RATE_LIMIT_REASONS = {
    "rateLimitExceeded",
    "sharingRateLimitExceeded",
    "userRateLimitExceeded",
}


def _quoted(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveUploader:
    def __init__(self):
        self._token = ""
        self._expires_at = 0
        self._folder_cache = {}

    @property
    def available(self):
        return CLIENT_FILE.is_file() and TOKEN_FILE.is_file()

    def _access_token(self):
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        raw_client = json.loads(CLIENT_FILE.read_text(encoding="utf8"))
        client = raw_client.get("installed") or raw_client.get("web") or raw_client
        saved = json.loads(TOKEN_FILE.read_text(encoding="utf8"))
        body = urllib.parse.urlencode({
            "client_id": client["client_id"], "client_secret": client["client_secret"],
            "refresh_token": saved["refresh_token"], "grant_type": "refresh_token",
        }).encode()
        request = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
        with urllib.request.urlopen(request, timeout=30) as response:
            token = json.load(response)
        self._token = token["access_token"]
        self._expires_at = time.time() + int(token.get("expires_in", 3600))
        return self._token

    @staticmethod
    def _http_error(error):
        detail = error.read().decode("utf8", "replace")[-800:]
        reasons = set()
        message = ""
        try:
            payload = json.loads(detail)
            body = payload.get("error", payload)
            message = str(body.get("message", ""))
            reasons.update(
                str(item.get("reason", ""))
                for item in body.get("errors", [])
                if isinstance(item, dict)
            )
            if body.get("status"):
                reasons.add(str(body["status"]))
        except (TypeError, ValueError, AttributeError):
            pass
        return detail, reasons, message

    @staticmethod
    def _retry_delay(error, attempt):
        retry_after = error.headers.get("Retry-After") if error.headers else None
        try:
            return min(max(float(retry_after), 1), 30)
        except (TypeError, ValueError):
            return min(2 ** (attempt + 1), 16)

    def _open(self, request, timeout=60, accepted=(200, 201)):
        for attempt in range(5):
            try:
                response = urllib.request.urlopen(request, timeout=timeout)
                if response.status not in accepted:
                    raise RuntimeError(f"Google Drive returned HTTP {response.status}.")
                return response
            except urllib.error.HTTPError as error:
                if error.code in accepted:
                    return error
                detail, reasons, message = self._http_error(error)
                rate_limited = error.code == 429 or bool(reasons & RATE_LIMIT_REASONS) or (
                    error.code == 403 and "rate limit" in (message or detail).lower()
                )
                retryable = rate_limited or error.code in (408, 500, 502, 503, 504)
                if not retryable or attempt == 4:
                    if rate_limited:
                        raise RuntimeError(
                            "Google Drive đang giới hạn tốc độ. Tool đã tự thử lại; "
                            "file vẫn an toàn trên máy. Hãy thử upload Drive lại sau ít phút."
                        ) from error
                    raise RuntimeError(f"Google Drive returned HTTP {error.code}: {detail}") from error
                time.sleep(self._retry_delay(error, attempt))
                continue
            except (TimeoutError, urllib.error.URLError) as error:
                if attempt == 4:
                    raise RuntimeError(f"Cannot reach Google Drive: {error}") from error
            time.sleep(min(2 ** attempt, 8))

    def _json(self, method, url, payload=None, timeout=60):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with self._open(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}

    def _children(self, drive_id, parents):
        def fetch_chunk(chunk):
            folders = []
            parent_query = " or ".join(f"'{_quoted(parent)}' in parents" for parent in chunk)
            page_token = ""
            while True:
                params = {
                    "corpora": "drive", "driveId": drive_id,
                    "includeItemsFromAllDrives": "true", "supportsAllDrives": "true",
                    "q": f"mimeType='{FOLDER_MIME}' and trashed=false and ({parent_query})",
                    "pageSize": 1000, "fields": "nextPageToken,files(id,name,parents)",
                }
                if page_token:
                    params["pageToken"] = page_token
                data = self._json("GET", "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params))
                folders.extend(data.get("files", []))
                page_token = data.get("nextPageToken", "")
                if not page_token:
                    break
            return folders

        chunks = [parents[start:start + 20] for start in range(0, len(parents), 20)]
        if not chunks:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(chunks))) as pool:
            pages = list(pool.map(fetch_chunk, chunks))
        folders = []
        for page in pages:
            folders.extend(page)
        return folders

    def discover_targets(self):
        if not self.available:
            return {}
        drives = self._json("GET", "https://www.googleapis.com/drive/v3/drives?" + urllib.parse.urlencode({
            "pageSize": 100, "fields": "drives(id,name)",
        })).get("drives", [])
        matches = [drive for drive in drives if drive.get("name") == DRIVE_NAME]
        if len(matches) != 1:
            return {}
        drive_id = matches[0]["id"]
        roots = [folder for folder in self._children(drive_id, [drive_id]) if folder.get("name") == CREATIVE_ROOT_NAME]
        if len(roots) != 1:
            return {}
        apps = self._children(drive_id, [roots[0]["id"]])
        app_children = self._children(drive_id, [app["id"] for app in apps])
        by_parent = {}
        for folder in app_children:
            for parent in folder.get("parents", []):
                by_parent.setdefault(parent, {}).setdefault(folder["name"], []).append(folder)
        ads = {}
        for app in apps:
            matches = by_parent.get(app["id"], {}).get("Creative Ads", [])
            if len(matches) == 1:
                ads[matches[0]["id"]] = app
        ad_children = self._children(drive_id, list(ads))
        by_ads = {}
        for folder in ad_children:
            for parent in folder.get("parents", []):
                by_ads.setdefault(parent, {}).setdefault(folder["name"], []).append(folder)
        result = {}
        for ads_id, app in ads.items():
            children = by_ads.get(ads_id, {})
            videos, images = children.get("Video", []), children.get("Image", [])
            thumbnails = children.get("Thumbnail", [])
            if len(videos) != 1 or len(images) != 1 or len(thumbnails) > 1:
                continue
            result[app["name"]] = {
                "drive_id": drive_id, "video_folder_id": videos[0]["id"],
                "image_folder_id": images[0]["id"],
                "thumbnail_folder_id": thumbnails[0]["id"] if thumbnails else images[0]["id"],
            }
        return result

    def _find(self, drive_id, parent_id, name, mime_type=""):
        query = f"trashed=false and '{_quoted(parent_id)}' in parents and name='{_quoted(name)}'"
        if mime_type:
            query += f" and mimeType='{mime_type}'"
        params = {
            "corpora": "drive", "driveId": drive_id, "includeItemsFromAllDrives": "true",
            "supportsAllDrives": "true", "q": query, "pageSize": 100,
            "fields": "files(id,name,mimeType,size)",
        }
        return self._json("GET", "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params)).get("files", [])

    def _ensure_folder(self, drive_id, parent_id, name):
        key = (parent_id, name)
        if key in self._folder_cache:
            return self._folder_cache[key]
        matches = self._find(drive_id, parent_id, name, FOLDER_MIME)
        if len(matches) > 1:
            raise RuntimeError(f"Google Drive has duplicate folder {name!r}.")
        if matches:
            folder_id = matches[0]["id"]
        else:
            folder_id = self._json("POST", "https://www.googleapis.com/drive/v3/files?supportsAllDrives=true&fields=id", {
                "name": name, "mimeType": FOLDER_MIME, "parents": [parent_id],
            })["id"]
        self._folder_cache[key] = folder_id
        return folder_id

    def upload(self, source, drive_id, parent_id, folder_parts, filename, cancel):
        if not self.available or not drive_id or not parent_id:
            return ""
        for part in folder_parts:
            if cancel.is_set():
                raise InterruptedError("Cancelled.")
            parent_id = self._ensure_folder(drive_id, parent_id, str(part))
        source_path = Path(source)
        source_size = source_path.stat().st_size
        stem, extension = os.path.splitext(filename)
        candidate, copy_number = filename, 2
        existing = self._find(drive_id, parent_id, candidate)
        if len(existing) == 1 and int(existing[0].get("size", -1)) == source_size:
            return f"https://drive.google.com/open?id={existing[0]['id']}"
        while existing:
            candidate = f"{stem}_{copy_number}{extension}"
            copy_number += 1
            existing = self._find(drive_id, parent_id, candidate)
        metadata = json.dumps({"name": candidate, "parents": [parent_id]}).encode()
        request = urllib.request.Request(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true&fields=id,name",
            data=metadata,
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json; charset=utf-8",
                "X-Upload-Content-Type": mimetypes.guess_type(candidate)[0] or "application/octet-stream",
                "X-Upload-Content-Length": str(source_path.stat().st_size),
            }, method="POST",
        )
        with self._open(request) as response:
            location = response.headers.get("Location")
        if not location:
            raise RuntimeError("Google Drive did not start the upload session.")
        total, offset, result = source_path.stat().st_size, 0, {}
        with source_path.open("rb") as stream:
            while offset < total:
                if cancel.is_set():
                    raise InterruptedError("Cancelled.")
                chunk = stream.read(min(8 * 1024 * 1024, total - offset))
                end = offset + len(chunk) - 1
                put = urllib.request.Request(location, data=chunk, headers={
                    "Content-Length": str(len(chunk)), "Content-Range": f"bytes {offset}-{end}/{total}",
                }, method="PUT")
                with self._open(put, timeout=120, accepted=(200, 201, 308)) as response:
                    if response.status in (200, 201):
                        result = json.loads(response.read() or b"{}")
                offset = end + 1
        if not result.get("id"):
            raise RuntimeError("Google Drive upload did not finish.")
        return f"https://drive.google.com/open?id={result['id']}"
