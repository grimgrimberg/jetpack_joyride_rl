"""
Fake capture backend for testing.

Returns deterministic frames from fixtures or generated test patterns.
"""

from typing import Optional
import numpy as np


class FakeCapture:
    """Fake capture backend that returns predetermined frames."""
    
    def __init__(
        self,
        frames: Optional[list] = None,
        default_frame: Optional[np.ndarray] = None,
        width: int = 480,
        height: int = 272,
    ):
        """
        Args:
            frames: List of frames to cycle through on each grab()
            default_frame: Frame to return if no frames list provided
            width: Default frame width
            height: Default frame height
        """
        self.frames = frames or []
        self.frame_index = 0
        self.width = width
        self.height = height
        self.grab_count = 0
        
        self.cap_x = 0
        self.cap_y = 0
        self.cap_w = width
        self.cap_h = height
        
        if default_frame is not None:
            self.default_frame = default_frame
        else:
            # Generate a gradient test pattern
            self.default_frame = self._generate_test_pattern()
        
        self.closed = False
    
    def _generate_test_pattern(self) -> np.ndarray:
        """Generate a gradient test pattern frame."""
        # Create gradient pattern (varies over time based on grab_count)
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        for y in range(self.height):
            for x in range(self.width):
                frame[y, x, 0] = (x * 255 // self.width) % 256  # B
                frame[y, x, 1] = (y * 255 // self.height) % 256  # G
                frame[y, x, 2] = 128  # R
        return frame
    
    def set_region(self, x: int, y: int, w: int, h: int) -> None:
        self.cap_x = x
        self.cap_y = y
        self.cap_w = w
        self.cap_h = h
    
    def grab(self) -> np.ndarray:
        """Return next frame in sequence or default."""
        self.grab_count += 1
        
        if self.frames:
            frame = self.frames[self.frame_index % len(self.frames)]
            self.frame_index += 1
            return frame.copy()
        
        # Modify default frame slightly each time to simulate motion
        frame = self.default_frame.copy()
        # Add some variation based on grab count
        frame = np.roll(frame, self.grab_count % 10, axis=1)
        return frame
    
    def close(self) -> None:
        self.closed = True


class BlackFrameCapture(FakeCapture):
    """Fake capture that returns all-black frames (simulates PrintWindow failure)."""
    
    def __init__(self, width: int = 480, height: int = 272):
        black_frame = np.zeros((height, width, 3), dtype=np.uint8)
        super().__init__(default_frame=black_frame, width=width, height=height)


class StaticFrameCapture(FakeCapture):
    """Fake capture that returns identical frames (simulates frozen screen / game over)."""
    
    def __init__(self, width: int = 480, height: int = 272, brightness: int = 128):
        static_frame = np.full((height, width, 3), brightness, dtype=np.uint8)
        super().__init__(default_frame=static_frame, width=width, height=height)
    
    def grab(self) -> np.ndarray:
        """Always return the exact same frame (no motion)."""
        self.grab_count += 1
        return self.default_frame.copy()
