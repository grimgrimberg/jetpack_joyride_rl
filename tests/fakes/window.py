"""
Fake window backend for testing.

Provides mock window handle and coordinates.
"""

from typing import Tuple, Dict


class FakeWindow:
    """Fake window backend for testing."""
    
    def __init__(
        self,
        mock_hwnd: int = 12345,
        client_rect: Tuple[int, int, int, int] = (100, 100, 960, 544),
        title: str = "PPSSPP v1.0 - Jetpack Joyride"
    ):
        """
        Args:
            mock_hwnd: Window handle to return
            client_rect: (x, y, width, height) to return from get_client_rect
            title: Window title for matching
        """
        self.mock_hwnd = mock_hwnd
        self.client_rect = client_rect
        self.title = title
        
        self.find_count = 0
        self.focus_count = 0
        self.get_rect_count = 0
        
        # Track what operations were called
        self._focused_hwnds: list = []
    
    def find_window(self, title_substr: str) -> int:
        """Return mock hwnd if title matches."""
        self.find_count += 1
        
        if title_substr.lower() in self.title.lower():
            return self.mock_hwnd
        
        raise RuntimeError(f"Could not find window containing '{title_substr}'. Is PPSSPP running?")
    
    def focus_window(self, hwnd: int) -> None:
        """Record focus call."""
        self.focus_count += 1
        self._focused_hwnds.append(hwnd)
    
    def get_client_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """Return mock client rectangle."""
        self.get_rect_count += 1
        return self.client_rect


class NotFoundWindow(FakeWindow):
    """Fake window that always fails to find the window."""
    
    def find_window(self, title_substr: str) -> int:
        self.find_count += 1
        raise RuntimeError(f"Could not find window containing '{title_substr}'. Is PPSSPP running?")
