import numpy as np
from unittest.mock import patch, MagicMock
from screen_capture import ScreenCapture


class TestScreenCapture:
    def test_capture_roi_translates_window_relative_coords(self):
        captured_monitor = {}

        def fake_grab(monitor):
            captured_monitor.update(monitor)
            return np.zeros((monitor["height"], monitor["width"], 4), dtype=np.uint8)

        with patch("mss.mss") as mock_mss_cls:
            mock_mss_cls.return_value = MagicMock()
            cap = ScreenCapture()
            cap._sct.grab = fake_grab
            cap.capture_roi((100, 200, 1380, 920), {"x": 50, "y": 30, "w": 80, "h": 60})

        assert captured_monitor["left"] == 150    # 100 + 50
        assert captured_monitor["top"] == 230     # 200 + 30
        assert captured_monitor["width"] == 80
        assert captured_monitor["height"] == 60

    def test_capture_roi_strips_alpha_channel(self):
        def fake_grab(monitor):
            return np.zeros((monitor["height"], monitor["width"], 4), dtype=np.uint8)

        with patch("mss.mss") as mock_mss_cls:
            mock_mss_cls.return_value = MagicMock()
            cap = ScreenCapture()
            cap._sct.grab = fake_grab
            result = cap.capture_roi((0, 0, 1280, 720), {"x": 10, "y": 10, "w": 50, "h": 40})

        assert result.shape == (40, 50, 3)

    def test_capture_roi_returns_uint8_numpy_array(self):
        def fake_grab(monitor):
            return np.zeros((monitor["height"], monitor["width"], 4), dtype=np.uint8)

        with patch("mss.mss") as mock_mss_cls:
            mock_mss_cls.return_value = MagicMock()
            cap = ScreenCapture()
            cap._sct.grab = fake_grab
            result = cap.capture_roi((0, 0, 1280, 720), {"x": 0, "y": 0, "w": 100, "h": 100})

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
