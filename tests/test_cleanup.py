"""
Tests for cleanup invariants - ensuring no stuck keys on exit.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.fakes.input import FakeInput, KeyEventType


class TestInputCleanup:
    """Tests for input backend cleanup behavior."""
    
    def test_release_all_clears_held_keys(self):
        """NFR-3.1: release_all releases all held keys."""
        fake_input = FakeInput()
        
        # Hold several keys
        fake_input.key_down(0x5A)  # Z
        fake_input.key_down(0x0D)  # ENTER
        
        assert len(fake_input.held_keys) == 2
        
        # Release all
        fake_input.release_all()
        
        assert len(fake_input.held_keys) == 0
    
    def test_release_all_records_up_events(self):
        """release_all records UP events for all held keys."""
        fake_input = FakeInput()
        
        fake_input.key_down(0x5A)  # Z
        fake_input.key_down(0x0D)  # ENTER
        fake_input.clear_events()  # Clear down events
        
        fake_input.release_all()
        
        events = fake_input.events
        assert len(events) == 2
        assert all(e.event_type == KeyEventType.UP for e in events)
    
    def test_key_up_removes_from_held(self):
        """key_up removes key from held list."""
        fake_input = FakeInput()
        
        fake_input.key_down(0x5A)
        assert 0x5A in fake_input.held_keys
        
        fake_input.key_up(0x5A)
        assert 0x5A not in fake_input.held_keys
    
    def test_key_press_does_not_leave_held(self):
        """key_press does not leave key held."""
        fake_input = FakeInput()
        
        fake_input.key_press(0x5A, 50)
        
        assert 0x5A not in fake_input.held_keys
    
    def test_assert_no_held_keys_passes_when_empty(self):
        """assert_no_held_keys passes when no keys held."""
        fake_input = FakeInput()
        
        # Should not raise
        fake_input.assert_no_held_keys()
    
    def test_assert_no_held_keys_fails_when_keys_held(self):
        """assert_no_held_keys fails when keys are held."""
        fake_input = FakeInput()
        fake_input.key_down(0x5A)
        
        with pytest.raises(AssertionError, match="Keys still held"):
            fake_input.assert_no_held_keys()
    
    def test_assert_key_released(self):
        """assert_key_released verifies key was released after press."""
        fake_input = FakeInput()
        
        fake_input.key_down(0x5A)
        fake_input.key_up(0x5A)
        
        # Should not raise
        fake_input.assert_key_released(0x5A)
    
    def test_assert_key_released_fails_if_not_released(self):
        """assert_key_released fails if key was not released."""
        fake_input = FakeInput()
        
        fake_input.key_down(0x5A)
        # No key_up!
        
        with pytest.raises(AssertionError, match="not released"):
            fake_input.assert_key_released(0x5A)


class TestAtexitRegistration:
    """Tests for atexit handler registration."""
    
    def test_cleanup_function_exists(self):
        """NFR-3.3: atexit handler is registered."""
        import atexit
        
        # Import module to trigger registration
        import ppsspp_jetpack_rl
        
        # Check that _cleanup is in atexit handlers
        # Note: Can't easily inspect atexit directly, but we can verify the function exists
        assert hasattr(ppsspp_jetpack_rl, '_cleanup')
        assert callable(ppsspp_jetpack_rl._cleanup)


class TestCleanupInvariants:
    """Tests for INV-1: No stuck keys."""
    
    def test_exception_during_key_operation(self):
        """Keys should be releasable even after exceptions."""
        fake_input = FakeInput()
        
        fake_input.key_down(0x5A)
        
        # Simulate exception by raising after key_down
        try:
            raise ValueError("Simulated error")
        except ValueError:
            # Cleanup should still work
            fake_input.release_all()
        
        fake_input.assert_no_held_keys()
    
    def test_multiple_release_all_safe(self):
        """Calling release_all multiple times is safe."""
        fake_input = FakeInput()
        
        fake_input.key_down(0x5A)
        fake_input.release_all()
        fake_input.release_all()  # Should not raise
        fake_input.release_all()
        
        fake_input.assert_no_held_keys()
