import os, re, platform, string, logging
from datetime import datetime
import psutil
from utils.logs import logger
import psutil

def get_free_space_bytes(path):
    """Return free space in bytes for the filesystem containing 'path'."""
    try:
        usage = psutil.disk_usage(path)
        return usage.free
    except Exception:
        return 0

def is_device_available(path):
    """Return True if the given device/mount path is still accessible."""
    return path and os.path.exists(path) and os.access(path, os.W_OK | os.R_OK)


def extract_timestamp_from_filename(filename):
    """
    Expect filenames to contain a GMT timestamp like: _YYYY-MM-DD_HH-MM-SS-ffffff_GMT
    If not present, returns None.
    """
    m = re.search(r'_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(?:-\d{1,6})?)_GMT', filename)
    if not m:
        return None
    ts_str = m.group(1)
    # Accept microseconds optional
    fmt = "%Y-%m-%d_%H-%M-%S-%f" if '-' in ts_str and ts_str.count('-') >= 6 else "%Y-%m-%d_%H-%M-%S"
    try:
        dt = datetime.strptime(ts_str, fmt)
        return dt  # this dt is GMT in your original design
    except Exception:
        # fallback attempt: try without microseconds
        try:
            return datetime.strptime(ts_str.split('-')[0:6].__repr__(), fmt)
        except Exception:
           return None

def ensure_device_mounts():
    """
    Returns a list of candidate device mount points (strings).
    Works across platforms with simple heuristics (no psutil).
    """
    system = platform.system()
    mounts = []
    try:
        if system == "Windows":
            # List drives A:..Z: and skip the current system drive (like C:)
            system_drive = os.environ.get("SystemDrive", "C:").upper()
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    if drive.upper() != system_drive and os.access(drive, os.W_OK | os.R_OK):
                        mounts.append(drive)
            if not mounts:
                # fall back to any writable drives including system drive if nothing else
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    if os.path.exists(drive) and os.access(drive, os.W_OK | os.R_OK):
                        mounts.append(drive)
        elif system == "Darwin":
            base = "/Volumes"
            if os.path.exists(base):
                for name in os.listdir(base):
                    mp = os.path.join(base, name)
                    if os.path.ismount(mp) and os.access(mp, os.W_OK | os.R_OK):
                        mounts.append(mp)
        elif system== "Linux":
            import psutil
            devices = []
            partitions = psutil.disk_partitions(all=False)
            for p in partitions:
                mp = p.mountpoint
                opts = p.opts.lower()
                if ("/media/" in mp or "/run/media/" in mp or "/mnt/" in mp) and "rw" in opts:
                    if os.path.ismount(mp) and os.access(mp, os.R_OK):
                        devices.append(mp)
            return devices if devices else ["No Device"]
    except Exception as e:
        logger.warning("Device detection error: %s", e)
    return mounts if mounts else ["No Device"]
def clean_camera_name(folder_name: str) -> str:
    """Return camera name without camId- prefix."""
    if "-" in folder_name:
        return folder_name.split("-", 1)[1]
    return folder_name