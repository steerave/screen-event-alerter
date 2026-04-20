"""
Calibration probe — prints live confidence scores for each configured event.
No alerts are fired. Use this to:

  1. Verify the ROI (x, y, w, h) covers the correct game window area.
  2. Observe confidence scores in both event-present and event-absent states.
  3. Confirm a clear gap (>= 0.20) exists to set a reliable threshold.

Usage:
    python calibrate.py               # live scoring only
    python calibrate.py --save-crops  # also save ROI crops to debug_crops/

Crop-saving captures up to 5 POSITIVE (near-hit) and 5 NEGATIVE (clear miss)
samples per event. Open them to visually confirm the ROI is positioned correctly.

After calibration, update config.yaml:
  - Set roi.x, roi.y, roi.w, roi.h to match the icon location
  - Set threshold = (lowest positive score observed) - 0.10
  - Verify gap >= 0.20 between baseline and peak
"""

import argparse
import ctypes
import os
import sys
import time
from datetime import datetime

import cv2
import yaml

from detector import Detector
from screen_capture import ScreenCapture
from window_finder import WindowFinder


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def save_crop(frame, label: str, event_name: str, debug_dir: str) -> None:
    os.makedirs(debug_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = os.path.join(debug_dir, f"{label}_{event_name}_{ts}.png")
    cv2.imwrite(path, frame)


def main() -> None:
    set_dpi_aware()

    parser = argparse.ArgumentParser(description="Last War Alert Watcher — calibration probe")
    parser.add_argument(
        "--save-crops",
        action="store_true",
        help="Save positive and negative ROI crops to debug_crops/",
    )
    args = parser.parse_args()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    window_title: str = config["window_title"]
    poll_fps: int = config.get("poll_fps", 2)
    poll_interval = 1.0 / poll_fps
    debug_dir = "debug_crops"
    CROP_CAP = 5

    events = config.get("events", [])
    if not events:
        print("No events defined in config.yaml.")
        sys.exit(1)

    detectors: list[tuple[dict, Detector]] = []
    for evt in events:
        templates = evt.get("templates", [])
        try:
            detectors.append((evt, Detector(templates)))
            print(f"Loaded {len(templates)} template(s) for '{evt['name']}':")
            for t in templates:
                print(f"  {t}")
        except (FileNotFoundError, ValueError) as e:
            print(f"WARNING: {e} — skipping '{evt['name']}'")

    if not detectors:
        print("No templates loaded. Create template images in templates/ first.")
        sys.exit(1)

    pos_counts = {d[0]["name"]: 0 for d in detectors}
    neg_counts = {d[0]["name"]: 0 for d in detectors}

    finder = WindowFinder()
    capture = ScreenCapture()

    print(f"\nCalibration mode — polling '{window_title}' at {poll_fps} FPS")
    if args.save_crops:
        print(f"Saving crops to {debug_dir}/ (max {CROP_CAP} positive + {CROP_CAP} negative per event)")
    print("Press Ctrl+C to stop.\n")

    col_w = 36
    header = "  ".join(f"{d[0]['name']:>{col_w}}" for d in detectors)
    print(f"  {header}")

    try:
        while True:
            loop_start = time.monotonic()

            hwnd, matched_title = finder.find(window_title)
            if hwnd is None:
                print(f"\r{'[window not found]':>{col_w}}", end="", flush=True)
                time.sleep(1)
                continue
            if finder.is_minimized(hwnd):
                print(f"\r{'[minimized]':>{col_w}}", end="", flush=True)
                time.sleep(1)
                continue

            client_rect = finder.get_client_rect(hwnd)
            cols = []

            for evt, detector in detectors:
                name = evt["name"]
                threshold = evt["threshold"]
                frame = capture.capture_roi(client_rect, evt["roi"])
                result = detector.match(frame)
                tname = os.path.basename(result.template_path) if result.template_path else "-"
                hit = " HIT" if result.score >= threshold else "    "
                cols.append(f"{result.score:.3f}{hit} [{tname}]")

                if args.save_crops:
                    if result.score >= threshold * 0.8 and pos_counts[name] < CROP_CAP:
                        save_crop(frame, "POSITIVE", name, debug_dir)
                        pos_counts[name] += 1
                    elif result.score < threshold * 0.3 and neg_counts[name] < CROP_CAP:
                        save_crop(frame, "NEGATIVE", name, debug_dir)
                        neg_counts[name] += 1

            line = "  ".join(f"{c:>{col_w}}" for c in cols)
            print(f"\r{line}", end="", flush=True)

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0.0, poll_interval - elapsed))

    except KeyboardInterrupt:
        print("\nCalibration stopped.")


if __name__ == "__main__":
    main()
