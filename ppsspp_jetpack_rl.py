"""
Jetpack Joyride RL - Train a PPO agent on PPSSPP

Features:
- Screen capture from PPSSPP (foreground or background mode)
- OCR-based score/distance extraction for reward shaping
- Tkinter calibration GUI for region selection
- TensorBoard + Weights & Biases logging
- Checkpoint support for resume training
- Evaluation mode for trained models
"""

import argparse
import json
import os
import time
import atexit
import re
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import cv2
from PIL import Image, ImageTk
import mss

import gymnasium as gym
from gymnasium import spaces

# Windows-only imports
import win32gui
import win32con
import win32api
import win32ui
import ctypes
from ctypes import windll

# Enable DPI awareness BEFORE any Win32 coordinate calls
# This fixes capture/calibration issues on displays with >100% scaling (RISK-1)
try:
    # Per-Monitor DPI Aware (Windows 8.1+)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        # System DPI Aware fallback (Windows Vista+)
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass  # Non-Windows or very old Windows

# RL imports
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecTransposeImage
from stable_baselines3.common.callbacks import CheckpointCallback, BaseCallback

# Optional imports
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    print("[Warning] pytesseract not installed - OCR features disabled")

try:
    import wandb
    from wandb.integration.sb3 import WandbCallback
    HAS_WANDB = True
except ImportError:
    HAS_WANDB = False

try:
    import torchviz
    HAS_TORCHVIZ = True
except ImportError:
    HAS_TORCHVIZ = False


# =========================
# Game State Detection for Auto-Restart
# =========================
from enum import Enum

class GameState(Enum):
    """States in the Jetpack Joyride game flow."""
    UNKNOWN = 0
    RESULTS = 1      # "PLAY AGAIN" / statistics screen after death
    SAVE_DIALOG = 2  # Memory Stick save prompt
    LOADING = 3      # Black/dark loading screen
    LABORATORY = 4   # Start area before running
    GAMEPLAY = 5     # Active gameplay - Barry is running


def detect_game_state(frame_gray: np.ndarray, frame_bgr: np.ndarray = None, debug: bool = False) -> GameState:
    """Detect current game state from screen capture.
    
    Key signals for death detection:
    1. LOADING: Very dark screen (mean < 25) - transition after death
    2. SAVE_DIALOG: Uniform gray screen (mean 100-140, low std)
    3. RESULTS: Dark screen with some bright text areas
    
    If none of these match, we're probably in GAMEPLAY.
    """
    mean_intensity = float(frame_gray.mean())
    std_intensity = float(frame_gray.std())
    
    if debug:
        print(f"[StateDetect] mean={mean_intensity:.1f}, std={std_intensity:.1f}")
    
    # Signal 1: Very dark screen = LOADING (transition after death)
    # After Barry dies, there's often a dark fade transition
    if mean_intensity < 25:
        if debug:
            print(f"[StateDetect] -> LOADING (dark: mean={mean_intensity:.1f})")
        return GameState.LOADING
    
    # Signal 2: Uniform gray = SAVE_DIALOG
    # The "Memory Stick" dialog has mean ~110-135 and very low std
    if 100 < mean_intensity < 145 and std_intensity < 25:
        if debug:
            print(f"[StateDetect] -> SAVE_DIALOG (uniform gray)")
        return GameState.SAVE_DIALOG
    
    # Signal 3: Dark with bright spots = RESULTS screen
    # Results screen has dark background but white text
    if mean_intensity < 70:
        # Count bright pixels (text)
        bright_ratio = np.sum(frame_gray > 180) / frame_gray.size
        if bright_ratio > 0.02:  # Has some white text
            if debug:
                print(f"[StateDetect] -> RESULTS (dark+text: bright_ratio={bright_ratio:.3f})")
            return GameState.RESULTS
    
    # Default: GAMEPLAY
    if debug:
        print(f"[StateDetect] -> GAMEPLAY (default)")
    return GameState.GAMEPLAY


# =========================
# CONFIG (edit these or use calibration)
# =========================
CONFIG = {
    # 1) Paths
    "ppsspp_exe": r"C:\Program Files\PPSSPP\PPSSPPWindows64.exe",
    "rom_path": r"C:\Users\yuval\Downloads\Jetpack Joyride  150K Coins (Europe) (v2.00) (PSN)\Jetpack Joyride + 150K Coins (Europe) (v2.00) (PSN).iso",
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",

    # 2) Window matching
    "window_title_substr": "PPSSPP",

    # 3) Controls
    "action_key": "Z",
    "reset_keys": ["ENTER"],

    # 4) Timing
    "agent_hz": 15,
    "hold_style": "hold",
    "tap_ms": 40,
    "reset_wait_s": 1.0,

    # 5) Observation
    "obs_w": 84,
    "obs_h": 84,
    "stack_n": 4,

    # 6) Done detection
    "use_gameover_template": True,
    "gameover_template_path": "gameover_template.png",
    "template_match_thresh": 0.80,
    "use_motion_done": True,
    "motion_diff_thresh": 1.5,
    "motion_static_steps": 20,

    # 7) Capture region (set by calibration)
    "cap_x": 0,
    "cap_y": 0,
    "cap_w": 480,
    "cap_h": 272,

    # 8) Score OCR region (relative to capture region)
    "score_roi_x": 10,
    "score_roi_y": 5,
    "score_roi_w": 120,
    "score_roi_h": 30,
    "use_ocr_reward": False,  # Disabled for faster training

    # 9) Training
    "checkpoint_freq": 10000,
    "checkpoint_dir": "checkpoints",
    "model_dir": "models",
    "tensorboard_dir": "tb_jetpack",

    # 10) Background mode
    "use_background_capture": False,
}

# Config file paths
CAP_CONFIG_FILE = "ppsspp_capture_config.json"
SCORE_CONFIG_FILE = "score_roi_config.json"


# =========================
# VK key mapping
# =========================
VK = {
    "ENTER": 0x0D, "SPACE": 0x20, "ESC": 0x1B,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12, "TAB": 0x09,
}

def key_to_vk(key: str) -> int:
    key = key.upper()
    if key in VK:
        return VK[key]
    if len(key) == 1 and "A" <= key <= "Z":
        return ord(key)
    if len(key) == 1 and "0" <= key <= "9":
        return ord(key)
    raise ValueError(f"Unsupported key: {key!r}")


# =========================
# Window utilities
# =========================
def find_window_handle(title_substr: str) -> int:
    """Find window handle by title substring."""
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


def focus_window(hwnd: int) -> None:
    """Bring window to foreground."""
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def get_client_rect_on_screen(hwnd: int) -> Tuple[int, int, int, int]:
    """Get client area position and size in screen coordinates."""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    x0, y0 = win32gui.ClientToScreen(hwnd, (0, 0))
    return x0, y0, right - left, bottom - top


# =========================
# Input control - Focus window then send input
# =========================
# Note: PPSSPP uses DirectInput/RawInput, so we need to:
# 1. Focus the PPSSPP window first
# 2. Send global keyboard events (which will go to the focused window)

_last_focused_hwnd = None

def ensure_window_focused(hwnd: int) -> None:
    """Make sure the target window is focused before sending input."""
    global _last_focused_hwnd

    # Only refocus if needed (reduce overhead)
    if _last_focused_hwnd != hwnd:
        try:
            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            # Bring to foreground
            win32gui.SetForegroundWindow(hwnd)
            _last_focused_hwnd = hwnd
            time.sleep(0.02)  # Small delay for focus to take effect
        except Exception:
            pass  # Focus might fail due to Windows restrictions

def key_down_to_window(hwnd: int, vk_code: int) -> None:
    """Send key down to window (focuses first)."""
    ensure_window_focused(hwnd)
    win32api.keybd_event(vk_code, 0, 0, 0)

def key_up_to_window(hwnd: int, vk_code: int) -> None:
    """Send key up to window (focuses first)."""
    ensure_window_focused(hwnd)
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)

def key_press_to_window(hwnd: int, vk_code: int, press_ms: int = 50) -> None:
    """Send key press (down + up) to window."""
    ensure_window_focused(hwnd)
    win32api.keybd_event(vk_code, 0, 0, 0)
    time.sleep(press_ms / 1000.0)
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)

# Legacy global input (for compatibility)
def key_down(vk_code: int) -> None:
    win32api.keybd_event(vk_code, 0, 0, 0)

def key_up(vk_code: int) -> None:
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)

def key_press(vk_code: int, press_ms: int = 40) -> None:
    key_down(vk_code)
    time.sleep(press_ms / 1000.0)
    key_up(vk_code)


# =========================
# Screen capture
# =========================
class ScreenCapture:
    """Screen capture with foreground (mss) or background (BitBlt) mode."""

    def __init__(self, hwnd: int, cap_x: int, cap_y: int, cap_w: int, cap_h: int,
                 background: bool = False):
        self.hwnd = hwnd
        self.cap_x = int(cap_x)
        self.cap_y = int(cap_y)
        self.cap_w = int(cap_w)
        self.cap_h = int(cap_h)
        self.background = background

        if not background:
            self.sct = mss.mss()
        else:
            self.sct = None

    def set_region(self, cap_x: int, cap_y: int, cap_w: int, cap_h: int):
        self.cap_x = int(cap_x)
        self.cap_y = int(cap_y)
        self.cap_w = int(cap_w)
        self.cap_h = int(cap_h)

    def grab(self) -> np.ndarray:
        """Capture screen region, returns BGR image."""
        if self.background:
            return self._grab_bitblt()
        else:
            return self._grab_mss()

    def _grab_mss(self) -> np.ndarray:
        """Foreground capture using mss."""
        x0, y0, _, _ = get_client_rect_on_screen(self.hwnd)
        monitor = {
            "left": x0 + self.cap_x,
            "top": y0 + self.cap_y,
            "width": self.cap_w,
            "height": self.cap_h
        }
        img = np.array(self.sct.grab(monitor))
        return img[:, :, :3]  # BGRA -> BGR

    def _grab_bitblt(self) -> np.ndarray:
        """Background capture using BitBlt (works when window not focused)."""
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

        # BitBlt copy
        result = ctypes.windll.user32.PrintWindow(hwnd, cDC.GetSafeHdc(), 3)

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

    def close(self):
        if self.sct:
            try:
                self.sct.close()
            except Exception:
                pass


def preprocess_frame(frame_bgr: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """Convert to grayscale and resize."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (out_w, out_h), interpolation=cv2.INTER_AREA)
    return resized


# =========================
# OCR Score Extraction
# =========================
class ScoreExtractor:
    """Extract score/distance from game screen using OCR."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.last_score = 0

        if HAS_TESSERACT and os.path.exists(cfg["tesseract_path"]):
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_path"]

    def extract(self, frame_bgr: np.ndarray) -> Optional[int]:
        """Extract score from frame. Returns None if OCR fails."""
        if not HAS_TESSERACT:
            return None

        try:
            # Crop score region
            x = self.cfg["score_roi_x"]
            y = self.cfg["score_roi_y"]
            w = self.cfg["score_roi_w"]
            h = self.cfg["score_roi_h"]

            roi = frame_bgr[y:y+h, x:x+w]

            # Preprocess for OCR
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # Threshold to make text clearer
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            # Dilate to connect broken characters
            kernel = np.ones((2, 2), np.uint8)
            processed = cv2.dilate(thresh, kernel, iterations=1)

            # OCR - only digits
            text = pytesseract.image_to_string(
                processed,
                config='--psm 7 -c tessedit_char_whitelist=0123456789'
            )

            # Extract numbers
            numbers = re.findall(r'\d+', text)
            if numbers:
                score = int(numbers[0])
                self.last_score = score
                return score

            return self.last_score

        except Exception as e:
            return self.last_score


# =========================
# Done detection
# =========================
class DoneDetector:
    """Detect game over via template matching or motion analysis."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.template = None
        self.static_count = 0
        self.prev_proc = None

        if cfg["use_gameover_template"] and os.path.exists(cfg["gameover_template_path"]):
            self.template = cv2.imread(cfg["gameover_template_path"], cv2.IMREAD_GRAYSCALE)

    def reset(self):
        self.static_count = 0
        self.prev_proc = None

    def is_done(self, proc_gray: np.ndarray) -> bool:
        done_by_template = False
        if self.cfg["use_gameover_template"] and self.template is not None:
            if (self.template.shape[0] <= proc_gray.shape[0] and
                self.template.shape[1] <= proc_gray.shape[1]):
                res = cv2.matchTemplate(proc_gray, self.template, cv2.TM_CCOEFF_NORMED)
                done_by_template = float(res.max()) >= self.cfg["template_match_thresh"]

        done_by_motion = False
        if self.cfg["use_motion_done"]:
            if self.prev_proc is None:
                self.prev_proc = proc_gray.copy()
            else:
                diff = cv2.absdiff(proc_gray, self.prev_proc)
                mean_diff = float(diff.mean())
                self.prev_proc = proc_gray.copy()

                if mean_diff < self.cfg["motion_diff_thresh"]:
                    self.static_count += 1
                else:
                    self.static_count = 0

                if self.static_count >= self.cfg["motion_static_steps"]:
                    done_by_motion = True

        return done_by_template or done_by_motion


# =========================
# Custom Callbacks
# =========================
class MetricsCallback(BaseCallback):
    """Custom callback for logging training metrics."""

    def __init__(self, verbose=0):
        super().__init__(verbose)
        self.episode_rewards = []
        self.episode_lengths = []

    def _on_step(self) -> bool:
        # Log custom metrics
        if len(self.model.ep_info_buffer) > 0:
            ep_info = self.model.ep_info_buffer[-1]
            if 'r' in ep_info:
                self.logger.record('custom/episode_reward', ep_info['r'])
            if 'l' in ep_info:
                self.logger.record('custom/episode_length', ep_info['l'])
        return True


# =========================
# Gym Environment
# =========================
class JetpackPPSSPPEnv(gym.Env):
    """Gymnasium environment for Jetpack Joyride on PPSSPP.

    Supports dependency injection for testing:
        - capture_backend: CaptureBackend protocol for screen capture
        - input_backend: InputBackend protocol for keyboard input
        - window_backend: WindowBackend protocol for window management
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, cfg: dict, render_mode: str = None,
                 capture_backend=None, input_backend=None, window_backend=None):
        super().__init__()
        self.cfg = cfg
        self.render_mode = render_mode

        # Injected backends (for testing)
        self._capture_backend = capture_backend
        self._input_backend = input_backend
        self._window_backend = window_backend

        self.hwnd = None
        self.cap = None
        self.score_extractor = ScoreExtractor(cfg) if cfg["use_ocr_reward"] else None
        self.prev_score = 0

        self.action_vk = key_to_vk(cfg["action_key"])
        self.reset_vks = [key_to_vk(k) for k in cfg["reset_keys"]]

        self.obs_w = cfg["obs_w"]
        self.obs_h = cfg["obs_h"]
        self.stack_n = cfg["stack_n"]
        self.frames = deque(maxlen=self.stack_n)

        self.action_space = spaces.Discrete(2)
        self.observation_space = spaces.Box(
            low=0, high=255, shape=(self.stack_n, self.obs_h, self.obs_w), dtype=np.uint8
        )

        self.done_detector = DoneDetector(cfg)
        self._action_is_down = False
        self._step_dt = 1.0 / float(cfg["agent_hz"])

        self._last_frame = None

    def _ensure_window(self):
        # Use injected backends if available (for testing)
        if self._capture_backend is not None:
            self.cap = self._capture_backend
            if self._window_backend is not None:
                self.hwnd = self._window_backend.find_window(self.cfg["window_title_substr"])
            else:
                self.hwnd = 0  # Dummy hwnd for fake backends
            return

        if self.hwnd is None:
            if self._window_backend is not None:
                self.hwnd = self._window_backend.find_window(self.cfg["window_title_substr"])
            else:
                self.hwnd = find_window_handle(self.cfg["window_title_substr"])
        if not self.cfg["use_background_capture"]:
            if self._window_backend is not None:
                self._window_backend.focus_window(self.hwnd)
            else:
                focus_window(self.hwnd)
        if self.cap is None:
            self.cap = ScreenCapture(
                self.hwnd,
                self.cfg["cap_x"], self.cfg["cap_y"],
                self.cfg["cap_w"], self.cfg["cap_h"],
                background=self.cfg["use_background_capture"]
            )

    def _grab_proc(self) -> Tuple[np.ndarray, np.ndarray]:
        """Grab and preprocess frame. Returns (processed, raw_bgr)."""
        frame = self.cap.grab()
        self._last_frame = frame
        proc = preprocess_frame(frame, self.obs_w, self.obs_h)
        return proc, frame

    def _stack_obs(self) -> np.ndarray:
        assert len(self.frames) == self.stack_n
        return np.stack(list(self.frames), axis=0)

    def _apply_action(self, a: int):
        """Apply action by sending key to PPSSPP window directly."""
        style = self.cfg["hold_style"].lower()

        # Use injected input backend if available
        if self._input_backend is not None:
            if style == "tap":
                if a == 1:
                    self._input_backend.key_press(self.action_vk, self.cfg["tap_ms"])
                return
            # Hold mode
            if a == 1 and not self._action_is_down:
                self._input_backend.key_down(self.action_vk)
                self._action_is_down = True
            elif a == 0 and self._action_is_down:
                self._input_backend.key_up(self.action_vk)
                self._action_is_down = False
            return

        # Default: use global key functions
        if style == "tap":
            if a == 1:
                key_press_to_window(self.hwnd, self.action_vk, self.cfg["tap_ms"])
            return

        # Hold mode
        if a == 1 and not self._action_is_down:
            key_down_to_window(self.hwnd, self.action_vk)
            self._action_is_down = True
        elif a == 0 and self._action_is_down:
            key_up_to_window(self.hwnd, self.action_vk)
            self._action_is_down = False

    def _release_action(self):
        """Release held action key. Safe to call multiple times."""
        if self._action_is_down:
            if self._input_backend is not None:
                self._input_backend.key_up(self.action_vk)
            elif self.hwnd:
                key_up_to_window(self.hwnd, self.action_vk)
            self._action_is_down = False

    def reset(self, seed=None, options=None):
        """Reset environment by navigating through menus until gameplay starts.
        
        This handles the game flow after death:
        1. Results screen -> press Z to select PLAY AGAIN
        2. Save dialog -> press Z for Yes
        3. Loading -> wait
        4. Laboratory -> press Z to start running
        5. Gameplay -> begin training
        """
        super().reset(seed=seed)
        self._ensure_window()
        self._release_action()
        
        # Navigate through menus until we reach gameplay
        self._navigate_to_gameplay()
        
        self.done_detector.reset()
        self.prev_score = 0

        self.frames.clear()
        proc, _ = self._grab_proc()
        for _ in range(self.stack_n):
            self.frames.append(proc.copy())

        return self._stack_obs(), {}
    
    def _navigate_to_gameplay(self, max_attempts: int = 60, debug: bool = False):
        """Navigate through menus until gameplay state is detected.
        
        Presses Z repeatedly while monitoring game state, with state-appropriate
        timing to handle loading screens and transitions.
        """
        action_key_vk = key_to_vk(self.cfg["action_key"])
        
        for attempt in range(max_attempts):
            proc, frame_bgr = self._grab_proc()
            state = detect_game_state(proc, frame_bgr)
            
            if debug:
                print(f"[Reset] Attempt {attempt}: State={state.name}, mean={proc.mean():.1f}, std={proc.std():.1f}")
            
            if state == GameState.GAMEPLAY:
                # We're in the game! Ready to train
                if debug:
                    print(f"[Reset] Gameplay detected after {attempt} attempts")
                return
            
            elif state == GameState.LOADING:
                # Wait for loading to finish, don't spam buttons
                time.sleep(0.5)
                
            elif state == GameState.SAVE_DIALOG:
                # Press Z to confirm save (select "Yes")
                if self._input_backend is not None:
                    self._input_backend.key_press(action_key_vk, 60)
                else:
                    key_press_to_window(self.hwnd, action_key_vk, 60)
                time.sleep(0.3)
                
            elif state == GameState.RESULTS:
                # Press Z to select PLAY AGAIN 
                if self._input_backend is not None:
                    self._input_backend.key_press(action_key_vk, 60)
                else:
                    key_press_to_window(self.hwnd, action_key_vk, 60)
                time.sleep(0.3)
                
            elif state == GameState.LABORATORY:
                # Press Z to start running
                if self._input_backend is not None:
                    self._input_backend.key_press(action_key_vk, 60)
                else:
                    key_press_to_window(self.hwnd, action_key_vk, 60)
                time.sleep(0.5)
                
            else:  # UNKNOWN
                # Generic button press to get through unknown screens
                if self._input_backend is not None:
                    self._input_backend.key_press(action_key_vk, 60)
                else:
                    key_press_to_window(self.hwnd, action_key_vk, 60)
                time.sleep(0.3)
        
        print(f"[Warning] Could not reach gameplay state after {max_attempts} attempts")

    def step(self, action):
        """Execute one step in the environment.

        Protected by try/finally to ensure action key is released on any exception.
        This prevents stuck keys (INV-1).
        
        Episode ends when:
        1. Motion-based done detector triggers (static screen)
        2. Game over template matched
        3. GameState transitions to RESULTS, SAVE_DIALOG, or LOADING (death detected)
        """
        self._ensure_window()
        t0 = time.perf_counter()

        try:
            self._apply_action(int(action))

            # Pace to match agent_hz
            elapsed = time.perf_counter() - t0
            remaining = self._step_dt - elapsed
            if remaining > 0:
                time.sleep(remaining)

            proc, frame_bgr = self._grab_proc()
            self.frames.append(proc)

            # Calculate reward
            reward = 0.1  # Small survival bonus (better scaling)

            if self.score_extractor and self.cfg["use_ocr_reward"]:
                score = self.score_extractor.extract(frame_bgr)
                if score is not None and score > self.prev_score:
                    # Distance-based reward
                    delta = score - self.prev_score
                    reward = delta * 0.1
                    self.prev_score = score

            # Check done using multiple methods
            done = False
            
            # Method 1: Motion/template based done detector
            if self.done_detector.is_done(proc):
                done = True
                print(f"[Step] DONE by motion/template detector")
            
            # Method 2: GameState detection (more reliable for death)
            # If we're no longer in GAMEPLAY, Barry died
            game_state = detect_game_state(proc, frame_bgr)
            if game_state in (GameState.RESULTS, GameState.SAVE_DIALOG, GameState.LOADING):
                done = True
                print(f"[Step] DONE by GameState={game_state.name}, mean={float(proc.mean()):.1f}")
            
            if done:
                reward = -10.0  # Death penalty (reduced from -100 for better learning)
                self._release_action()

            return self._stack_obs(), reward, done, False, {"score": self.prev_score}

        except Exception:
            # INV-1: Always release keys on exception to prevent stuck keys
            self._release_action()
            raise

    def render(self):
        if self.render_mode == "human" and self._last_frame is not None:
            cv2.imshow("Jetpack RL", self._last_frame)
            cv2.waitKey(1)

    def close(self):
        self._release_action()
        if self._input_backend is not None:
            self._input_backend.release_all()
        if self.cap:
            self.cap.close()
        cv2.destroyAllWindows()
        super().close()


# =========================
# Safety cleanup
# =========================
_env_global = None
def _cleanup():
    global _env_global
    if _env_global is not None:
        try:
            _env_global.close()
        except Exception:
            pass
atexit.register(_cleanup)


# =========================
# Tkinter Calibration GUI
# =========================
class CalibrationGUI:
    """
    Improved Tkinter GUI for capture region calibration.

    Features:
    - Live auto-refreshing screenshot
    - Clear step-by-step instructions
    - Side-by-side preview showing what the agent will see
    - Large, clear buttons
    - Status bar with feedback
    """

    def __init__(self, hwnd: int, cfg: dict, mode: str = "capture"):
        self.hwnd = hwnd
        self.cfg = cfg
        self.mode = mode  # "capture" or "score"

        # Selection state
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.selection = None
        self.is_dragging = False

        # Screen capture
        self.sct = mss.mss()

        # Create window
        self.root = tk.Tk()
        self.root.title("🎮 Jetpack RL - Region Calibration")
        self.root.configure(bg='#2b2b2b')

        # Styling
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='#2b2b2b', foreground='white', font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 12, 'bold'), padding=10)
        style.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'), foreground='#00ff88')
        style.configure('Status.TLabel', font=('Segoe UI', 12), foreground='#ffcc00')
        style.configure('Coords.TLabel', font=('Consolas', 12), foreground='#88ccff')

        self._setup_ui()
        self._start_auto_refresh()

    def _setup_ui(self):
        # Configure root window - set minimum size and don't allow resize
        self.root.resizable(False, False)

        # Main container with dark background
        main_frame = tk.Frame(self.root, bg='#2b2b2b', padx=20, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header with mode-specific title
        if self.mode == "capture":
            title = "📺 Step 1: Select GAME CAPTURE Region"
            instruction = "Draw a rectangle around the ENTIRE game screen area"
        else:
            title = "🔢 Step 2: Select SCORE Region"
            instruction = "Draw a rectangle around the DISTANCE/SCORE numbers"

        title_label = tk.Label(main_frame, text=title, bg='#2b2b2b', fg='#00ff88',
                               font=('Segoe UI', 16, 'bold'))
        title_label.pack(pady=(0, 5))

        instr_label = tk.Label(main_frame, text=instruction, bg='#2b2b2b', fg='white',
                               font=('Segoe UI', 11))
        instr_label.pack(pady=(0, 15))

        # Content area - use a tk.Frame with grid for proper layout
        content_frame = tk.Frame(main_frame, bg='#2b2b2b')
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Get PPSSPP window dimensions
        x0, y0, w, h = get_client_rect_on_screen(self.hwnd)

        # Scale to fit (max 550px width)
        max_size = 550
        self.scale = min(1.0, max_size / max(w, h))
        self.display_w = int(w * self.scale)
        self.display_h = int(h * self.scale)
        self.orig_w, self.orig_h = w, h

        # LEFT COLUMN: Screenshot canvas
        left_col = tk.Frame(content_frame, bg='#2b2b2b')
        left_col.grid(row=0, column=0, padx=(0, 20), sticky='n')

        tk.Label(left_col, text="👇 Click and drag to select:", bg='#2b2b2b', fg='white',
                 font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 5))

        # Canvas with green border
        canvas_border = tk.Frame(left_col, bg='#00ff88', padx=3, pady=3)
        canvas_border.pack()

        self.canvas = tk.Canvas(
            canvas_border,
            width=self.display_w,
            height=self.display_h,
            bg='black',
            highlightthickness=0,
            cursor='crosshair'
        )
        self.canvas.pack()

        # Bind mouse events
        self.canvas.bind("<Button-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # RIGHT COLUMN: Preview and info
        right_col = tk.Frame(content_frame, bg='#2b2b2b')
        right_col.grid(row=0, column=1, sticky='n')

        tk.Label(right_col, text="🤖 Agent sees (84×84):", bg='#2b2b2b', fg='white',
                 font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 5))

        # Preview canvas with yellow border
        preview_border = tk.Frame(right_col, bg='#ffcc00', padx=3, pady=3)
        preview_border.pack()

        self.preview_canvas = tk.Canvas(
            preview_border,
            width=168,
            height=168,
            bg='#1a1a1a',
            highlightthickness=0
        )
        self.preview_canvas.pack()

        # Placeholder text in preview
        self.preview_canvas.create_text(
            84, 84,
            text="Select a region\nto see preview",
            fill='#666666',
            font=('Segoe UI', 10),
            justify='center',
            tags='placeholder'
        )

        # Coordinates display
        self.coord_var = tk.StringVar(value="No region selected")
        coord_label = tk.Label(right_col, textvariable=self.coord_var, bg='#2b2b2b',
                               fg='#88ccff', font=('Consolas', 11))
        coord_label.pack(pady=10)

        # Status bar
        self.status_var = tk.StringVar(value="⏳ Waiting for selection...")
        status_label = tk.Label(main_frame, textvariable=self.status_var, bg='#2b2b2b',
                                fg='#ffcc00', font=('Segoe UI', 12))
        status_label.pack(pady=15)

        # Buttons row
        btn_frame = tk.Frame(main_frame, bg='#2b2b2b')
        btn_frame.pack()

        self.save_btn = tk.Button(
            btn_frame,
            text="💾 SAVE & CONTINUE",
            command=self._save,
            state=tk.DISABLED,
            font=('Segoe UI', 11, 'bold'),
            bg='#00aa55',
            fg='white',
            padx=15,
            pady=8,
            cursor='hand2'
        )
        self.save_btn.pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="🔄 Refresh",
            command=self._refresh_screenshot,
            font=('Segoe UI', 10),
            padx=10,
            pady=8
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="❌ Cancel",
            command=self._cancel,
            font=('Segoe UI', 10),
            padx=10,
            pady=8
        ).pack(side=tk.LEFT, padx=5)

        # Initial screenshot
        self._refresh_screenshot()

    def _start_auto_refresh(self):
        """Auto-refresh screenshot every 2 seconds."""
        def refresh_loop():
            if not self.is_dragging and self.root.winfo_exists():
                self._refresh_screenshot()
                self.root.after(2000, refresh_loop)
        self.root.after(2000, refresh_loop)

    def _refresh_screenshot(self):
        """Capture and display current screenshot."""
        try:
            x0, y0, w, h = get_client_rect_on_screen(self.hwnd)
            monitor = {"left": x0, "top": y0, "width": w, "height": h}

            screenshot = self.sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # Resize for display
            img = img.resize((self.display_w, self.display_h), Image.Resampling.LANCZOS)

            self.photo = ImageTk.PhotoImage(img)
            self.canvas.delete("screenshot")
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo, tags="screenshot")

            # Redraw selection rectangle if exists
            if self.rect_id:
                self.canvas.tag_raise(self.rect_id)

        except Exception as e:
            self.status_var.set(f"⚠️ Error capturing screenshot: {e}")

    def _on_mouse_down(self, event):
        self.is_dragging = True
        self.start_x = event.x
        self.start_y = event.y

        # Remove old rectangle
        if self.rect_id:
            self.canvas.delete(self.rect_id)

        # Create new rectangle
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline='#00ff88', width=3, dash=(5, 5)
        )
        self.status_var.set("📐 Drawing... release to confirm")

    def _on_mouse_drag(self, event):
        if self.rect_id:
            # Clamp to canvas bounds
            x = max(0, min(event.x, self.display_w))
            y = max(0, min(event.y, self.display_h))
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, x, y)

            # Show size while dragging
            w = abs(x - self.start_x)
            h = abs(y - self.start_y)
            orig_w = int(w / self.scale)
            orig_h = int(h / self.scale)
            self.coord_var.set(f"Size: {orig_w} × {orig_h} pixels")

    def _on_mouse_up(self, event):
        self.is_dragging = False

        # Calculate selection in display coords
        x1 = max(0, min(self.start_x, event.x))
        y1 = max(0, min(self.start_y, event.y))
        x2 = min(self.display_w, max(self.start_x, event.x))
        y2 = min(self.display_h, max(self.start_y, event.y))

        # Convert to original coordinates
        ox = int(x1 / self.scale)
        oy = int(y1 / self.scale)
        ow = int((x2 - x1) / self.scale)
        oh = int((y2 - y1) / self.scale)

        # Minimum size check
        if ow < 10 or oh < 10:
            self.status_var.set("⚠️ Selection too small! Please try again.")
            self.selection = None
            self.save_btn.configure(state=tk.DISABLED)
            return

        self.selection = (ox, oy, ow, oh)

        # Update rectangle to solid
        self.canvas.itemconfig(self.rect_id, dash=(), outline='#00ff88')

        # Update displays
        self.coord_var.set(f"X: {ox}  Y: {oy}  W: {ow}  H: {oh}")
        self.status_var.set("✅ Region selected! Click SAVE to continue.")
        self.save_btn.configure(state=tk.NORMAL)

        # Update preview
        self._update_preview()

    def _update_preview(self):
        """Show what the agent will see with current selection."""
        if not self.selection:
            return

        try:
            ox, oy, ow, oh = self.selection
            x0, y0, _, _ = get_client_rect_on_screen(self.hwnd)

            monitor = {"left": x0 + ox, "top": y0 + oy, "width": ow, "height": oh}
            screenshot = self.sct.grab(monitor)

            # Convert to numpy and preprocess
            img = np.array(screenshot)[:, :, :3]
            proc = preprocess_frame(img, 84, 84)

            # Scale up for display (2x)
            display = cv2.resize(proc, (168, 168), interpolation=cv2.INTER_NEAREST)

            # Convert to PIL and display
            pil_img = Image.fromarray(display)
            self.preview_photo = ImageTk.PhotoImage(pil_img)

            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self.preview_photo)

        except Exception as e:
            self.status_var.set(f"⚠️ Preview error: {e}")

    def _save(self):
        """Save selection to config file."""
        if not self.selection:
            messagebox.showwarning("No Selection", "Please select a region first!")
            return

        ox, oy, ow, oh = self.selection

        if self.mode == "capture":
            data = {"cap_x": ox, "cap_y": oy, "cap_w": ow, "cap_h": oh}
            filepath = CAP_CONFIG_FILE
            msg = f"✅ Saved game capture region to {filepath}"
        else:
            data = {"score_roi_x": ox, "score_roi_y": oy, "score_roi_w": ow, "score_roi_h": oh}
            filepath = SCORE_CONFIG_FILE
            msg = f"✅ Saved score region to {filepath}"

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        print(msg)
        messagebox.showinfo("Saved!", msg)
        self.root.destroy()

    def _cancel(self):
        """Cancel without saving."""
        if self.selection:
            if not messagebox.askyesno("Cancel?", "Discard selection and exit?"):
                return
        self.root.destroy()

    def run(self):
        """Run the calibration GUI."""
        # Position window on LEFT side of screen so it doesn't block PPSSPP
        self.root.update_idletasks()
        # Put GUI at x=10, y=50 (top-left corner with some margin)
        self.root.geometry(f"+10+50")

        # Keep on top so it's always visible
        self.root.attributes('-topmost', True)

        self.root.mainloop()

        try:
            self.sct.close()
        except:
            pass


def calibrate_gui(cfg: dict, mode: str = "capture"):
    """Launch the calibration GUI."""
    try:
        hwnd = find_window_handle(cfg["window_title_substr"])
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        print("Make sure PPSSPP is running with the game loaded.")
        return

    focus_window(hwnd)
    time.sleep(0.3)

    gui = CalibrationGUI(hwnd, cfg, mode)
    gui.run()


# =========================
# Config loading
# =========================
def load_configs(cfg: dict):
    """Load saved configuration files."""
    if os.path.exists(CAP_CONFIG_FILE):
        with open(CAP_CONFIG_FILE, "r") as f:
            cfg.update(json.load(f))
    if os.path.exists(SCORE_CONFIG_FILE):
        with open(SCORE_CONFIG_FILE, "r") as f:
            cfg.update(json.load(f))


# =========================
# PPSSPP launcher
# =========================
def launch_ppsspp(cfg: dict):
    """Launch PPSSPP with the ROM."""
    exe = cfg["ppsspp_exe"]
    rom = cfg["rom_path"]

    if not os.path.exists(exe):
        raise FileNotFoundError(f"PPSSPP not found: {exe}")
    if not os.path.exists(rom):
        raise FileNotFoundError(f"ROM not found: {rom}")

    os.spawnl(os.P_NOWAIT, exe, exe, rom)


# =========================
# Modes
# =========================
def play_random(cfg: dict, duration: int = 30):
    """Run random actions for testing."""
    global _env_global
    env = JetpackPPSSPPEnv(cfg, render_mode="human")
    _env_global = env

    # First, ensure window is focused
    env._ensure_window()

    # Press ENTER to start the game from title screen
    print("Pressing ENTER to start game...")
    key_press_to_window(env.hwnd, key_to_vk("ENTER"), 100)
    time.sleep(1.0)  # Wait for game to start

    # Press ENTER again (sometimes needed for menu)
    key_press_to_window(env.hwnd, key_to_vk("ENTER"), 100)
    time.sleep(0.5)

    obs, _ = env.reset()
    t_end = time.time() + duration

    print(f"Running random play for {duration} seconds...")
    print("Sending inputs to PPSSPP window...")

    while time.time() < t_end:
        action = env.action_space.sample()
        obs, reward, done, trunc, info = env.step(action)
        env.render()

        if done:
            print(f"Episode ended. Score: {info.get('score', 'N/A')}")
            obs, _ = env.reset()

    env.close()
    print("Random play finished.")


def capture_gameover_template(cfg: dict):
    """Capture game-over screen for template matching."""
    hwnd = find_window_handle(cfg["window_title_substr"])
    focus_window(hwnd)

    cap = ScreenCapture(hwnd, cfg["cap_x"], cfg["cap_y"], cfg["cap_w"], cfg["cap_h"])

    print("Navigate to GAME OVER screen, then press 'T' to save, ESC to exit.")
    while True:
        frame = cap.grab()
        proc = preprocess_frame(frame, cfg["obs_w"], cfg["obs_h"])

        # Display
        display = cv2.resize(proc, (336, 336), interpolation=cv2.INTER_NEAREST)
        cv2.imshow("Game Over Capture (press T to save)", display)

        k = cv2.waitKey(100) & 0xFF
        if k in (ord('t'), ord('T')):
            cv2.imwrite(cfg["gameover_template_path"], proc)
            print(f"Saved: {cfg['gameover_template_path']}")
            break
        elif k == 27:
            break

    cv2.destroyAllWindows()
    cap.close()


def diagnose_capture(cfg: dict, num_frames: int = 30):
    """Diagnose capture reliability by capturing frames and analyzing them.

    Reports:
    - Mean pixel intensity per frame
    - Number of black frames (potential PrintWindow failures)
    - Capture latency statistics
    - Recommendations for fixing issues
    """
    print("=" * 60)
    print("CAPTURE DIAGNOSTICS")
    print("=" * 60)

    try:
        hwnd = find_window_handle(cfg["window_title_substr"])
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        print("Make sure PPSSPP is running with the game loaded.")
        return

    focus_window(hwnd)
    time.sleep(0.3)

    # Test foreground capture
    print(f"\n📷 Testing foreground capture ({num_frames} frames)...")
    cap_fg = ScreenCapture(hwnd, cfg["cap_x"], cfg["cap_y"], cfg["cap_w"], cfg["cap_h"], background=False)

    fg_intensities = []
    fg_latencies = []

    for _ in range(num_frames):
        t0 = time.perf_counter()
        frame = cap_fg.grab()
        latency = (time.perf_counter() - t0) * 1000
        fg_latencies.append(latency)
        fg_intensities.append(float(frame.mean()))

    cap_fg.close()

    fg_black = sum(1 for x in fg_intensities if x < 5)
    print(f"  Mean intensity: {np.mean(fg_intensities):.1f} (0=black, 255=white)")
    print(f"  Black frames: {fg_black}/{num_frames}")
    print(f"  Latency: {np.mean(fg_latencies):.1f}ms avg, {np.max(fg_latencies):.1f}ms max")

    # Test background capture
    print(f"\n🖼️  Testing background capture ({num_frames} frames)...")
    cap_bg = ScreenCapture(hwnd, cfg["cap_x"], cfg["cap_y"], cfg["cap_w"], cfg["cap_h"], background=True)

    bg_intensities = []
    bg_latencies = []

    for _ in range(num_frames):
        t0 = time.perf_counter()
        frame = cap_bg.grab()
        latency = (time.perf_counter() - t0) * 1000
        bg_latencies.append(latency)
        bg_intensities.append(float(frame.mean()))

    cap_bg.close()

    bg_black = sum(1 for x in bg_intensities if x < 5)
    print(f"  Mean intensity: {np.mean(bg_intensities):.1f}")
    print(f"  Black frames: {bg_black}/{num_frames}")
    print(f"  Latency: {np.mean(bg_latencies):.1f}ms avg, {np.max(bg_latencies):.1f}ms max")

    # Recommendations
    print("\n💡 RECOMMENDATIONS:")

    if fg_black > 0:
        print("  ⚠️  Foreground capture has black frames - check DPI scaling settings")

    if bg_black > num_frames // 2:
        print("  ❌ Background capture failing - switch PPSSPP to D3D11 renderer")
        print("     (Settings → Graphics → Backend → Direct3D 11)")
    elif bg_black > 0:
        print("  ⚠️  Some background capture failures - D3D11 renderer recommended")
    else:
        print("  ✅ Background capture working - safe to use --background flag")

    if np.mean(fg_latencies) > 50:
        print("  ⚠️  High capture latency - consider lowering agent_hz")
    else:
        print("  ✅ Capture latency acceptable for training")

    print()


def debug_visual(cfg: dict):
    """Show live visualization of what the agent sees.
    
    Displays:
    - Raw captured frame from PPSSPP
    - Preprocessed 84x84 grayscale frame (what agent sees)
    - Current detected game state
    - Real-time statistics
    
    Press 'q' to quit, 'r' to reset state detector.
    """
    print("=" * 60)
    print("DEBUG VISUALIZATION")
    print("=" * 60)
    print("Press 'q' to quit, 'r' to simulate reset")
    print()
    
    try:
        hwnd = find_window_handle(cfg["window_title_substr"])
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        print("Make sure PPSSPP is running with the game loaded.")
        return
    
    focus_window(hwnd)
    time.sleep(0.3)
    
    cap = ScreenCapture(hwnd, cfg["cap_x"], cfg["cap_y"], cfg["cap_w"], cfg["cap_h"], 
                        background=cfg.get("use_background_capture", False))
    
    obs_w, obs_h = cfg["obs_w"], cfg["obs_h"]
    
    print("Starting visualization... (Press 'q' in OpenCV window to quit)")
    
    frame_count = 0
    start_time = time.time()
    
    while True:
        # Capture frame
        frame_bgr = cap.grab()
        
        # Preprocess (same as agent sees)
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        frame_resized = cv2.resize(frame_gray, (obs_w, obs_h), interpolation=cv2.INTER_AREA)
        
        # Detect state
        state = detect_game_state(frame_resized, frame_bgr)
        
        # Calculate stats
        mean_val = float(frame_resized.mean())
        std_val = float(frame_resized.std())
        fps = frame_count / max(0.001, time.time() - start_time)
        
        # Create display image
        # Scale up the 84x84 for visibility
        display_processed = cv2.resize(frame_resized, (336, 336), interpolation=cv2.INTER_NEAREST)
        display_processed = cv2.cvtColor(display_processed, cv2.COLOR_GRAY2BGR)
        
        # Add text overlay
        cv2.putText(display_processed, f"State: {state.name}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(display_processed, f"Mean: {mean_val:.1f}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
        cv2.putText(display_processed, f"Std: {std_val:.1f}", (10, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
        cv2.putText(display_processed, f"FPS: {fps:.1f}", (10, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
        
        # Color code based on state
        state_colors = {
            GameState.GAMEPLAY: (0, 255, 0),    # Green
            GameState.LOADING: (0, 0, 255),      # Red
            GameState.RESULTS: (0, 165, 255),    # Orange
            GameState.SAVE_DIALOG: (255, 0, 255), # Magenta
            GameState.LABORATORY: (255, 255, 0),  # Cyan
            GameState.UNKNOWN: (128, 128, 128),   # Gray
        }
        border_color = state_colors.get(state, (128, 128, 128))
        cv2.rectangle(display_processed, (0, 0), (335, 335), border_color, 3)
        
        # Show original capture resized
        display_raw = cv2.resize(frame_bgr, (336, 336))
        cv2.putText(display_raw, "Raw Capture", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Combine side by side
        combined = np.hstack([display_raw, display_processed])
        
        cv2.imshow("Debug Visual - Agent View", combined)
        
        frame_count += 1
        
        key = cv2.waitKey(33) & 0xFF  # ~30 FPS
        if key == ord('q'):
            break
        elif key == ord('r'):
            print("[Debug] Simulating reset...")
            # Show what happens during reset
            for i in range(10):
                frame_bgr = cap.grab()
                frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                frame_resized = cv2.resize(frame_gray, (obs_w, obs_h))
                state = detect_game_state(frame_resized, frame_bgr, debug=True)
                time.sleep(0.3)
    
    cap.close()
    cv2.destroyAllWindows()
    print("\\nVisualization ended.")



def visualize_network(cfg: dict):
    """Visualize the CNN architecture."""
    if not HAS_TORCHVIZ:
        print("torchviz not installed. Run: pip install torchviz graphviz")
        return

    import torch

    # Create a dummy model to visualize
    env = DummyVecEnv([lambda: JetpackPPSSPPEnv(cfg)])
    model = PPO("CnnPolicy", env, verbose=0)

    # Get network
    policy = model.policy

    # Create dummy input
    dummy_input = torch.randn(1, cfg["stack_n"], cfg["obs_h"], cfg["obs_w"])

    # Forward pass
    features = policy.features_extractor(dummy_input)

    # Visualize
    dot = torchviz.make_dot(features, params=dict(policy.features_extractor.named_parameters()))

    output_path = "network_architecture"
    dot.render(output_path, format="png", cleanup=True)
    print(f"Saved network visualization to {output_path}.png")

    env.close()


def train_ppo(cfg: dict, timesteps: int = 300000, resume: str = None, use_wandb: bool = False):
    """Train PPO agent."""
    global _env_global

    # Create directories
    Path(cfg["checkpoint_dir"]).mkdir(exist_ok=True)
    Path(cfg["model_dir"]).mkdir(exist_ok=True)

    # Create environment
    env = DummyVecEnv([lambda: JetpackPPSSPPEnv(cfg)])
    _env_global = env

    # Callbacks
    callbacks = [
        CheckpointCallback(
            save_freq=cfg["checkpoint_freq"],
            save_path=cfg["checkpoint_dir"],
            name_prefix="ppo_jetpack"
        ),
        MetricsCallback()
    ]

    # Weights & Biases
    if use_wandb and HAS_WANDB:
        run = wandb.init(
            project="jetpack-joyride-rl",
            config=cfg,
            sync_tensorboard=True,
            monitor_gym=True
        )
        callbacks.append(WandbCallback(
            gradient_save_freq=1000,
            model_save_path=f"models/{run.id}",
            verbose=2
        ))

    # Create or load model
    if resume and os.path.exists(resume):
        print(f"Resuming from {resume}")
        model = PPO.load(resume, env=env)
    else:
        model = PPO(
            "CnnPolicy",
            env,
            verbose=1,
            n_steps=1024,
            batch_size=256,
            gamma=0.99,
            learning_rate=2.5e-4,
            tensorboard_log=cfg["tensorboard_dir"],
        )

    print(f"Starting training for {timesteps} timesteps...")
    print("Monitor with: tensorboard --logdir tb_jetpack")

    model.learn(total_timesteps=timesteps, callback=callbacks)

    # Save final model
    model_path = os.path.join(cfg["model_dir"], "ppo_jetpack_final.zip")
    model.save(model_path)
    print(f"Saved model: {model_path}")

    if use_wandb and HAS_WANDB:
        wandb.finish()

    env.close()


def evaluate(cfg: dict, model_path: str, episodes: int = 10):
    """Evaluate trained model."""
    global _env_global

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")

    env = JetpackPPSSPPEnv(cfg, render_mode="human")
    _env_global = env

    model = PPO.load(model_path)

    print(f"Evaluating model: {model_path}")
    print(f"Running {episodes} episodes...")

    total_rewards = []

    for ep in range(episodes):
        obs, _ = env.reset()
        done = False
        episode_reward = 0
        steps = 0

        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, trunc, info = env.step(action)
            env.render()
            episode_reward += reward
            steps += 1

        total_rewards.append(episode_reward)
        print(f"Episode {ep+1}: Reward={episode_reward:.1f}, Steps={steps}, Score={info.get('score', 'N/A')}")

    print(f"\nAverage reward: {np.mean(total_rewards):.1f} ± {np.std(total_rewards):.1f}")
    env.close()


# =========================
# Main
# =========================
def main():
    parser = argparse.ArgumentParser(description="Jetpack Joyride RL Trainer")

    # Actions
    parser.add_argument("--launch", action="store_true", help="Launch PPSSPP with ROM")
    parser.add_argument("--calibrate", action="store_true", help="Calibrate capture region (GUI)")
    parser.add_argument("--calibrate-score", action="store_true", help="Calibrate score OCR region (GUI)")
    parser.add_argument("--play-random", action="store_true", help="Run 30s of random actions")
    parser.add_argument("--capture-gameover", action="store_true", help="Capture game-over template")
    parser.add_argument("--diagnose-capture", action="store_true", help="Test capture reliability (foreground/background)")
    parser.add_argument("--train", action="store_true", help="Train PPO agent")
    parser.add_argument("--eval", type=str, metavar="MODEL", help="Evaluate trained model")
    parser.add_argument("--visualize-network", action="store_true", help="Visualize CNN architecture")
    parser.add_argument("--debug-visual", action="store_true", help="Live visualization of what agent sees")

    # Training options
    parser.add_argument("--timesteps", type=int, default=300000, help="Training timesteps")
    parser.add_argument("--resume", type=str, help="Resume from checkpoint")
    parser.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    parser.add_argument("--background", action="store_true", help="Use background capture (no focus needed)")

    args = parser.parse_args()

    # Load saved configs
    load_configs(CONFIG)

    # Apply flags
    if args.background:
        CONFIG["use_background_capture"] = True

    # Execute actions
    if args.launch:
        launch_ppsspp(CONFIG)
        time.sleep(3.0)

    if args.calibrate:
        calibrate_gui(CONFIG, mode="capture")
        return

    if args.calibrate_score:
        calibrate_gui(CONFIG, mode="score")
        return

    if args.capture_gameover:
        capture_gameover_template(CONFIG)
        return

    if args.diagnose_capture:
        diagnose_capture(CONFIG)
        return

    if args.play_random:
        play_random(CONFIG)
        return

    if args.visualize_network:
        visualize_network(CONFIG)
        return

    if args.debug_visual:
        debug_visual(CONFIG)
        return

    if args.train:
        train_ppo(CONFIG, timesteps=args.timesteps, resume=args.resume, use_wandb=args.wandb)
        return

    if args.eval:
        evaluate(CONFIG, args.eval)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
