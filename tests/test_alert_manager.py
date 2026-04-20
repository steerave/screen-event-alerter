import time
import numpy as np
from unittest.mock import patch, MagicMock
from alert_manager import AlertManager


class TestAlertManager:
    def test_fire_sound_calls_winsound_beep_with_configured_values(self):
        mgr = AlertManager()
        with patch("winsound.Beep") as mock_beep:
            mgr.fire_sound(frequency=1000, duration=300)
            mock_beep.assert_called_once_with(1000, 300)

    def test_fire_sound_does_not_raise_on_failure(self):
        mgr = AlertManager()
        with patch("winsound.Beep", side_effect=Exception("audio error")):
            mgr.fire_sound(frequency=1000, duration=300)   # must not raise

    def test_fire_toast_does_not_raise_when_unavailable(self):
        mgr = AlertManager()
        with patch("alert_manager._TOAST_AVAILABLE", False):
            mgr.fire_toast("Title", "Message")

    def test_fire_toast_calls_show_toast_when_available(self):
        mgr = AlertManager()
        mock_notifier = MagicMock()
        with patch("alert_manager._TOAST_AVAILABLE", True), \
             patch("alert_manager.ToastNotifier", return_value=mock_notifier):
            mgr.fire_toast("Last War Alert", "Test message")
        mock_notifier.show_toast.assert_called_once_with(
            "Last War Alert", "Test message", duration=5, threaded=True
        )

    def test_fire_toast_does_not_raise_on_notifier_failure(self):
        mgr = AlertManager()
        with patch("alert_manager._TOAST_AVAILABLE", True), \
             patch("alert_manager.ToastNotifier", side_effect=Exception("toast error")):
            mgr.fire_toast("Title", "Message")   # must not raise

    def test_fire_slack_posts_to_webhook_asynchronously(self):
        mgr = AlertManager()
        with patch("requests.post") as mock_post:
            mgr.fire_slack("https://hooks.slack.com/fake", "Alert")
            time.sleep(0.2)
            mock_post.assert_called_once_with(
                "https://hooks.slack.com/fake",
                json={"text": "Alert"},
                timeout=10,
            )

    def test_fire_slack_does_not_raise_on_network_error(self):
        mgr = AlertManager()
        with patch("requests.post", side_effect=Exception("network down")):
            mgr.fire_slack("https://hooks.slack.com/fake", "Alert")
            time.sleep(0.2)   # must not raise from the thread

    def test_save_roi_crop_creates_file_with_event_name(self, tmp_path):
        mgr = AlertManager(debug_dir=str(tmp_path))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mgr.save_roi_crop(frame, "dig_event", score=0.92, template_name="dig_event.png")
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert "dig_event" in files[0].name
        assert files[0].suffix == ".png"

    def test_save_roi_crop_includes_score_in_filename(self, tmp_path):
        mgr = AlertManager(debug_dir=str(tmp_path))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mgr.save_roi_crop(frame, "dig_event", score=0.923, template_name="t.png")
        files = list(tmp_path.iterdir())
        assert "0.923" in files[0].name

    def test_save_annotated_window_draws_roi_rectangle(self, tmp_path):
        mgr = AlertManager(debug_dir=str(tmp_path))
        window = np.zeros((720, 1280, 3), dtype=np.uint8)
        roi = {"x": 100, "y": 400, "w": 80, "h": 80}
        mgr.save_annotated_window(window, roi, "dig_event", score=0.92)
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert "dig_event" in files[0].name

    def test_save_roi_crop_does_not_raise_on_write_failure(self, tmp_path):
        mgr = AlertManager(debug_dir=str(tmp_path))
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with patch("cv2.imwrite", return_value=False):
            mgr.save_roi_crop(frame, "dig_event", score=0.9, template_name="t.png")
