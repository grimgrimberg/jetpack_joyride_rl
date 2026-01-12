# TROUBLESHOOTING — PPSSPP + Capture

## Cannot Find PPSSPP Window
- Confirm PPSSPP is running and the title contains `PPSSPP`; adjust `window_title_substr` if localized.
- Place PPSSPP on the primary monitor and keep it unminimized; background capture fails on minimized windows.
- Run `python ppsspp_jetpack_rl.py --diagnose-capture` to log hwnd discovery and client rect.

## DPI or Offset Issues
- Ensure DPI awareness is enabled (SetProcessDPIAware/PerMonitor). Restart PPSSPP after changing scaling.
- Recalibrate after any DPI or monitor change: `python ppsspp_jetpack_rl.py --calibrate`.
- Compare logged client rect vs ROI in `--diagnose-capture`; adjust if borders are included instead of client area.

## Black Frames (Background Mode)
- Switch PPSSPP renderer to Direct3D 11; Vulkan may return black frames to PrintWindow/BitBlt.
- Avoid minimized windows; PrintWindow cannot capture minimized windows on some drivers.
- If frames are still black, fall back to foreground capture (unset `--background`) and retest.

## OCR Returns Wrong Numbers
- Recalibrate score ROI via `--calibrate-score`; ensure ROI is tight around digits.
- Verify Tesseract is installed and on PATH, or set `tesseract_path` explicitly.
- Try increasing contrast: grayscale → threshold → dilate. Reduce in-game post-processing effects.

## Focus or Input Oddities
- Input requires focus even in background capture; avoid repeatedly forcing focus—use a single focus on start.
- If calibration steals focus, ensure UI is not topmost and pause refresh while dragging.
- Stuck keys: press the action key once, or rerun cleanup; report via logs from `input` module.

## ROI or Template Files Missing
- `ppsspp_capture_config.json`, `score_roi_config.json`, and `gameover_template.png` must exist or be regenerated.
- Placeholders are acceptable for headless tests; document missing assets and rerun calibration/capture when available.
