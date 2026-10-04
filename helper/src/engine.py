"""Native FFmpeg engine; the browser only controls jobs and shows progress."""
import copy
import errno
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from autoresize_tool.naming import (
    sanitize_filename, initial_asset_metadata, asset_file_name,
    random_asset_label, is_asset_label,
)
from autoresize_tool.storage import save_json_atomic, load_json, next_available_path
from autoresize_tool.media import dated_upload_root, copy_image_assets, image_asset_item
from autoresize_tool.targets import build_app_target_snapshot
from autoresize_tool.platform_paths import configured_path_for_platform, discover_local_app_targets, local_shared_drives_root
from google_drive import GoogleDriveUploader

SIZES = {"916": (1080, 1920), "11": (1080, 1080), "169": (1920, 1080), "45": (1080, 1350)}
EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".png", ".jpg", ".jpeg", ".webp"}
TRANSIENT_FILE_PROVIDER_ERRORS = {
    errno.EAGAIN,
    errno.EBUSY,
    errno.EDEADLK,
    errno.ETIMEDOUT,
}


def destination_available(path):
    """Check a destination without taking the helper offline during Drive sync.

    macOS File Provider can temporarily return EDEADLK/EAGAIN while a Google
    Drive placeholder is materialising. The path is still a valid configured
    destination and the later copy operation can retry it normally.
    """
    if not path:
        return False
    if sys.platform == "darwin":
        parts = Path(path).parts
        for index, part in enumerate(parts):
            if part == "CloudStorage" and index + 2 < len(parts) and parts[index + 1].startswith("GoogleDrive-"):
                # Checking a deep File Provider placeholder can block or raise
                # EDEADLK. The canonical catalog already validates the rest of
                # the path, so only probe the mounted Shared drives root.
                path = Path(*parts[: index + 3])
                break
    try:
        return Path(path).is_dir()
    except OSError as error:
        if error.errno in TRANSIENT_FILE_PROVIDER_ERRORS:
            return True
        return False


def export_metadata(source_name, options):
    metadata = initial_asset_metadata(source_name)
    optional = lambda value: sanitize_filename(str(value)) if str(value or "").strip() else ""
    metadata.update({
        "theme": sanitize_filename(options.get("theme", "Exports")),
        "app_code": optional(options.get("appCode", "")),
        "label": optional(options.get("label", "")),
        "language": optional(options.get("language", "EN")).upper(),
        "w2w_flow_token": optional(options.get("flowToken", "")),
    })
    return metadata


def export_relative_folder(pattern, metadata):
    value = pattern or "{YYMM}/{YYMMDD}/{Theme}"
    replacements = {
        "{YYMM}": metadata["date_code"][:4], "{YYMMDD}": metadata["date_code"],
        "{App}": metadata["app_code"] or "_unknown_app", "{Theme}": metadata["theme"] or "_unknown_theme",
        "{Label}": metadata["label"] or "_unknown_label", "{Language}": metadata["language"] or "_unknown_language",
    }
    for token, replacement in replacements.items():
        value = value.replace(token, replacement)
    value = value.replace("\\", "/")
    parts = [sanitize_filename(part) for part in value.split("/") if part.strip()]
    if not parts or len(parts) > 8 or any(part in (".", "..") for part in parts):
        raise ValueError("Choose a valid relative folder pattern.")
    return Path(*parts)


def filter_args(size, mode, color="#111111", blur=24):
    w, h = SIZES[size]
    if mode == "blur":
        if not isinstance(blur, (int, float)) or not 1 <= blur <= 60:
            raise ValueError("Blur must be between 1 and 60.")
        graph = (f"[0:v]split=2[fg][bg];[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
                 f"crop={w}:{h},gblur=sigma={blur}[b];[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[f];"
                 "[b][f]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]")
        return ["-filter_complex", graph, "-map", "[v]"]
    if mode == "crop":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p"
    elif mode in ("color", "fit"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Choose a valid background color.")
        fill = "black" if mode == "fit" else "0x" + color[1:]
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:"
              f"color={fill},setsar=1,format=yuv420p")
    else:
        raise ValueError("Choose Fit, Crop, Blur or Color.")
    return ["-vf", vf, "-map", "0:v:0"]


def safe_targets(raw):
    if not isinstance(raw, dict) or len(raw) > 500:
        raise ValueError("Import an app destination JSON object with at most 500 apps.")
    result = {}
    shared_drives_root = local_shared_drives_root()
    for tag, value in raw.items():
        if not isinstance(tag, str) or not tag.strip() or not isinstance(value, dict):
            raise ValueError("Invalid app destination.")
        item = {}
        for field in ("video_folder", "image_folder", "thumbnail_folder"):
            val = value.get(field) or (value.get("folder", "") if field == "video_folder" else "")
            if not isinstance(val, str) or len(val) > 2000 or "\x00" in val:
                raise ValueError("Invalid destination path.")
            item[field] = configured_path_for_platform(
                val.strip(), shared_drives_root=shared_drives_root
            )
        if not item["thumbnail_folder"] and item["video_folder"]:
            item["thumbnail_folder"] = str(Path(item["video_folder"]).parent / "Thumbnail")
        for field in ("drive_id", "video_folder_id", "image_folder_id", "thumbnail_folder_id"):
            val = value.get(field, "")
            if val and (not isinstance(val, str) or len(val) > 200):
                raise ValueError("Invalid Google Drive destination ID.")
            item[field] = val
        result[tag[:150]] = item
    return result


class Engine:
    def __init__(self, root, ffmpeg):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "inputs").mkdir(exist_ok=True)
        (self.root / "exports").mkdir(exist_ok=True)
        self.output_root = Path(load_json(str(self.root / "settings.json"), {}).get("outputFolder", str(self.root / "exports")))
        self.ffmpeg = ffmpeg
        self.drive = GoogleDriveUploader()
        self.lock = threading.RLock()
        self.inputs = load_json(str(self.root / "inputs.json"), {})
        self.targets = safe_targets(load_json(str(self.root / "targets.json"), {}))
        self.jobs = load_json(str(self.root / "jobs.json"), {})
        stored_labels = load_json(str(self.root / "used-labels.json"), [])
        self.used_labels = {label for label in stored_labels if is_asset_label(label)}
        for existing_job in self.jobs.values():
            source_labels = existing_job.get("options", {}).get("sourceLabels", {})
            if isinstance(source_labels, dict):
                self.used_labels.update(label for label in source_labels.values() if is_asset_label(label))
        save_json_atomic(str(self.root / "used-labels.json"), sorted(self.used_labels))
        self.cancel_events = {}
        self.work = queue.Queue()
        for job in self.jobs.values():
            if job["status"] in ("queued", "running", "cancelling"):
                job["status"] = "interrupted"
                job["error"] = "The local processor restarted. Completed outputs are preserved."
                for item in job["items"]:
                    if item["status"] in ("running", "queued"):
                        item["status"] = "cancelled"
        threading.Thread(target=self._worker, daemon=True).start()

    def persist(self):
        with self.lock:
            save_json_atomic(str(self.root / "jobs.json"), self.jobs)

    def add_input(self, path, name):
        key = Path(path).stem
        item = {"id": key, "name": sanitize_filename(name), "path": str(path), "size": Path(path).stat().st_size,
                "kind": "image" if Path(name).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else "video"}
        with self.lock:
            self.inputs[key] = item
            save_json_atomic(str(self.root / "inputs.json"), self.inputs)
        return {k: v for k, v in item.items() if k != "path"}

    def configure(self, targets):
        value = safe_targets(targets)
        # The web catalog is authoritative. Deep-scanning every Google Drive
        # destination here can block the session while File Provider syncs.
        with self.lock:
            self.targets = value
            save_json_atomic(str(self.root / "targets.json"), value)

    def refresh_targets(self):
        # Merge app folders discovered from the canonical Drive root. Discovery
        # is deliberately shallow so File Provider placeholders cannot block
        # the helper, while the server catalog keeps any legacy path exceptions.
        discovered = safe_targets(discover_local_app_targets())
        try:
            drive_targets = self.drive.discover_targets()
        except Exception:
            drive_targets = {}
        if discovered:
            with self.lock:
                # The exact canonical root is authoritative. Preserve catalog
                # exceptions for apps that still exist, add new apps, and drop
                # stale names after a full Shared Drive replacement/backup.
                refreshed = {}
                for name, target in discovered.items():
                    refreshed[name] = self.targets.get(name, target)
                    refreshed[name].update(drive_targets.get(name, {}))
                self.targets = refreshed
                save_json_atomic(str(self.root / "targets.json"), self.targets)
        return self.target_view()

    def configure_output(self, folder):
        if not isinstance(folder, str) or not folder.strip() or not Path(folder).expanduser().is_absolute():
            raise ValueError("Choose an absolute output folder on this computer.")
        destination = Path(folder).expanduser().resolve()
        if not destination.is_dir():
            raise ValueError("That folder is unavailable. Connect the drive or choose another folder.")
        # Check actual write access (including external volumes), not just mode bits.
        probe = destination / (".flow-write-check-" + str(uuid.uuid4()))
        try:
            with probe.open("xb") as stream:
                stream.write(b"flow")
        except OSError:
            raise ValueError("This folder is not writable. Choose another folder.")
        finally:
            probe.unlink(missing_ok=True)
        with self.lock:
            save_json_atomic(str(self.root / "settings.json"), {"outputFolder": str(destination)})
            self.output_root = destination
        return {"outputFolder": str(destination)}

    def target_view(self):
        return [{"id": k, "name": k, **v, "available": bool(v.get("drive_id") and self.drive.available) or any(destination_available(p) for field, p in v.items() if field.endswith("_folder") and p)}
                for k, v in self.targets.items()]

    def create(self, request):
        ids = request.get("inputIds")
        sizes = request.get("sizes", [])
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or len(ids) != len(set(ids)):
            raise ValueError("Choose 1–50 different inputs.")
        if any(not isinstance(i, str) or i not in self.inputs for i in ids):
            raise ValueError("An input is no longer available. Add it again.")
        if not isinstance(sizes, list) or any(s not in SIZES for s in sizes) or len(set(sizes)) != len(sizes):
            raise ValueError("Choose valid output sizes.")
        inputs = [copy.deepcopy(self.inputs[i]) for i in ids]
        if any(i["kind"] == "video" for i in inputs) and not sizes:
            raise ValueError("Choose at least one output size.")
        mode = request.get("mode", "blur")
        filter_args("916", mode, request.get("color", "#111111"), request.get("blur", 24))
        if request.get("quality", "balanced") not in ("fast", "balanced"):
            raise ValueError("Invalid export quality.")
        selected = request.get("targets", [])
        if not isinstance(selected, list) or any(not isinstance(s, str) for s in selected):
            raise ValueError("Invalid Drive destinations.")
        if len(selected) != len(set(selected)) or len(selected) > 20:
            raise ValueError("Choose up to 20 different Drive destinations.")
        snapshot = {}
        if selected:
            _, snapshot = build_app_target_snapshot(self.targets, selected)
            for target in snapshot.values():
                for kind in set(i["kind"] for i in inputs):
                    destination = target[kind + "_folder"]
                    if not destination_available(destination):
                        raise ValueError("A selected Drive folder is unavailable. Mount Google Drive or choose an existing folder.")
                if any(i["kind"] == "video" for i in inputs) and not destination_available(target["thumbnail_folder"]):
                    raise ValueError("The selected Thumbnail folder is unavailable.")
        with self.lock:
            output_root = self.output_root
        if not output_root.is_dir():
            raise ValueError("Output folder is unavailable. Connect the drive or choose another folder.")
        required = sum(i["size"] for i in inputs) * max(len(sizes), 1) * 3
        if shutil.disk_usage(output_root).free < required + 256 * 1024 * 1024:
            raise ValueError("Not enough local disk space for this batch.")
        key = str(uuid.uuid4())
        theme = sanitize_filename(request.get("theme", "Exports"))
        if theme in (".", ".."):
            raise ValueError("Choose a valid export folder name.")
        naming_mode = str(request.get("namingMode", "source"))
        if naming_mode not in ("source", "OS", "AUTO", "W2W", "W2WOS"):
            raise ValueError("Choose a valid file naming rule.")
        naming_options = {"theme": theme, "folderPattern": str(request.get("folderPattern", "{YYMM}/{YYMMDD}/{Theme}"))[:180],
                          "namingMode": naming_mode, "appCode": str(request.get("appCode", ""))[:80],
                          "label": str(request.get("label", ""))[:80], "language": str(request.get("language", "EN"))[:20],
                          "flowToken": str(request.get("flowToken", ""))[:80]}
        raw_target_codes = request.get("targetAppCodes", {})
        if not isinstance(raw_target_codes, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                         for k, v in raw_target_codes.items()):
            raise ValueError("Invalid app codes for Drive destinations.")
        target_app_codes = {
            tag: sanitize_filename(raw_target_codes.get(tag, naming_options["appCode"]))[:80]
            for tag in selected
        }
        metadata = export_metadata(inputs[0]["name"], naming_options)
        if naming_mode != "source" and not all(metadata[field] for field in ("theme", "app_code", "language")):
            raise ValueError("Theme, app code and language are required for structured file names.")
        if naming_mode in ("W2W", "W2WOS") and not metadata["w2w_flow_token"]:
            raise ValueError("A W2W flow token is required for this naming rule.")
        if naming_mode != "source" and any(not code for code in target_app_codes.values()):
            raise ValueError("Every selected Drive app needs an app code.")
        with self.lock:
            source_labels = {}
            if naming_mode != "source":
                for source in inputs:
                    if source["kind"] != "video":
                        continue
                    allocated = random_asset_label(self.used_labels)
                    self.used_labels.add(allocated)
                    source_labels[source["id"]] = allocated
                save_json_atomic(str(self.root / "used-labels.json"), sorted(self.used_labels))
            folder_metadata = {**metadata, "label": next(iter(source_labels.values()), metadata.get("label", ""))}
            relative_folder = export_relative_folder(naming_options["folderPattern"], folder_metadata)
            job = {"id": key, "status": "queued", "createdAt": int(time.time()*1000), "items": [], "targets": snapshot,
                   "options": {"mode": mode, "color": request.get("color", "#111111"), "blur": request.get("blur", 24),
                               "quality": request.get("quality", "balanced"), **naming_options,
                               "sourceLabels": source_labels,
                               "targetAppCodes": target_app_codes,
                               "relativeFolder": str(relative_folder)}, "error": None,
                   "outputFolder": str(output_root / relative_folder), "inputs": inputs}
            for source in inputs:
                for size in sizes if source["kind"] == "video" else ["original"]:
                    job["items"].append({"id": str(uuid.uuid4()), "inputId": source["id"], "name": source["name"],
                                         "kind": source["kind"], "size": size, "status": "queued", "progress": 0,
                                         "driveStatus": "pending" if snapshot else "not_requested"})
            self.jobs[key] = job
            self.cancel_events[key] = threading.Event()
            self.persist()
        self.work.put(key)
        return self.view(key)

    def view(self, key):
        with self.lock:
            if key not in self.jobs:
                raise KeyError("Job not found.")
            return copy.deepcopy({k: v for k, v in self.jobs[key].items() if k != "inputs"})

    def cancel(self, key):
        with self.lock:
            job = self.jobs[key]
            if job["status"] in ("queued", "running", "cancelling"):
                job["status"] = "cancelling"
                self.cancel_events[key].set()
                self.persist()
        return self.view(key)

    def delete(self, key):
        """Remove a terminal job and only the local output files owned by it.

        Drive copies are intentionally preserved. Output folders can be shared by
        multiple packs, so remove the exact recorded files rather than the folder.
        """
        with self.lock:
            if key not in self.jobs:
                raise KeyError("Job not found.")
            job = self.jobs[key]
            if job["status"] in ("queued", "running", "cancelling"):
                raise ValueError("Wait for this pack to finish or stop it before deleting.")
            output_root = Path(job["outputFolder"]).resolve()
            files = []
            for item in job["items"]:
                for field in ("path", "thumbnail"):
                    value = item.get(field)
                    if not value:
                        continue
                    path = Path(value).resolve()
                    if not path.is_relative_to(output_root):
                        raise ValueError("Refusing to delete a file outside this pack's output folder.")
                    files.append(path)
            deleted = 0
            for path in files:
                if path.is_file():
                    path.unlink()
                    deleted += 1
            del self.jobs[key]
            self.cancel_events.pop(key, None)
            self.persist()
        return {"deleted": key, "filesDeleted": deleted}

    def _run(self, args, cancel, update=None, duration=0):
        process = subprocess.Popen([self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", *args],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        errors = []
        def drain():
            for line in iter(process.stderr.readline, b""):
                errors.append(line.decode("utf8", "replace"))
                if len(errors) > 30:
                    errors.pop(0)
        def progress():
            for line in iter(process.stdout.readline, b""):
                if update and duration and line.startswith(b"out_time_us="):
                    try:
                        update(min(97, int(float(line.split(b"=")[1]) / 1000000 / duration * 100)))
                    except ValueError:
                        pass
        readers = [threading.Thread(target=drain), threading.Thread(target=progress)]
        for reader in readers:
            reader.start()
        while process.poll() is None:
            if cancel.wait(.15):
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
        process.wait()
        for reader in readers:
            reader.join(timeout=3)
        process.stdout.close()
        process.stderr.close()
        if cancel.is_set():
            raise InterruptedError("Cancelled.")
        if process.returncode:
            raise RuntimeError("".join(errors)[-1800:] or "FFmpeg could not process this file.")

    def _duration(self, path):
        result = subprocess.run([self.ffmpeg, "-nostdin", "-hide_banner", "-i", path], capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr.decode("utf8", "replace"))
        if not match:
            raise ValueError("Cannot read this video's duration. Try an MP4, MOV or WebM file.")
        h, m, s = map(float, match.groups())
        return h*3600 + m*60 + s

    def _copy(self, source, destination, cancel):
        if cancel.is_set():
            raise InterruptedError("Cancelled.")
        destination = Path(next_available_path(str(destination)))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".part-" + uuid.uuid4().hex)
        try:
            with open(source, "rb") as src, open(temporary, "xb") as dst:
                while True:
                    if cancel.is_set():
                        raise InterruptedError("Cancelled.")
                    block = src.read(1024*1024)
                    if not block:
                        break
                    dst.write(block)
            os.replace(temporary, destination)
            return str(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _copy_to_target(self, source, target, kind, folder_parts, filename, cancel):
        """Prefer Drive Desktop; use the API only for File Provider failures."""
        destination = Path(target[kind + "_folder"]).joinpath(*folder_parts, filename)
        try:
            if destination.is_file() and destination.stat().st_size == Path(source).stat().st_size:
                return str(destination)
            return self._copy(source, destination, cancel)
        except OSError as local_error:
            uploaded = self.drive.upload(
                source,
                target.get("drive_id", ""),
                target.get(kind + "_folder_id", ""),
                folder_parts,
                filename,
                cancel,
            )
            if uploaded:
                return uploaded
            raise local_error

    def _upload_item(self, job, item, source, duration, cancel):
        options = job["options"]
        source_label = options.get("sourceLabels", {}).get(source["id"], options.get("label", ""))
        item["copiedTo"] = []
        for tag, snapshot_target in job["targets"].items():
            if cancel.is_set():
                raise InterruptedError("Cancelled.")
            # Old jobs may predate Drive IDs. Merge current catalog metadata so
            # retrying an already-rendered pack can use the API fallback.
            target = {**snapshot_target, **{
                key: value for key, value in self.targets.get(tag, {}).items()
                if key.endswith("_id")
            }}
            if source["kind"] == "video":
                target_options = {
                    **options, "label": source_label,
                    "appCode": options.get("targetAppCodes", {}).get(tag, options.get("appCode", "")),
                }
                target_metadata = export_metadata(source["name"], target_options)
                target_folder = export_relative_folder(options.get("folderPattern"), target_metadata)
                target_name = (
                    asset_file_name(target_metadata, item["size"], duration, options["namingMode"])
                    if options.get("namingMode") != "source" else Path(item["path"]).name
                )
                copied = self._copy_to_target(
                    item["path"], target, "video", target_folder.parts, target_name, cancel
                )
                thumbnail_name = Path(target_name).with_suffix(".jpg").name
                self._copy_to_target(
                    item["thumbnail"], target, "thumbnail", target_folder.parts,
                    thumbnail_name, cancel,
                )
            else:
                image_folder = (
                    time.strftime("%y%m"), time.strftime("%y%m%d"),
                    sanitize_filename(options["theme"]),
                )
                copied = self._copy_to_target(
                    item["path"], target, "image", image_folder,
                    Path(item["path"]).name, cancel,
                )
            item["copiedTo"].append({"app": tag, "path": copied})
        if job["targets"]:
            item["driveStatus"] = "copied"

    def retry_drive(self, key):
        with self.lock:
            if key not in self.jobs:
                raise KeyError("Job not found.")
            job = self.jobs[key]
            if job["status"] in ("queued", "running", "cancelling", "uploading"):
                raise ValueError("Wait for the pack to finish before retrying Drive upload.")
            failed = [item for item in job["items"] if item.get("path") and item.get("driveStatus") == "failed"]
            if not failed:
                return self.view(key)
            cancel = threading.Event()
            job["status"] = "uploading"
            self.persist()
        try:
            for item in failed:
                source = next(source for source in job["inputs"] if source["id"] == item["inputId"])
                duration = self._duration(source["path"]) if source["kind"] == "video" else 0
                item["error"] = None
                item["driveStatus"] = "uploading"
                self.persist()
                try:
                    self._upload_item(job, item, source, duration, cancel)
                except Exception as error:
                    item["driveStatus"] = "failed"
                    item["error"] = str(error)
                self.persist()
        finally:
            job["status"] = "partial" if any(
                item.get("driveStatus") == "failed" or item.get("status") != "succeeded"
                for item in job["items"]
            ) else "succeeded"
            self.persist()
        return self.view(key)

    def _worker(self):
        while True:
            key = self.work.get()
            try:
                self._execute(key)
            except Exception as error:
                with self.lock:
                    self.jobs[key]["status"] = "failed"
                    self.jobs[key]["error"] = str(error)
                    self.persist()
            finally:
                self.work.task_done()

    def _execute(self, key):
        job = self.jobs[key]
        cancel = self.cancel_events[key]
        if not cancel.is_set():
            job["status"] = "running"
        output_root = Path(job["outputFolder"])
        output_root.mkdir(parents=True, exist_ok=True)
        options = job["options"]
        for item in job["items"]:
            if cancel.is_set():
                item["status"] = "cancelled"
                continue
            source = next(x for x in job["inputs"] if x["id"] == item["inputId"])
            item["status"] = "running"
            temporary = None
            try:
                duration = self._duration(source["path"]) if source["kind"] == "video" else 0
                stem = sanitize_filename(Path(source["name"]).stem)
                source_label = options.get("sourceLabels", {}).get(source["id"], options.get("label", ""))
                metadata = export_metadata(source["name"], {**options, "label": source_label})
                if source["kind"] == "video" and options.get("namingMode") != "source":
                    filename = asset_file_name(metadata, item["size"], duration, options["namingMode"])
                else:
                    filename = f"{stem}_{item['size']}_{round(duration)}s.mp4" if source["kind"] == "video" else source["name"]
                output = Path(next_available_path(str(output_root / filename)))
                if source["kind"] == "video":
                    temporary = output.with_suffix(".part.mp4")
                    args = ["-y", "-i", source["path"], *filter_args(item["size"], options["mode"], options["color"], options["blur"]),
                            "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast" if options["quality"] == "fast" else "veryfast",
                            "-crf", "23", "-pix_fmt", "yuv420p", "-threads", "2", "-filter_complex_threads", "2",
                            "-c:a", "aac", "-ar", "44100", "-b:a", "128k", "-movflags", "+faststart", "-progress", "pipe:1", str(temporary)]
                    self._run(args, cancel, lambda p: item.update(progress=p), duration)
                    os.replace(temporary, output)
                    # First output frame, same size, JPEG: same behavior as the source tool.
                    thumbnail = output.with_suffix(".jpg")
                    self._run(["-y", "-i", str(output), "-map", "0:v:0", "-frames:v", "1", "-q:v", "2", "-update", "1", str(thumbnail)], cancel)
                    item["thumbnail"] = str(thumbnail)
                else:
                    self._copy(source["path"], output, cancel)
                item["path"] = str(output)
                item["name"] = output.name
                item["bytes"] = output.stat().st_size
                item["progress"] = 100
                item["status"] = "succeeded"
                if job["targets"]:
                    item["driveStatus"] = "uploading"
                    self.persist()
                self._upload_item(job, item, source, duration, cancel)
            except InterruptedError:
                if item.get("path"):
                    item["driveStatus"] = "cancelled"
                else:
                    item["status"] = "cancelled"
            except Exception as error:
                if item.get("path"):
                    item["driveStatus"] = "failed"
                else:
                    item["status"] = "failed"
                item["error"] = str(error)
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
                self.persist()
        job["status"] = "cancelled" if cancel.is_set() else "partial" if any(i["status"] != "succeeded" or i["driveStatus"] == "failed" for i in job["items"]) else "succeeded"
        self.persist()
