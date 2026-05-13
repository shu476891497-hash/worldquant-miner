"""Check API pagination mechanism"""
import requests, json, os, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SCRIPT_DIR, 'auth.json'), 'r') as f:
    jwt = [c['value'] for c in json.load(f).get('cookies', []) if c.get('name') == 't'][0]

sess = requests.Session()
sess.headers['Authorization'] = f'Bearer {jwt}'
sess.headers['User-Agent'] = 'Mozilla/5.0'

# Check /data-fields response structure
print("--- Page 1 (limit=5) ---")
time.sleep(3)
r = sess.get('https://api.worldquantbrain.com/data-fields',
             params={'dataset.id': 'fundamental6', 'delay': 1, 'instrumentType': 'EQUITY',
                     'region': 'USA', 'universe': 'TOP3000', 'limit': 5},
             timeout=30)
data = r.json()
print(f"Keys: {list(data.keys())}")
print(f"count: {data.get('count')}")
print(f"next: {data.get('next')}")
print(f"previous: {data.get('previous')}")
ids1 = [f['id'] for f in data.get('results', [])]
print(f"IDs: {ids1}")

# Try using 'next' URL if available
next_url = data.get('next')
if next_url:
    print(f"\n--- Next URL: {next_url} ---")
    time.sleep(3)
    r2 = sess.get(next_url, timeout=30)
    data2 = r2.json()
    ids2 = [f['id'] for f in data2.get('results', [])]
    print(f"count: {data2.get('count')}")
    print(f"next: {data2.get('next')}")
    print(f"IDs: {ids2}")
    print(f"Overlap with page1: {set(ids1) & set(ids2)}")
else:
    # Try offset-based
    print("\n--- Try offset=5, limit=5 ---")
    time.sleep(3)
    r2 = sess.get('https://api.worldquantbrain.com/data-fields',
                  params={'dataset.id': 'fundamental6', 'delay': 1, 'instrumentType': 'EQUITY',
                          'region': 'USA', 'universe': 'TOP3000', 'limit': 5, 'offset': 5},
                  timeout=30)
    data2 = r2.json()
    ids2 = [f['id'] for f in data2.get('results', [])]
    print(f"IDs: {ids2}")
    print(f"Overlap: {set(ids1) & set(ids2)}")
