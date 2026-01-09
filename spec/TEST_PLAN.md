# TEST_PLAN.md — Test Coverage Matrix

This document maps requirements to tests and specifies the type of verification for each.

---

## Test Types

| Type | Description | Requires PPSSPP |
|------|-------------|-----------------|
| **Unit** | Pure function tests with no external dependencies | No |
| **Integration (Fake)** | Gym environment tests using fake capture/input backends | No |
| **Integration (Real)** | Tests against actual PPSSPP | Yes |
| **Manual** | Human-executed verification | Yes |

---

## Requirement → Test Matrix

### Functional Requirements

| Req ID | Requirement | Test Type | Test File/Location | Status |
|--------|-------------|-----------|--------------------|-|
| FR-1.1 | Foreground capture (mss) | Integration (Real) | Manual smoke | TODO |
| FR-1.2 | Background capture (PrintWindow) | Integration (Real) | Manual smoke | TODO |
| FR-1.3 | Capture region from config | Unit | `tests/test_capture.py::test_region_from_config` | TODO |
| FR-1.4 | BGR numpy output | Unit | `tests/test_capture.py::test_output_format` | TODO |
| FR-2.1 | Calibrate capture GUI | Manual | AC-1.1 | TODO |
| FR-2.2 | Calibrate score GUI | Manual | AC-1.2 | TODO |
| FR-2.3 | GUI live preview | Manual | AC-1.1 | TODO |
| FR-2.4 | 84×84 preview | Manual | AC-1.1 | TODO |
| FR-2.5 | No keyboard interference | Manual | AC-1.1 | TODO |
| FR-3.1 | Action key control | Integration (Fake) | `tests/test_input.py::test_action_key` | TODO |
| FR-3.2 | Reset keys | Integration (Fake) | `tests/test_input.py::test_reset_keys` | TODO |
| FR-3.3 | Focus before input | Unit | `tests/test_input.py::test_focus_called` | TODO |
| FR-3.4 | Hold mode | Integration (Fake) | `tests/test_env.py::test_hold_mode` | TODO |
| FR-3.5 | Tap mode | Integration (Fake) | `tests/test_env.py::test_tap_mode` | TODO |
| FR-4.1 | Grayscale conversion | Unit | `tests/test_preprocess.py::test_grayscale` | TODO |
| FR-4.2 | Resize to 84×84 | Unit | `tests/test_preprocess.py::test_resize` | TODO |
| FR-4.3 | Frame stacking | Unit | `tests/test_env.py::test_frame_stacking` | TODO |
| FR-4.4 | Dtype uint8 | Unit | `tests/test_env.py::test_observation_dtype` | TODO |
| FR-5.1 | OCR delta reward | Unit | `tests/test_reward.py::test_ocr_delta_reward` | TODO |
| FR-5.2 | Fallback reward | Unit | `tests/test_reward.py::test_fallback_reward` | TODO |
| FR-5.3 | Game-over penalty | Unit | `tests/test_reward.py::test_gameover_penalty` | TODO |
| FR-6.1 | Template matching done | Unit | `tests/test_done.py::test_template_done` | TODO |
| FR-6.2 | Motion-based done | Unit | `tests/test_done.py::test_motion_done` | TODO |
| FR-6.3 | Detection toggles | Unit | `tests/test_done.py::test_detection_toggles` | TODO |
| FR-7.1 | Training starts | Integration (Fake) | `tests/test_training.py::test_ppo_init` | TODO |
| FR-7.2 | Checkpoint saving | Manual | AC-3.1 | TODO |
| FR-7.3 | Resume training | Manual | AC-3.2 | TODO |
| FR-7.4 | W&B integration | Manual | Optional | TODO |
| FR-7.5 | TensorBoard logs | Manual | AC-3.1 | TODO |
| FR-8.1 | Load model for eval | Unit | `tests/test_eval.py::test_model_load` | TODO |
| FR-8.2 | Episode rewards | Manual | AC-4 | TODO |
| FR-8.3 | Average reward | Manual | AC-4 | TODO |
| FR-9.1 | Tesseract OCR | Unit | `tests/test_ocr.py::test_extract_digits` | TODO |
| FR-9.2 | OCR config file | Unit | `tests/test_config.py::test_score_roi_config` | TODO |
| FR-9.3 | OCR preprocessing | Unit | `tests/test_ocr.py::test_preprocessing` | TODO |
| FR-9.4 | OCR fallback | Unit | `tests/test_ocr.py::test_fallback` | TODO |
| FR-10.1 | Launch PPSSPP | Manual | User verification | TODO |
| FR-10.2 | Path configuration | Unit | `tests/test_config.py::test_paths_config` | TODO |

### Non-Functional Requirements

| Req ID | Requirement | Test Type | Test File/Location | Status |
|--------|-------------|-----------|--------------------|-|
| NFR-1.1 | Capture at agent_hz | Integration (Real) | `tests/test_perf.py::test_capture_fps` | TODO |
| NFR-1.2 | Step latency | Integration (Fake) | `tests/test_perf.py::test_step_latency` | TODO |
| NFR-2.1 | Window not found error | Unit | `tests/test_window.py::test_window_not_found` | TODO |
| NFR-2.2 | OCR failure recovery | Unit | `tests/test_ocr.py::test_failure_recovery` | TODO |
| NFR-3.1 | Keys released on close | Integration (Fake) | `tests/test_cleanup.py::test_close_releases_keys` | TODO |
| NFR-3.2 | Keys released on done | Integration (Fake) | `tests/test_cleanup.py::test_done_releases_keys` | TODO |
| NFR-3.3 | atexit cleanup | Integration (Fake) | `tests/test_cleanup.py::test_atexit_registered` | TODO |
| NFR-4.1 | TensorBoard logging | Manual | AC-3.1 | TODO |
| NFR-4.2 | Console output | Manual | AC-3.1 | TODO |

### Safety Invariants

| Inv ID | Invariant | Test Type | Test File/Location | Status |
|--------|-----------|-----------|--------------------|-|
| INV-1 | No stuck keys | Integration (Fake) | `tests/test_invariants.py::test_no_stuck_keys_on_exception` | TODO |
| INV-2 | No orphan windows | Manual | AC-5 | TODO |
| INV-3 | Config persistence | Unit | `tests/test_config.py::test_config_persistence` | TODO |
| INV-4 | Gymnasium API | Integration (Fake) | `tests/test_env.py::test_gymnasium_api` | TODO |

---

## Test File Structure

```
tests/
├── conftest.py              # Fixtures, fakes, shared setup
├── fakes/
│   ├── __init__.py
│   ├── capture.py           # FakeCapture returning fixture frames
│   ├── input.py             # FakeInput recording calls
│   └── window.py            # FakeWindow with mock hwnd
├── fixtures/
│   ├── frame_gameplay.png   # Sample gameplay frame
│   ├── frame_gameover.png   # Sample game-over frame
│   └── gameover_template.png # Template for matching
├── test_capture.py          # ScreenCapture unit tests
├── test_cleanup.py          # Cleanup invariant tests
├── test_config.py           # Config loading/saving tests
├── test_done.py             # DoneDetector tests
├── test_env.py              # JetpackPPSSPPEnv integration tests
├── test_input.py            # Input backend tests
├── test_invariants.py       # Safety invariant tests
├── test_ocr.py              # ScoreExtractor tests
├── test_preprocess.py       # preprocess_frame tests
├── test_reward.py           # Reward calculation tests
└── test_window.py           # Window finding tests
```

---

## Test Execution Commands

### Unit & Integration Tests (No PPSSPP Required)
```powershell
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=ppsspp_jetpack_rl --cov-report=html

# Run specific test file
python -m pytest tests/test_env.py -v

# Run tests matching pattern
python -m pytest tests/ -k "test_gymnasium" -v
```

### Manual Smoke Tests (PPSSPP Required)
See `ACCEPTANCE.md` for detailed steps. Quick reference:

```powershell
# 1. Calibration (visual inspection)
python ppsspp_jetpack_rl.py --calibrate

# 2. Random play (30 seconds, verify input works)
python ppsspp_jetpack_rl.py --play-random

# 3. Short training (verify no crashes)
python ppsspp_jetpack_rl.py --train --timesteps 1000

# 4. Evaluation (verify model loads)
python ppsspp_jetpack_rl.py --eval models/ppo_jetpack_final.zip
```

---

## Priority Tests (Must Pass Before Release)

1. **test_gymnasium_api** — Environment follows Gymnasium contract
2. **test_observation_dtype** — Observations are uint8
3. **test_frame_stacking** — 4-frame stacks with correct shape
4. **test_no_stuck_keys_on_exception** — Safety invariant
5. **test_close_releases_keys** — Cleanup invariant
6. **test_template_done** — Game-over detection works
7. **test_fallback_reward** — OCR failure doesn't crash
