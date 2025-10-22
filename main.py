import os
# Disable Kivy’s default file + console logging
os.environ["KIVY_NO_FILELOG"] = "1"
os.environ["KIVY_NO_CONSOLELOG"] = "1"
import sys, os, fcntl
from kivymd.app import MDApp
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from utils.ui_utils import SelectionScreen,IncidentScreen
from utils.config import LOCAL_PROJECT_ROOT
from utils.logs import logger
from kivy.config import Config
# NEW: hook Kivy + OpenCV logs into our logger
from kivy.logger import Logger as KivyLogger
import logging
import cv2

# Remove all default Kivy handlers (console + ~/.kivy/logs/*.txt)
try:
    KivyLogger.handlers.clear()
except Exception:
    pass

# Set Kivy logging level
KivyLogger.setLevel(logging.INFO)

# Attach our handlers from logs.py (Incident.log + err.log)
for h in logger.handlers:
    KivyLogger.addHandler(h)

# Silence OpenCV ffmpeg spam (only show real errors)
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

# UI tweaks similar to your original file
Config.set('input', 'mouse', 'mouse,disable_multitouch')
Config.set('input', 'wm_touch', '0')
Config.set('input', 'wm_pen', '0')  

def check_single_instance(lockfile="/tmp/incident_viewer.lock"):
    """Ensure only one instance runs at a time."""
    global lock_fp
    lock_fp = open(lockfile, "w")

    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Another instance already has the lock
        sys.exit(0)

class IncidentViewerApp(MDApp):
    def build(self):
        sm = ScreenManager()
        selection_screen = Screen(name="selection")
        selection_screen.add_widget(SelectionScreen(screen_manager=sm))
        incident_screen = Screen(name="incidents")
        incident_screen.add_widget(IncidentScreen(screen_manager=sm))
        sm.add_widget(selection_screen)
        sm.add_widget(incident_screen)
        sm.current = "selection"
        Window.size = (1000, 650)
        Window.resizable = False
        return sm

if __name__ == "__main__":
    # Quick sanity message about the assumed local root
    check_single_instance()
    logger.info("Local images root assumed at: %s", LOCAL_PROJECT_ROOT)
    IncidentViewerApp().run()