"""
Backends for Jetpack Joyride RL - Abstraction layer for testability.

This module defines protocols for capture, input, and window operations,
allowing the environment to be tested with fake implementations.
"""

from typing import Protocol, Tuple, List, runtime_checkable
import numpy as np


@runtime_checkable
class CaptureBackend(Protocol):
    """Protocol for screen capture backends."""

    def grab(self) -> np.ndarray:
        """Capture screen region, returns BGR image as numpy array."""
        ...

    def set_region(self, x: int, y: int, w: int, h: int) -> None:
        """Update the capture region."""
        ...

    def close(self) -> None:
        """Release resources."""
        ...


@runtime_checkable
class InputBackend(Protocol):
    """Protocol for keyboard input backends."""

    def key_down(self, vk_code: int) -> None:
        """Send key down event."""
        ...

    def key_up(self, vk_code: int) -> None:
        """Send key up event."""
        ...

    def key_press(self, vk_code: int, press_ms: int = 50) -> None:
        """Send key press (down + delay + up)."""
        ...

    def release_all(self) -> None:
        """Release all currently held keys."""
        ...


@runtime_checkable
class WindowBackend(Protocol):
    """Protocol for window management backends."""

    def find_window(self, title_substr: str) -> int:
        """Find window by title substring, returns hwnd."""
        ...

    def focus_window(self, hwnd: int) -> None:
        """Bring window to foreground."""
        ...

    def get_client_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """Get client area (x, y, width, height) in screen coordinates."""
        ...


# =============================================================================
# Windows Implementations
# =============================================================================

class WindowsCapture:
    """Windows screen capture using mss (foreground) or PrintWindow (background)."""

    def __init__(self, hwnd: int, cap_x: int, cap_y: int, cap_w: int, cap_h: int,
                 background: bool = False, window_backend: 'WindowBackend' = None):
        import mss
        import cv2

        self.hwnd = hwnd
        self.cap_x = int(cap_x)
        self.cap_y = int(cap_y)
        self.cap_w = int(cap_w)
        self.cap_h = int(cap_h)
        self.background = background
        self.window_backend = window_backend

        if not background:
            self.sct = mss.mss()
        else:
            self.sct = None

    def set_region(self, x: int, y: int, w: int, h: int) -> None:
        self.cap_x = int(x)
        self.cap_y = int(y)
        self.cap_w = int(w)
        self.cap_h = int(h)

    def grab(self) -> np.ndarray:
        """Capture screen region, returns BGR image."""
        if self.background:
            return self._grab_bitblt()
        else:
            return self._grab_mss()

    def _grab_mss(self) -> np.ndarray:
        """Foreground capture using mss."""
        import win32gui

        # Get window client area in screen coordinates
        left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
        x0, y0 = win32gui.ClientToScreen(self.hwnd, (0, 0))

        monitor = {
            "left": x0 + self.cap_x,
            "top": y0 + self.cap_y,
            "width": self.cap_w,
            "height": self.cap_h
        }
        img = np.array(self.sct.grab(monitor))
        return img[:, :, :3]  # BGRA -> BGR

    def _grab_bitblt(self) -> np.ndarray:
        """Background capture using PrintWindow."""
        import win32gui
        import win32ui
        import ctypes
        import cv2

        hwnd = self.hwnd

        # Get window dimensions
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bottom - top

        # Create device contexts
        wDC = win32gui.GetWindowDC(hwnd)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        cDC = dcObj.CreateCompatibleDC()

        # Create bitmap
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, width, height)
        cDC.SelectObject(dataBitMap)

        # PrintWindow with PW_RENDERFULLCONTENT
        ctypes.windll.user32.PrintWindow(hwnd, cDC.GetSafeHdc(), 3)

        # Convert to numpy
        bmpinfo = dataBitMap.GetInfo()
        bmpstr = dataBitMap.GetBitmapBits(True)

        img = np.frombuffer(bmpstr, dtype=np.uint8)
        img = img.reshape((bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4))

        # Cleanup
        dcObj.DeleteDC()
        cDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, wDC)
        win32gui.DeleteObject(dataBitMap.GetHandle())

        # Crop to ROI
        img_bgr = img[:, :, :3]
        x1 = max(0, self.cap_x)
        y1 = max(0, self.cap_y)
        x2 = min(width, self.cap_x + self.cap_w)
        y2 = min(height, self.cap_y + self.cap_h)

        cropped = img_bgr[y1:y2, x1:x2]
        if cropped.shape[0] != self.cap_h or cropped.shape[1] != self.cap_w:
            cropped = cv2.resize(cropped, (self.cap_w, self.cap_h))

        return cropped

    def close(self) -> None:
        if self.sct:
            try:
                self.sct.close()
            except Exception:
                pass


class WindowsInput:
    """Windows keyboard input using win32api."""

    def __init__(self, hwnd: int = None, window_backend: 'WindowBackend' = None):
        self.hwnd = hwnd
        self.window_backend = window_backend
        self._held_keys: List[int] = []
        self._last_focused_hwnd = None

    def _ensure_focus(self) -> None:
        """Ensure target window is focused before sending input."""
        if self.hwnd is None:
            return

        import win32gui
        import win32con
        import time

        if self._last_focused_hwnd != self.hwnd:
            try:
                if win32gui.IsIconic(self.hwnd):
                    win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(self.hwnd)
                self._last_focused_hwnd = self.hwnd
                time.sleep(0.02)
            except Exception:
                pass

    def key_down(self, vk_code: int) -> None:
        import win32api

        self._ensure_focus()
        win32api.keybd_event(vk_code, 0, 0, 0)
        if vk_code not in self._held_keys:
            self._held_keys.append(vk_code)

    def key_up(self, vk_code: int) -> None:
        import win32api
        import win32con

        self._ensure_focus()
        win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
        if vk_code in self._held_keys:
            self._held_keys.remove(vk_code)

    def key_press(self, vk_code: int, press_ms: int = 50) -> None:
        import time

        self.key_down(vk_code)
        time.sleep(press_ms / 1000.0)
        self.key_up(vk_code)

    def release_all(self) -> None:
        """Release all held keys."""
        import win32api
        import win32con

        for vk_code in list(self._held_keys):
            try:
                win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
            except Exception:
                pass
        self._held_keys.clear()


class WindowsWindow:
    """Windows window management using win32gui."""

    def find_window(self, title_substr: str) -> int:
        import win32gui

        matches = []
        def enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if title_substr.lower() in title.lower():
                matches.append(hwnd)

        win32gui.EnumWindows(enum_cb, None)

        if not matches:
            raise RuntimeError(f"Could not find window containing '{title_substr}'. Is PPSSPP running?")
        return matches[0]

    def focus_window(self, hwnd: int) -> None:
        import win32gui
        import win32con

        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def get_client_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        import win32gui

        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        x0, y0 = win32gui.ClientToScreen(hwnd, (0, 0))
        return x0, y0, right - left, bottom - top
