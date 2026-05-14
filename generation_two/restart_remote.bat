@echo off
ssh -o StrictHostKeyChecking=no root@124.220.69.2 "pkill -f continuous_evolution 2>/dev/null; sleep 1; cd /root/worldquant-miner; PYTHONPATH=/root/worldquant-miner nohup python3 generation_two/continuous_evolution.py > mining.log 2>&1 & disown; sleep 3; ps aux | grep continuous_evolution | grep -v grep; echo '---'; tail -10 mining.log 2>/dev/null"
