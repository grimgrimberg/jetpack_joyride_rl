# ACCEPTANCE_TESTS — Jetpack Joyride RL

## Pre-Flight Checklist
- [ ] Branch set to `codex/spec-refactor` (or feature branch) with no unintended staged changes.
- [ ] Config files present or placeholders noted: `ppsspp_capture_config.json`, `score_roi_config.json`, `ppsspp_jetpack_rl.py` CONFIG paths updated for local PPSSPP/ROM.
- [ ] Windows display scaling confirmed (100–150%) and PPSSPP running on primary monitor.
- [ ] Tesseract installed/disabled explicitly; OCR reward toggle set accordingly.

## Execution Checklist (phase gates)
- [ ] Phase 0 guardrails in repo (`AGENTS.md`, `docs/*`, Makefile/pyproject updates).
- [ ] Phase 1 audit + refactor plan documented in `docs/TECH_SPEC.md` with second-opinion notes.
- [ ] Phase 2 architecture split (package modules, config loader, record/replay seam) with lint/test/smoke passing.
- [ ] Phase 3 capture/focus diagnostics implemented and validated via `--diagnose-capture` + manual UI checks.
- [ ] Phase 4 tests/lint/CI updated; replay smoke green; PPSSPP-dependent smoke marked/manual.
- [ ] Phase 5 evaluation artifacts produced (metrics + overlays/report) and repro steps recorded.

## Automation (must run)
- [ ] `make format` (when Python files were touched)
- [ ] `make lint`
- [ ] `make test`
- [ ] `make smoke` (PPSSPP-free replay/preprocess smoke)

## Smoke Tests (PPSSPP-free)
- [ ] Replay/preprocess smoke: `make smoke` (runs quick pytest targets; should finish <30s).
- [ ] PPO init smoke (headless): `make test` covers PPO wiring without PPSSPP when fakes are used.

## PPSSPP-Required Checks
- [ ] Calibration flow: `python ppsspp_jetpack_rl.py --calibrate` (UI opens, no focus stealing, ROI saved).
- [ ] Score ROI flow: `python ppsspp_jetpack_rl.py --calibrate-score` (ROI saved).
- [ ] Capture diagnostics: `python ppsspp_jetpack_rl.py --diagnose-capture` (logs backend, ROI, DPI mode; saves sample frames).
- [ ] Random play sanity: `python ppsspp_jetpack_rl.py --play-random --timesteps 300` (keys released on exit).
- [ ] Agent monitor overlay: `python ppsspp_jetpack_rl.py --eval <model.zip>` (OpenCV window shows raw + agent view with action/reward/state overlays).
- [ ] Short train smoke: `python ppsspp_jetpack_rl.py --train --timesteps 5000 --background` (or foreground) completes and checkpoints.
- [ ] Short eval smoke: `python ppsspp_jetpack_rl.py --eval models/<model>.zip --timesteps 1000` emits metrics and artifacts.

## Repro Notes
- Capture/eval artifacts should land in `debug_frames/`, `checkpoints/`, `models/`, and `tb_jetpack/` as configured.
- When PPSSPP assets are missing, document the required paths and skip PPSSPP-dependent checks while still running `make lint`, `make test`, and `make smoke`.
- Manual steps may need PowerShell if `make` is unavailable; equivalent commands are listed in the Makefile.
