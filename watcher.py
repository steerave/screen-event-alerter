"""
Last War Alert Watcher — main entry point.

Run:   python watcher.py
Stop:  Ctrl+C
"""

import ctypes
import logging
import os
import sys
import time
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv

from alert_manager import AlertManager
from detector import Detector
from event_state import EventState
from screen_capture import ScreenCapture
from window_finder import WindowFinder

_ALLOWED_DETECTION_MODES = {"template"}


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def setup_logging(debug: bool) -> logging.Logger:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("watcher")


@dataclass
class EventConfig:
    name: str
    templates: list[str]
    roi: dict
    threshold: float
    consecutive_hits_required: int
    cooldown_seconds: int
    blank_prefilter: bool
    alert_sound: bool
    alert_sound_file: str | None
    alert_sound_name: str | None
    alert_sound_frequency: int
    alert_sound_duration: int
    alert_beep_pattern: list[list[int]] | None
    alert_toast: bool
    alert_slack: bool
    slack_message: str
    grayscale: bool
    detector: Detector = field(init=False)

    def __post_init__(self):
        self.detector = Detector(self.templates, grayscale=self.grayscale)


def validate_config(config: dict) -> list[str]:
    """Return a list of validation error strings. Empty means valid."""
    errors: list[str] = []

    poll_fps = config.get("poll_fps", 2)
    if not isinstance(poll_fps, (int, float)) or poll_fps <= 0:
        errors.append(f"poll_fps must be > 0, got: {poll_fps!r}")

    window_w = config.get("window_width")
    window_h = config.get("window_height")
    if not window_w or not window_h:
        errors.append("window_width and window_height must be set in config.yaml")

    events = config.get("events", [])
    if not events:
        errors.append("No events defined in config.yaml")
        return errors

    for i, evt in enumerate(events):
        prefix = f"events[{i}] '{evt.get('name', '?')}'"

        mode = evt.get("detection_mode", "template")
        if mode not in _ALLOWED_DETECTION_MODES:
            errors.append(f"{prefix}: detection_mode '{mode}' not supported (allowed: {_ALLOWED_DETECTION_MODES})")

        threshold = evt.get("threshold")
        if threshold is None or not (0.0 <= float(threshold) <= 1.0):
            errors.append(f"{prefix}: threshold must be 0.0–1.0, got: {threshold!r}")

        templates = evt.get("templates", [])
        if not templates:
            errors.append(f"{prefix}: must have at least one template")
        else:
            for tpl in templates:
                if not os.path.exists(tpl):
                    errors.append(f"{prefix}: template not found: {tpl}")

        roi = evt.get("roi", {})
        roi_w = roi.get("w", 0)
        roi_h = roi.get("h", 0)
        roi_x = roi.get("x", 0)
        roi_y = roi.get("y", 0)
        if roi_w <= 0:
            errors.append(f"{prefix}: roi.w must be > 0, got: {roi_w}")
        if roi_h <= 0:
            errors.append(f"{prefix}: roi.h must be > 0, got: {roi_h}")
        if window_w and roi_x + roi_w > window_w:
            errors.append(f"{prefix}: roi extends beyond window_width ({roi_x}+{roi_w} > {window_w})")
        if window_h and roi_y + roi_h > window_h:
            errors.append(f"{prefix}: roi extends beyond window_height ({roi_y}+{roi_h} > {window_h})")

        hits = evt.get("consecutive_hits_required", 2)
        if not isinstance(hits, int) or hits < 1:
            errors.append(f"{prefix}: consecutive_hits_required must be >= 1, got: {hits!r}")

        cooldown = evt.get("cooldown_seconds", 60)
        if not isinstance(cooldown, (int, float)) or cooldown < 0:
            errors.append(f"{prefix}: cooldown_seconds must be >= 0, got: {cooldown!r}")

    return errors


def load_events(config: dict, log: logging.Logger) -> list[EventConfig]:
    loaded = []
    for raw in config.get("events", []):
        try:
            evt = EventConfig(
                name=raw["name"],
                templates=raw["templates"],
                roi=raw["roi"],
                threshold=raw["threshold"],
                consecutive_hits_required=raw.get("consecutive_hits_required", 2),
                cooldown_seconds=raw.get("cooldown_seconds", 60),
                blank_prefilter=raw.get("blank_prefilter", True),
                alert_sound=raw.get("alert_sound", True),
                alert_sound_file=raw.get("alert_sound_file"),
                alert_sound_name=raw.get("alert_sound_name"),
                alert_sound_frequency=raw.get("alert_sound_frequency", 1000),
                alert_sound_duration=raw.get("alert_sound_duration", 300),
                alert_beep_pattern=raw.get("alert_beep_pattern"),
                alert_toast=raw.get("alert_toast", True),
                alert_slack=raw.get("alert_slack", False),
                slack_message=raw.get("slack_message", raw["name"]),
                grayscale=raw.get("grayscale", True),
            )
            loaded.append(evt)
            log.info(f"Loaded '{evt.name}' with {len(evt.templates)} template(s)")
        except (FileNotFoundError, ValueError, KeyError) as e:
            log.error(f"Skipping event '{raw.get('name', '?')}': {e}")
    return loaded


def _warn_if_errors(state: EventState, name: str, log: logging.Logger) -> None:
    n = state.consecutive_errors
    if n == 5 or (n > 5 and n % 10 == 0):
        log.warning(f"{name}: {n} consecutive capture/detect errors")


def main() -> None:
    set_dpi_aware()
    load_dotenv()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    debug_mode: bool = config.get("debug_mode", False)
    log = setup_logging(debug_mode)

    errors = validate_config(config)
    if errors:
        for err in errors:
            log.error(f"Config error: {err}")
        sys.exit(1)

    window_title: str = config["window_title"]
    expected_w: int = config["window_width"]
    expected_h: int = config["window_height"]
    poll_fps: float = config.get("poll_fps", 2)
    poll_interval = 1.0 / poll_fps
    slack_url: str = os.getenv("SLACK_WEBHOOK_URL", "")

    events = load_events(config, log)
    if not events:
        log.error("No events loaded. Check config.yaml and template files.")
        sys.exit(1)

    event_states = {
        evt.name: EventState(
            consecutive_hits_required=evt.consecutive_hits_required,
            cooldown_seconds=evt.cooldown_seconds,
        )
        for evt in events
    }
    finder = WindowFinder()
    capture = ScreenCapture()
    alert_mgr = AlertManager(debug_dir="debug_screenshots")

    log.info(f"Watching '{window_title}' at {poll_fps} FPS. Ctrl+C to stop.")

    last_not_found_log: float = 0.0
    last_warned_size: tuple | None = None
    logged_window_title: bool = False

    try:
        while True:
            loop_start = time.monotonic()

            hwnd, matched_title = finder.find(window_title)

            if hwnd is None:
                logged_window_title = False
                now = time.monotonic()
                if now - last_not_found_log > 60:
                    log.warning(f"Window '{window_title}' not found — will retry")
                    last_not_found_log = now
                time.sleep(max(0.0, poll_interval - (time.monotonic() - loop_start)))
                continue

            if not logged_window_title:
                log.info(f"Window found: '{matched_title}'")
                if finder.last_match_count > 1:
                    log.warning(
                        f"{finder.last_match_count} windows match '{window_title}'. "
                        "Using first match. Close duplicate windows if detection is unreliable."
                    )
                logged_window_title = True

            if finder.is_minimized(hwnd):
                time.sleep(max(0.0, poll_interval - (time.monotonic() - loop_start)))
                continue

            w, h = finder.get_client_size(hwnd)
            if (w, h) != (expected_w, expected_h) and (w, h) != last_warned_size:
                log.warning(
                    f"Window size mismatch: expected {expected_w}x{expected_h}, "
                    f"got {w}x{h}. ROIs and templates may be misaligned."
                )
                last_warned_size = (w, h)
            elif (w, h) == (expected_w, expected_h):
                last_warned_size = None

            client_rect = finder.get_client_rect(hwnd)

            for evt in events:
                state = event_states[evt.name]

                try:
                    frame = capture.capture_roi(client_rect, evt.roi)
                    state.clear_errors()
                except Exception as e:
                    log.error(f"{evt.name}: capture failed: {e}")
                    state.increment_error()
                    _warn_if_errors(state, evt.name, log)
                    continue

                if evt.blank_prefilter and Detector.is_blank(frame):
                    log.debug(f"{evt.name}: blank frame — treating as absent")
                    state.update(above_threshold=False)
                    continue

                try:
                    result = evt.detector.match(frame)
                    state.clear_errors()
                except Exception as e:
                    log.error(f"{evt.name}: detection failed: {e}")
                    state.increment_error()
                    _warn_if_errors(state, evt.name, log)
                    continue

                above = result.score >= evt.threshold
                log.debug(
                    f"{evt.name}: score={result.score:.3f} "
                    f"hits={state.consecutive_hits} "
                    f"template={os.path.basename(result.template_path)}"
                )

                should_alert = state.update(above_threshold=above)

                if should_alert:
                    log.info(
                        f"DETECTED: {evt.name} "
                        f"score={result.score:.3f} "
                        f"template={os.path.basename(result.template_path)}"
                    )

                    if evt.alert_sound:
                        alert_mgr.fire_sound(
                            frequency=evt.alert_sound_frequency,
                            duration=evt.alert_sound_duration,
                            sound_file=evt.alert_sound_file,
                            sound_name=evt.alert_sound_name,
                            beep_pattern=evt.alert_beep_pattern,
                        )

                    if evt.alert_toast:
                        alert_mgr.fire_toast("Last War Alert", evt.slack_message)

                    if evt.alert_slack and slack_url:
                        alert_mgr.fire_slack(slack_url, evt.slack_message)

                    if debug_mode:
                        alert_mgr.save_roi_crop(
                            frame,
                            evt.name,
                            score=result.score,
                            template_name=result.template_path,
                        )
                        try:
                            full_roi = {"x": 0, "y": 0, "w": expected_w, "h": expected_h}
                            window_frame = capture.capture_roi(client_rect, full_roi)
                            alert_mgr.save_annotated_window(
                                window_frame, evt.roi, evt.name, score=result.score
                            )
                        except Exception as e:
                            log.debug(f"{evt.name}: could not save annotated window: {e}")

            time.sleep(max(0.0, poll_interval - (time.monotonic() - loop_start)))

    except KeyboardInterrupt:
        log.info("Watcher stopped.")


if __name__ == "__main__":
    main()
