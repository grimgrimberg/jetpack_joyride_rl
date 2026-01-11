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
| FR-1.1 | Foreground capture (mss) | Integration (Real) | Manual smoke | MANUAL |
| FR-1.2 | Background capture (PrintWindow) | Integration (Real) | `--diagnose-capture` | MANUAL |
| FR-1.3 | Capture region from config | Unit | `conftest.py` fixture | ✅ PASS |
| FR-1.4 | BGR numpy output | Unit | `tests/test_preprocess.py` | ✅ PASS |
| FR-2.1 | Calibrate capture GUI | Manual | AC-1.1 | MANUAL |
| FR-2.2 | Calibrate score GUI | Manual | AC-1.2 | MANUAL |
| FR-2.3 | GUI live preview | Manual | AC-1.1 | MANUAL |
| FR-2.4 | 84×84 preview | Manual | AC-1.1 | MANUAL |
| FR-2.5 | No keyboard interference | Manual | AC-1.1 | MANUAL |
| FR-3.1 | Action key control | Integration (Fake) | `tests/test_env.py::TestInputControl` | ✅ PASS |
| FR-3.2 | Reset keys | Integration (Fake) | `tests/test_env.py` (via reset flow) | ✅ PASS |
| FR-3.3 | Focus before input | Integration (Fake) | `tests/test_env.py` | ✅ PASS |
| FR-3.4 | Hold mode | Integration (Fake) | `tests/test_env.py::test_action_1_sends_key_down` | ✅ PASS |
| FR-3.5 | Tap mode | Integration (Fake) | Not yet implemented | TODO |
| FR-4.1 | Grayscale conversion | Unit | `tests/test_preprocess.py::test_grayscale_conversion` | ✅ PASS |
| FR-4.2 | Resize to 84×84 | Unit | `tests/test_preprocess.py::test_resize_to_84x84` | ✅ PASS |
| FR-4.3 | Frame stacking | Unit | `tests/test_env.py::TestFrameStacking` | ✅ PASS |
| FR-4.4 | Dtype uint8 | Unit | `tests/test_env.py::test_observation_dtype` | ✅ PASS |
| FR-5.1 | OCR delta reward | Unit | Manual smoke | MANUAL |
| FR-5.2 | Fallback reward | Unit | `tests/test_env.py::test_default_reward_without_ocr` | ✅ PASS |
| FR-5.3 | Game-over penalty | Unit | `tests/test_env.py::test_gameover_penalty` | ✅ PASS |
| FR-6.1 | Template matching done | Unit | `tests/test_done.py::TestDoneDetectorTemplate` | ✅ PASS |
| FR-6.2 | Motion-based done | Unit | `tests/test_done.py::TestDoneDetectorMotion` | ✅ PASS |
| FR-6.3 | Detection toggles | Unit | `tests/test_done.py::TestDoneDetectorToggles` | ✅ PASS |
| FR-7.1 | Training starts | Integration (Fake) | Manual smoke | MANUAL |
| FR-7.2 | Checkpoint saving | Manual | AC-3.1 | MANUAL |
| FR-7.3 | Resume training | Manual | AC-3.2 | MANUAL |
| FR-7.4 | W&B integration | Manual | Optional | MANUAL |
| FR-7.5 | TensorBoard logs | Manual | AC-3.1 | MANUAL |
| FR-8.1 | Evaluation mode | Manual | AC-4 | MANUAL |
| FR-8.2 | Episode rewards | Manual | AC-4 | MANUAL |
| FR-8.3 | Average reward | Manual | AC-4 | MANUAL |
| FR-9.1 | Tesseract OCR | Unit | Manual smoke | MANUAL |
| FR-9.2 | OCR config file | Unit | `conftest.py` fixture | ✅ PASS |
| FR-9.3 | OCR preprocessing | Unit | Manual smoke | MANUAL |
| FR-9.4 | OCR fallback | Unit | `tests/test_env.py` | ✅ PASS |
| FR-10.1 | Launch PPSSPP | Manual | User verification | MANUAL |
| FR-10.2 | Path configuration | Unit | `conftest.py` fixture | ✅ PASS |

### Non-Functional Requirements

| Req ID | Requirement | Test Type | Test File/Location | Status |
|--------|-------------|-----------|--------------------|-|
| NFR-1.1 | Capture at agent_hz | Integration (Real) | `--diagnose-capture` | MANUAL |
| NFR-1.2 | Step latency | Integration (Fake) | Not yet implemented | TODO |
| NFR-2.1 | Window not found error | Unit | Implemented in code, no test | TODO |
| NFR-2.2 | OCR failure recovery | Unit | `tests/test_env.py` | ✅ PASS |
| NFR-3.1 | Keys released on close | Integration (Fake) | `tests/test_env.py::test_close_releases_action_key` | ✅ PASS |
| NFR-3.2 | Keys released on done | Integration (Fake) | `tests/test_env.py::test_gameover_penalty` | ✅ PASS |
| NFR-3.3 | atexit cleanup | Integration (Fake) | `tests/test_cleanup.py::test_cleanup_function_exists` | ✅ PASS |
| NFR-4.1 | TensorBoard logging | Manual | AC-3.1 | MANUAL |
| NFR-4.2 | Console output | Manual | AC-3.1 | MANUAL |

### Safety Invariants

| Inv ID | Invariant | Test Type | Test File/Location | Status |
|--------|-----------|-----------|--------------------|-|
| INV-1 | No stuck keys | Integration (Fake) | `tests/test_cleanup.py::TestCleanupInvariants` | ✅ PASS |
| INV-2 | No orphan windows | Manual | AC-5 | MANUAL |
| INV-3 | Config persistence | Unit | `conftest.py` fixture | ✅ PASS |
| INV-4 | Gymnasium API | Integration (Fake) | `tests/test_env.py::TestGymnasiumAPI` | ✅ PASS |

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
