import mss
import numpy as np


class ScreenCapture:
    def __init__(self):
        self._sct = mss.mss()

    def capture_roi(
        self,
        client_rect: tuple[int, int, int, int],
        roi: dict,
    ) -> np.ndarray:
        """
        Capture a region of the screen and return it as a BGR numpy array.

        client_rect: (left, top, right, bottom) of the game window client area
                     in screen coordinates.
        roi: dict with x, y, w, h relative to the client area top-left corner.

        The alpha channel from mss (BGRA) is stripped before returning.
        """
        monitor = {
            "top": client_rect[1] + roi["y"],
            "left": client_rect[0] + roi["x"],
            "width": roi["w"],
            "height": roi["h"],
        }
        screenshot = self._sct.grab(monitor)
        img = np.array(screenshot)
        return img[:, :, :3]
