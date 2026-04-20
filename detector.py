from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class DetectionResult:
    score: float                  # best confidence across all templates, 0.0–1.0
    template_path: str            # which template produced the best score
    location: tuple[int, int]     # (x, y) of the best match within the frame


class Detector:
    """
    Matches one or more template images against a frame using normalized
    cross-correlation. Returns the best result across all templates.

    Grayscale matching is used by default: more robust to lighting/tint
    variation between game states, and faster than colour matching.
    Set grayscale=False only if icon colour is the primary distinguishing
    feature and background colour is identical to the icon in greyscale.
    """

    def __init__(self, template_paths: list[str], grayscale: bool = True):
        if not template_paths:
            raise ValueError("Detector requires at least one template path.")
        self._grayscale = grayscale
        self._templates: list[tuple[str, np.ndarray]] = []
        for path in template_paths:
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is None:
                raise FileNotFoundError(f"Template not found: {path}")
            if grayscale:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            self._templates.append((path, img))

    def match(self, frame: np.ndarray) -> DetectionResult:
        """Score all templates against frame; return the highest-confidence result."""
        if self._grayscale:
            frame_to_match = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            frame_to_match = frame

        best = DetectionResult(score=0.0, template_path="", location=(0, 0))

        for path, template in self._templates:
            th, tw = template.shape[:2]
            fh, fw = frame_to_match.shape[:2]
            if fh < th or fw < tw:
                continue
            result = cv2.matchTemplate(frame_to_match, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if float(max_val) > best.score:
                best = DetectionResult(
                    score=float(max_val),
                    template_path=path,
                    location=(max_loc[0], max_loc[1]),
                )

        return best

    @staticmethod
    def is_blank(frame: np.ndarray, min_brightness: float = 10.0) -> bool:
        """
        Return True if the frame is too dark to be worth matching.

        Useful for skipping matchTemplate when the game is not visible (minimized,
        occluded). Disable per-event via blank_prefilter: false if the event icon
        appears against a very dark background — the prefilter would suppress it.
        """
        return float(np.mean(frame)) < min_brightness
