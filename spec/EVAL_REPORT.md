# EVAL_REPORT.md — Spec Evaluation Report

**Generated:** 2026-01-11
**Evaluator:** Automated spec-driven completeness check

---

## 1. Environment Info

| Component | Version |
|-----------|---------|
| OS | Windows 10/11 |
| Python | 3.13.2 |
| pytest | 8.4.1 |
| pytest-cov | 7.0.0 |

---

## 2. Installation & Test Commands

```powershell
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-cov

# Run all tests (no PPSSPP required)
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=ppsspp_jetpack_rl --cov-report=term-missing
```

---

## 3. Test Results Summary

| Metric | Value |
|--------|-------|
| Total tests | 42 |
| Passed | 42 |
| Failed | 0 |
| Skipped | 0 |
| Duration | ~95 seconds |

### Tests by File

| File | Tests | Status |
|------|-------|--------|
| `test_cleanup.py` | 11 | ✅ All passed |
| `test_done.py` | 9 | ✅ All passed |
| `test_env.py` | 14 | ✅ All passed |
| `test_preprocess.py` | 8 | ✅ All passed |

---

## 4. Coverage Summary

| Metric | Value |
|--------|-------|
| Statements | 981 |
| Missed | 686 |
| Coverage | **30%** |

> [!NOTE]
> Coverage is intentionally low because:
> - Most code paths require PPSSPP (GUI, real capture, training loops)
> - Tests focus on testable units with fake backends
> - CLI entry points and calibration GUI are not unit-tested

---

## 5. Spec Consistency Findings

### 5.1 CLI Contract Verification

| Flag | SPEC.md | ACCEPT.md | Implemented | Notes |
|------|---------|-----------|-------------|-------|
| `--launch` | ✅ | ✅ | ✅ | |
| `--calibrate` | ✅ | ✅ | ✅ | |
| `--calibrate-score` | ✅ | ✅ | ✅ | |
| `--play-random` | ✅ | ✅ | ✅ | |
| `--capture-gameover` | ✅ | ✅ | ✅ | |
| `--diagnose-capture` | ✅ | ❌ | ✅ | Not in ACCEPTANCE.md but exists |
| `--train` | ✅ | ✅ | ✅ | |
| `--timesteps` | ✅ | ✅ | ✅ | |
| `--resume` | ✅ | ✅ | ✅ | |
| `--eval` | ✅ | ✅ | ✅ | |
| `--wandb` | ✅ | ✅ | ✅ | |
| `--background` | ✅ | ✅ | ✅ | |
| `--visualize-network` | ✅ | ❌ | ✅ | |
| `--debug-visual` | ❌ | ❌ | ✅ | Undocumented in specs |
| `--no-ocr` | ❌ | ⚠️ | ❌ | **ACCEPTANCE.md AC-7.2 mentions it** |

### 5.2 Documentation Issues Found

#### Issue 1: `--no-ocr` Flag Missing (ACCEPTANCE.md AC-7.2)

**Location:** `spec/ACCEPTANCE.md` line 191-192
```markdown
1. Set `--no-ocr` (or disable in config) and run `--play-random`
   *(Note: this flag may need to be added)*
```

**Status:** Flag NOT implemented. ACCEPTANCE criteria cannot be verified.

**Recommendation:** Either:
- Implement `--no-ocr` flag (low risk, see "Next PRs")
- Update ACCEPTANCE.md to reference config setting instead

---

#### Issue 2: SPEC.md Known Limitations #2 is Stale

**Location:** `spec/SPEC.md` line 225
```markdown
2. **DPI scaling**: The application does not call `SetProcessDPIAware()`.
```

**Actual Code:** `ppsspp_jetpack_rl.py` lines 41-49
```python
try:
    # Per-Monitor DPI Aware (Windows 8.1+)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        # System DPI Aware fallback (Windows Vista+)
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
```

**Status:** DPI awareness IS implemented—spec is outdated.

**Recommendation:** Update SPEC.md Known Limitations #2.

---

#### Issue 3: TEST_PLAN.md Statuses All "TODO" But Tests Exist

**Location:** `spec/TEST_PLAN.md`

All 60+ requirements listed show `Status: TODO`, but:
- TRACEABILITY.md shows 32 requirements as ✅
- Actual tests exist and pass

**Recommendation:** Sync TEST_PLAN.md statuses with TRACEABILITY.md.

---

## 6. Risk Mitigation Status

| Risk ID | Description | Mitigation Status |
|---------|-------------|-------------------|
| RISK-1 | DPI Scaling | ✅ **IMPLEMENTED** (SetProcessDpiAwareness call) |
| RISK-3 | PrintWindow black frames | ✅ Implemented (`--diagnose-capture`) |
| RISK-4 | Input requires focus | ✅ Documented in README |
| RISK-7 | Stuck keys on crash | ✅ Implemented (try/finally + atexit) |
| RISK-2 | Multi-monitor coords | ⚠️ Documented only, no runtime detection |
| RISK-5 | OCR variability | ⚠️ No `--test-ocr` command |
| RISK-6 | Calibration focus-stealing | ❓ Low priority |
| RISK-8 | Capture/OCR latency | ⚠️ No profiling tools |

---

## 7. Next PRs (Ordered by Impact)

### P1 — High Priority (Doc Sync)

1. **chore(spec): sync TEST_PLAN.md statuses with TRACEABILITY.md**
   - Update all Status columns from TODO to ✅ where tests exist
   - Add actual test file references

2. **chore(spec): fix SPEC.md Known Limitations #2**
   - Update to reflect that DPI awareness IS implemented
   - Note remaining edge cases (>150% scaling not fully tested)

### P2 — Medium Priority (Feature Gap)

3. **feat(cli): add --no-ocr flag**
   - Implement `--no-ocr` to disable OCR reward during training
   - Already have config key `use_ocr_reward: False` (default)
   - Wire CLI flag to set this config
   - Low risk: no behavior change unless flag used

### P3 — Low Priority (Enhancements)

4. **docs(spec): document --debug-visual and --diagnose-capture in ACCEPTANCE.md**
   - These exist but aren't in acceptance criteria

5. **feat(cli): add --test-ocr for OCR debugging (RISK-5)**
   - Would help users verify OCR setup before training

---

## 8. Summary

| Category | Status |
|----------|--------|
| Tests | ✅ 42/42 passing |
| Coverage | ⚠️ 30% (expected for PPSSPP-dependent code) |
| CLI Contract | ⚠️ `--no-ocr` missing |
| Spec Consistency | ⚠️ 3 issues found |
| Risk Mitigations | ✅ 4/4 P1 risks addressed |

**Overall Assessment:** The codebase is functional and well-tested for its core components. Documentation is mostly accurate but has fallen behind recent implementation changes. Priority should be given to syncing TEST_PLAN.md and fixing the stale SPEC.md limitation about DPI.
