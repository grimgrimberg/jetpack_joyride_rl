# 🚀 Jetpack Joyride RL

Train a reinforcement learning agent to play **Jetpack Joyride** on PPSSPP (PSP emulator) using PPO and screen capture.

![Status](https://img.shields.io/badge/status-experimental-orange)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- 🎮 **Real-time training** on PPSSPP emulator via screen capture
- 🔢 **OCR-based rewards** using distance/score extraction
- 🖼️ **Tkinter calibration GUI** for region selection
- 📊 **TensorBoard + Weights & Biases** logging
- 💾 **Checkpoint support** - resume training anytime
- 🧠 **Network visualization** - see the CNN architecture
- 🔍 **Capture diagnostics** - diagnose background capture issues

---

## ⚠️ Known Limitations

| Limitation | Details |
|------------|---------|
| **Windows only** | Uses pywin32 for capture and input |
| **Input requires focus** | Keyboard events need PPSSPP in foreground; `--background` helps with capture, not input |
| **DPI scaling** | Tested at 100%; higher scaling may need verification |
| **PrintWindow + Vulkan** | Background capture may fail with Vulkan renderer; use D3D11 |

---

## Installation

### 1. Prerequisites

- **Python 3.10+**
- **PPSSPP Emulator**: [Download here](https://www.ppsspp.org/download/)
- **Jetpack Joyride PSP ROM** (`.iso` or `.cso`)
- **Tesseract OCR** (optional, for score extraction)

### 2. Install Tesseract OCR (Windows)

```powershell
# Option A: Using winget
winget install UB-Mannheim.TesseractOCR

# Option B: Manual download
# https://github.com/UB-Mannheim/tesseract/wiki
```

### 3. Install Python Dependencies

```powershell
cd jetpack_joyride_rl
pip install -r requirements.txt
```

### 4. Configure PPSSPP Controls

Open PPSSPP → Settings → Controls → Control Mapping:

| Action | Recommended Key |
|--------|-----------------|
| Cross (✕) / Boost | `Z` |
| Start | `Enter` |

---

## Quick Start

### Step 1: Launch PPSSPP with the game

```powershell
python ppsspp_jetpack_rl.py --launch
```

Or open PPSSPP manually and load the ROM.

### Step 2: Calibrate capture region

```powershell
python ppsspp_jetpack_rl.py --calibrate
```

A Tkinter window opens. Click and drag to select the game area, then click "Save".

### Step 3: Test with random actions

```powershell
python ppsspp_jetpack_rl.py --play-random
```

Runs 30 seconds of random play to verify everything works.

### Step 4: Train the agent

```powershell
# Short test run
python ppsspp_jetpack_rl.py --train --timesteps 10000

# Full training with logging
python ppsspp_jetpack_rl.py --train --timesteps 300000 --wandb
```

---

## Verify Installation

Run these commands to verify your setup:

```powershell
# 1. Run tests (no PPSSPP required)
python -m pytest tests/ -q

# 2. Check capture reliability (PPSSPP required)
python ppsspp_jetpack_rl.py --diagnose-capture

# 3. Test keyboard input (PPSSPP required)
python ppsspp_jetpack_rl.py --play-random
```

---

## CLI Reference

| Flag | Description |
|------|-------------|
| `--launch` | Launch PPSSPP with configured ROM |
| `--calibrate` | Open Tkinter GUI to set game capture region |
| `--calibrate-score` | Set OCR region for score extraction |
| `--play-random` | Run 30s of random actions (test mode) |
| `--capture-gameover` | Capture game-over template for detection |
| `--diagnose-capture` | Test capture reliability (foreground & background) |
| `--train` | Start PPO training |
| `--timesteps N` | Training duration (default: 300000) |
| `--resume PATH` | Resume training from checkpoint |
| `--eval PATH` | Run trained model (no training) |
| `--wandb` | Enable Weights & Biases logging |
| `--visualize-network` | Render CNN architecture diagram |
| `--background` | Enable background capture (BitBlt) |

---

## Troubleshooting

### "Could not find PPSSPP window"
- Make sure PPSSPP is running
- Check that window title contains "PPSSPP"

### Capture region looks wrong / offset
- **DPI Scaling**: If using >100% scaling, try setting Windows display to 100%
- **Multi-monitor**: Ensure PPSSPP is on primary monitor, or recalibrate
- Run `--diagnose-capture` to check for capture issues

### Black frames in background mode
- PPSSPP Vulkan renderer doesn't support PrintWindow
- **Fix**: Settings → Graphics → Backend → **Direct3D 11**
- Run `--diagnose-capture` to verify

### OCR returning wrong numbers
- Recalibrate score region with `--calibrate-score`
- Ensure Tesseract is installed and in PATH
- Try adjusting the game's display settings

### Training too slow
- Reduce `agent_hz` (fewer decisions/second)
- Consider that input always requires focus

### Agent not learning
- Train for longer (300k+ timesteps minimum)
- Check that game-over detection works (`--capture-gameover`)
- Verify reward is being tracked in TensorBoard

### Stuck keys after training
- This should be fixed (try/finally protection added)
- If it happens, press the stuck key to unstick it

---

## Project Structure

```
jetpack_joyride_rl/
├── ppsspp_jetpack_rl.py    # Main script
├── backends.py              # Capture/Input/Window protocols
├── requirements.txt         # Python dependencies
├── pyproject.toml          # Project configuration
├── README.md               # This file
├── ppsspp_capture_config.json  # Saved capture region
├── score_roi_config.json       # Saved score ROI
├── gameover_template.png       # Game-over detection template
├── spec/                       # Specifications
│   ├── SPEC.md
│   ├── ACCEPTANCE.md
│   ├── TEST_PLAN.md
│   ├── RISKS.md
│   └── TRACEABILITY.md
├── tests/                      # Automated tests
│   ├── conftest.py
│   ├── fakes/
│   ├── test_env.py
│   ├── test_done.py
│   ├── test_cleanup.py
│   └── test_preprocess.py
├── checkpoints/                # Training checkpoints
├── models/                     # Final trained models
└── tb_jetpack/                 # TensorBoard logs
```

---

## Development

### Running Tests

```powershell
# Install dev dependencies
pip install pytest pytest-cov ruff

# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=ppsspp_jetpack_rl

# Lint code
ruff check .
```

---

## License

MIT License - Feel free to use and modify!

---

## Acknowledgments

- [Stable-Baselines3](https://github.com/DLR-RM/stable-baselines3) for PPO implementation
- [PPSSPP](https://www.ppsspp.org/) for PSP emulation
- Halfbrick Studios for Jetpack Joyride
