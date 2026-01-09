# RISKS.md — Technical Risks and Mitigations

This document identifies technical risks that may affect the reliability, usability, or correctness of the Jetpack Joyride RL trainer.

---

## RISK-1: Windows DPI Scaling

### Description
Windows systems with display scaling >100% may report incorrect screen coordinates. The Win32 API returns coordinates in "real" pixels by default, but some functions may return scaled values depending on DPI awareness mode.

### Current State
The application does NOT call `SetProcessDPIAware()` or use a DPI-aware manifest. This can cause:
- Calibration coords to be incorrect
- Capture region to be offset or wrong size
- Mouse/click coords in Tkinter to be misaligned

### Impact
**High** — Users at 125%+ scaling will have broken capture/calibration.

### Mitigation
1. Call `ctypes.windll.shcore.SetProcessDpiAwareness(2)` at startup (Per-Monitor DPI Aware)
2. Or call `ctypes.windll.user32.SetProcessDPIAware()` (simpler, System DPI Aware)
3. Add troubleshooting note for DPI issues
4. Test on 100%, 125%, 150% scaling

### Test Plan
- Manual test at multiple DPI settings (AC-2)
- Document expected behavior

---

## RISK-2: Multi-Monitor Coordinates

### Description
When PPSSPP is on a secondary monitor, screen coordinates may be offset or negative. The `mss` library uses absolute screen coordinates, which differ from client/window coordinates.

### Current State
- `get_client_rect_on_screen()` correctly uses `ClientToScreen`, which works across monitors
- Calibration GUI auto-refreshes using absolute screen coordinates
- Issue: if PPSSPP moves between calibration and use, coords are invalid

### Impact
**Medium** — Users with multi-monitor setups may encounter capture issues.

### Mitigation
1. Detect if PPSSPP moved since calibration
2. Store window position in config and warn if it differs
3. Add `--recalibrate` hint when window position changes

### Test Plan
- Manual test with PPSSPP on secondary monitor
- Document limitation

---

## RISK-3: PrintWindow Black Frames

### Description
The `PrintWindow` API may return black or corrupted frames with certain graphics drivers or renderers:
- Vulkan renderer in PPSSPP
- Hardware-accelerated overlays
- Some DirectX 12 applications

### Current State
- Code uses `PrintWindow(hwnd, hdc, 3)` where flag 3 = PW_RENDERFULLCONTENT
- No detection of black/empty frames
- No fallback to foreground capture

### Impact
**Medium** — Background capture silently fails with some renderers.

### Mitigation
1. Add black-frame detection (mean pixel intensity < threshold)
2. Log warning when black frames detected
3. Auto-fallback to foreground capture with user notification
4. Add `--diagnose-capture` command to test capture reliability
5. Document renderer compatibility (D3D11 recommended)

### Test Plan
- Unit test for black-frame detection
- Manual test with Vulkan vs D3D11

---

## RISK-4: Input Delivery via Global Keyboard Events

### Description
The application uses `win32api.keybd_event()` which sends global keyboard events. This requires:
1. The target window to be focused
2. No other application intercepting keyboard events

### Current State
- `ensure_window_focused()` calls `SetForegroundWindow` before keybd_event
- This STEALS FOCUS from other applications
- Users cannot use their computer during training

### Impact
**High** — Contradicts the "background training" claim in README.

### Mitigation
1. **Document the limitation clearly** — Background capture ≠ background input
2. Investigate `SendMessage`/`PostMessage` alternatives (likely blocked by PPSSPP/DirectInput)
3. Consider separate "headless" mode where only capture works and user must focus manually
4. Add prominent warning when `--background` is used

### Test Plan
- Integration test verifying focus is called before input
- Manual verification of input delivery

---

## RISK-5: OCR Tesseract Variability

### Description
Tesseract OCR accuracy depends on:
- Image resolution and quality
- Font rendering (anti-aliasing, color)
- Preprocessing parameters (threshold value, kernel size)
- Tesseract trained data version

### Current State
- Hardcoded threshold (150) may not work for all setups
- Single preprocessing pipeline
- No confidence score filtering
- Falls back to last known score on failure

### Impact
**Medium** — Reward shaping may be inaccurate or inconsistent.

### Mitigation
1. Provide more preprocessing options
2. Add OCR confidence threshold parameter
3. Allow fallback strategy configuration
4. Add `--test-ocr` command to verify OCR accuracy before training

### Test Plan
- Unit test for OCR with fixture images
- Manual test with various game resolutions

---

## RISK-6: Focus-Stealing During Calibration

### Description
The calibration GUI:
- Sets `-topmost` attribute
- May trigger auto-refresh while other apps are focused
- Does not use any global hotkeys (safe)

### Current State
- GUI correctly does NOT register global keyboard hooks
- Auto-refresh captures screenshot without stealing focus
- Window is always-on-top which may be annoying

### Impact
**Low** — User experience issue, not functional.

### Mitigation
1. Add option to disable topmost
2. Pause auto-refresh when GUI not focused
3. Clearly document calibration workflow

### Test Plan
- Manual verification (AC-1.1)

---

## RISK-7: Stuck Keys on Crash

### Description
If the application crashes while a key is held down (action=1), the key remains "pressed" from the OS perspective, causing:
- Jetpack to continuously fire in PPSSPP
- Key repeating in other applications

### Current State
- `_release_action()` called in `close()` and on done
- `atexit.register(_cleanup)` attempts cleanup on exit
- Not called on unhandled exceptions during `step()`

### Impact
**High** — Poor user experience, potential key input issues.

### Mitigation
1. Wrap `step()` logic in try/finally for key release
2. Add signal handlers for SIGINT/SIGTERM
3. Test exception during step explicitly

### Test Plan
- Unit test: exception during step → keys released (INV-1)
- Manual test: Ctrl+C during training

---

## RISK-8: Performance — Capture and OCR Latency

### Description
Frame capture (especially background mode) and OCR are slow operations that may exceed the step budget at high agent_hz.

### Current State
- Default agent_hz = 15 → 66.7ms per step
- PrintWindow typically takes 10-30ms
- OCR can take 50-200ms depending on image size
- No parallel processing

### Impact
**Medium** — Training speed may be limited by capture/OCR, not GPU.

### Mitigation
1. Profile capture and OCR latency
2. Consider running OCR in background thread
3. Skip OCR frames (extract every Nth frame)
4. Lower default agent_hz or make it adaptive

### Test Plan
- Performance test measuring capture latency
- Manual observation of actual step rate

---

## Risk Summary Matrix

| Risk ID | Description | Probability | Impact | Priority |
|---------|-------------|-------------|--------|----------|
| RISK-1 | DPI Scaling | High | High | P1 |
| RISK-4 | Input requires focus | High | High | P1 |
| RISK-7 | Stuck keys on crash | Medium | High | P1 |
| RISK-3 | PrintWindow black frames | Medium | Medium | P2 |
| RISK-5 | OCR variability | Medium | Medium | P2 |
| RISK-2 | Multi-monitor coords | Low | Medium | P3 |
| RISK-6 | Calibration focus-stealing | Low | Low | P4 |
| RISK-8 | Capture/OCR latency | Low | Medium | P3 |
