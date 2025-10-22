import os
import sys
import logging
from datetime import datetime, timedelta, timezone
import subprocess
import tempfile
import re

ANSI_ESCAPE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
REAL_STDERR = sys.__stderr__
REAL_STDOUT = sys.__stdout__


# ---------------------
# Custom GMT Formatter
# ---------------------
class GMTFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S.%f") + " GMT"

class StderrRedirect:
    """Redirect C-level stderr (like FFmpeg) into Python logger."""
    def __enter__(self):
        self.stderr_fd = REAL_STDERR.fileno()
        self.saved_stderr_fd = os.dup(self.stderr_fd)
        self.temp_fd, self.temp_path = tempfile.mkstemp()
        os.dup2(self.temp_fd, self.stderr_fd)
        os.close(self.temp_fd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.dup2(self.saved_stderr_fd, self.stderr_fd)
        os.close(self.saved_stderr_fd)
        with open(self.temp_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    logger.warning("[FFMPEG] %s", line)
        os.remove(self.temp_path)

# ---------------------
# Filters
# ---------------------
class InfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno == logging.INFO


# ---------------------
# Log File Paths
# ---------------------
if getattr(sys, 'frozen', False):  # running in a PyInstaller exe
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)  # go up from /logs to project root

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

# ✅ Always create logs folder if missing
os.makedirs(LOG_DIR, exist_ok=True)


def clean_old_logs(folder, days=30):
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    for file in os.listdir(folder):
        path = os.path.join(folder, file)
        if os.path.isfile(path):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
                if mtime < cutoff:
                    os.remove(path)
                    print(f"Deleted old log: {file}")
            except Exception as e:
                print(f"Failed to delete old log {file}: {e}")


clean_old_logs(LOG_DIR)

info_log_path = os.path.join(LOG_DIR, "Incident.log")
error_log_path = os.path.join(LOG_DIR, "err.log")


# ---------------------import re
ANSI_ESCAPE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')

# Setup Logging
# ---------------------
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.propagate = False 

formatter = GMTFormatter('%(asctime)s [%(levelname)s] %(message)s')

# INFO Handler
info_handler = logging.FileHandler(info_log_path, mode='a')
info_handler.setLevel(logging.INFO)
info_handler.addFilter(InfoFilter())
info_handler.setFormatter(formatter)
logger.addHandler(info_handler)

# ERROR/Warning Handler
err_handler = logging.FileHandler(error_log_path, mode='a')
err_handler.setLevel(logging.WARNING)
err_handler.setFormatter(formatter)
logger.addHandler(err_handler)


# ---------------------
# Redirect stdout/stderr
# ---------------------
class StreamToLogger:
    def __init__(self, logger, default_level):
        self.logger = logger
        self.default_level = default_level
        self._in_write = False

    def write(self, message):
        if self._in_write:
            return

        # Strip ANSI escape codes
        message = ANSI_ESCAPE.sub('', str(message)).strip()
        if not message:
            return

        level = self.default_level
        if "[INFO" in message:
            level = logging.INFO
        elif "[WARNING" in message:
            level = logging.WARNING
        elif "[ERROR" in message:
            level = logging.ERROR
        elif "[CRITICAL" in message:
            level = logging.CRITICAL
        elif "[DEBUG" in message:
            level = logging.DEBUG

        try:
            self._in_write = True
            if level == logging.INFO:
                logger.handle(logging.LogRecord(logger.name, level, "", 0, message, None, None))
            else:
                self.logger.log(level, message)
        finally:
            self._in_write = False

    def flush(self):
        pass
# Redirect print() to err.log as WARNING
sys.stdout = StreamToLogger(logger, logging.INFO)
# Redirect errors to err.log as ERROR
sys.stderr = StreamToLogger(logger, logging.ERROR)


# ---------------------
# Catch uncaught exceptions into err.log
# ---------------------
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Use logger but disable propagation to avoid recursion
    try:
        logger.error(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
    except Exception as e:
        # If logging fails, write directly to the error log file
        with open(error_log_path, "a") as f:
            f.write(f"\nFAILED TO LOG EXCEPTION: {e}\n")
            import traceback
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)



# ---------------------
# Log App Start with GMT
# ---------------------
now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S.%f") + " GMT"
with open(info_log_path, 'a') as f:
    f.write('\n' + '*' * 80 + '\nAPP STARTED at ' + now + '\n')

with open(error_log_path, 'a') as f:
    f.write('\n' + '*' * 80 + '\nAPP STARTED at ' + now + '\n')

sys.excepthook = handle_exception

