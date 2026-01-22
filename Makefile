PYTHON ?= python

.PHONY: setup format lint test smoke train-smoke eval-smoke capture-debug

setup:
	$(PYTHON) -m pip install -r requirements.txt

format:
	$(PYTHON) -m black ppsspp_jetpack_rl.py backends.py tests

lint:
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest tests

smoke:
	$(PYTHON) -m pytest tests/test_preprocess.py -q

train-smoke:
	$(PYTHON) ppsspp_jetpack_rl.py --train --timesteps 5000 --background

eval-smoke:
	$(PYTHON) ppsspp_jetpack_rl.py --eval models/latest.zip --timesteps 1000

capture-debug:
	$(PYTHON) ppsspp_jetpack_rl.py --diagnose-capture
