# Brainstorm: Episode Termination Logic

## 1. The Problem

**Symptom**: Episodes end prematurely or at wrong times
**Evidence**: Logs show `[Step] DONE by GameState=LOADING` when Barry hasn't died

---

## 2. What We Know (Facts)

### Jetpack Joyride Game Flow
```
START → GAMEPLAY → DEATH → RESULTS_SCREEN → SAVE_DIALOG → TAP_TO_PLAY → GAMEPLAY
                   ↑ Barry dies           ↑ Shows stats  ↑ "Save?"   ↑ Restart
```

### Current Detection Methods
1. **Motion detection** - Screen stops moving = done
2. **Template matching** - Game-over screen template
3. **GameState heuristics** - Based on pixel mean/std values

---

## 3. Questions to Answer

1. How accurate is the current GameState detection?
2. What distinguishes DEATH from MENU transitions visually?
3. Can we detect Barry's death directly (e.g., death animation)?
4. Should we let the agent learn to handle menus?

---

## 4. Potential Solutions

### Option A: Visual Death Marker
- Detect specific death animation/explosion
- Most accurate but needs template for death

### Option B: Distance-Based Done
- Episode ends when distance score stops increasing
- Simple and reliable if OCR works

### Option C: Timeout-Based Done  
- If gameplay_steps > N and no reward for M steps → done
- Robust but may miss actual deaths

### Option D: Let Agent Handle Everything
- Don't end episode on menus, let PPO learn
- Pros: Simpler code
- Cons: Trains on junk states

### Option E: Debug Mode First
- Add `--debug-states` flag to visualize game state detection
- Understand WHY current detection fails before fixing

---

## 5. Recommended Next Step

**OPTION E: Debug First**

Before fixing, we need to SEE what the state detection is doing:
1. Add real-time state visualization to GUI
2. Log transitions: GAMEPLAY → X → Y
3. Run for 30 seconds and observe when/why it fails

This will reveal the actual failure mode.

---

## 6. Debug Implementation

Add to GUI:
- Current detected state (GAMEPLAY/LOADING/etc)
- Mean pixel value
- Last N state transitions

Then observe:
- Does state detection correctly identify GAMEPLAY?
- What state is detected when Barry dies?
- What state is detected during menus?
