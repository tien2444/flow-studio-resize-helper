import json
import os
import tempfile


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default.copy() if isinstance(default, dict) else default


def save_json_atomic(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def append_json_line(path, data):
    """Append one UTF-8 JSON record and flush it to disk."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def next_available_path(path):
    """Return a path that does not overwrite an existing file or directory."""
    if not os.path.exists(path):
        return path
    base, extension = os.path.splitext(path)
    copy_number = 2
    while True:
        candidate = f"{base}_{copy_number}{extension}"
        if not os.path.exists(candidate):
            return candidate
        copy_number += 1


def packaged_file(configured_path, base_dir, filename):
    configured_path = (configured_path or "").strip()
    if configured_path:
        candidate = configured_path
        if not os.path.isabs(candidate):
            candidate = os.path.join(base_dir, candidate)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return os.path.join(base_dir, filename)
