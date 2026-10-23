# resource.py (new file, project root)
import os
import sys

def resource_path(relative_path: str) -> str:
    """Absolute path to a bundled resource, for dev and for PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)