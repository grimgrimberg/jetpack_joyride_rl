"""
Fake input backend for testing.

Records all key events for assertion and verification.
"""

from typing import List, Tuple
from dataclasses import dataclass, field
from enum import Enum


class KeyEventType(Enum):
    DOWN = "down"
    UP = "up"
    PRESS = "press"


@dataclass
class KeyEvent:
    """Record of a single key event."""
    event_type: KeyEventType
    vk_code: int
    press_ms: int = 0


class FakeInput:
    """Fake input backend that records all key events."""
    
    def __init__(self, hwnd: int = None):
        self.hwnd = hwnd
        self._held_keys: List[int] = []
        self._events: List[KeyEvent] = []
        self.focus_count = 0
    
    @property
    def events(self) -> List[KeyEvent]:
        """Get list of all recorded events."""
        return self._events.copy()
    
    @property
    def held_keys(self) -> List[int]:
        """Get list of currently held keys."""
        return self._held_keys.copy()
    
    def key_down(self, vk_code: int) -> None:
        self._events.append(KeyEvent(KeyEventType.DOWN, vk_code))
        if vk_code not in self._held_keys:
            self._held_keys.append(vk_code)
    
    def key_up(self, vk_code: int) -> None:
        self._events.append(KeyEvent(KeyEventType.UP, vk_code))
        if vk_code in self._held_keys:
            self._held_keys.remove(vk_code)
    
    def key_press(self, vk_code: int, press_ms: int = 50) -> None:
        self._events.append(KeyEvent(KeyEventType.PRESS, vk_code, press_ms))
        # Press doesn't leave key held
    
    def release_all(self) -> None:
        """Release all held keys and record events."""
        for vk_code in list(self._held_keys):
            self._events.append(KeyEvent(KeyEventType.UP, vk_code))
        self._held_keys.clear()
    
    def clear_events(self) -> None:
        """Clear event history."""
        self._events.clear()
    
    def assert_no_held_keys(self) -> None:
        """Assert that no keys are currently held."""
        assert len(self._held_keys) == 0, f"Keys still held: {self._held_keys}"
    
    def assert_key_released(self, vk_code: int) -> None:
        """Assert that a specific key was released (has UP event after last DOWN)."""
        down_index = -1
        up_index = -1
        
        for i, event in enumerate(self._events):
            if event.vk_code == vk_code:
                if event.event_type == KeyEventType.DOWN:
                    down_index = i
                elif event.event_type == KeyEventType.UP:
                    up_index = i
        
        if down_index >= 0:
            assert up_index > down_index, f"Key {vk_code} was pressed but not released"
    
    def get_event_sequence(self) -> List[Tuple[str, int]]:
        """Get simplified event sequence for easy assertion."""
        return [(e.event_type.value, e.vk_code) for e in self._events]
