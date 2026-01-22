# AGENTS Guardrails — Jetpack Joyride RL

## Definition of Done
- Guardrail docs (`AGENTS.md`, `docs/*`) updated alongside code/CLI/config changes.
- Mandatory commands executed with results recorded or justified (see below).
- Config paths validated or replaced with clear placeholders and next actions for the user.
- No regressions to capture/input focus handling; manual checklist in `docs/ACCEPTANCE_TESTS.md` addressed.
- Branch remains on feature branch with intentional commits; no stray atexit/key-hold leaks.

## Must Run Before Finishing
- `make format` (when Python files are touched).
- `make lint`
- `make test` (or the narrowest failing subset with explanation).
- `make smoke` (fast, PPSSPP-free).
- PPSSPP-dependent checks only when available: `python ppsspp_jetpack_rl.py --diagnose-capture` and quick calibration/ROI sanity.

## Safety Constraints
- No destructive git commands (`reset --hard`, `checkout -- .`, forced deletes).
- No unapproved installs or system-level changes; surface exact commands before running them.
- Keep Windows compatibility; do not introduce WSL-only capture/input assumptions.
- Avoid focus-stealing UI changes; calibration/debug UIs must be dismissible and non-topmost by default.
- Preserve user data (ROMs, templates, checkpoints); read-only unless explicitly configured.

## Coding Standards
- Prefer typed functions and explicit dependency injection (capture/input/window backends, config objects).
- Structured logging over ad-hoc prints; include context (hwnd, ROI, backend, scaling).
- Avoid hidden global state; keep configuration immutable during a run when possible.
- Deterministic/reproducible modes (seeded RNG, fixed timesteps) for tests and smoke runs.
- Small, testable modules with seams for record/replay and headless validation.
