#!/bin/bash
cd /var/www/GIA
# Use absolute path for python from venv
PYTHON_EXE="/var/www/GIA/venv/bin/python"
while true; do
    echo "[$(date)] Starting GIA..." >> loop.log
    $PYTHON_EXE run_live_demo.py --model_idx 5 --risk 1.0 --lev 100 --guard 0 >> loop.log 2>&1
    echo "[$(date)] GIA Crashed or Stopped. Restarting in 10s..." >> loop.log
    sleep 10
done
