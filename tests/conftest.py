"""
Pytest configuration and shared fixtures.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fakes.capture import BlackFrameCapture, FakeCapture, StaticFrameCapture
from tests.fakes.input import FakeInput
from tests.fakes.window import FakeWindow


@pytest.fixture
def default_config():
    """Default configuration for testing."""
    return {
        # Paths (not used in tests with fakes)
        "ppsspp_exe": r"C:\Program Files\PPSSPP\PPSSPPWindows64.exe",
        "rom_path": r"C:\test.iso",
        "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",

        # Window
        "window_title_substr": "PPSSPP",

        # Controls
        "action_key": "Z",
        "reset_keys": ["ENTER"],

        # Timing
        "agent_hz": 15,
        "hold_style": "hold",
        "tap_ms": 40,
        "reset_wait_s": 0.01,  # Fast for tests

        # Observation
        "obs_w": 84,
        "obs_h": 84,
        "stack_n": 4,

        # Done detection
        "use_gameover_template": False,  # Disabled for most tests
        "gameover_template_path": "gameover_template.png",
        "template_match_thresh": 0.80,
        "use_motion_done": True,
        "motion_diff_thresh": 1.5,
        "motion_static_steps": 5,  # Faster for tests
        "motion_debug": False,
        "min_gameplay_steps_for_done": 0,
        "game_state_done_confirm_frames": 1,

        # Capture
        "cap_x": 0,
        "cap_y": 0,
        "cap_w": 480,
        "cap_h": 272,

        # OCR
        "score_roi_x": 10,
        "score_roi_y": 5,
        "score_roi_w": 120,
        "score_roi_h": 30,
        "use_ocr_reward": False,  # Disabled by default in tests

        # Training
        "checkpoint_freq": 1000,
        "checkpoint_dir": "checkpoints",
        "model_dir": "models",
        "tensorboard_dir": "tb_jetpack",

        # Background mode
        "use_background_capture": False,
    }


@pytest.fixture
def fake_capture():
    """Basic fake capture backend."""
    return FakeCapture(width=480, height=272)


@pytest.fixture
def static_capture():
    """Fake capture returning identical frames (for motion-done testing)."""
    return StaticFrameCapture(width=480, height=272)


@pytest.fixture
def black_capture():
    """Fake capture returning black frames."""
    return BlackFrameCapture(width=480, height=272)


@pytest.fixture
def fake_input():
    """Fake input backend."""
    return FakeInput(hwnd=12345)


@pytest.fixture
def fake_window():
    """Fake window backend."""
    return FakeWindow(
        mock_hwnd=12345,
        client_rect=(100, 100, 960, 544),
        title="PPSSPP v1.0 - Jetpack Joyride"
    )


@pytest.fixture
def sample_bgr_frame():
    """Sample BGR frame for preprocessing tests."""
    # Create a colorful test frame
    frame = np.zeros((272, 480, 3), dtype=np.uint8)
    # Add some color variation
    frame[:, :, 0] = np.arange(480)[None, :] % 256  # Blue gradient
    frame[:, :, 1] = np.arange(272)[:, None] % 256  # Green gradient
    frame[:, :, 2] = 128  # Constant red
    return frame


@pytest.fixture
def sample_gray_frame():
    """Sample grayscale 84x84 frame for done detector tests."""
    frame = np.random.randint(0, 256, (84, 84), dtype=np.uint8)
    return frame


@pytest.fixture
def gameover_template():
    """Sample game-over template for template matching tests."""
    # Create a distinctive pattern
    template = np.zeros((40, 40), dtype=np.uint8)
    template[10:30, 10:30] = 255  # White square in center
    return template
