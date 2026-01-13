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
import atexit
import ctypes
import json
import os
import re
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional, Tuple

import cv2
import gymnasium as gym
import mss
import numpy as np
import win32api
import win32con

# Windows-only imports
import win32gui
import win32ui
from gymnasium import spaces
from PIL import Image, ImageTk

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
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv

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
            print("[StateDetect] -> SAVE_DIALOG (uniform gray)")
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
        print("[StateDetect] -> GAMEPLAY (default)")
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
    "motion_static_steps": 60,             # stricter motion detector to avoid false deaths
    # Episode-ending guards to avoid premature resets on transient black frames
    "min_gameplay_steps_for_done": 30,       # must see at least this many gameplay steps
    "game_state_done_confirm_frames": 6,     # require consecutive non-gameplay frames

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

        except Exception:
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
# MLP Feature Extraction
# =========================
class FeatureExtractor:
    """Extract structured features from game frame for MLP policy.
    
    Extracts:
    - Barry's Y position (via face template matching)
    - Barry's velocity (frame-to-frame Y delta)
    - Nearest 5 objects: coins, zappers, missiles
    
    Returns normalized 17-float vector per frame (68 with 4-frame stacking).
    """
    
    # Object type encoding
    OBJ_NONE = 0
    OBJ_COIN = 1
    OBJ_ZAPPER = 2
    OBJ_MISSILE = 3
    
    # Detection thresholds
    BARRY_THRESHOLD = 0.5
    COIN_THRESHOLD = 0.7
    ELECTRODE_THRESHOLD = 0.6
    MISSILE_THRESHOLD = 0.6
    
    # Zapper pairing
    MAX_ZAPPER_LENGTH = 200  # Max pixels between electrode pairs
    
    def __init__(self, templates_dir: str = "templates/", frame_w: int = 480, frame_h: int = 272):
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.templates_dir = Path(templates_dir)
        
        # State tracking
        self.prev_barry_y = frame_h / 2  # Start at center
        self.prev_features = None
        
        # Performance: scale factor for faster template matching
        # 0.25 = 4x smaller = ~16x faster matching
        self.FAST_SCALE = 0.25
        self.fast_w = int(frame_w * self.FAST_SCALE)
        self.fast_h = int(frame_h * self.FAST_SCALE)
        
        # Load and resize templates for fast matching
        self.barry_face = self._load_and_resize_template("barry_face.png")
        self.coin = self._load_and_resize_template("coin2.png")
        self.electrode = self._load_and_resize_template("electrode.png")
        self.missile = self._load_and_resize_template("Missile_Unbroken.jpeg")
        
        # Fallback: create electrode template from zapper if not found
        if self.electrode is None:
            self._create_electrode_template()
        
        # Fallback: create face template from fly.png if not found
        if self.barry_face is None:
            self._create_face_template()
    
    def _load_template(self, filename: str) -> Optional[np.ndarray]:
        """Load template image, return None if not found."""
        path = self.templates_dir / filename
        if path.exists():
            img = cv2.imread(str(path))
            if img is not None:
                return img
        return None
    
    def _load_and_resize_template(self, filename: str) -> Optional[np.ndarray]:
        """Load template and resize for fast matching."""
        img = self._load_template(filename)
        if img is not None:
            h, w = img.shape[:2]
            new_w = max(8, int(w * self.FAST_SCALE))
            new_h = max(8, int(h * self.FAST_SCALE))
            return cv2.resize(img, (new_w, new_h))
        return None
    
    def _create_electrode_template(self):
        """Create electrode template by cropping from zap.png."""
        zap = self._load_template("zap.png")
        if zap is not None:
            h, w = zap.shape[:2]
            crop = zap[:, :w//4].copy()
            # Resize for fast matching
            new_w = max(8, int(crop.shape[1] * self.FAST_SCALE))
            new_h = max(8, int(crop.shape[0] * self.FAST_SCALE))
            self.electrode = cv2.resize(crop, (new_w, new_h))
            print(f"[FeatureExtractor] Created electrode template: {self.electrode.shape[:2]}")
    
    def _create_face_template(self):
        """Create face template by cropping from fly.png."""
        fly = self._load_template("fly.png")
        if fly is not None:
            h, w = fly.shape[:2]
            face_h, face_w = min(40, h//2), min(30, w//3)
            crop = fly[:face_h, w//2:w//2+face_w].copy()
            # Resize for fast matching
            new_w = max(8, int(face_w * self.FAST_SCALE))
            new_h = max(8, int(face_h * self.FAST_SCALE))
            self.barry_face = cv2.resize(crop, (new_w, new_h))
            print(f"[FeatureExtractor] Created face template: {self.barry_face.shape[:2]}")
    
    def extract(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Extract normalized 17-float feature vector from frame."""
        # PERFORMANCE: Resize frame once for all template matching
        self._small_frame = cv2.resize(frame_bgr, (self.fast_w, self.fast_h))
        
        barry_x, barry_y = self._detect_barry(self._small_frame)
        # Scale back to original coordinates
        barry_x = barry_x / self.FAST_SCALE
        barry_y = barry_y / self.FAST_SCALE
        self.last_barry_x = barry_x  # Store for GUI
        velocity = self._calc_velocity(barry_y)
        self.prev_barry_y = barry_y
        objects = self._detect_all_objects(self._small_frame, barry_y * self.FAST_SCALE)

        return self._build_vector(barry_y, velocity, objects)
    
    def _detect_barry(self, frame_bgr: np.ndarray) -> Tuple[float, float]:
        """Detect Barry's position. Returns (x, y) in scaled coordinates."""
        # Barry is always in the left third of the screen (use scaled dimensions)
        search_w = frame_bgr.shape[1] // 3
        search_region = frame_bgr[:, :search_w]
        
        if self.barry_face is not None:
            try:
                result = cv2.matchTemplate(search_region, self.barry_face, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                if max_val >= self.BARRY_THRESHOLD:
                    x = max_loc[0] + self.barry_face.shape[1] / 2
                    y = max_loc[1] + self.barry_face.shape[0] / 2
                    return (x, y)
            except cv2.error:
                pass
        
        # Fallback: color-based detection (Barry's skin/jetpack colors)
        # Look for bright orange-ish pixels in left region
        hsv = cv2.cvtColor(search_region, cv2.COLOR_BGR2HSV)
        # Skin tone range
        mask = cv2.inRange(hsv, (5, 50, 100), (20, 200, 255))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) > 100:  # Minimum size
                M = cv2.moments(largest)
                if M["m00"] > 0:
                    x = M["m10"] / M["m00"]
                    y = M["m01"] / M["m00"]
                    return (x, y)
        
        # Return previous position if detection fails
        return (getattr(self, 'last_barry_x', 70), self.prev_barry_y)
    
    def _detect_barry_y(self, frame_bgr: np.ndarray) -> float:
        """Detect Barry's Y position (legacy wrapper)."""
        _, y = self._detect_barry(frame_bgr)
        return y
    
    def _calc_velocity(self, current_y: float) -> float:
        """Calculate velocity from frame-to-frame Y delta."""
        velocity = current_y - self.prev_barry_y
        return max(-50, min(50, velocity))
    
    def _detect_all_objects(self, frame_bgr: np.ndarray, barry_y: float) -> list:
        """Detect all objects and return sorted by X distance."""
        objects = []
        objects.extend(self._detect_coins(frame_bgr))
        objects.extend(self._detect_zappers(frame_bgr))
        objects.extend(self._detect_missiles(frame_bgr))
        objects.sort(key=lambda o: o['x'])
        return objects[:5]
    
    def _detect_coins(self, frame_bgr: np.ndarray) -> list:
        if self.coin is None:
            return []
        return self._match_template(frame_bgr, self.coin, self.OBJ_COIN, self.COIN_THRESHOLD)
    
    def _detect_missiles(self, frame_bgr: np.ndarray) -> list:
        if self.missile is None:
            return []
        return self._match_template(frame_bgr, self.missile, self.OBJ_MISSILE, self.MISSILE_THRESHOLD)
    
    def _detect_zappers(self, frame_bgr: np.ndarray) -> list:
        """Detect zappers by finding electrode pairs."""
        if self.electrode is None:
            return []
        electrodes = self._match_template(frame_bgr, self.electrode, -1, self.ELECTRODE_THRESHOLD)
        zappers = []
        used = set()
        for i, e1 in enumerate(electrodes):
            if i in used:
                continue
            for j, e2 in enumerate(electrodes):
                if j <= i or j in used:
                    continue
                dist = np.sqrt((e1['x'] - e2['x'])**2 + (e1['y'] - e2['y'])**2)
                if dist < self.MAX_ZAPPER_LENGTH:
                    zappers.append({
                        'type': self.OBJ_ZAPPER,
                        'x': (e1['x'] + e2['x']) / 2,
                        'y': (e1['y'] + e2['y']) / 2,
                    })
                    used.add(i)
                    used.add(j)
                    break
        return zappers
    
    def _match_template(self, frame_bgr: np.ndarray, template: np.ndarray, 
                        obj_type: int, threshold: float) -> list:
        """Template matching with non-maximum suppression."""
        try:
            result = cv2.matchTemplate(frame_bgr, template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= threshold)
            objects = []
            h, w = template.shape[:2]
            for pt in zip(*locations[::-1]):
                obj = {'type': obj_type, 'x': pt[0] + w / 2, 'y': pt[1] + h / 2}
                objects.append(obj)
            objects = self._non_max_suppression(objects, overlap_dist=w/2)
            return objects
        except cv2.error:
            return []
    
    def _non_max_suppression(self, objects: list, overlap_dist: float) -> list:
        """Remove overlapping detections."""
        if len(objects) <= 1:
            return objects
        kept = []
        for obj in objects:
            is_duplicate = False
            for kept_obj in kept:
                dist = np.sqrt((obj['x'] - kept_obj['x'])**2 + (obj['y'] - kept_obj['y'])**2)
                if dist < overlap_dist:
                    is_duplicate = True
                    break
            if not is_duplicate:
                kept.append(obj)
        return kept
    
    def _build_vector(self, barry_y: float, velocity: float, objects: list) -> np.ndarray:
        """Build normalized 17-float feature vector."""
        vec = np.zeros(17, dtype=np.float32)
        vec[0] = barry_y / self.frame_h
        vec[1] = velocity / 50.0
        for i in range(5):
            base_idx = 2 + i * 3
            if i < len(objects):
                obj = objects[i]
                vec[base_idx] = obj['x'] / self.frame_w
                vec[base_idx + 1] = (obj['y'] - barry_y) / self.frame_h
                vec[base_idx + 2] = obj['type'] / 3.0
            else:
                vec[base_idx] = 1.0
                vec[base_idx + 1] = 0.0
                vec[base_idx + 2] = 0.0
        return vec
    
    def reset(self):
        """Reset state for new episode."""
        self.prev_barry_y = self.frame_h / 2
        self.prev_features = None


class CachedFeatureExtractor(FeatureExtractor):
    """Feature extractor with caching for faster training.
    
    Only runs full template matching every N frames.
    Interpolates object positions in between.
    """
    
    def __init__(self, templates_dir: str = "templates/", frame_w: int = 480, frame_h: int = 272,
                 detect_every_n: int = 3):
        super().__init__(templates_dir, frame_w, frame_h)
        self.detect_every_n = detect_every_n
        self.frame_count = 0
        self.cached_objects = []
        self.cached_barry_y = frame_h / 2
        self.last_detections = {'barry': None, 'objects': [], 'confidence': {}}
    
    def extract(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Extract features with caching."""
        self.frame_count += 1
        
        # Full detection every N frames
        if self.frame_count % self.detect_every_n == 0:
            barry_x, barry_y = self._detect_barry(frame_bgr)
            objects = self._detect_all_objects(frame_bgr, barry_y)
            self.cached_barry_y = barry_y
            self.cached_barry_x = barry_x
            self.cached_objects = objects
            self.last_barry_x = barry_x  # For GUI
            self.last_detections = {
                'barry': barry_y,
                'barry_x': barry_x,
                'objects': objects.copy(),
                'frame': frame_bgr.copy() if frame_bgr is not None else None
            }
        else:
            # Use cached with interpolation
            barry_y = self.cached_barry_y
            barry_x = getattr(self, 'cached_barry_x', 70)

            objects = self._interpolate_objects()
        
        velocity = self._calc_velocity(barry_y)
        self.prev_barry_y = barry_y
        
        return self._build_vector(barry_y, velocity, objects)
    
    def _interpolate_objects(self) -> list:
        """Interpolate object positions (objects move left)."""
        interpolated = []
        scroll_speed = 5  # pixels per frame estimate
        
        for obj in self.cached_objects:
            new_obj = obj.copy()
            new_obj['x'] = max(0, obj['x'] - scroll_speed)  # Objects scroll left
            if new_obj['x'] > 0:  # Only keep if still on screen
                interpolated.append(new_obj)
        
        # Update cache with interpolated positions
        self.cached_objects = interpolated
        return interpolated
    
    def get_last_detections(self) -> dict:
        """Get last detection results for visualization."""
        return self.last_detections
    
    def reset(self):
        """Reset state for new episode."""
        super().reset()
        self.frame_count = 0
        self.cached_objects = []
        self.cached_barry_y = self.frame_h / 2


class TrainingVisualizerGUI:
    """Tkinter GUI for visualizing training in real-time.
    
    Shows:
    - Game frame with detection overlays
    - Barry position marked
    - Objects with colored boxes
    - Episode statistics
    """
    
    def __init__(self, title: str = "Jetpack RL Training Monitor"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("900x500")
        
        # Main frame
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Left panel - game view
        self.game_frame = ttk.LabelFrame(self.main_frame, text="Game View", padding="5")
        self.game_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self.canvas = tk.Canvas(self.game_frame, width=480, height=272, bg="black")
        self.canvas.pack()
        
        # Detection info below canvas
        self.detection_label = ttk.Label(self.game_frame, text="Detection: -", font=("Consolas", 9))
        self.detection_label.pack(pady=5)
        
        # Right panel - stats
        self.stats_frame = ttk.LabelFrame(self.main_frame, text="Training Stats", padding="10")
        self.stats_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        # Stats labels - including debug stats for state detection
        self.stats_labels = {}
        stats = ["Episode", "Total Steps", "Episode Steps", "Episode Reward", 
                 "Avg Reward", "FPS", "Game State", "Pixel Mean", "Pixel Std", "State Reason"]
        for i, stat in enumerate(stats):
            ttk.Label(self.stats_frame, text=f"{stat}:", font=("Arial", 10, "bold")).grid(
                row=i, column=0, sticky="w", pady=2)
            self.stats_labels[stat] = ttk.Label(self.stats_frame, text="-", font=("Arial", 10))
            self.stats_labels[stat].grid(row=i, column=1, sticky="w", padx=10, pady=2)

        
        # Control buttons
        self.control_frame = ttk.Frame(self.main_frame)
        self.control_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        self.paused = False
        self.stopped = False
        
        self.pause_btn = ttk.Button(self.control_frame, text="Pause", command=self._toggle_pause)
        self.pause_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(self.control_frame, text="Stop", command=self._stop)
        self.stop_btn.pack(side="left", padx=5)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=2)
        self.main_frame.columnconfigure(1, weight=1)
        
        self._photo = None
        self._last_update = time.time()
    
    def _toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.config(text="Resume" if self.paused else "Pause")
    
    def _stop(self):
        self.stopped = True
    
    def update(self, frame_bgr: np.ndarray, detections: dict, stats: dict):
        """Update GUI with new frame and stats."""
        if self.stopped:
            return
        
        # PERFORMANCE: Throttle updates to ~5 FPS (every 200ms)
        now = time.time()
        if now - self._last_update < 0.2:
            return
        self._last_update = now
        
        # Convert to grayscale for performance display
        if frame_bgr is not None:
            gray_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            display_frame = cv2.cvtColor(gray_frame, cv2.COLOR_GRAY2BGR)  # Back to BGR for drawing
        else:
            display_frame = np.zeros((272, 480, 3), dtype=np.uint8)
        
        # Draw Barry position
        if detections.get('barry') is not None:
            barry_y = int(detections['barry'])
            barry_x = int(detections.get('barry_x', 70))  # Use detected X position
            cv2.circle(display_frame, (barry_x, barry_y), 15, (0, 255, 0), 2)  # Green circle
            cv2.putText(display_frame, "Barry", (barry_x - 20, barry_y - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Draw objects
        colors = {1: (0, 215, 255), 2: (0, 0, 255), 3: (0, 165, 255)}  # Coin=gold, Zapper=red, Missile=orange
        names = {1: "Coin", 2: "Zap", 3: "Mis"}
        
        for obj in detections.get('objects', []):
            x, y = int(obj['x']), int(obj['y'])
            obj_type = obj.get('type', 0)
            color = colors.get(obj_type, (255, 255, 255))
            name = names.get(obj_type, "?")
            cv2.rectangle(display_frame, (x-15, y-15), (x+15, y+15), color, 2)
            cv2.putText(display_frame, name, (x-10, y-20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        # Convert to PhotoImage
        rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)

        pil_img = Image.fromarray(rgb_frame)
        self._photo = ImageTk.PhotoImage(pil_img)
        
        # Update canvas
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        
        # Update detection label
        barry_str = f"Barry Y: {detections.get('barry', 0):.1f}" if detections.get('barry') else "Barry: -"
        obj_count = len(detections.get('objects', []))
        self.detection_label.config(text=f"{barry_str} | Objects: {obj_count}")
        
        # Update stats
        for key, value in stats.items():
            if key in self.stats_labels:
                self.stats_labels[key].config(text=str(value))
        
        # Process Tkinter events
        self.root.update_idletasks()
        self.root.update()
    
    def is_stopped(self) -> bool:
        return self.stopped
    
    def is_paused(self) -> bool:
        return self.paused
    
    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


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
        self._last_proc = None
        self._last_action = None
        self._last_reward = 0.0
        self._last_done_reason = None
        self._last_state = GameState.UNKNOWN
        self._has_seen_gameplay = False
        self._gameplay_steps = 0
        self._non_gameplay_frames = 0

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
        self._last_proc = proc
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

        self._last_action = None
        self._last_reward = 0.0
        self._last_done_reason = None
        self._last_state = GameState.UNKNOWN
        self._has_seen_gameplay = False
        self._gameplay_steps = 0
        self._non_gameplay_frames = 0

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
            done_reason = None

            if self.score_extractor and self.cfg["use_ocr_reward"]:
                score = self.score_extractor.extract(frame_bgr)
                if score is not None and score > self.prev_score:
                    # Distance-based reward
                    delta = score - self.prev_score
                    reward = delta * 0.1
                    self.prev_score = score

            # Game state detection for gating and done reasons
            game_state = detect_game_state(proc, frame_bgr)

            # If we haven't reached gameplay yet, try to navigate and avoid ending early
            if not self._has_seen_gameplay and game_state != GameState.GAMEPLAY:
                self._navigate_to_gameplay(max_attempts=6, debug=False)
                proc, frame_bgr = self._grab_proc()
                self.frames[-1] = proc
                game_state = detect_game_state(proc, frame_bgr)

            if game_state == GameState.GAMEPLAY:
                self._has_seen_gameplay = True
                self._gameplay_steps += 1
                self._non_gameplay_frames = 0
            else:
                # Do not reward/penalize while still navigating menus
                reward = 0.0
                if self._has_seen_gameplay:
                    self._non_gameplay_frames += 1

            done = False

            if self._has_seen_gameplay:
                enough_steps = self._gameplay_steps >= self.cfg.get("min_gameplay_steps_for_done", 0)
                # Method 1: Motion/template based done detector
                if enough_steps and self.done_detector.is_done(proc):
                    done = True
                    done_reason = "done_detector"
                    print("[Step] DONE by motion/template detector")

                # Method 2: GameState detection (more reliable for death)
                # ONLY end on death states (RESULTS, SAVE_DIALOG)
                # LOADING is restart transition - don't end episode there
                confirm_frames = self.cfg.get("game_state_done_confirm_frames", 1)
                if game_state in (GameState.RESULTS, GameState.SAVE_DIALOG):
                    if enough_steps and self._non_gameplay_frames >= confirm_frames:
                        done = True
                        done_reason = done_reason or f"death_{game_state.name.lower()}"
                        print(f"[Step] DONE by death: {game_state.name}, mean={float(proc.mean()):.1f}")


            if done:
                reward = -10.0  # Death penalty (reduced from -100 for better learning)
                self._release_action()

            self._last_action = int(action)
            self._last_reward = reward
            self._last_done_reason = done_reason
            self._last_state = game_state
            self._last_raw_frame = frame_bgr  # PERF: Expose for subclass reuse

            info = {
                "score": self.prev_score,
                "done_reason": done_reason,
                "game_state": game_state.name,
                "waiting_for_gameplay": not self._has_seen_gameplay,
                "gameplay_steps": self._gameplay_steps,
            }

            return self._stack_obs(), reward, done, False, info

        except Exception:
            # INV-1: Always release keys on exception to prevent stuck keys
            self._release_action()
            raise

    def render(self):
        if self.render_mode == "human" and self._last_frame is not None:
            raw_display = cv2.resize(self._last_frame, (336, 336))
            proc_display = None

            if self._last_proc is not None:
                proc_display = cv2.resize(self._last_proc, (336, 336), interpolation=cv2.INTER_NEAREST)
                proc_display = cv2.cvtColor(proc_display, cv2.COLOR_GRAY2BGR)
            else:
                proc_display = np.zeros((336, 336, 3), dtype=np.uint8)

            # Overlay status text
            overlay_text = [
                f"Action: {self._last_action}",
                f"Reward: {self._last_reward:.2f}",
                f"State: {self._last_state.name if self._last_state else 'UNKNOWN'}",
                f"DoneReason: {self._last_done_reason or '-'}",
            ]
            y = 25
            for line in overlay_text:
                cv2.putText(proc_display, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                y += 25

            combined = np.hstack([raw_display, proc_display])
            cv2.imshow("Jetpack RL Monitor (raw | agent view)", combined)
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
# MLP-Based Gym Environment
# =========================
class JetpackMLPEnv(JetpackPPSSPPEnv):
    """MLP-based environment using structured feature observations.
    
    Uses CachedFeatureExtractor for faster training:
    - Full detection every 3 frames, interpolates between
    - Barry Y position and velocity
    - 5 nearest objects (x, y, type each)
    
    With 4-frame stacking: 68-float observation space.
    
    Optional GUI visualization via TrainingVisualizerGUI.
    """
    
    # Minimum steps before allowing episode to end
    MIN_GAMEPLAY_STEPS = 30  # ~2 seconds at 15Hz
    
    def __init__(self, cfg: dict, render_mode: str = None,
                 capture_backend=None, input_backend=None, window_backend=None,
                 use_gui: bool = False):
        # Initialize parent (CNN-based env)
        super().__init__(cfg, render_mode, capture_backend, input_backend, window_backend)
        
        # Use cached feature extractor for speed
        detect_every_n = cfg.get("detect_every_n", 3)
        self.feature_extractor = CachedFeatureExtractor(
            templates_dir=cfg.get("templates_dir", "templates/"),
            frame_w=cfg["cap_w"],
            frame_h=cfg["cap_h"],
            detect_every_n=detect_every_n
        )
        
        # 17 features × 4 stacked frames = 68
        self.feature_stack_n = cfg.get("stack_n", 4)
        self.feature_frames = deque(maxlen=self.feature_stack_n)
        
        # Override observation space
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0,
            shape=(17 * self.feature_stack_n,),
            dtype=np.float32
        )
        
        # GUI visualization
        self.use_gui = use_gui
        self.gui = None
        if use_gui:
            try:
                self.gui = TrainingVisualizerGUI()
            except Exception as e:
                print(f"[Warning] Could not initialize GUI: {e}")
                self.use_gui = False
        
        # Episode tracking for improved stats
        self.episode_count = 0
        self.total_steps = 0
        self.episode_steps = 0
        self.episode_reward = 0.0
        self.episode_rewards_history = []
        self._fps_counter = 0
        self._fps_time = time.time()
        self._current_fps = 0.0
    
    def _stack_features(self) -> np.ndarray:
        """Stack feature vectors into flat observation."""
        assert len(self.feature_frames) == self.feature_stack_n
        return np.concatenate(list(self.feature_frames), axis=0)
    
    def reset(self, seed=None, options=None):
        """Reset and return feature-based observation."""
        # Track episode completion
        if self.episode_steps > 0:
            self.episode_rewards_history.append(self.episode_reward)
            self.episode_count += 1
        
        # Use parent reset for navigation
        super().reset(seed=seed, options=options)
        
        self.feature_extractor.reset()
        self.feature_frames.clear()
        
        # Reset episode tracking
        self.episode_steps = 0
        self.episode_reward = 0.0
        
        # Get initial frame and extract features
        frame = self._last_frame
        if frame is None:
            frame = self.cap.grab()
        
        features = self.feature_extractor.extract(frame)
        for _ in range(self.feature_stack_n):
            self.feature_frames.append(features.copy())
        
        return self._stack_features(), {}
    
    def step(self, action):
        """Step and return feature-based observation."""
        # Use parent step (handles input, timing, done detection)
        _, reward, done, truncated, info = super().step(action)
        
        # Episode must have minimum steps before allowing DONE
        if done and self.episode_steps < self.MIN_GAMEPLAY_STEPS:
            done = False
            info['done_blocked'] = f"Need {self.MIN_GAMEPLAY_STEPS - self.episode_steps} more steps"
        
        # Update tracking
        self.episode_steps += 1
        self.total_steps += 1
        self.episode_reward += reward
        
        # Calculate FPS
        self._fps_counter += 1
        now = time.time()
        if now - self._fps_time >= 1.0:
            self._current_fps = self._fps_counter / (now - self._fps_time)
            self._fps_counter = 0
            self._fps_time = now
        
        # PERF: Reuse parent's captured frame instead of recapturing
        raw_frame = self._last_raw_frame
        
        if raw_frame is not None:
            features = self.feature_extractor.extract(raw_frame)
            self.feature_frames.append(features)

            
            # Update GUI if enabled (pass raw color frame, not preprocessed)
            if self.use_gui and self.gui:
                avg_reward = sum(self.episode_rewards_history[-10:]) / max(1, len(self.episode_rewards_history[-10:]))
                
                # DEBUG: Calculate state detection values for visualization
                gray_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
                pixel_mean = float(gray_frame.mean())
                pixel_std = float(gray_frame.std())
                
                # Determine why this state was detected
                state_reason = "Default=GAMEPLAY"
                if pixel_mean < 25:
                    state_reason = "mean<25 → LOADING"
                elif 100 < pixel_mean < 145 and pixel_std < 25:
                    state_reason = "gray+low_std → SAVE_DIALOG"
                elif pixel_mean < 70:
                    bright_ratio = np.sum(gray_frame > 180) / gray_frame.size
                    if bright_ratio > 0.02:
                        state_reason = f"dark+text({bright_ratio:.2f}) → RESULTS"
                
                stats = {
                    "Episode": self.episode_count + 1,
                    "Total Steps": self.total_steps,
                    "Episode Steps": self.episode_steps,
                    "Episode Reward": f"{self.episode_reward:.1f}",
                    "Avg Reward": f"{avg_reward:.1f}" if self.episode_rewards_history else "-",
                    "FPS": f"{self._current_fps:.1f}",
                    "Game State": self._last_state.name if self._last_state else "UNKNOWN",
                    "Pixel Mean": f"{pixel_mean:.1f}",
                    "Pixel Std": f"{pixel_std:.1f}",
                    "State Reason": state_reason
                }
                detections = self.feature_extractor.get_last_detections()
                self.gui.update(raw_frame, detections, stats)

                
                if self.gui.is_stopped():
                    done = True
                    truncated = True
                    info['stopped_by_gui'] = True
        
        return self._stack_features(), reward, done, truncated, info

    
    def close(self):
        """Clean up resources."""
        if self.gui:
            self.gui.close()
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
        self.root.geometry("+10+50")

        # Keep on top so it's always visible
        self.root.attributes('-topmost', True)

        self.root.mainloop()

        try:
            self.sct.close()
        except Exception:
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


def train_ppo(cfg: dict, timesteps: int = 300000, resume: str = None, use_wandb: bool = False, use_mlp: bool = False, use_gui: bool = False):
    """Train PPO agent.
    
    Args:
        cfg: Configuration dictionary
        timesteps: Total training timesteps
        resume: Path to checkpoint to resume from
        use_wandb: Enable Weights & Biases logging
        use_mlp: Use MLP policy with structured features instead of CNN
        use_gui: Show training GUI with detection visualization (MLP only)
    """
    global _env_global

    # Create directories
    Path(cfg["checkpoint_dir"]).mkdir(exist_ok=True)
    Path(cfg["model_dir"]).mkdir(exist_ok=True)

    # Create environment (MLP or CNN)
    if use_mlp:
        print("[MLP Mode] Using structured features with CachedFeatureExtractor")
        if use_gui:
            print("[GUI Mode] Training visualization enabled")
        env = DummyVecEnv([lambda: JetpackMLPEnv(cfg, use_gui=use_gui)])
        policy_name = "MlpPolicy"
        policy_kwargs = dict(
            net_arch=[128, 128],  # 2 hidden layers, 128 units each
        )
    else:
        if use_gui:
            print("[Warning] --gui flag only works with --mlp mode")
        print("[CNN Mode] Using raw pixels with CnnPolicy")
        env = DummyVecEnv([lambda: JetpackPPSSPPEnv(cfg)])
        policy_name = "CnnPolicy"
        policy_kwargs = None
    
    _env_global = env

    # Callbacks
    callbacks = [
        CheckpointCallback(
            save_freq=cfg["checkpoint_freq"],
            save_path=cfg["checkpoint_dir"],
            name_prefix=f"ppo_jetpack_{'mlp' if use_mlp else 'cnn'}"
        ),
        MetricsCallback()
    ]

    # Weights & Biases
    if use_wandb and HAS_WANDB:
        run = wandb.init(
            project="jetpack-joyride-rl",
            config={**cfg, "policy": policy_name},
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
            policy_name,
            env,
            verbose=1,
            n_steps=1024,
            batch_size=256,
            gamma=0.99,
            learning_rate=2.5e-4,
            policy_kwargs=policy_kwargs,
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
    parser.add_argument("--mlp", action="store_true", help="Use MLP policy with structured features (instead of CNN)")
    parser.add_argument("--gui", action="store_true", help="Show training GUI with detection visualization")

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
        train_ppo(CONFIG, timesteps=args.timesteps, resume=args.resume, use_wandb=args.wandb, use_mlp=args.mlp, use_gui=args.gui)
        return

    if args.eval:
        evaluate(CONFIG, args.eval)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
