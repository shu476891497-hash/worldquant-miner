"""Deploy update: pull, reset, restart"""
import paramiko
import time
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

HOST = "124.220.69.2"
USER = "root"
PASSWD = "Shu476891497"

def ssh_exec(client, cmd, timeout=30):
    print(f"  > {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    stdout.channel.settimeout(timeout)
    stderr.channel.settimeout(timeout)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out:
        for line in out.split('\n')[-20:]:
            try:
                print(f"    {line}")
            except UnicodeEncodeError:
                print(f"    {line.encode('ascii', 'replace').decode()}")
    return out

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print(f"Connecting to {HOST}...")
client.connect(HOST, port=22, username=USER, password=PASSWD, timeout=15)
print("Connected!\n")

# 1. Kill old
print("=== 1. Kill old process ===")
ssh_exec(client, "pkill -9 -f continuous_evolution.py 2>/dev/null || true")
time.sleep(2)

# 2. Pull & reset (split to avoid compound timeout)
print("\n=== 2. Git pull ===")
ssh_exec(client, "cd ~/worldquant-miner && git fetch origin master", timeout=120)
ssh_exec(client, "cd ~/worldquant-miner && git reset --hard origin/master", timeout=60)

# 3. Verify
print("\n=== 3. Verify syntax ===")
ssh_exec(client, "cd ~/worldquant-miner/generation_two && python3 -c \"import py_compile; py_compile.compile('continuous_evolution.py', doraise=True); print('Syntax OK')\"")

# 4. Verify kill threshold in code
print("\n=== 4. Verify kill threshold ===")
ssh_exec(client, "grep -A5 '_should_kill' ~/worldquant-miner/generation_two/continuous_evolution.py | head -8")

# 5. Start engine (fire and forget)
print("\n=== 5. Start engine ===")
transport = client.get_transport()
channel = transport.open_session()
channel.exec_command(
    "cd ~/worldquant-miner/generation_two && "
    "nohup python3 continuous_evolution.py --mode both > mining.log 2>&1 &"
)
channel.close()
print("  Engine starting...")
time.sleep(10)

# 6. Verify running
print("\n=== 6. Verify ===")
out = ssh_exec(client, "ps aux | grep continuous_evolution | grep -v grep")
if out and 'python3' in out:
    print("    >>> ENGINE IS RUNNING! <<<")
else:
    print("    >>> FAILED - checking log <<<")
    ssh_exec(client, "tail -20 ~/worldquant-miner/generation_two/mining.log")

print("\n=== Last 15 lines of mining.log ===")
ssh_exec(client, "tail -15 ~/worldquant-miner/generation_two/mining.log")

client.close()
print("\nDone!")
