# SPEC.md — Jetpack Joyride RL Trainer

## 1. Overview

A reinforcement learning trainer that plays **Jetpack Joyride** on the PPSSPP PSP emulator using PPO (Stable-Baselines3). The trainer captures the game screen, processes it into observations, sends keyboard input to control the character, and uses OCR for reward shaping.

### 1.1 Scope

**In Scope:**
- Screen capture from PPSSPP window (foreground via mss, background via PrintWindow/BitBlt)
- Tkinter-based calibration GUI for region selection
- OCR-based score/distance extraction for reward shaping
- PPO training with TensorBoard and optional W&B logging
- Checkpoint save/resume
- Evaluation mode for trained models
- Game-over detection via template matching and motion analysis

**Out of Scope:**
- Support for other emulators or games
- Non-Windows operating systems
- GPU-accelerated capture (OBS, NVENC)
- Multiple simultaneous training instances
- Automated ROM launching without user configuration

### 1.2 Supported OS and Limitations

| Aspect | Support Level | Notes |
|--------|---------------|-------|
| Windows 10/11 | Primary | Tested target |
| Windows DPI scaling | Partial | Must call SetProcessDPIAware; may have issues at >100% |
| Multi-monitor | Partial | Capture uses screen coordinates; issues if PPSSPP moves between monitors |
| Background mode | Limited | Capture works; **input requires window focus** |
| macOS/Linux | Not supported | Uses pywin32, ctypes.windll |

---

## 2. Functional Requirements

### FR-1: Screen Capture
The system SHALL capture the PPSSPP game viewport at a configurable region.

- **FR-1.1**: Foreground capture using `mss` library when `--background` is not set.
- **FR-1.2**: Background capture using `PrintWindow` when `--background` is set.
- **FR-1.3**: Capture region is defined by `(cap_x, cap_y, cap_w, cap_h)` stored in `ppsspp_capture_config.json`.
- **FR-1.4**: Captured frames are converted to BGR numpy arrays.

### FR-2: Calibration GUI
The system SHALL provide a Tkinter GUI for region calibration.

- **FR-2.1**: `--calibrate` opens GUI to select game capture region, saves to `ppsspp_capture_config.json`.
- **FR-2.2**: `--calibrate-score` opens GUI to select OCR region, saves to `score_roi_config.json`.
- **FR-2.3**: GUI displays live preview of PPSSPP window with auto-refresh.
- **FR-2.4**: GUI shows 84×84 grayscale preview of what the agent will see.
- **FR-2.5**: GUI does NOT send keyboard input to other applications during calibration.

### FR-3: Input Control
The system SHALL send keyboard input to PPSSPP for game control.

- **FR-3.1**: Action key (default: Z) controls jetpack thrust.
- **FR-3.2**: Reset keys (default: ENTER) restart the game after episode end.
- **FR-3.3**: Input uses `win32api.keybd_event` after focusing the PPSSPP window.
- **FR-3.4**: Hold mode: action=1 → key down; action=0 → key up.
- **FR-3.5**: Tap mode: action=1 → key press with configurable duration.

### FR-4: Observation Processing
The system SHALL transform raw captures into RL observations.

- **FR-4.1**: Convert captured frame to grayscale.
- **FR-4.2**: Resize to 84×84 pixels.
- **FR-4.3**: Stack 4 consecutive frames (channel-first: shape `(4, 84, 84)`).
- **FR-4.4**: Output dtype is `np.uint8`, values 0–255.

### FR-5: Reward Shaping
The system SHALL compute rewards based on game progress.

- **FR-5.1**: If OCR is enabled and score increases: reward = `(new_score - old_score) * 0.1`.
- **FR-5.2**: If OCR is disabled or fails: reward = `+1.0` per step (survival bonus).
- **FR-5.3**: On game over: reward = `-100.0`.

### FR-6: Done Detection
The system SHALL detect when an episode ends.

- **FR-6.1**: Template matching: if game-over template matches with score ≥ threshold (default: 0.80), done = True.
- **FR-6.2**: Motion detection: if mean frame diff < threshold for N consecutive steps, done = True.
- **FR-6.3**: Template and motion detection can be independently enabled/disabled.

### FR-7: Training
The system SHALL train a PPO agent on the environment.

- **FR-7.1**: `--train` starts training for `--timesteps` steps (default: 300000).
- **FR-7.2**: Checkpoints saved every `checkpoint_freq` steps to `checkpoints/` directory.
- **FR-7.3**: `--resume PATH` loads model from checkpoint and continues training.
- **FR-7.4**: `--wandb` enables Weights & Biases logging.
- **FR-7.5**: TensorBoard logs saved to `tb_jetpack/` directory.

### FR-8: Evaluation
The system SHALL run a trained model without training.

- **FR-8.1**: `--eval PATH` loads model and runs N episodes (default: 10).
- **FR-8.2**: Displays per-episode reward and score.
- **FR-8.3**: Shows average reward at completion.

### FR-9: OCR Score Extraction
The system SHALL extract score/distance from the game screen.

- **FR-9.1**: Uses Tesseract OCR on a configured ROI.
- **FR-9.2**: OCR region configured via `--calibrate-score`, stored in `score_roi_config.json`.
- **FR-9.3**: Preprocessing: grayscale → threshold → dilate → digits-only whitelist.
- **FR-9.4**: Falls back to last known score on OCR failure.

### FR-10: PPSSPP Launcher
The system SHALL optionally launch PPSSPP.

- **FR-10.1**: `--launch` starts PPSSPP with the configured ROM.
- **FR-10.2**: Paths configured in `CONFIG` dict: `ppsspp_exe`, `rom_path`.

---

## 3. Non-Functional Requirements

### NFR-1: Performance
- **NFR-1.1**: Capture and process frames at configurable Hz (default: 15 FPS).
- **NFR-1.2**: Step latency should not exceed `1/agent_hz` seconds under normal conditions.

### NFR-2: Reliability
- **NFR-2.1**: System recovers gracefully if PPSSPP window is not found (clear error message).
- **NFR-2.2**: OCR failures do not crash the system; fallback reward is applied.

### NFR-3: Cleanup
- **NFR-3.1**: All held keys are released on environment close.
- **NFR-3.2**: All held keys are released on game-over.
- **NFR-3.3**: atexit handler ensures cleanup on abnormal exit.

### NFR-4: Logging
- **NFR-4.1**: Training progress logged to TensorBoard.
- **NFR-4.2**: Console output shows episode rewards and scores.

---

## 4. Safety Invariants

### INV-1: No Stuck Keys
If the environment is closed or an exception occurs mid-step, the action key MUST be released.

### INV-2: No Orphan Windows
All Tkinter windows and OpenCV windows MUST be destroyed on cleanup.

### INV-3: Configuration Persistence
Calibration data MUST be persisted to JSON files and loaded on subsequent runs.

### INV-4: Gymnasium API Compliance
- `reset()` returns `(observation, info)` where observation matches `observation_space`.
- `step(action)` returns `(observation, reward, terminated, truncated, info)`.

---

## 5. CLI Contract

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--launch` | flag | - | Launch PPSSPP with configured ROM |
| `--calibrate` | flag | - | Open capture region calibration GUI |
| `--calibrate-score` | flag | - | Open score ROI calibration GUI |
| `--play-random` | flag | - | Run 30s of random actions |
| `--capture-gameover` | flag | - | Capture game-over template |
| `--train` | flag | - | Start PPO training |
| `--timesteps` | int | 300000 | Training duration |
| `--resume` | path | - | Resume training from checkpoint |
| `--eval` | path | - | Evaluate trained model |
| `--wandb` | flag | - | Enable W&B logging |
| `--background` | flag | - | Use background capture mode |
| `--visualize-network` | flag | - | Render CNN architecture diagram |

### Exit Codes
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error (exception) |
| (custom) | Not currently implemented |

---

## 6. Configuration Contract

### 6.1 ppsspp_capture_config.json
```json
{
  "cap_x": <int>,   // X offset from client area origin
  "cap_y": <int>,   // Y offset from client area origin
  "cap_w": <int>,   // Capture width in pixels
  "cap_h": <int>    // Capture height in pixels
}
```

### 6.2 score_roi_config.json
```json
{
  "score_roi_x": <int>,   // X offset relative to capture region
  "score_roi_y": <int>,   // Y offset relative to capture region
  "score_roi_w": <int>,   // ROI width in pixels
  "score_roi_h": <int>    // ROI height in pixels
}
```

### 6.3 CONFIG Dict (in-code)
Key configuration values with their purposes:
- `ppsspp_exe`: Path to PPSSPP executable
- `rom_path`: Path to game ROM
- `tesseract_path`: Path to Tesseract OCR executable
- `window_title_substr`: Substring to match PPSSPP window title
- `action_key`: Key for jetpack control
- `reset_keys`: Key sequence to restart game
- `agent_hz`: Decisions per second
- `obs_w`, `obs_h`: Observation dimensions
- `stack_n`: Number of stacked frames
- `template_match_thresh`: Game-over template matching threshold
- `motion_diff_thresh`, `motion_static_steps`: Motion-based done detection parameters

---

## 7. Known Limitations

1. **Background mode input**: While background capture works, keyboard input STILL requires window focus. The `--background` flag enables capture without focus but input delivery will focus the window.

2. **DPI scaling**: The application does not call `SetProcessDPIAware()`. On systems with >100% scaling, screen coordinates may be incorrect.

3. **PrintWindow reliability**: Some graphics drivers (especially Vulkan) may return black frames with PrintWindow.

4. **OCR variability**: Tesseract accuracy depends on game resolution, font rendering, and preprocessing parameters.
