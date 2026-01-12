# TECH_SPEC — Jetpack Joyride RL

## Architecture Overview
- **Current state**: `ppsspp_jetpack_rl.py` is a monolithic script handling config, capture, calibration, env, training, and CLI. `backends.py` defines protocols and Windows implementations but wiring remains centralized. Tests rely on fakes for capture/input/window to avoid PPSSPP.
- **Target state**: A package-style layout (`jetpack_rl/`) with clear modules for capture, input, calibration, OCR, env, training, eval, and configuration. Each module is swappable via dependency injection to enable headless tests and record/replay.

## Current Findings (Phase 1 audit)
- Capture: Foreground via MSS; background via `PrintWindow`/BitBlt using client rect. DPI awareness is enabled globally, but ROI math and BitBlt cropping depend on client coords without explicit DPI metadata.
- Calibration: Tkinter UI is always topmost and forces focus to PPSSPP before launching; refresh loop continues while topmost, risking focus churn. Score ROI calibration uses full client coords, not capture-relative coordinates.
- Input: Key events focus window before every send (`ensure_window_focused`), storing global `_last_focused_hwnd`; no “no-focus” mode.
- Reward/Done: OCR optional but uses capture-relative ROI; motion + template + game-state heuristics combined. Done detector stores previous frame; template path loaded if present.
- Config/state: Single global `CONFIG` dict updated by JSON files; no validation or structured logging. `atexit` cleanup references global env instance.
- Tests: Fakes exist for capture/input/window, but importing `ppsspp_jetpack_rl` pulls win32 dependencies, limiting Linux/CI runs.

## Components and Responsibilities
- **capture/**: Window discovery, DPI-aware client rects, ROI math, and capture backends (MSS foreground, PrintWindow/BitBlt background). Emits structured metadata (hwnd, backend, scaling, ROI).
- **input/**: Keyboard injection with optional focus management and a “no-focus” mode that refuses to steal focus unless explicitly requested. Must track held keys and guarantee release on close/exception.
- **calibration/**: Tkinter UI for ROI selection and score ROI; never topmost by default; pauses auto-refresh while dragging; logs coordinates. Uses capture module for previews and writes configs.
- **ocr/**: Tesseract integration with preprocessing, confidence handling, and graceful fallbacks. ROI definitions live in config.
- **env/**: Gymnasium env that consumes capture/input/ocr modules, handles preprocessing and frame stacking, and raises clear errors when configuration is invalid.
- **training/**: PPO wiring (policy setup, callbacks, checkpoints, logging). Uses env factory with config and dependency injection.
- **eval/**: Replay/evaluation runner that records metrics, overlays, and artifact bundles (video or strips + markdown report).
- **config/**: Single schema (dataclass or pydantic optional) that can load from JSON + env vars + CLI overrides. Validates paths, backends, ROI, and frequency parameters with actionable errors.
- **record_replay/**: Seam to write captured frames to disk (small sample) and replay them through the pipeline/headless env for tests and smoke runs.

## Data Flow
1) **Window selection** → capture module resolves hwnd + client rect with DPI awareness.
2) **Capture** → frame (BGR) + metadata (backend, scaling, ROI) flows to preprocessing.
3) **Preprocess** → grayscale, resize to `(obs_h, obs_w)`, stack `stack_n`.
4) **Policy loop** → PPO chooses action; input module issues key events (guarded by focus policy).
5) **Done/reward** → done detector (template + motion + state heuristics) and OCR reward pipeline compute outcomes.
6) **Logging** → structured logs + TensorBoard/W&B + optional overlay/video artifacts.

## Configuration and CLI
- Configuration stored in JSON (capture, score ROI, run config) and enriched via env vars/CLI flags.
- CLI provides commands: launch, calibrate, calibrate-score, diagnose-capture, capture-gameover, train, eval, play-random, visualize-network, background toggle, and new record/replay helpers.
- Config loader validates: required paths (PPSSPP exe, ROM, tesseract), ROI bounds within client rect, timing (agent_hz), and backend availability; emits clear remediation steps.

## Diagnostics and Instrumentation
- `capture_debug`: draws ROI overlay, saves screenshots, logs raw vs scaled coordinates, notes backend (MSS vs PrintWindow) and DPI awareness.
- Calibration UI should expose preview FPS, backend in use, and a “pause refresh” toggle while dragging.
- Structured logs include hwnd, client rect, ROI, dpi awareness mode, backend name, action frequency, and input focus policy.

## Testing Strategy
- **Unit**: ROI scaling math, config validation, OCR parsing (with canned frames or mocked OCR), done detection thresholds, record/replay codecs.
- **Smoke (PPSSPP-free)**: Replay a saved frame sequence through preprocessing/env/ppo init; verify deterministic rewards and absence of key holds.
- **Manual (PPSSPP)**: Capture debug, calibration flow, short train/eval runs to confirm focus/capture stability.

## Refactor Plan
1) **Packaging & CLI**: Create `jetpack_rl/` with submodules listed above. Provide a thin CLI (e.g., `python -m jetpack_rl` or `scripts/`) that mirrors current flags while delegating to modules.
2) **Config Loader**: Replace global `CONFIG` with a validated schema (dataclass/pydantic). Support load order: defaults → JSON files → env vars → CLI overrides. Emit clear errors for missing PPSSPP/ROM/Tesseract paths and ROI bounds.
3) **Capture Module**: Centralize hwnd discovery + DPI-aware client rect. Wrap MSS/PrintWindow in objects that expose metadata (backend, dpi mode, client rect). Add capture-debug routine that draws ROI overlay, saves frames, and logs coords/backends.
4) **Input Module**: Abstract focus policies (`focus_once`, `focus_never`, `focus_every_action`). Track held keys and ensure release on close/exception. Avoid forcing focus during calibration/debug unless explicitly requested.
5) **Calibration Module**: Use capture module for previews; pause refresh while dragging; no topmost by default. Ensure score ROI is relative to capture ROI (or store both coordinate spaces with clear labels).
6) **OCR Module**: Encapsulate Tesseract path resolution, preprocessing, and confidence thresholds. Return `(value, confidence, raw_text)` and fall back gracefully; unit-test with canned frames or mocked OCR.
7) **Env Module**: Wrap capture/input/ocr/done detectors with dependency injection. Separate preprocessing/stacking into testable helpers. Ensure win32 imports are optional when fakes are provided to keep tests portable.
8) **Record/Replay Seam**: CLI flag to record N frames (with metadata) and replay them through env/headless PPO init. Use this for smoke tests and debugging without PPSSPP.
9) **Training/Eval Modules**: Factor PPO setup, callbacks, checkpointing, and logging out of CLI. Add evaluation artifacts (videos/overlays/markdown report) and metrics summary (reward, distance proxy, done reasons, action histogram).
10) **Diagnostics & Logging**: Structured logs (JSON or key=value) with hwnd, backend, dpi mode, ROI, timings. Add capture latency stats and backend selection to diagnostics.
11) **Testing & Automation**: Expand unit tests for config validation, ROI math, OCR parsing, done detection, record/replay. Smoke uses replay frames. Makefile/CI run lint/test/smoke; PPSSPP-dependent steps marked manual.

## Second-Opinion Review (risks/gaps)
- **Win32 imports at module load**: Blocks Linux/CI; plan to lazy-load or gate imports and rely on backends via dependency injection.
- **Coordinate space confusion**: Score ROI calibration uses full client coords while extractor expects capture-relative; plan includes dual-space storage or conversion utilities plus validation.
- **Focus churn**: Frequent `SetForegroundWindow` calls and topmost calibration can disrupt other apps; plan adds explicit focus policies and disables topmost by default.
- **PrintWindow brittleness**: Add backend selection logs and fallback to MSS; capture-debug will surface black-frame/latency data.
- **Template/OCR assets**: Missing/incorrect assets can crash or mis-score; config validation will flag absent files and offer recovery guidance.

Adjustments from review: prioritize gating win32 imports, add coordinate conversion tests, and ensure calibration UI opts into focus/topmost behavior instead of forcing it.
