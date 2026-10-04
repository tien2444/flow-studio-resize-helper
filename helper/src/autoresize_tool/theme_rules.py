import os

from .naming import asset_folder_name, path_key


def folders_ready_for_upload(output_root, folders, metadata_values, minimum_videos=5):
    """Return folders ready to upload.

    The minimum applies only to structured theme folders represented by
    metadata. Ordinary local input folders are not theme batches and must not
    be rejected with a synthetic 0-video count.
    """
    source_counts = {}
    for metadata in metadata_values:
        source_path = metadata.get("source_path", "")
        if not source_path:
            continue
        theme_folder = os.path.normcase(
            os.path.abspath(os.path.join(output_root, asset_folder_name(metadata)))
        )
        source_counts.setdefault(theme_folder, set()).add(path_key(source_path))

    ready, skipped = [], []
    for folder in folders:
        count = source_counts.get(os.path.normcase(os.path.abspath(folder)))
        if count is None:
            ready.append(folder)
            continue
        source_count = len(count)
        if source_count < minimum_videos:
            skipped.append((folder, source_count))
        else:
            ready.append(folder)
    return ready, skipped
