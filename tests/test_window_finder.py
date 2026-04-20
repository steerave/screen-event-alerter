from unittest.mock import patch
from window_finder import WindowFinder


class TestWindowFinder:
    def _enum_once(self, hwnd):
        def fake_enum(callback, extra):
            callback(hwnd, None)
        return fake_enum

    def test_find_returns_hwnd_and_title_when_match(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(42)), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", return_value="Last War: Survival"):
            hwnd, title = finder.find("Last War")
        assert hwnd == 42
        assert title == "Last War: Survival"

    def test_find_returns_none_when_no_match(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(42)), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", return_value="Notepad"):
            hwnd, title = finder.find("Last War")
        assert hwnd is None
        assert title is None

    def test_find_ignores_invisible_windows(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(42)), \
             patch("win32gui.IsWindowVisible", return_value=False), \
             patch("win32gui.GetWindowText", return_value="Last War"):
            hwnd, title = finder.find("Last War")
        assert hwnd is None

    def test_find_is_case_insensitive(self):
        finder = WindowFinder()
        with patch("win32gui.EnumWindows", side_effect=self._enum_once(99)), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", return_value="LAST WAR"):
            hwnd, title = finder.find("last war")
        assert hwnd == 99

    def test_find_returns_first_match_when_multiple_exist(self):
        finder = WindowFinder()
        titles = {10: "Last War Instance 1", 20: "Last War Instance 2"}
        def fake_enum(callback, extra):
            callback(10, None)
            callback(20, None)
        with patch("win32gui.EnumWindows", side_effect=fake_enum), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", side_effect=lambda h: titles[h]):
            hwnd, title = finder.find("Last War")
        assert hwnd == 10

    def test_find_records_match_count(self):
        finder = WindowFinder()
        titles = {10: "Last War A", 20: "Last War B"}
        def fake_enum(callback, extra):
            callback(10, None)
            callback(20, None)
        with patch("win32gui.EnumWindows", side_effect=fake_enum), \
             patch("win32gui.IsWindowVisible", return_value=True), \
             patch("win32gui.GetWindowText", side_effect=lambda h: titles[h]):
            finder.find("Last War")
        assert finder.last_match_count == 2

    def test_is_minimized_true_when_iconic(self):
        finder = WindowFinder()
        with patch("win32gui.IsIconic", return_value=True):
            assert finder.is_minimized(42) is True

    def test_is_minimized_false_when_not_iconic(self):
        finder = WindowFinder()
        with patch("win32gui.IsIconic", return_value=False):
            assert finder.is_minimized(42) is False

    def test_get_client_size_returns_width_and_height(self):
        finder = WindowFinder()
        with patch("win32gui.GetClientRect", return_value=(0, 0, 1280, 720)):
            w, h = finder.get_client_size(42)
        assert w == 1280
        assert h == 720

    def test_get_client_rect_combines_origin_and_size(self):
        finder = WindowFinder()
        finder.get_client_size = lambda hwnd: (1280, 720)
        finder._client_to_screen = lambda hwnd: (10, 30)
        rect = finder.get_client_rect(42)
        assert rect == (10, 30, 1290, 750)
