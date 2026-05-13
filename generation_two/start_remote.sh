#!/bin/bash
pkill -f continuous_evolution 2>/dev/null
sleep 1

cd /root/worldquant-miner/generation_two
export PYTHONPATH=/root/worldquant-miner:$PYTHONPATH

echo "=== Files check ==="
ls evolution/ core/ data_fetcher/ 2>/dev/null | head -20
echo ""

nohup python3 continuous_evolution.py --mode d1 > mining.log 2>&1 &
echo "PID=$!"
sleep 5
head -50 mining.log
echo "=== ENGINE STARTED ==="
