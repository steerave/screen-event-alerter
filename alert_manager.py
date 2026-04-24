import os
import threading
from datetime import datetime

import cv2
import numpy as np
import requests
import winsound

try:
    from win10toast import ToastNotifier
    _TOAST_AVAILABLE = True
except ImportError:
    _TOAST_AVAILABLE = False


class AlertManager:
    def __init__(self, debug_dir: str = "debug_screenshots"):
        self._debug_dir = debug_dir

    def fire_sound(
        self,
        frequency: int = 1000,
        duration: int = 300,
        sound_name: str | None = None,
        sound_file: str | None = None,
        beep_pattern: list[list[int]] | None = None,
    ) -> None:
        if beep_pattern:
            def _play_pattern():
                try:
                    for freq, dur in beep_pattern:
                        winsound.Beep(int(freq), int(dur))
                except Exception:
                    pass
            threading.Thread(target=_play_pattern, daemon=True).start()
        elif sound_file:
            try:
                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass
        elif sound_name:
            try:
                winsound.PlaySound(sound_name, winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass
        else:
            try:
                winsound.Beep(frequency, duration)
            except Exception:
                pass

    def fire_toast(self, title: str, message: str) -> None:
        """Show a Windows toast notification (non-blocking via threaded=True)."""
        if not _TOAST_AVAILABLE:
            return
        try:
            notifier = ToastNotifier()
            notifier.show_toast(title, message, duration=5, threaded=True)
        except Exception:
            pass

    def fire_slack(self, webhook_url: str, message: str) -> None:
        """POST to Slack webhook in a daemon thread (non-blocking)."""
        def _send():
            try:
                requests.post(webhook_url, json={"text": message}, timeout=10)
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()

    def save_roi_crop(
        self,
        frame: np.ndarray,
        event_name: str,
        score: float,
        template_name: str,
    ) -> None:
        """Save the ROI frame with score and template name in the filename."""
        try:
            os.makedirs(self._debug_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            tname = os.path.splitext(os.path.basename(template_name))[0]
            filename = os.path.join(
                self._debug_dir,
                f"{event_name}_{score:.3f}_{tname}_{ts}_roi.png",
            )
            cv2.imwrite(filename, frame)
        except Exception:
            pass

    def save_annotated_window(
        self,
        window_frame: np.ndarray,
        roi: dict,
        event_name: str,
        score: float,
    ) -> None:
        """
        Save the full window screenshot with a rectangle drawn around the ROI.
        Provides visual context for debugging false positives or missed detections.
        """
        try:
            os.makedirs(self._debug_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            annotated = window_frame.copy()
            x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                annotated,
                f"{event_name} {score:.3f}",
                (x, max(y - 8, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )
            filename = os.path.join(
                self._debug_dir,
                f"{event_name}_{score:.3f}_{ts}_window.png",
            )
            cv2.imwrite(filename, annotated)
        except Exception:
            pass
