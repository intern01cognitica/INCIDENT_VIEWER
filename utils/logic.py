import os
import getpass
import threading
import platform, time
from datetime import datetime, timedelta
from kivy.clock import Clock
# from utils.file_utils import extract_timestamp_from_filename, ensure_device_mounts,is_device_available,clean_camera_name
from utils.config import IST_OFFSET
from utils.logs import logger
from utils.video_utils import create_video_from_image_paths, group_images_by_incident
from utils.file_utils import (
    extract_timestamp_from_filename,
    ensure_device_mounts,
    is_device_available,
    clean_camera_name,
    get_free_space_bytes
)

def estimate_group_size(group):
    """Estimate output video size based on input image sizes."""
    if not group:
        return 0
    sizes = [os.path.getsize(p) for p, _ in group if os.path.exists(p)]
    if not sizes:
        return 0
    avg_img_size = sum(sizes) / len(sizes)
    est = avg_img_size * len(group) * 1.1  # add ~10% overhead
    return int(est)
def get_camera_folders(camera_root):
    """Return (names, map) where names = cleaned camera names for UI, map = clean→real folder."""
    try:
        if not os.path.exists(camera_root):
            logger.warning("Camera root not found: %s", camera_root)
            return None, None   # <- return None so UI can handle popup

        folders = [d for d in os.listdir(camera_root) if os.path.isdir(os.path.join(camera_root, d))]

        # Build mapping: clean name -> real folder
        camera_map = {clean_camera_name(f): f for f in folders}
        return list(camera_map.keys()) if folders else ["No Camera"], camera_map

    except Exception as e:
        logger.error("Error listing camera folders: %s", e)
        return None, None

def eject_device(mount_point):
    """Try to safely eject the USB device after successful copy."""
    try:
        if platform.system() == "Linux":
            device = os.popen(f"df --output=source {mount_point} | tail -1").read().strip()
            if device:
                os.system(f"udisksctl unmount -b {device} >/dev/null 2>&1")
                os.system(f"udisksctl power-off -b {device} >/dev/null 2>&1")
                time.sleep(2)
        elif platform.system() == "Darwin":
            os.system(f"diskutil unmount {mount_point}")
        elif platform.system() == "Windows":
            logger.warning("Auto-eject not implemented on Windows. User must eject manually.")
            return False
        logger.info(f"Safely unmounted: {mount_point}")
        return True
    except Exception as e:
        logger.error(f"Auto-eject failed: {e}")
        return False
def get_nuc_identifier():
    """Return system identifier (username or hostname)."""
    try:
        return getpass.getuser()  # logged-in user
    except Exception:
        return "unknown_system"
def on_camera_selected(self, camera_value):
    if camera_value.upper().startswith(("NO", "SELECT")):
        return

    real_folder = self.camera_map.get(camera_value, camera_value)
    camera_path = os.path.join(self.camera_root, real_folder)

    self.image_paths = []
    try:
        for root, _, files in os.walk(camera_path):
            for f in sorted(files):
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    self.image_paths.append(os.path.join(root, f))
        logger.info("Camera selected: %s (%d images found)", camera_value, len(self.image_paths))
    except Exception as e:
        logger.error("Error scanning camera folder: %s", e)
        self.image_paths.clear()

    # 🔹 Reset date/hour whenever camera changes
    self.start_date = None
    self.start_button.text = "Select Date"
    self.hour_spinner.text = "Select Hour"
    self.hour_spinner.values = []
    self.available_images.clear()
    self.hour_label_map.clear()

def auto_refresh_devices(self):
    new_devices = ensure_device_mounts()
    if set(new_devices) != set(self.device_spinner.values):
        self.device_spinner.values = new_devices
        if self.device_spinner.text not in new_devices:
            self.device_spinner.text = "Select Device" if new_devices else "No Device"


def on_date_selected(self, selected_ist_date):
    """Load images for the selected camera & date.
       If none, then check other cameras to decide popup message with suggestions."""
    if not hasattr(self, "image_paths"):
        self.show_popup("Please select a camera first.")
        return

    #  Step 1: Check selected camera
    self.available_images.clear()
    for path in self.image_paths:
        ts_gmt = extract_timestamp_from_filename(os.path.basename(path))
        if not ts_gmt:
            ts_gmt = datetime.utcfromtimestamp(os.path.getmtime(path))
        ts_ist = ts_gmt + IST_OFFSET

        if ts_ist.strftime("%Y-%m-%d") == selected_ist_date:
            self.available_images.append((path, ts_gmt, ts_ist))

    #  If selected camera has images → build hours & stop
    if self.available_images:
        ist_hours = sorted(set(ist.replace(minute=0, second=0, microsecond=0) 
                               for _, _, ist in self.available_images))
        self.hour_label_map = {}
        display = []
        for h in ist_hours:
            start_label = h.strftime("%I:%M%p")
            end_label = (h + timedelta(hours=1)).strftime("%I:%M%p")
            label = f"{start_label} - {end_label}"
            self.hour_label_map[label] = h
            display.append(label)

        self.hour_spinner.text = "Select Hour"
        self.hour_spinner.values = display if display else []
        return

    #  Step 2: Selected camera empty → check all cameras
    available_cams = []
    for cam_clean, real_folder in self.camera_map.items():
        camera_path = os.path.join(self.camera_root, real_folder)
        for root, _, files in os.walk(camera_path):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    ts_gmt = extract_timestamp_from_filename(f)
                    if not ts_gmt:
                        ts_gmt = datetime.utcfromtimestamp(
                            os.path.getmtime(os.path.join(root, f))
                        )
                    ts_ist = ts_gmt + IST_OFFSET
                    if ts_ist.strftime("%Y-%m-%d") == selected_ist_date:
                        available_cams.append(cam_clean)
                        break
            if cam_clean in available_cams:
                break

    #  Step 3: Popup message
    if available_cams:
        cams_str = ", ".join(available_cams)
        self.show_popup(
            f"This camera has no images for {selected_ist_date}.\n"
            f"Images are available in: {cams_str}."      
        )
        self.camera_spinner.text = "Select Camera"
    else:
        self.show_popup(f"No images found for {selected_ist_date}.")


def on_device_selected(self, value):
    from utils.ui_utils import show_snackbar 
    self.external_device_path = value
    if value and not value.upper().startswith("SELECT") and not value.upper().startswith("NO"):
        Clock.schedule_once(lambda dt: show_snackbar(f"Device selected: {self.external_device_path}", duration=1), 0)
def start_device_monitor(self):
    def check_device(dt):
        device = self.device_spinner.text
        if device and not is_device_available(device):
            self.abort_processing = True
            self.hide_loading()

            # 🔹 Dismiss overwrite popup if it’s still open
            if hasattr(self, "active_overwrite_popup") and self.active_overwrite_popup:
                try:
                    self.active_overwrite_popup.dismiss()
                except Exception as e:
                    logger.warning("Failed to dismiss overwrite popup: %s", e)
                self.active_overwrite_popup = None

            self.show_popup("Device disconnected. Please re-select device.")
            logger.warning("Device %s disconnected.", device)
            return False  # stop the interval

    # check every 0.2 seconds
    self.abort_processing = False 
    self.device_monitor_event = Clock.schedule_interval(check_device, 0.2)

def stop_device_monitor(self):
    if hasattr(self, "device_monitor_event") and self.device_monitor_event is not None:
        self.device_monitor_event.cancel()
        self.device_monitor_event = None
        logger.info("Device monitor stopped.")



def process_images(self):
    device = self.device_spinner.text
    camera = self.camera_spinner.text
    date_val = self.start_date
    hour_label = self.hour_spinner.text

    def is_select_or_no(x):
        return (not x) or x.upper().startswith("SELECT") or x.upper().startswith("NO")

    # 🟢 Collect all missing fields
    missing = []
    if is_select_or_no(device):
        missing.append("Device")
    if is_select_or_no(camera):
        missing.append("Camera")
    if is_select_or_no(date_val):
        missing.append("Date")
    if is_select_or_no(hour_label):
        missing.append("Hour")

    if missing:
        # Build user-friendly message
        if len(missing) == 1:
            msg = f"Please select: {missing[0]}"
        else:
            msg = "Please select: " + ", ".join(missing[:-1]) + f" and {missing[-1]}"
        self.show_popup(msg, reset_ui=False)
        return

    # ✅ If everything is selected
    Clock.schedule_once(lambda dt: self.show_loading("Checking incidents..."), 0)
    start_device_monitor(self)   # not self.start_device_monitor()

    threading.Thread(target=lambda: _process_images_thread(self), daemon=True).start()


def _process_images_thread(self):
    """Run heavy OpenCV/image grouping work in background."""
    try:
        _process_images_deferred(self)
    except Exception as e:
        Clock.schedule_once(lambda dt, err=e: self.show_popup(f"Error: {err}"), 0)

    finally:
        Clock.schedule_once(lambda dt: self.hide_loading(), 0)

def _process_images_deferred(self):
    device = self.device_spinner.text
    camera = self.camera_spinner.text
    date_val = self.start_date
    hour_label = self.hour_spinner.text

    # 🔹 Abort early if device already flagged as disconnected
    if getattr(self, "abort_processing", False):
        logger.warning("Processing aborted before start (device disconnected).")
        return

    if hour_label not in self.hour_label_map:
        Clock.schedule_once(lambda dt: self.hide_loading(), 0)
        Clock.schedule_once(lambda dt: self.show_popup("Invalid hour selected."), 0)
        return

    ist_start = self.hour_label_map[hour_label]
    ist_end = ist_start + timedelta(hours=1)

    selected = [(p, gmt) for p, gmt, ist in self.available_images if ist_start <= ist < ist_end]
    if not selected:
        Clock.schedule_once(lambda dt: self.hide_loading(), 0)
        Clock.schedule_once(lambda dt: self.show_popup("No images found for selection."), 0)
        return

    if getattr(self, "abort_processing", False):
        logger.warning("Processing aborted after image selection.")
        return

    groups = group_images_by_incident(selected, gap_seconds=30)
    filtered_groups = [g for g in groups if len(g) >= 2]

    if not filtered_groups:
        Clock.schedule_once(lambda dt: self.hide_loading(), 0)
        Clock.schedule_once(lambda dt: self.show_popup("No incidents found."), 0)
        return

    # 🟢 Free-space pre-check
    total_required = sum(estimate_group_size(g) for g in filtered_groups)
    free_space = get_free_space_bytes(device)
    if free_space < total_required:
        stop_device_monitor(self)
        Clock.schedule_once(lambda dt: self.hide_loading(), 0)
        Clock.schedule_once(lambda dt: self._show_space_warning_popup(
            total_required, free_space, filtered_groups, device, camera, date_val, hour_label
        ), 0)
        return

    if getattr(self, "abort_processing", False):
        logger.warning("Processing aborted before folder creation.")
        return

    safe_date = date_val
    system_name = f"Vehicle_{get_nuc_identifier()}"
    dest_root = os.path.join(device, "Cognitica AI")
    os.makedirs(dest_root, exist_ok=True)

    system_folder = os.path.join(dest_root, system_name)
    os.makedirs(system_folder, exist_ok=True)

    date_folder = os.path.join(system_folder, safe_date)
    os.makedirs(date_folder, exist_ok=True)

    # Build hour + camera folders
    hour_folder_name = hour_label.replace(" ", "").replace(":", ".").replace("-", "_to_")
    hour_folder = os.path.join(date_folder, hour_folder_name)
    os.makedirs(hour_folder, exist_ok=True)

    camera_folder = os.path.join(hour_folder, camera)

    # 🔹 Overwrite check
    if os.path.exists(camera_folder): 
        Clock.schedule_once(lambda dt: self.hide_loading(), 0)
        Clock.schedule_once(lambda dt: self._show_overwrite_popup(
            f"{camera} already has incidents for {hour_label}. Do you want to overwrite them?",
            camera_folder, device, hour_folder
        ), 0)
        return

    # ✅ Switch to "Processing incidents..."
    Clock.schedule_once(lambda dt: self.hide_loading(), 0)
    Clock.schedule_once(lambda dt: self.show_loading("Processing incidents..."), 0)

    os.makedirs(camera_folder, exist_ok=True)

    saved_files = []
    for idx, g in enumerate(sorted(filtered_groups, key=lambda grp: grp[0][1]), start=1):

        if getattr(self, "abort_processing", False):
            logger.warning("Processing aborted while saving incident %d.", idx)
            return

        # 🟢 Per-incident space check
        required_space = estimate_group_size(g)
        free_space = get_free_space_bytes(device)
        if free_space < required_space:
            stop_device_monitor(self)
            Clock.schedule_once(lambda dt: self.hide_loading(), 0)
            Clock.schedule_once(lambda dt: self.show_popup(
                f"Device ran out of space while saving incident {idx}.\n"
                f"Required ~{required_space // (1024*1024)} MB, "
                f"Available ~{free_space // (1024*1024)} MB.\n"
                f"Only {len(saved_files)} incident(s) were saved."
            ), 0)
            logger.error("Out of space on incident %d: need %d MB, have %d MB",
                         idx, required_space // (1024*1024), free_space // (1024*1024))
            return

        start_ist = (g[0][1] + IST_OFFSET).strftime("%I.%M.%S%p")
        end_ist = (g[-1][1] + IST_OFFSET).strftime("%I.%M.%S%p")
        safe_name = f"incident_{idx}_{start_ist}_to_{end_ist}.mp4"
        full_out = os.path.join(camera_folder, safe_name)

        imgs = [(p, ts) for p, ts in g]
        success, error_msg = create_video_from_image_paths(imgs, full_out, fps=5)
        if success:
            saved_files.append(full_out)
        else:
            if not getattr(self, "abort_processing", False):
                Clock.schedule_once(lambda dt: self.show_popup(
                    f"Could not create video for {camera} ({hour_label})."
                    # f"Check logs for details: {error_msg}"
                ), 0)
            logger.error("Failed to create incident video %s: %s", full_out, error_msg)
    def finalize(dt):
        # 🔹 Skip final popups if aborted
        if getattr(self, "abort_processing", False):
            logger.info("Finalize skipped due to device disconnect.")
            self.hide_loading()  # make sure loading spinner is closed
            return

        self.hide_loading()

        # 🔹 Verify actual files exist on disk
        verified_files = [f for f in saved_files if os.path.exists(f) and os.path.getsize(f) > 0]

        if verified_files and len(verified_files) == len(saved_files):
            #  All videos exist → success
            msg = (
                f"Successfully saved videos of {len(verified_files)} incident(s) "
                f"to the selected device under the 'Cognitica AI' folder."
            )
            self.show_success_popup(msg, device)

            logger.info(msg)
        elif verified_files:
            # ⚠ Partial success
            msg = (
                f"Only {len(verified_files)} out of {len(saved_files)} incident(s) "
                f"were successfully copied before device disconnect."
            )
            self.show_popup(msg)
            logger.warning(msg)
        else:
            #  None saved
            self.show_popup("Failed to create any video files.")
            logger.error("No valid incident videos found after processing.")

        stop_device_monitor(self)
    if not getattr(self, "abort_processing", False):
        Clock.schedule_once(finalize, 0)
    else:
        logger.info("Finalize not scheduled because processing was aborted.")