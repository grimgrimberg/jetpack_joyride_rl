# PRD — Jetpack Joyride RL Stabilization

## Problem Statement
Training Jetpack Joyride via PPSSPP is brittle: capture regions drift with DPI changes, calibration windows can steal focus, and the monolithic script makes it hard to test or debug regressions. We need a stable, reproducible stack that works on Windows without disturbing other apps.

## Goals
- Reliable capture of the PPSSPP client area with correct DPI handling and window geometry.
- Training/eval that does not disrupt user focus; calibration/debug UIs behave politely.
- Modular, testable codebase with seams for record/replay so PPSSPP is not required for fast validation.
- Repeatable developer workflow (lint/format/tests/smoke) with documented commands.
- Explainable outputs: metrics, overlays/videos, reward breakdowns, and evaluation reports.

## Non-Goals
- Support for non-Windows platforms or non-PPSSPP emulators.
- GPU/driver-specific optimizations (OBS/NVENC) beyond existing BitBlt/PrintWindow + MSS paths.
- Automating ROM acquisition or PPSSPP installation.

## Users and Use Cases
- RL developers iterating on PPO hyperparameters and reward shaping.
- Tooling/infra contributors improving capture, calibration, or diagnostics.
- Reviewers running smoke tests to validate no regressions before training.

## Success Metrics
- Capture correctness: ROI matches client area within 1 px at 100–150% DPI; `--diagnose-capture` reports backend and coordinates.
- Stability: zero stuck-key incidents or orphaned windows during 1-hour runs; cleanup verified by tests.
- Reproducibility: `make lint && make test && make smoke` pass on a clean checkout; smoke does not require PPSSPP.
- Explainability: evaluation run produces metrics + artifact bundle (plots or annotated frames) in a single folder.

## Dependencies and Assumptions
- Windows 10/11 with PPSSPP installed and a Jetpack Joyride ROM path provided by the user.
- PyWin32 available for capture/input; Tesseract optional for OCR rewards.
- Users can run PowerShell or bash for the provided Makefile commands; alternative scripts can be added if needed.
