import os
import re
import secrets
from datetime import datetime


VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv")
ASSET_LABEL_PATTERN = re.compile(r"^A[1-9]\d*B[1-9]\d*C[1-9]\d*D[1-9]\d*E[1-9]\d*F[1-9]\d*G[1-9]\d*$")


def random_asset_label(used_labels=None):
    """Create an Advanced Rename label and never return one already reserved."""
    used = set(used_labels or ())
    for _ in range(10000):
        label = "".join(f"{letter}{secrets.randbelow(99) + 1}" for letter in "ABCDEFG")
        if label not in used:
            return label
    raise RuntimeError("Unable to allocate a unique file label.")


def is_asset_label(value):
    return isinstance(value, str) and bool(ASSET_LABEL_PATTERN.fullmatch(value))


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "untitled")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or "untitled"


def path_key(path):
    return os.path.normcase(os.path.abspath(path))


def initial_asset_metadata(source_name, now=None):
    stem = os.path.splitext(sanitize_filename(source_name))[0]
    parts = [part.strip(" _") for part in stem.split("_") if part.strip(" _")]
    theme = parts[0] if len(parts) > 0 else ""
    app_code = parts[1] if len(parts) > 1 else ""
    label = parts[2] if len(parts) > 2 else ""
    language = parts[3].upper() if len(parts) > 3 else ""
    w2w_flow_token = parts[4] if len(parts) > 4 else ""
    return {
        "source_name": source_name,
        "theme": theme,
        "app_code": app_code,
        "label": label,
        "language": language,
        "w2w_flow_token": (
            sanitize_filename(w2w_flow_token).strip("_ ") if w2w_flow_token else ""
        ),
        "date_code": (now or datetime.now()).strftime("%y%m%d"),
        "structured_name": bool(theme and app_code and label and language),
    }


def asset_folder_name_from_values(date_code, theme, _label=""):
    month_folder = sanitize_filename(date_code[:4])
    day_folder = sanitize_filename(date_code)
    theme_folder = sanitize_filename(theme) or "_unknown"
    return os.path.join(month_folder, day_folder, theme_folder)


def asset_folder_name(metadata):
    return asset_folder_name_from_values(metadata["date_code"], metadata["theme"])


def resolve_w2w_flow_token(metadata=None):
    raw_flow_token = (metadata.get("w2w_flow_token") or "").strip() if metadata else ""
    flow_token = sanitize_filename(raw_flow_token).strip("_ ") if raw_flow_token else ""
    if flow_token and not flow_token.upper().startswith("W2W"):
        flow_token = f"W2W{flow_token}"
    return flow_token


def asset_file_name(metadata, size_suffix, duration_sec, naming_mode="OS"):
    size_code = size_suffix.lstrip("_")
    duration_code = f"{max(int(duration_sec or 0), 0)}s"
    naming_mode = (naming_mode or "OS").strip().upper()
    if naming_mode in ("W2W", "W2WOS"):
        flow_token = resolve_w2w_flow_token(metadata)
        outsource_token = "_OS" if naming_mode == "W2WOS" else ""
        name = (
            f"{metadata['theme']}_{metadata['app_code']}_{metadata['label']}_"
            f"{metadata['language']}_{flow_token}{outsource_token}_"
            f"{size_code}_{duration_code}_{metadata['date_code']}"
        )
    else:
        marker = "AT" if naming_mode == "AUTO" else "OS"
        name = (
            f"{metadata['theme']}_{metadata['app_code']}_{metadata['label']}_"
            f"{metadata['language']}_{marker}_{size_code}_{duration_code}_{metadata['date_code']}"
        )
    return sanitize_filename(name) + ".mp4"


def infer_structured_asset_metadata(path):
    metadata = initial_asset_metadata(os.path.basename(path))
    if not metadata.get("structured_name"):
        return None
    metadata["source_path"] = os.path.abspath(path)
    return metadata


def validate_output_naming_metadata(metadata, naming_mode="OS"):
    if (naming_mode or "OS").strip().upper() in ("W2W", "W2WOS") and not resolve_w2w_flow_token(metadata):
        return "Chua co ten luong W2W trong ten video input."
    return ""
