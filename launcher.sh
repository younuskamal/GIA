
#!/bin/bash
cd /var/www/GIA
source venv/bin/activate
while true; do
    echo "Starting GIA..." >> loop.log
    python3 run_live_demo.py --model_idx P --risk 1.0 --lev 100 --guard 80 >> loop.log 2>&1
    echo "GIA Crashed. Restarting in 5s..." >> loop.log
    sleep 5
done
