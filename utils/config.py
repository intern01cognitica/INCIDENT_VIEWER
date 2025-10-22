
import sys, os, logging
from datetime import timedelta
from kivy.utils import get_color_from_hex
from kivy.core.text import LabelBase

# Figure out base path (development vs PyInstaller bundle)
def get_base_dir():
    if hasattr(sys, "_MEIPASS"):  # PyInstaller sets this
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()
RESOURCES_DIR = os.path.join(BASE_DIR, "resources")

# Paths
LOCAL_PROJECT_ROOT = os.path.join(os.path.expanduser("~"), "project", "forklift_temp_rect")
IST_OFFSET = timedelta(hours=5, minutes=30)

# Font
arial_path = os.path.join(RESOURCES_DIR, "arial.ttf")
if os.path.exists(arial_path):
    LabelBase.register(name="Arial", fn_regular=arial_path)

# Colors
BG_COLOR = get_color_from_hex("#ADB3AD")

# Helper: build full path for a resource
def resource_path(relative_path: str) -> str:
    """
    Build absolute path to a resource inside the bundled 'resources' folder.
    
    Examples:
        resource_path("dropdown_icon.png")
        resource_path("spinner_frames/frame1.png")
        resource_path("fonts/arial.ttf")
    """
    return os.path.join(RESOURCES_DIR, relative_path)