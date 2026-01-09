# ACCEPTANCE.md — Definition of Done

This document defines acceptance criteria that a human can manually verify.

---

## AC-1: Calibration Behavior

### AC-1.1: Capture Region Calibration
**Precondition**: PPSSPP is running with the game loaded.

**Steps**:
1. Run `python ppsspp_jetpack_rl.py --calibrate`
2. A Tkinter window appears on the left side of the screen
3. The PPSSPP window screenshot appears in the GUI with auto-refresh
4. Click and drag to select the game viewport
5. The 84×84 preview updates to show the agent's view
6. Click "Save & Continue"

**Expected**:
- ✅ No keystrokes sent to PPSSPP or other applications during selection
- ✅ No other applications (VS Code, browser) react to keyboard input
- ✅ File `ppsspp_capture_config.json` is created/updated with `cap_x`, `cap_y`, `cap_w`, `cap_h`
- ✅ GUI closes cleanly after save

### AC-1.2: Score Region Calibration
**Precondition**: Capture region already calibrated.

**Steps**:
1. Run `python ppsspp_jetpack_rl.py --calibrate-score`
2. Select the score/distance number area
3. Click "Save & Continue"

**Expected**:
- ✅ File `score_roi_config.json` is created with `score_roi_x`, `score_roi_y`, `score_roi_w`, `score_roi_h`
- ✅ Coordinates are relative to capture region (not screen)

---

## AC-2: DPI Scaling Correctness

### AC-2.1: 100% Scaling
**Precondition**: Windows display scaling set to 100%.

**Steps**:
1. Run calibration
2. Select a region
3. Run `--play-random`

**Expected**:
- ✅ Captured frames match the selected region exactly
- ✅ No offset or size mismatch

### AC-2.2: 125%/150% Scaling
**Precondition**: Windows display scaling set to 125% or 150%.

**Steps**:
1. Run calibration
2. Select a region
3. Run `--play-random`

**Expected**:
- ✅ Captured frames match the selected region (accounting for DPI)
- ✅ OR clear warning/error message if DPI scaling is not supported

---

## AC-3: Training Smoke Test

### AC-3.1: Short Training Run
**Precondition**: PPSSPP running with game loaded, calibration complete.

**Steps**:
1. Start training:
   ```powershell
   python ppsspp_jetpack_rl.py --train --timesteps 1000
   ```
2. Let it run for ~1 minute

**Expected**:
- ✅ Training starts without errors
- ✅ Console shows training progress
- ✅ Checkpoint saved to `checkpoints/`
- ✅ TensorBoard logs created in `tb_jetpack/`
- ✅ On completion, model saved to `models/ppo_jetpack_final.zip`

### AC-3.2: Resume Training
**Steps**:
1. Run training with resume:
   ```powershell
   python ppsspp_jetpack_rl.py --train --timesteps 500 --resume checkpoints/ppo_jetpack_1000_steps.zip
   ```

**Expected**:
- ✅ Training resumes from checkpoint
- ✅ No reset of episode counter

---

## AC-4: Evaluation Smoke Test

**Precondition**: Trained model exists at `models/ppo_jetpack_final.zip`.

**Steps**:
1. Run evaluation:
   ```powershell
   python ppsspp_jetpack_rl.py --eval models/ppo_jetpack_final.zip
   ```

**Expected**:
- ✅ Model loads successfully
- ✅ Agent plays the game (actions visible)
- ✅ Episode rewards printed to console
- ✅ Average reward printed at completion

---

## AC-5: Cleanup Expectations

### AC-5.1: Normal Exit
**Steps**:
1. Run `--play-random`
2. Wait for completion

**Expected**:
- ✅ No stuck keys (jetpack not continuously firing after exit)
- ✅ All OpenCV windows closed
- ✅ Process exits cleanly

### AC-5.2: Keyboard Interrupt
**Steps**:
1. Start a long training run
2. Press Ctrl+C to interrupt

**Expected**:
- ✅ Action key released (jetpack stops)
- ✅ Environment closes cleanly
- ✅ No zombie windows

### AC-5.3: Exception During Step
**Steps**:
1. Manually test by closing PPSSPP window mid-training

**Expected**:
- ✅ Exception is raised with clear message
- ✅ Action key is released before exception propagates
- ✅ Environment cleanup runs

---

## AC-6: Background Mode

### AC-6.1: Background Capture
**Precondition**: Using `--background` flag.

**Steps**:
1. Start training with background mode:
   ```powershell
   python ppsspp_jetpack_rl.py --train --background --timesteps 1000
   ```
2. Move another window in front of PPSSPP

**Expected**:
- ✅ Capture still works (frames are not black/corrupted)
- ✅ OR clear warning if PrintWindow fails

### AC-6.2: Background Mode Input Limitation
**Documented Behavior**: Input still steals focus in background mode.

**Expected**:
- ✅ README documents this limitation
- ✅ Console warning when using `--background` about focus requirement

---

## AC-7: OCR Reward

### AC-7.1: OCR Extraction
**Precondition**: Tesseract installed, score region calibrated.

**Steps**:
1. Run `--play-random`
2. Watch console output

**Expected**:
- ✅ Score values extracted and printed in episode info
- ✅ If OCR fails, fallback reward (+1.0) applied without crash

### AC-7.2: OCR Disabled
**Steps**:
1. Set `--no-ocr` (or disable in config) and run `--play-random`
   *(Note: this flag may need to be added)*

**Expected**:
- ✅ Training works without OCR
- ✅ Fallback reward used

---

## AC-8: Game-Over Detection

### AC-8.1: Template Capture
**Steps**:
1. Run `python ppsspp_jetpack_rl.py --capture-gameover`
2. Navigate to game-over screen in PPSSPP
3. Press 'T' to capture

**Expected**:
- ✅ File `gameover_template.png` created
- ✅ Image is 84×84 grayscale

### AC-8.2: Detection During Play
**Steps**:
1. With template captured, run `--play-random`
2. Let the agent die

**Expected**:
- ✅ Episode ends (done=True) when game-over screen appears
- ✅ -100 reward applied
- ✅ Game resets for next episode

---

## AC-9: CLI Help
**Steps**:
1. Run `python ppsspp_jetpack_rl.py --help`

**Expected**:
- ✅ All documented flags are listed
- ✅ Descriptions match behavior
