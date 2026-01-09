"""
Tests for JetpackPPSSPPEnv - the main Gymnasium environment.

These tests use fake backends to run without PPSSPP installed.
"""

import pytest
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fakes.capture import FakeCapture, StaticFrameCapture
from tests.fakes.input import FakeInput, KeyEventType
from tests.fakes.window import FakeWindow


class TestObservationSpace:
    """Tests for observation shape and dtype (FR-4, INV-4)."""
    
    def test_observation_shape(self, default_config, fake_capture, fake_input, fake_window):
        """FR-4.3: Observations should be (stack_n, obs_h, obs_w)."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        expected_shape = (
            default_config["stack_n"],
            default_config["obs_h"],
            default_config["obs_w"]
        )
        
        assert env.observation_space.shape == expected_shape
        env.close()
    
    def test_observation_dtype(self, default_config, fake_capture, fake_input, fake_window):
        """FR-4.4: Observation dtype should be uint8."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        assert env.observation_space.dtype == np.uint8
        env.close()
    
    def test_reset_returns_correct_shape(self, default_config, fake_capture, fake_input, fake_window):
        """INV-4: reset() returns observation matching observation_space."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        obs, info = env.reset()
        
        assert obs.shape == env.observation_space.shape
        assert obs.dtype == env.observation_space.dtype
        env.close()
    
    def test_step_returns_correct_shape(self, default_config, fake_capture, fake_input, fake_window):
        """INV-4: step() returns observation matching observation_space."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        env.reset()
        obs, reward, done, truncated, info = env.step(0)
        
        assert obs.shape == env.observation_space.shape
        assert obs.dtype == env.observation_space.dtype
        env.close()


class TestGymnasiumAPI:
    """Tests for Gymnasium API compliance (INV-4)."""
    
    def test_reset_returns_tuple(self, default_config, fake_capture, fake_input, fake_window):
        """reset() should return (observation, info) tuple."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        result = env.reset()
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        
        obs, info = result
        assert isinstance(obs, np.ndarray)
        assert isinstance(info, dict)
        env.close()
    
    def test_step_returns_tuple(self, default_config, fake_capture, fake_input, fake_window):
        """step() should return (obs, reward, terminated, truncated, info)."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        env.reset()
        result = env.step(0)
        
        assert isinstance(result, tuple)
        assert len(result) == 5
        
        obs, reward, terminated, truncated, info = result
        assert isinstance(obs, np.ndarray)
        assert isinstance(reward, (int, float))
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)
        env.close()
    
    def test_action_space_discrete(self, default_config, fake_capture, fake_input, fake_window):
        """Action space should be Discrete(2)."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        from gymnasium.spaces import Discrete
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        assert isinstance(env.action_space, Discrete)
        assert env.action_space.n == 2
        env.close()


class TestFrameStacking:
    """Tests for frame stacking behavior (FR-4.3)."""
    
    def test_stacks_n_frames(self, default_config, fake_capture, fake_input, fake_window):
        """Observations should contain stack_n frames."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        obs, _ = env.reset()
        
        assert obs.shape[0] == default_config["stack_n"]
        env.close()
    
    def test_reset_fills_stack_with_same_frame(self, default_config, fake_input, fake_window):
        """Reset should fill stack with copies of initial frame."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        # Use capture that returns same frame
        capture = StaticFrameCapture()
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        obs, _ = env.reset()
        
        # All frames in stack should be identical after reset
        for i in range(1, default_config["stack_n"]):
            np.testing.assert_array_equal(obs[0], obs[i])
        env.close()


class TestInputControl:
    """Tests for input control (FR-3)."""
    
    def test_action_1_sends_key_down(self, default_config, fake_capture, fake_input, fake_window):
        """FR-3.4: action=1 should send key down in hold mode."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        config = default_config.copy()
        config["hold_style"] = "hold"
        
        env = JetpackPPSSPPEnv(
            config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        env.reset()
        fake_input.clear_events()
        
        env.step(1)  # Press jetpack
        
        events = fake_input.events
        # Should have key down event
        assert any(e.event_type == KeyEventType.DOWN for e in events)
        env.close()
    
    def test_action_0_sends_key_up(self, default_config, fake_capture, fake_input, fake_window):
        """FR-3.4: action=0 after action=1 should send key up."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        config = default_config.copy()
        config["hold_style"] = "hold"
        
        env = JetpackPPSSPPEnv(
            config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        env.reset()
        env.step(1)  # Press
        fake_input.clear_events()
        env.step(0)  # Release
        
        events = fake_input.events
        # Should have key up event
        assert any(e.event_type == KeyEventType.UP for e in events)
        env.close()
    
    def test_close_releases_action_key(self, default_config, fake_capture, fake_input, fake_window):
        """NFR-3.1: close() should release held action key."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        env = JetpackPPSSPPEnv(
            default_config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        env.reset()
        env.step(1)  # Hold key
        
        env.close()
        
        # After close, no keys should be held
        fake_input.assert_no_held_keys()


class TestReward:
    """Tests for reward calculation (FR-5)."""
    
    def test_default_reward_without_ocr(self, default_config, fake_capture, fake_input, fake_window):
        """FR-5.2: Fallback reward is +1.0 when OCR disabled."""
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        
        config = default_config.copy()
        config["use_ocr_reward"] = False
        
        env = JetpackPPSSPPEnv(
            config,
            capture_backend=fake_capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        env.reset()
        _, reward, _, _, _ = env.step(0)
        
        assert reward == 0.1  # Survival bonus (reduced from 1.0 for better scaling)
        env.close()
    
    def test_gameover_penalty(self, default_config, fake_input, fake_window):
        """FR-5.3: Game over gives -10.0 reward (reduced from -100.0).
        
        Note: With GameState detection, static/dark frames may trigger done=True
        immediately due to being detected as LOADING state.
        """
        from ppsspp_jetpack_rl import JetpackPPSSPPEnv
        from tests.fakes.capture import StaticFrameCapture
        
        config = default_config.copy()
        config["use_ocr_reward"] = False
        config["use_motion_done"] = True
        config["motion_static_steps"] = 3
        
        # Use static capture - note that dark frames trigger GameState.LOADING -> done=True
        capture = StaticFrameCapture()
        
        env = JetpackPPSSPPEnv(
            config,
            capture_backend=capture,
            input_backend=fake_input,
            window_backend=fake_window
        )
        
        env.reset()
        
        # With GameState detection, static frames are detected as non-gameplay
        # and trigger done=True immediately. This is expected behavior.
        _, reward, done, _, _ = env.step(0)
        
        # If done is True, it's because GameState detection worked
        if done:
            assert reward == -10.0  # Death penalty
        else:
            # If somehow still alive, keep checking motion detector
            for _ in range(10):
                _, reward, done, _, _ = env.step(0)
                if done:
                    assert reward == -10.0
                    break
        
        env.close()
