"""
Tests for preprocessing functions.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))


def preprocess_frame(frame_bgr: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """Convert to grayscale and resize."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (out_w, out_h), interpolation=cv2.INTER_AREA)
    return resized


class TestPreprocessFrame:
    """Tests for the preprocess_frame function."""

    def test_grayscale_conversion(self, sample_bgr_frame):
        """FR-4.1: Convert to grayscale."""
        result = preprocess_frame(sample_bgr_frame, 84, 84)

        # Should be 2D (grayscale)
        assert len(result.shape) == 2

    def test_resize_to_84x84(self, sample_bgr_frame):
        """FR-4.2: Resize to 84x84 pixels."""
        result = preprocess_frame(sample_bgr_frame, 84, 84)

        assert result.shape == (84, 84)

    def test_resize_preserves_aspect_ratio_not_enforced(self, sample_bgr_frame):
        """Resize stretches to target size (does not preserve aspect ratio)."""
        # Original is 480x272, target is 84x84
        result = preprocess_frame(sample_bgr_frame, 84, 84)

        # Should be exactly 84x84 regardless of input aspect ratio
        assert result.shape == (84, 84)

    def test_output_dtype_uint8(self, sample_bgr_frame):
        """FR-4.4: Output dtype is uint8."""
        result = preprocess_frame(sample_bgr_frame, 84, 84)

        assert result.dtype == np.uint8

    def test_output_value_range(self, sample_bgr_frame):
        """Output values should be in 0-255 range."""
        result = preprocess_frame(sample_bgr_frame, 84, 84)

        assert result.min() >= 0
        assert result.max() <= 255

    def test_different_output_sizes(self, sample_bgr_frame):
        """Test with various output sizes."""
        for size in [(42, 42), (64, 64), (84, 84), (128, 128)]:
            result = preprocess_frame(sample_bgr_frame, size[0], size[1])
            assert result.shape == (size[1], size[0])

    def test_handles_small_input(self):
        """Test with very small input frame."""
        small_frame = np.random.randint(0, 256, (10, 10, 3), dtype=np.uint8)
        result = preprocess_frame(small_frame, 84, 84)

        assert result.shape == (84, 84)
        assert result.dtype == np.uint8

    def test_handles_large_input(self):
        """Test with large input frame."""
        large_frame = np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)
        result = preprocess_frame(large_frame, 84, 84)

        assert result.shape == (84, 84)
        assert result.dtype == np.uint8
