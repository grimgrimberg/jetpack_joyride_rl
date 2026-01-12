# DESIGN.md — Superpowers + VoltAgent Integration

**Date:** 2026-01-12
**Branch:** `superpowers-voltagent-integration`
**Worktree:** `../wjr-superpowers`

---

## Brainstorming Results

### Top 3 Spec Inconsistencies Found

1. **TRACEABILITY.md line numbers are stale**
   - Issue: Line references (e.g., `L275-285`, `L511-514`) don't match current code
   - Cause: MLP implementation added ~500 lines, shifting all references
   - Impact: Traceability links are broken, making audits unreliable

2. **Missing MLP mode in spec documents**
   - Issue: FR-4 (Observation Processing) only describes CNN mode (84×84 grayscale)
   - MLP mode uses 68-float vectors, not documented in SPEC.md
   - `--mlp` and `--gui` flags not listed in CLI contract

3. **TEST_PLAN.md missing MLP test coverage**
   - Issue: No tests for FeatureExtractor, CachedFeatureExtractor, JetpackMLPEnv
   - TRACEABILITY.md shows 42 tests but MLP code is untested

### Proposed Improvement PR

**Focus:** Fix #1 and #2 - Update spec documents to reflect MLP feature

**Scope:**
- Add FR-4.5 for MLP observation mode
- Add CLI entries for `--mlp` and `--gui`
- Update TRACEABILITY.md references (general fix, not line-by-line)
- Mark MLP tests as TODO in TEST_PLAN.md

---

## Subagent Assignments

| Task | Subagent | Deliverable |
|------|----------|-------------|
| Spec analysis | spec-architect | This DESIGN.md |
| SPEC.md updates | docs-librarian | FR-4.5 added |
| Test plan updates | docs-librarian | MLP test status |
| Review changes | code-reviewer | Approval |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Stale line numbers | Use function/class names instead of line numbers |
| Scope creep | Limit to documentation, no code changes |
| Missing MLP tests | Mark as TODO, defer to separate PR |
