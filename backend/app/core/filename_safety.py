"""Helpers for safely handling user-supplied filenames."""


def sanitize_attachment_filename(filename: str) -> str:
    """Return a display-safe attachment filename without path components."""
    normalized = str(filename or "").replace("\\", "/")
    parts = [
        part
        for part in normalized.split("/")
        if part not in {"", ".", ".."}
    ]
    sanitized = "".join(parts)
    for char in ('"', "\r", "\n", "\x00"):
        sanitized = sanitized.replace(char, "")
    return sanitized.strip() or "attachment"
