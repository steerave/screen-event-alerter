"""
Offline regression tests using the real game screenshots.

These tests validate that:
  1. All configured templates score above threshold on the positive reference screenshot.
  2. All configured templates score below threshold on the negative reference screenshot.
  3. The gap between positive and negative scores is at least 0.20.

They skip automatically if the reference screenshots or templates are missing.
Run these tests after every template recapture or threshold change.

The detector is configured exactly as the watcher will use it at runtime:
  - same threshold from config.yaml
  - same ROI cropped from the full screenshot
  - all configured templates for the event
  - grayscale matching (default)
"""

import os

import cv2
import pytest
import yaml

POSITIVE_REF = "SS - Dig.png"
NEGATIVE_REF = "SS - No Dig.png"
CONFIG_FILE = "config.yaml"


def _load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def _has_refs_and_templates():
    if not os.path.exists(POSITIVE_REF) or not os.path.exists(NEGATIVE_REF):
        return False
    config = _load_config()
    if not config:
        return False
    for evt in config.get("events", []):
        for tpl in evt.get("templates", []):
            if os.path.exists(tpl):
                return True
    return False


def _crop_roi(img, roi: dict):
    """Crop the configured ROI from a full screenshot."""
    x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
    return img[y : y + h, x : x + w]


skip_if_missing = pytest.mark.skipif(
    not _has_refs_and_templates(),
    reason="Reference screenshots or templates not found — run calibration first",
)


@skip_if_missing
def test_all_templates_score_above_threshold_on_positive_screenshot():
    """
    Every configured template must score above threshold on the positive ref.
    A failure here means the template crop is wrong or the threshold is too high.
    """
    from detector import Detector

    config = _load_config()
    pos = cv2.imread(POSITIVE_REF, cv2.IMREAD_COLOR)
    assert pos is not None, f"Could not load {POSITIVE_REF}"

    for evt in config.get("events", []):
        roi = evt["roi"]
        threshold = evt["threshold"]
        pos_crop = _crop_roi(pos, roi)

        for tpl_path in evt.get("templates", []):
            if not os.path.exists(tpl_path):
                continue
            detector = Detector([tpl_path])
            result = detector.match(pos_crop)
            assert result.score >= threshold, (
                f"Event '{evt['name']}', template '{tpl_path}': "
                f"expected score >= {threshold} on positive ref, got {result.score:.3f}. "
                "Re-crop the template or lower the threshold."
            )


@skip_if_missing
def test_all_templates_score_below_threshold_on_negative_screenshot():
    """
    Every configured template must score below threshold on the negative ref.
    A failure here means the template is too generic — re-crop more tightly.
    """
    from detector import Detector

    config = _load_config()
    neg = cv2.imread(NEGATIVE_REF, cv2.IMREAD_COLOR)
    assert neg is not None, f"Could not load {NEGATIVE_REF}"

    for evt in config.get("events", []):
        roi = evt["roi"]
        threshold = evt["threshold"]
        neg_crop = _crop_roi(neg, roi)

        for tpl_path in evt.get("templates", []):
            if not os.path.exists(tpl_path):
                continue
            detector = Detector([tpl_path])
            result = detector.match(neg_crop)
            assert result.score < threshold, (
                f"Event '{evt['name']}', template '{tpl_path}': "
                f"expected score < {threshold} on negative ref, got {result.score:.3f}. "
                "Template may be too generic — re-crop the icon more tightly."
            )


@skip_if_missing
def test_score_gap_is_sufficient_for_reliable_threshold():
    """
    The gap between the positive and negative scores must be >= 0.20.
    A smaller gap means the threshold has little headroom and false positives
    or missed detections are likely.
    """
    from detector import Detector

    config = _load_config()
    pos = cv2.imread(POSITIVE_REF, cv2.IMREAD_COLOR)
    neg = cv2.imread(NEGATIVE_REF, cv2.IMREAD_COLOR)

    for evt in config.get("events", []):
        roi = evt["roi"]
        templates = [t for t in evt.get("templates", []) if os.path.exists(t)]
        if not templates:
            continue

        detector = Detector(templates)
        pos_score = detector.match(_crop_roi(pos, roi)).score
        neg_score = detector.match(_crop_roi(neg, roi)).score
        gap = pos_score - neg_score

        assert gap >= 0.20, (
            f"Event '{evt['name']}': score gap too small "
            f"(positive={pos_score:.3f}, negative={neg_score:.3f}, gap={gap:.3f}). "
            "Need >= 0.20. Re-crop template or adjust ROI."
        )
