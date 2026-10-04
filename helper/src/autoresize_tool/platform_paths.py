import glob
import ntpath
import os
import posixpath
import re
import sys
import unicodedata


APP_DIRECTORY_NAME = "AutoResizeTool"
CREATIVE_APPS_RELATIVE_PATH = (
    "iKame Apps - Creative",
    "Creative Asset - MKT",
)


def safe_is_dir(path):
    """Treat transient macOS File Provider errors as unavailable, not fatal."""
    try:
        return os.path.isdir(path)
    except OSError:
        return False


def application_data_dir(platform=None, home=None, local_app_data=None):
    platform = platform or sys.platform
    home = home or os.path.expanduser("~")
    if platform == "darwin":
        return posixpath.join(home, "Library", "Application Support", APP_DIRECTORY_NAME)
    if platform == "win32":
        return os.path.join(local_app_data or os.environ.get("LOCALAPPDATA") or home, APP_DIRECTORY_NAME)
    return os.path.join(
        os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"),
        APP_DIRECTORY_NAME,
    )


def default_resize_output_root(platform=None, home=None):
    platform = platform or sys.platform
    home = home or os.path.expanduser("~")
    if platform == "darwin":
        return posixpath.join(home, "Movies", APP_DIRECTORY_NAME, "Output")
    if platform == "win32":
        return ntpath.join(home, "Videos", "Flow Studio", "Exports")
    return os.path.join(home, "Videos", APP_DIRECTORY_NAME, "Output")


def mac_shared_drives_root(home=None, candidates=None):
    home = home or os.path.expanduser("~")
    if candidates is None:
        candidates = []
        drive_roots = glob.glob(os.path.join(home, "Library", "CloudStorage", "GoogleDrive-*"))
        shared_names = {
            "shared drives",
            "bộ nhớ dùng chung",
            "drives partagés",
            "freigegebene ablagen",
            "unidades compartidas",
        }
        for drive_root in drive_roots:
            try:
                entries = os.listdir(drive_root)
            except OSError:
                continue
            candidates.extend(
                os.path.join(drive_root, entry)
                for entry in entries
                if unicodedata.normalize("NFC", entry).casefold() in shared_names
            )
        candidates.extend([
            "/Volumes/GoogleDrive/Shared drives",
            "/Volumes/GoogleDrive/Shared Drives",
        ])
    existing = [path for path in candidates if safe_is_dir(path)]
    preferred = [
        path for path in existing
        if safe_is_dir(os.path.join(path, *CREATIVE_APPS_RELATIVE_PATH))
    ]
    return (preferred or existing or [""])[0]


def configured_path_for_platform(path, platform=None, shared_drives_root=""):
    """Translate catalog paths to this machine's Google Drive mount."""
    value = str(path or "").strip()
    platform = platform or sys.platform
    if not value or platform not in ("darwin", "win32"):
        return value

    normalized = value.replace("\\", "/")
    match = re.match(r"^[A-Za-z]:/Shared drives(?:/(.*))?$", normalized, re.IGNORECASE)
    if not match:
        return value
    shared_root = shared_drives_root or local_shared_drives_root(platform)
    if not shared_root:
        return value
    relative = match.group(1) or ""
    join = ntpath.join if platform == "win32" else posixpath.join
    return join(shared_root, *[part for part in relative.split("/") if part])


def local_shared_drives_root(platform=None, home=None):
    """Find Google Drive for Desktop's Shared drives mount on this machine."""
    platform = platform or sys.platform
    configured = os.environ.get("FLOW_SHARED_DRIVES_ROOT", "").strip()
    if configured and safe_is_dir(configured):
        return configured
    if platform == "darwin":
        return mac_shared_drives_root(home=home)
    if platform == "win32":
        shared_names = (
            "Shared drives",
            "Shared Drives",
            "Bộ nhớ dùng chung",
            "Drives partagés",
            "Freigegebene Ablagen",
            "Unidades compartidas",
        )
        # Drive for desktop lets each user choose a mount letter. Scan every
        # local drive instead of assuming G:, while still preferring a drive
        # that contains the canonical Creative folder.
        candidates = [
            ntpath.join(f"{letter}:\\", name)
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for name in shared_names
        ]
        existing = [path for path in candidates if safe_is_dir(path)]
        preferred = [
            path for path in existing
            if safe_is_dir(ntpath.join(path, *CREATIVE_APPS_RELATIVE_PATH))
        ]
        return (preferred or existing or [""])[0]
    return ""


def discover_local_app_targets(shared_drives_root="", platform=None, home=None):
    """Read app destinations from the canonical Drive for Desktop branch.

    This is intentionally read-only and shallow. Google Drive File Provider can
    deadlock while probing a deep placeholder, so listing the verified app root
    is the only filesystem operation here. Every app uses the canonical
    Creative Ads/Video and Creative Ads/Image layout. The server catalog still
    supplies legacy Image/Input and Thumbnail exceptions for existing apps.
    """
    shared_root = shared_drives_root or local_shared_drives_root(platform, home)
    if not shared_root:
        return {}
    apps_root = os.path.join(shared_root, *CREATIVE_APPS_RELATIVE_PATH)
    if not safe_is_dir(apps_root):
        return {}

    try:
        with os.scandir(apps_root) as entries:
            app_names = sorted(
                entry.name
                for entry in entries
                if not entry.name.startswith(".") and entry.is_dir(follow_symlinks=False)
            )
    except OSError:
        return {}

    discovered = {}
    for app_name in app_names:
        app_root = os.path.join(apps_root, app_name)
        creative_root = os.path.join(app_root, "Creative Ads")
        video_root = os.path.join(creative_root, "Video")
        image_root = os.path.join(creative_root, "Image")
        discovered[app_name] = {
            "folder": video_root,
            "video_folder": video_root,
            "image_folder": image_root,
            "thumbnail_folder": image_root,
            "pinned": False,
        }
    return discovered
