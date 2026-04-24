import sqlite3
import os

db_path = 'C:/Users/22637/OneDrive/Desktop/antigravity/worldquant_iqc/worldquant-miner/generation_two/generation_two_backtests.db'

if not os.path.exists(db_path):
    print("Database file not found!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print(f"--- Database Scan ---")
for t in tables:
    table_name = t[0]
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"Table '{table_name}': {count} records")

    # If this is the backtests table, let's see how many passed (Sharpe > 1.25)
    if 'backtest' in table_name.lower() or 'alpha' in table_name.lower():
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE sharpe > 1.0")
            good_count = cursor.fetchone()[0]
            print(f" -> Of which, {good_count} have Sharpe > 1.0 (approaching WQ standard)")
        except:
            pass
conn.close()
