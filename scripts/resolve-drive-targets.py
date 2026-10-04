#!/usr/bin/env python3
"""Resolve the local Auto Resize target catalog to Google Drive folder IDs.

Credentials are read from the user's AutoResizeTool support directory. Only
folder IDs and names are written into the repository; OAuth secrets never are.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.parse
import urllib.error
import urllib.request


SUPPORT = pathlib.Path.home() / "Library/Application Support/AutoResizeTool"
CLIENT_FILE = pathlib.Path(os.environ.get("GOOGLE_OAUTH_CLIENT_FILE", SUPPORT / "oauth_client.json"))
TOKEN_FILE = pathlib.Path(os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", SUPPORT / "drive_oauth_token.json"))
REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
LOCAL_OUTPUT = REPOSITORY / "lib/processor-targets.json"
DRIVE_OUTPUT = REPOSITORY / "lib/processor-drive-targets.json"
DRIVE_NAME = os.environ.get("GOOGLE_SHARED_DRIVE", "iKame Apps - Creative")
CREATIVE_ROOT_NAME = "Creative Asset - MKT"
WINDOWS_SHARED_ROOT = rf"G:\Shared drives\{DRIVE_NAME}\{CREATIVE_ROOT_NAME}"


def request_json(url: str, access_token: str):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (ConnectionError, TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def access_token() -> str:
    raw_client = json.loads(CLIENT_FILE.read_text())
    client = raw_client.get("installed") or raw_client.get("web") or raw_client
    token = json.loads(TOKEN_FILE.read_text())
    body = urllib.parse.urlencode(
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    request = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def find_drive(token: str) -> dict:
    data = request_json(
        "https://www.googleapis.com/drive/v3/drives?"
        + urllib.parse.urlencode({"pageSize": 100, "fields": "drives(id,name)"}),
        token,
    )
    matches = [drive for drive in data.get("drives", []) if drive.get("name") == DRIVE_NAME]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one Shared Drive named {DRIVE_NAME!r}; found {len(matches)}")
    return matches[0]


def folder_children(token: str, drive_id: str, parents: list[str]) -> list[dict]:
    """List only the required branch instead of scanning a very large Drive."""
    folders: list[dict] = []
    for start in range(0, len(parents), 20):
        chunk = parents[start : start + 20]
        parent_query = " or ".join(f"'{parent}' in parents" for parent in chunk)
        page_token = ""
        while True:
            params = {
                "corpora": "drive",
                "driveId": drive_id,
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "q": f"mimeType='application/vnd.google-apps.folder' and trashed=false and ({parent_query})",
                "pageSize": 1000,
                "fields": "nextPageToken,files(id,name,parents)",
            }
            if page_token:
                params["pageToken"] = page_token
            data = request_json(
                "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(params),
                token,
            )
            folders.extend(data.get("files", []))
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break
    return folders


def main() -> None:
    token = access_token()
    drive = find_drive(token)
    children: dict[str, dict[str, list[dict]]] = {}

    def load(parents: list[str]) -> None:
        for folder in folder_children(token, drive["id"], parents):
            for parent in folder.get("parents", []):
                children.setdefault(parent, {}).setdefault(folder["name"], []).append(folder)

    def child(parent: str, name: str) -> str:
        matches = children.get(parent, {}).get(name, [])
        if len(matches) != 1:
            raise KeyError(f"{name!r} below {parent}: expected 1 folder, found {len(matches)}")
        return matches[0]["id"]

    def optional_child(parent: str, name: str) -> str | None:
        matches = children.get(parent, {}).get(name, [])
        if len(matches) > 1:
            raise KeyError(f"{name!r} below {parent}: expected at most 1 folder, found {len(matches)}")
        return matches[0]["id"] if matches else None

    root = drive["id"]
    load([root])
    creative = child(root, CREATIVE_ROOT_NAME)
    load([creative])
    app_folders = [
        folder
        for folders in children.get(creative, {}).values()
        for folder in folders
    ]
    duplicate_names = sorted(
        name for name, folders in children.get(creative, {}).items() if len(folders) != 1
    )
    if duplicate_names:
        raise RuntimeError(
            "Duplicate app folders below Creative Asset - MKT: " + ", ".join(duplicate_names)
        )
    app_folders.sort(key=lambda folder: folder["name"].casefold())
    app_ids = [folder["id"] for folder in app_folders]
    load(app_ids)
    ads_ids = [child(folder["id"], "Creative Ads") for folder in app_folders]
    load(ads_ids)
    image_ids = [child(ads_id, "Image") for ads_id in ads_ids]
    load(image_ids)
    previous_local = json.loads(LOCAL_OUTPUT.read_text()) if LOCAL_OUTPUT.exists() else {}
    local_resolved: dict[str, dict] = {}
    drive_resolved: dict[str, dict] = {}
    failures: dict[str, str] = {}
    for folder in app_folders:
        app = folder["name"]
        try:
            app_id = folder["id"]
            ads_id = child(app_id, "Creative Ads")
            video_id = child(ads_id, "Video")
            image_root_id = child(ads_id, "Image")
            # The replacement Shared Drive stores assets directly in Image.
            # Keep accepting the legacy Image/Input layout so the resolver can
            # safely be used during future migrations.
            image_id = optional_child(image_root_id, "Input") or image_root_id
            # The new layout also removed the separate Thumbnail directory.
            # Generated thumbnails are image assets, so store them in Image.
            thumbnail_id = optional_child(ads_id, "Thumbnail") or image_root_id
            thumbnail_folder = "Thumbnail" if optional_child(ads_id, "Thumbnail") else "Image"
            pinned = bool(previous_local.get(app, {}).get("pinned", False))
            app_root = WINDOWS_SHARED_ROOT + rf"\{app}\Creative Ads"
            local_resolved[app] = {
                "folder": app_root + r"\Video",
                "video_folder": app_root + r"\Video",
                "image_folder": app_root + r"\Image",
                "pinned": pinned,
                "thumbnail_folder": app_root + rf"\{thumbnail_folder}",
            }
            drive_resolved[app] = {
                "id": app,
                "name": app,
                "drive_id": drive["id"],
                "video_folder_id": video_id,
                "image_folder_id": image_id,
                "thumbnail_folder_id": thumbnail_id,
                "pinned": pinned,
            }
        except KeyError as error:
            failures[app] = str(error)

    payload = {
        "version": "2026-09-29",
        "shared_drive": {"id": drive["id"], "name": drive["name"]},
        "targets": drive_resolved,
    }
    if failures:
        print("Unresolved targets:")
        for app, reason in failures.items():
            print(f"- {app}: {reason}")
        raise SystemExit(2)
    local_temporary = LOCAL_OUTPUT.with_suffix(LOCAL_OUTPUT.suffix + ".tmp")
    local_temporary.write_text(json.dumps(local_resolved, ensure_ascii=False, indent=2) + "\n")
    local_temporary.replace(LOCAL_OUTPUT)
    drive_temporary = DRIVE_OUTPUT.with_suffix(DRIVE_OUTPUT.suffix + ".tmp")
    drive_temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    drive_temporary.replace(DRIVE_OUTPUT)
    print(
        f"Resolved {len(drive_resolved)}/{len(app_folders)} Drive app targets into "
        f"{LOCAL_OUTPUT} and {DRIVE_OUTPUT}"
    )


if __name__ == "__main__":
    main()
