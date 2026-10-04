import os
import re
import shutil
import subprocess
from datetime import datetime

from .naming import sanitize_filename
from .storage import next_available_path


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
IMAGE_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")
IGNORED_LOCAL_IMAGE_FILES = (".ds_store", "thumbs.db", "desktop.ini")


def is_dated_folder_name(name):
    """Return True only for valid YYMM or YYMMDD folder names."""
    value = str(name or "").strip()
    if not re.fullmatch(r"\d{4}(?:\d{2})?", value):
        return False
    date_format = "%y%m" if len(value) == 4 else "%y%m%d"
    try:
        return datetime.strptime(value, date_format).strftime(date_format) == value
    except ValueError:
        return False


def validate_image_items_for_upload(image_items):
    """Reject source hierarchies that would nest old dates in a new date."""
    dated_folders = set()
    for item in image_items:
        relative_path = _safe_destination_relative(item)
        directory_parts = relative_path.replace("\\", "/").split("/")[:-1]
        dated_folders.update(
            part for part in directory_parts if is_dated_folder_name(part)
        )
    if dated_folders:
        raise ValueError(
            "Folder ảnh nguồn đang chứa folder ngày tháng: "
            + ", ".join(sorted(dated_folders))
            + ".\nHãy chọn trực tiếp folder Theme; tool sẽ tự tạo YYMM/YYMMDD mới."
        )
    return True


def validate_image_source_folders(folder_paths):
    """Validate a multi-theme selection before collecting its images."""
    normalized = [os.path.abspath(path) for path in folder_paths]
    theme_names = {}
    for path in normalized:
        theme_name = os.path.basename(os.path.normpath(path))
        if is_dated_folder_name(theme_name):
            raise ValueError(
                f"'{theme_name}' là folder ngày tháng. "
                "Hãy chọn trực tiếp một hoặc nhiều folder Theme."
            )
        name_key = os.path.normcase(theme_name)
        if name_key in theme_names:
            raise ValueError(
                f"Hai folder Theme đang trùng tên '{theme_name}'. "
                "Hãy đổi tên để tránh trộn ảnh."
            )
        theme_names[name_key] = path

    for index, first in enumerate(normalized):
        for second in normalized[index + 1:]:
            try:
                common = os.path.commonpath([first, second])
            except ValueError:
                continue
            if common in (first, second):
                raise ValueError(
                    "Không chọn đồng thời folder cha và folder con. "
                    "Hãy chỉ chọn các folder Theme ngang cấp."
                )
    return True


def dated_upload_root(destination_root, now=None):
    """Return YYMM/YYMMDD below a Drive asset destination."""
    timestamp = now or datetime.now()
    return os.path.join(
        destination_root,
        timestamp.strftime("%y%m"),
        timestamp.strftime("%y%m%d"),
    )


def thumbnail_folder_from_config(app_config):
    """Return the configured or conventional Thumbnail folder for an app."""
    configured = str((app_config or {}).get("thumbnail_folder") or "").strip()
    if configured:
        return configured
    video_folder = str(
        (app_config or {}).get("video_folder")
        or (app_config or {}).get("folder")
        or ""
    ).strip()
    if not video_folder:
        return ""
    creative_ads_folder = os.path.dirname(os.path.normpath(video_folder))
    return os.path.join(creative_ads_folder, "Thumbnail")


def image_folder_from_config(app_config):
    """Return the configured or conventional Image/Input folder for an app."""
    configured = str((app_config or {}).get("image_folder") or "").strip()
    if configured:
        return configured
    video_folder = str(
        (app_config or {}).get("video_folder")
        or (app_config or {}).get("folder")
        or ""
    ).strip()
    if not video_folder:
        return ""
    creative_ads_folder = os.path.dirname(os.path.normpath(video_folder))
    return os.path.join(creative_ads_folder, "Image", "Input")


def is_image_asset(name, mime_type=""):
    lower_name = (name or "").lower()
    lower_mime = (mime_type or "").lower()
    extension = os.path.splitext(lower_name)[1]
    if extension:
        return extension in IMAGE_EXTS
    return lower_mime in IMAGE_MIME_TYPES


def image_asset_item(source_path, source_name="", relative_directory=""):
    """Build one copyable image record while preserving its source folders."""
    filename = source_name or os.path.basename(source_path)
    destination_relative = os.path.join(relative_directory, filename)
    return {
        "source_path": source_path,
        "source_name": filename,
        "destination_relative": destination_relative,
    }


def inspect_local_image_assets(folder_paths):
    image_items = []
    skipped_files = []
    for folder_path in folder_paths:
        source_root = os.path.abspath(folder_path)
        if not os.path.isdir(source_root):
            continue
        root_name = sanitize_filename(os.path.basename(os.path.normpath(source_root)))
        for current_root, directory_names, file_names in os.walk(source_root):
            directory_names.sort(key=str.lower)
            for file_name in sorted(file_names, key=str.lower):
                if not is_image_asset(file_name):
                    if file_name.lower() not in IGNORED_LOCAL_IMAGE_FILES:
                        skipped_files.append(os.path.join(current_root, file_name))
                    continue
                source_path = os.path.join(current_root, file_name)
                relative_path = os.path.relpath(source_path, source_root)
                destination_relative = os.path.join(root_name, relative_path)
                image_items.append(image_asset_item(
                    source_path,
                    file_name,
                    os.path.dirname(destination_relative),
                ))
    return image_items, skipped_files


def collect_local_image_assets(folder_paths):
    image_items, _skipped_files = inspect_local_image_assets(folder_paths)
    return image_items


def _safe_destination_relative(item):
    relative_path = item.get("destination_relative", "")
    if not relative_path:
        relative_path = item.get("source_name", "")
    parts = []
    for part in relative_path.replace("\\", "/").split("/"):
        if part in ("", ".", ".."):
            continue
        parts.append(sanitize_filename(part))
    return os.path.join(*parts) if parts else sanitize_filename(
        os.path.basename(item.get("source_path", "image"))
    )


def copy_image_assets(image_items, destination_root):
    if image_items and not destination_root:
        raise RuntimeError("App chưa có đường dẫn Drive local Image.")
    copied_directories = []
    copied_files = []
    for item in image_items:
        source_path = item.get("source_path", "")
        if not os.path.isfile(source_path):
            continue
        destination_path = os.path.join(
            destination_root,
            _safe_destination_relative(item),
        )
        if os.path.normcase(os.path.abspath(source_path)) != os.path.normcase(os.path.abspath(destination_path)):
            destination_path = next_available_path(destination_path)
        destination_dir = os.path.dirname(destination_path)
        os.makedirs(destination_dir, exist_ok=True)
        if os.path.normcase(os.path.abspath(source_path)) != os.path.normcase(os.path.abspath(destination_path)):
            shutil.copy2(source_path, destination_path)
        safe_relative = _safe_destination_relative(item)
        relative_parent = os.path.dirname(safe_relative)
        copied_root = (
            os.path.join(destination_root, safe_relative.split(os.sep)[0])
            if relative_parent
            else destination_root
        )
        if copied_root not in copied_directories:
            copied_directories.append(copied_root)
        copied_files.append(destination_path)
    return copied_directories, copied_files


def copy_files_flat(file_paths, destination_root):
    """Copy files directly into a destination without overwriting names."""
    if file_paths and not destination_root:
        raise RuntimeError("App chưa có đường dẫn Drive local Thumbnail.")
    os.makedirs(destination_root, exist_ok=True)
    copied_files = []
    for source_path in file_paths:
        if not os.path.isfile(source_path):
            continue
        destination_path = next_available_path(
            os.path.join(destination_root, os.path.basename(source_path))
        )
        if os.path.normcase(os.path.abspath(source_path)) != os.path.normcase(
            os.path.abspath(destination_path)
        ):
            shutil.copy2(source_path, destination_path)
        copied_files.append(destination_path)
    return copied_files


def extract_video_thumbnail(video_path, thumbnail_path, ffmpeg_exe, creationflags=0):
    """Extract the first frame of a rendered video to a JPEG atomically."""
    destination_dir = os.path.dirname(os.path.abspath(thumbnail_path))
    os.makedirs(destination_dir, exist_ok=True)
    thumbnail_base, thumbnail_extension = os.path.splitext(thumbnail_path)
    temp_thumbnail = next_available_path(
        f"{thumbnail_base}.part{thumbnail_extension or '.jpg'}"
    )
    command = [
        ffmpeg_exe,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        video_path,
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-update",
        "1",
        temp_thumbnail,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            creationflags=creationflags,
        )
        if result.returncode != 0:
            error_text = result.stderr.decode("utf-8", "ignore").strip()
            raise RuntimeError(error_text[:1800] or "FFmpeg không tạo được thumbnail.")
        os.replace(temp_thumbnail, thumbnail_path)
        return thumbnail_path
    finally:
        if os.path.exists(temp_thumbnail):
            try:
                os.remove(temp_thumbnail)
            except OSError:
                pass
