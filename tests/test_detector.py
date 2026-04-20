import os
import tempfile

import cv2
import numpy as np
import pytest

from detector import Detector, DetectionResult


class TestDetector:
    def _write_template(self, color: tuple, size: tuple = (20, 20)) -> str:
        # Solid-color templates have zero variance and break TM_CCOEFF_NORMED.
        # Use a structured template: black border + colored interior.
        h, w = size[1], size[0]
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[2:h - 2, 2:w - 2] = color
        path = tempfile.mktemp(suffix=".png")
        cv2.imwrite(path, img)
        return path

    def test_match_returns_detection_result(self):
        path = self._write_template(color=(0, 200, 0))
        try:
            detector = Detector([path])
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            result = detector.match(frame)
            assert isinstance(result, DetectionResult)
            assert isinstance(result.score, float)
            assert isinstance(result.template_path, str)
            assert isinstance(result.location, tuple) and len(result.location) == 2
        finally:
            os.unlink(path)

    def test_match_returns_high_confidence_when_template_present(self):
        path = self._write_template(color=(0, 200, 0), size=(20, 20))
        try:
            detector = Detector([path])
            template_img = cv2.imread(path, cv2.IMREAD_COLOR)
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[10:30, 10:30] = template_img   # embed exact template in frame
            result = detector.match(frame)
            assert result.score > 0.95
            assert result.template_path == path
        finally:
            os.unlink(path)

    def test_match_returns_low_confidence_when_template_absent(self):
        path = self._write_template(color=(0, 200, 0))
        try:
            detector = Detector([path])
            frame = np.full((100, 100, 3), 128, dtype=np.uint8)
            result = detector.match(frame)
            assert result.score < 0.5
        finally:
            os.unlink(path)

    def test_match_returns_zero_when_frame_smaller_than_template(self):
        path = self._write_template(color=(0, 200, 0), size=(50, 50))
        try:
            detector = Detector([path])
            frame = np.zeros((20, 20, 3), dtype=np.uint8)
            result = detector.match(frame)
            assert result.score == 0.0
        finally:
            os.unlink(path)

    def test_match_picks_best_score_across_multiple_templates(self):
        # Use maximally distinct grayscale intensities: white interior vs mid-gray.
        # Frame contains the white template; mid-gray template should score lower.
        path_good = self._write_template(color=(255, 255, 255), size=(20, 20))
        path_bad = self._write_template(color=(100, 100, 100), size=(20, 20))
        try:
            detector = Detector([path_bad, path_good])
            good_img = cv2.imread(path_good, cv2.IMREAD_COLOR)
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[10:30, 10:30] = good_img   # embed path_good template exactly
            result = detector.match(frame)
            assert result.score > 0.95
            assert result.template_path == path_good
        finally:
            os.unlink(path_good)
            os.unlink(path_bad)

    def test_raises_file_not_found_for_missing_template(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            Detector(["nonexistent_xyz.png"])

    def test_raises_value_error_for_empty_template_list(self):
        with pytest.raises(ValueError, match="at least one"):
            Detector([])

    def test_is_blank_true_for_dark_frame(self):
        assert Detector.is_blank(np.zeros((100, 100, 3), dtype=np.uint8)) is True

    def test_is_blank_false_for_bright_frame(self):
        assert Detector.is_blank(np.full((100, 100, 3), 128, dtype=np.uint8)) is False

    def test_is_blank_respects_custom_threshold(self):
        mid = np.full((10, 10, 3), 20, dtype=np.uint8)
        assert Detector.is_blank(mid, min_brightness=30.0) is True
        assert Detector.is_blank(mid, min_brightness=10.0) is False
