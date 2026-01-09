# TRACEABILITY.md — Requirement to Implementation to Test

This document traces each requirement from SPEC.md to its implementation and test.

---

## Functional Requirements

| Req ID | Requirement | Implementation | Test(s) | Status |
|--------|-------------|----------------|---------|--------|
| FR-1.1 | Foreground capture (mss) | `ppsspp_jetpack_rl.py:ScreenCapture._grab_mss()` L275-285 | Manual smoke | ✅ |
| FR-1.2 | Background capture (PrintWindow) | `ppsspp_jetpack_rl.py:ScreenCapture._grab_bitblt()` L287-333 | `--diagnose-capture` | ✅ |
| FR-1.3 | Capture region from config | `ppsspp_jetpack_rl.py:load_configs()` L1107-1115 | `conftest.py` fixture | ✅ |
| FR-1.4 | BGR numpy output | `ppsspp_jetpack_rl.py:ScreenCapture.grab()` | `test_preprocess.py` | ✅ |
| FR-2.1 | Calibrate capture GUI | `ppsspp_jetpack_rl.py:CalibrationGUI` | Manual: AC-1.1 | ✅ |
| FR-2.2 | Calibrate score GUI | `ppsspp_jetpack_rl.py:calibrate_gui(mode="score")` | Manual: AC-1.2 | ✅ |
| FR-2.5 | No keyboard interference | CalibrationGUI uses only mouse events | Manual: AC-1.1 | ✅ |
| FR-3.1 | Action key control | `JetpackPPSSPPEnv._apply_action()` L573-606 | `test_env.py::TestInputControl` | ✅ |
| FR-3.4 | Hold mode | `JetpackPPSSPPEnv._apply_action()` L582-598 | `test_env.py::test_action_1_sends_key_down` | ✅ |
| FR-4.1 | Grayscale conversion | `preprocess_frame()` L343-347 | `test_preprocess.py::test_grayscale_conversion` | ✅ |
| FR-4.2 | Resize to 84x84 | `preprocess_frame()` L346 | `test_preprocess.py::test_resize_to_84x84` | ✅ |
| FR-4.3 | Frame stacking | `JetpackPPSSPPEnv._stack_obs()` L569-571 | `test_env.py::TestFrameStacking` | ✅ |
| FR-4.4 | Dtype uint8 | `observation_space` definition L511-514 | `test_env.py::test_observation_dtype` | ✅ |
| FR-5.1 | OCR delta reward | `step()` L656-670 | Tested via manual smoke | ✅ |
| FR-5.2 | Fallback reward | `step()` L653 | `test_env.py::test_default_reward_without_ocr` | ✅ |
| FR-5.3 | Game-over penalty | `step()` L675 | `test_env.py::test_gameover_penalty` | ✅ |
| FR-6.1 | Template matching done | `DoneDetector.is_done()` L436-441 | `test_done.py::TestDoneDetectorTemplate` | ✅ |
| FR-6.2 | Motion-based done | `DoneDetector.is_done()` L443-458 | `test_done.py::TestDoneDetectorMotion` | ✅ |
| FR-6.3 | Detection toggles | `DoneDetector` config flags | `test_done.py::TestDoneDetectorToggles` | ✅ |
| FR-7.1 | Training starts | `train_ppo()` L1233-1302 | Manual: AC-3.1 | ✅ |
| FR-8.1 | Evaluation mode | `evaluate()` L1305-1414 | Manual: AC-4 | ✅ |
| FR-9.1 | OCR extraction | `ScoreExtractor.extract()` L363-401 | Manual smoke | ✅ |

---

## Non-Functional Requirements

| Req ID | Requirement | Implementation | Test(s) | Status |
|--------|-------------|----------------|---------|--------|
| NFR-1.1 | Capture at agent_hz | `step()` timing logic L650-658 | `--diagnose-capture` | ✅ |
| NFR-2.1 | Window not found error | `find_window_handle()` raises RuntimeError | Error message in code | ✅ |
| NFR-2.2 | OCR failure recovery | `ScoreExtractor.extract()` returns `last_score` | Fallback logic | ✅ |
| NFR-3.1 | Keys released on close | `close()` L690-698 | `test_env.py::test_close_releases_action_key` | ✅ |
| NFR-3.2 | Keys released on done | `step()` L676 | `test_env.py::test_gameover_penalty` | ✅ |
| NFR-3.3 | atexit cleanup | `atexit.register(_cleanup)` L703 | `test_cleanup.py::test_cleanup_function_exists` | ✅ |

---

## Safety Invariants

| Inv ID | Invariant | Implementation | Test(s) | Status |
|--------|-----------|----------------|---------|--------|
| INV-1 | No stuck keys on exception | `step()` try/finally L631-683 | `test_cleanup.py::test_exception_during_key_operation` | ✅ |
| INV-2 | No orphan windows | `close()` calls `cv2.destroyAllWindows()` | Manual verification | ✅ |
| INV-3 | Config persistence | `load_configs()` + JSON files | `conftest.py` fixture | ✅ |
| INV-4 | Gymnasium API | `reset()` / `step()` signatures | `test_env.py::TestGymnasiumAPI` | ✅ |

---

## Risk Mitigations

| Risk ID | Risk | Mitigation | Implementation |
|---------|------|------------|----------------|
| RISK-1 | DPI Scaling | SetProcessDpiAwareness(2) | `ppsspp_jetpack_rl.py` L41-51 |
| RISK-3 | PrintWindow black frames | `--diagnose-capture` command | `diagnose_capture()` L1192-1278 |
| RISK-4 | Input requires focus | Documented in README | Limitation section |
| RISK-7 | Stuck keys on crash | try/finally in step() | `step()` L631-683 |

---

## Test Summary

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_preprocess.py` | 8 | FR-4.1, FR-4.2, FR-4.4 |
| `test_done.py` | 9 | FR-6.1, FR-6.2, FR-6.3 |
| `test_cleanup.py` | 11 | NFR-3.1, NFR-3.3, INV-1 |
| `test_env.py` | 14 | FR-3, FR-4.3, FR-5, INV-4 |
| **Total** | **42** | |

---

## Manual Smoke Tests Required

These cannot be automated without PPSSPP:

1. **AC-1.1**: Calibration capture region
2. **AC-1.2**: Calibration score region
3. **AC-2**: DPI scaling correctness
4. **AC-3**: Training smoke test
5. **AC-4**: Evaluation smoke test
6. **AC-5**: Cleanup behavior (Ctrl+C)
