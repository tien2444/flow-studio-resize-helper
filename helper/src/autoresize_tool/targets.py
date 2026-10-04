def build_app_target_snapshot(custom_links, selected_apps):
    """Freeze selected app names and destinations for one complete workflow."""
    selected = tuple(sorted(dict.fromkeys(selected_apps)))
    if not selected:
        raise ValueError("Chưa chọn ứng dụng đích.")

    missing = [tag for tag in selected if tag not in custom_links]
    if missing:
        raise ValueError(
            "App đã chọn không còn trong Quản lý App: " + ", ".join(missing)
        )

    return selected, {
        tag: dict(custom_links[tag])
        for tag in selected
    }
