import ctypes
import ctypes.wintypes

import win32gui


class WindowFinder:
    """
    Locates a game window by partial title match and provides client-area geometry.

    Extension point: find() accepts optional process_name and window_class kwargs
    (unused in v1) so callers can pass them without breaking the interface when
    those validations are added later.
    """

    def __init__(self):
        self.last_match_count: int = 0

    def find(
        self,
        title_substring: str,
        *,
        process_name: str | None = None,   # reserved for v2 validation
        window_class: str | None = None,   # reserved for v2 validation
    ) -> tuple[int | None, str | None]:
        """
        Return (hwnd, exact_title) for the first visible window whose title
        contains title_substring (case-insensitive), or (None, None) if not found.
        Sets self.last_match_count to the total number of matching windows found.
        """
        found: list[tuple[int, str]] = []

        def callback(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if title_substring.lower() in title.lower():
                found.append((hwnd, title))

        win32gui.EnumWindows(callback, None)
        self.last_match_count = len(found)

        # TODO (v2): if process_name is set, filter found by process name via
        # win32process.GetWindowThreadProcessId + win32api.OpenProcess
        # TODO (v2): if window_class is set, filter by win32gui.GetClassName(hwnd)

        return (found[0][0], found[0][1]) if found else (None, None)

    def is_minimized(self, hwnd: int) -> bool:
        return bool(win32gui.IsIconic(hwnd))

    def get_client_size(self, hwnd: int) -> tuple[int, int]:
        rect = win32gui.GetClientRect(hwnd)
        return (rect[2], rect[3])

    def get_client_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        """Return (left, top, right, bottom) of the client area in screen coordinates."""
        w, h = self.get_client_size(hwnd)
        left, top = self._client_to_screen(hwnd)
        return (left, top, left + w, top + h)

    def _client_to_screen(self, hwnd: int) -> tuple[int, int]:
        pt = ctypes.wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
        return (pt.x, pt.y)
