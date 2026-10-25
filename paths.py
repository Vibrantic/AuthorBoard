import os


def app_home() -> str:
    """Folder that holds all AuthorBoard data (``AUTHORBOARD_HOME`` or ``~/.authorboard``)."""
    return os.environ.get("AUTHORBOARD_HOME") or os.path.join(
        os.path.expanduser("~"), ".authorboard"
    )