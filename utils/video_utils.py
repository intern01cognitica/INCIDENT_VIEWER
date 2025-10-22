import cv2, os
from utils.config import IST_OFFSET
from utils.logs import logger,StderrRedirect
from utils.file_utils import clean_camera_name

def group_images_by_incident(images_with_times, gap_seconds=30):
    """
    images_with_times: list of tuples (image_path, timestamp_gmt)
    Groups by time gaps: new group when gap > gap_seconds
    Returns list of groups: each group is list of (image_path, timestamp_gmt)
    """
    groups = []
    current = []
    last_t = None
    for img_path, ts in sorted(images_with_times, key=lambda x: x[1]):
        if not last_t or (ts - last_t).total_seconds() > gap_seconds:
            if current:
                groups.append(current)
            current = [(img_path, ts)]
        else:
            current.append((img_path, ts))
        last_t = ts
    if current:
        groups.append(current)
    return groups

# def create_video_from_image_paths(image_path_and_ts, output_path, fps=5):
#     """
#     Create a playable MP4 video from list of (image_path, timestamp).
#     Ensures consistent frame size and overlays camera + IST timestamp.
#     """
#     if not image_path_and_ts:
#         return False

#     first_img = cv2.imread(image_path_and_ts[0][0])
#     if first_img is None:
#         logger.error("Unable to read first image: %s", image_path_and_ts[0][0])
#         return False

#     height, width = first_img.shape[:2]
#     with StderrRedirect():
#         fourcc = cv2.VideoWriter_fourcc(*'XVID')  # more compatible than mp4v
#         out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

#         font = cv2.FONT_HERSHEY_SIMPLEX
#         font_scale = 0.7
#         thickness = 2

#         for path, ts_gmt in image_path_and_ts:
#             img = cv2.imread(path)
#             if img is None:
#                 continue

#             # resize if needed
#             if img.shape[1] != width or img.shape[0] != height:
#                 img = cv2.resize(img, (width, height))

#             # camera_name = os.path.basename(os.path.dirname(path))
#             raw_name = os.path.basename(os.path.dirname(path))
#             camera_name = clean_camera_name(raw_name)
#             ist_ts = ts_gmt + IST_OFFSET
#             ist_str = ist_ts.strftime("%Y-%m-%d %I:%M:%S %p")
#             overlay = f"{camera_name} | {ist_str}"

#             (text_w, text_h), _ = cv2.getTextSize(overlay, font, font_scale, thickness)
#             text_x = (width - text_w) // 2
#             text_y = 40
#             cv2.rectangle(img, (text_x - 8, text_y - 28),
#                           (text_x + text_w + 8, text_y + 8), (0, 0, 0), -1)
#             cv2.putText(img, overlay, (text_x, text_y),
#                         font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

#             out.write(img)

#         out.release()
#         return True
def create_video_from_image_paths(image_path_and_ts, output_path, fps=5):
    """
    Create a playable MP4 video from list of (image_path, timestamp).
    Ensures consistent frame size and overlays camera + IST timestamp.
    Returns (success: bool, error_msg: str | None).
    """
    if not image_path_and_ts:
        msg = "No images provided for video creation."
        logger.error(msg)
        return False, msg
    MIN_FILE_SIZE = 30 * 1024  # 30 KB
    filtered_paths = [(p, ts) for p, ts in image_path_and_ts if os.path.getsize(p) >= MIN_FILE_SIZE]

    if not filtered_paths:
        msg = "All images are below 30KB or unreadable."
        logger.error(msg)
        return False, msg
    first_img = cv2.imread(image_path_and_ts[0][0])
    if first_img is None:
        msg = f"Unable to read first image: {image_path_and_ts[0][0]}"
        logger.error(msg)
        return False, msg

    try:
        height, width = first_img.shape[:2]
        with StderrRedirect():
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            if not out.isOpened():
                msg = f"Failed to open video writer for {output_path}"
                logger.error(msg)
                return False, msg

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            thickness = 2

            for path, ts_gmt in image_path_and_ts:
                if not out.isOpened():
                    msg = f"Video writer closed unexpectedly while writing {output_path}"
                    logger.error(msg)
                    out.release()
                    return False, "Device disconnected while saving. Videos may be incomplete."
                try:
                    img = cv2.imread(path)
                    if img is None:
                        logger.warning("Skipped unreadable image: %s", path)
                        continue

                    if img.shape[1] != width or img.shape[0] != height:
                        img = cv2.resize(img, (width, height))

                    raw_name = os.path.basename(os.path.dirname(path))
                    camera_name = clean_camera_name(raw_name)
                    ist_ts = ts_gmt + IST_OFFSET
                    ist_str = ist_ts.strftime("%Y-%m-%d %I:%M:%S %p")
                    overlay = f"{camera_name} | {ist_str}"

                    (text_w, text_h), _ = cv2.getTextSize(overlay, font, font_scale, thickness)
                    text_x = (width - text_w) // 2
                    text_y = 40
                    cv2.rectangle(img, (text_x - 8, text_y - 28),
                                  (text_x + text_w + 8, text_y + 8), (0, 0, 0), -1)
                    cv2.putText(img, overlay, (text_x, text_y),
                                font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

                    out.write(img)

                except Exception as e:
                    # log per-image exception with full traceback
                    logger.exception("Error processing image %s", path)

            out.release()
        return True, None

    except Exception as e:
        msg = f"Error while creating video {output_path}"
        # full traceback here
        logger.exception(msg)
        return False, msg

