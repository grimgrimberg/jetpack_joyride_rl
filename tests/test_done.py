"""
Tests for DoneDetector.
"""

import numpy as np
import cv2
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the actual class from main module
from ppsspp_jetpack_rl import DoneDetector


class TestDoneDetectorMotion:
    """Tests for motion-based done detection."""
    
    def test_motion_done_after_static_frames(self, default_config):
        """FR-6.2: Motion-based done triggers after N static frames."""
        config = default_config.copy()
        config["use_gameover_template"] = False
        config["use_motion_done"] = True
        config["motion_diff_thresh"] = 1.5
        config["motion_static_steps"] = 5
        
        detector = DoneDetector(config)
        
        # Create a static frame
        static_frame = np.full((84, 84), 128, dtype=np.uint8)
        
        # First call initializes prev_proc (no counting)
        result = detector.is_done(static_frame)
        assert result is False
        
        # Next 4 frames increment counter (1, 2, 3, 4)
        for i in range(4):
            assert detector.is_done(static_frame) is False
        
        # 6th call: counter hits 5 >= motion_static_steps
        assert detector.is_done(static_frame) is True
    
    def test_motion_resets_count_on_movement(self, default_config):
        """Motion resets static counter when movement detected."""
        config = default_config.copy()
        config["use_gameover_template"] = False
        config["use_motion_done"] = True
        config["motion_diff_thresh"] = 1.5
        config["motion_static_steps"] = 3  # Use smaller value for simpler test
        
        detector = DoneDetector(config)
        
        static_frame = np.full((84, 84), 128, dtype=np.uint8)
        moving_frame = np.full((84, 84), 200, dtype=np.uint8)  # Very different intensity
        
        # Call 1: init prev_proc to static_frame(128)
        detector.is_done(static_frame)
        # Call 2: static vs static -> diff=0 -> counter=1
        detector.is_done(static_frame)
        # Call 3: static vs static -> diff=0 -> counter=2
        detector.is_done(static_frame)
        
        # Call 4: moving(200) vs static(128) -> diff=72 >> 1.5 -> counter=0
        detector.is_done(moving_frame)
        
        # Call 5: static(128) vs moving(200) -> diff=72 >> 1.5 -> counter=0 (reset again!)
        detector.is_done(static_frame)
        
        # Now prev_proc is static(128), so next comparisons will be static vs static
        # Need 3 more static frames to trigger done
        # Call 6: counter=1
        assert detector.is_done(static_frame) is False
        # Call 7: counter=2
        assert detector.is_done(static_frame) is False
        # Call 8: counter=3 >= motion_static_steps=3
        assert detector.is_done(static_frame) is True
    
    def test_reset_clears_state(self, default_config):
        """Detector reset clears internal state."""
        config = default_config.copy()
        config["use_gameover_template"] = False
        config["use_motion_done"] = True
        config["motion_static_steps"] = 3
        
        detector = DoneDetector(config)
        
        static_frame = np.full((84, 84), 128, dtype=np.uint8)
        
        # Build up counter
        detector.is_done(static_frame)  # Init prev_proc
        detector.is_done(static_frame)  # Count = 1
        
        # Reset clears both counter and prev_proc
        detector.reset()
        
        # Need full count again - first call inits prev_proc, then need 3 more
        detector.is_done(static_frame)  # Init prev_proc (counter = 0)
        assert detector.is_done(static_frame) is False  # counter = 1
        assert detector.is_done(static_frame) is False  # counter = 2
        assert detector.is_done(static_frame) is True   # counter = 3 >= motion_static_steps


class TestDoneDetectorTemplate:
    """Tests for template-based done detection."""
    
    def test_template_match_triggers_done(self, default_config, gameover_template):
        """FR-6.1: Template matching triggers done when score >= threshold."""
        config = default_config.copy()
        config["use_gameover_template"] = True
        config["use_motion_done"] = False
        config["template_match_thresh"] = 0.80
        
        # Create detector and inject template
        detector = DoneDetector(config)
        detector.template = gameover_template
        
        # Create frame containing the template
        frame = np.zeros((84, 84), dtype=np.uint8)
        frame[22:62, 22:62] = gameover_template  # Place template in frame
        
        assert detector.is_done(frame) is True
    
    def test_template_no_match_below_threshold(self, default_config, gameover_template):
        """Template matching does not trigger done below threshold."""
        config = default_config.copy()
        config["use_gameover_template"] = True
        config["use_motion_done"] = False
        config["template_match_thresh"] = 0.80
        
        detector = DoneDetector(config)
        detector.template = gameover_template
        
        # Create frame with different content
        frame = np.random.randint(0, 256, (84, 84), dtype=np.uint8)
        
        # Random frame should not match template
        # Note: might pass occasionally by chance, but very unlikely
        assert detector.is_done(frame) is False
    
    def test_no_template_loaded(self, default_config):
        """No crash when template file doesn't exist."""
        config = default_config.copy()
        config["use_gameover_template"] = True
        config["gameover_template_path"] = "nonexistent.png"
        config["use_motion_done"] = False
        
        detector = DoneDetector(config)
        
        frame = np.random.randint(0, 256, (84, 84), dtype=np.uint8)
        
        # Should not crash, just return False
        assert detector.is_done(frame) is False


class TestDoneDetectorToggles:
    """Tests for detection toggle configuration."""
    
    def test_both_disabled(self, default_config):
        """FR-6.3: Both detections disabled returns False."""
        config = default_config.copy()
        config["use_gameover_template"] = False
        config["use_motion_done"] = False
        
        detector = DoneDetector(config)
        
        frame = np.full((84, 84), 128, dtype=np.uint8)
        
        # Should never trigger done
        for _ in range(20):
            assert detector.is_done(frame) is False
    
    def test_only_template_enabled(self, default_config, gameover_template):
        """Only template detection when motion disabled."""
        config = default_config.copy()
        config["use_gameover_template"] = True
        config["use_motion_done"] = False
        
        detector = DoneDetector(config)
        detector.template = gameover_template
        
        static_frame = np.full((84, 84), 128, dtype=np.uint8)
        
        # Static frames should not trigger done (motion disabled)
        for _ in range(20):
            assert detector.is_done(static_frame) is False
    
    def test_only_motion_enabled(self, default_config):
        """Only motion detection when template disabled."""
        config = default_config.copy()
        config["use_gameover_template"] = False
        config["use_motion_done"] = True
        config["motion_static_steps"] = 3
        
        detector = DoneDetector(config)
        
        static_frame = np.full((84, 84), 128, dtype=np.uint8)
        
        # First call inits prev_proc, then need 3 static comparisons
        detector.is_done(static_frame)  # Init
        detector.is_done(static_frame)  # count = 1
        detector.is_done(static_frame)  # count = 2
        assert detector.is_done(static_frame) is True  # count = 3 >= motion_static_steps
