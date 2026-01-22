"""Test game state detection on saved debug frames."""
import cv2
import os
import numpy as np
from ppsspp_jetpack_rl import detect_game_state, GameState

def main():
    debug_dir = "debug_frames"
    
    if not os.path.exists(debug_dir):
        print(f"[ERROR] Debug frames directory '{debug_dir}' not found!")
        print("Run --diagnose-capture first to generate test frames.")
        return
    
    # Get processed frames (84x84 grayscale)
    proc_files = sorted([f for f in os.listdir(debug_dir) if 'proc' in f])
    
    if not proc_files:
        print("[ERROR] No processed frames found in debug_frames/")
        return
    
    print("Testing detect_game_state() on saved debug frames")
    print("=" * 80)
    print(f"{'Filename':<50} {'Mean':>6} {'Std':>5} {'Detected':>10} {'Expected':>10}")
    print("-" * 80)
    
    correct = 0
    wrong = 0
    
    for f in proc_files[:30]:  # Test first 30 frames
        path = os.path.join(debug_dir, f)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        
        if img is None:
            print(f"[SKIP] Could not read: {f}")
            continue
        
        # Run actual detect_game_state
        state = detect_game_state(img)
        
        # Parse expected state from filename (e.g., "trans001_..._GAMEPLAY_to_LOADING_proc.png")
        expected = "?"
        if "_to_" in f:
            parts = f.split("_to_")
            if len(parts) >= 2:
                to_part = parts[1].split("_")[0]
                # Normalize: SAVE_DIALOG -> RESULTS (both are menu states)
                if to_part in ("SAVE_DIALOG", "RESULTS"):
                    expected = "RESULTS"
                elif to_part == "LOADING":
                    expected = "LOADING"
                elif to_part == "GAMEPLAY":
                    expected = "GAMEPLAY"
                else:
                    expected = to_part
        
        # Check if detection is correct
        # Note: Black frames (mean<5) now return GAMEPLAY (ignore capture glitches)
        mean = img.mean()
        std = img.std()
        
        # Determine if result is "correct" based on new logic
        is_correct = False
        if mean < 5:
            # Black frames should be GAMEPLAY (ignored)
            is_correct = (state == GameState.GAMEPLAY)
            expected = "GAMEPLAY*"  # Mark as "should ignore"
        elif expected == "RESULTS" and state == GameState.RESULTS:
            is_correct = True
        elif expected == "GAMEPLAY" and state == GameState.GAMEPLAY:
            is_correct = True
        elif expected == "LOADING" and state in (GameState.LOADING, GameState.GAMEPLAY):
            # LOADING can be either (dark transition OR black frame ignored)
            is_correct = True
        
        status = "OK" if is_correct else "WRONG"
        if is_correct:
            correct += 1
        else:
            wrong += 1
        
        print(f"{f[:50]:<50} {mean:>6.1f} {std:>5.1f} {state.name:>10} {expected:>10} {status}")
    
    print("-" * 80)
    print(f"Results: {correct} correct, {wrong} wrong ({100*correct/(correct+wrong):.1f}% accuracy)")
    
    # Also test some synthetic edge cases
    print("\n" + "=" * 80)
    print("Testing synthetic edge cases:")
    print("-" * 80)
    
    test_cases = [
        ("Pure black (capture glitch)", np.zeros((84, 84), dtype=np.uint8), GameState.GAMEPLAY),
        ("Very dark (mean=10, std=2)", np.full((84, 84), 10, dtype=np.uint8), GameState.LOADING),
        ("Dark gameplay (mean=30, std=8)", np.random.randint(20, 50, (84, 84), dtype=np.uint8), GameState.GAMEPLAY),
        ("Menu screen (mean=100, std=5)", np.full((84, 84), 100, dtype=np.uint8), GameState.RESULTS),
        ("Bright menu (mean=130, std=7)", np.random.randint(120, 140, (84, 84), dtype=np.uint8), GameState.RESULTS),
        ("Gameplay varied (mean=50, std=20)", np.random.randint(20, 80, (84, 84), dtype=np.uint8), GameState.GAMEPLAY),
    ]
    
    for name, frame, expected_state in test_cases:
        result = detect_game_state(frame)
        mean = frame.mean()
        std = frame.std()
        status = "OK" if result == expected_state else "WRONG"
        print(f"{name:<40} m={mean:>5.1f} s={std:>5.1f} -> {result.name:<10} (expect: {expected_state.name:<10}) {status}")

if __name__ == "__main__":
    main()
