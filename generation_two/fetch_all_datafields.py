"""
WQ Brain Data Fields Scraper v6 - Rate Limit Aware
====================================================
Rate limits: 1 req/sec, 30 req/min
Strategy: 1 request every 3 seconds to stay safely under limits
"""
import requests, json, os, sys, time, shutil

BASE_URL = "https://api.worldquantbrain.com"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "constants")
REQ_INTERVAL = 3  # seconds between requests (safe: 1/sec limit, 30/min)

last_request_time = 0


def throttle():
    """Enforce minimum interval between requests"""
    global last_request_time
    elapsed = time.time() - last_request_time
    if elapsed < REQ_INTERVAL:
        time.sleep(REQ_INTERVAL - elapsed)
    last_request_time = time.time()


def jwt_auth(sess):
    with open(os.path.join(SCRIPT_DIR, 'auth.json'), 'r') as f:
        storage = json.load(f)
    jwt = None
    for c in storage.get('cookies', []):
        if c.get('name') == 't':
            jwt = c['value']
    if not jwt:
        print("[ERR] No JWT in auth.json")
        return False
    sess.headers['Authorization'] = f'Bearer {jwt}'
    throttle()
    r = sess.get(f"{BASE_URL}/users/self", timeout=30)
    if r.status_code == 200:
        u = r.json()
        print(f"[OK] {u.get('email')} Level={u.get('geniusLevel')}")
        return True
    print(f"[ERR] JWT: {r.status_code} {r.text[:200]}")
    return False


def api_get(sess, url, params):
    """Rate-limited GET with retry"""
    short_url = url.split('/')[-1]
    for attempt in range(5):
        throttle()
        try:
            sys.stdout.write(f"    [{short_url} attempt {attempt+1}] ... ")
            sys.stdout.flush()
            r = sess.get(url, params=params, timeout=90)
            sys.stdout.write(f"HTTP {r.status_code}\n")
            sys.stdout.flush()
            if r.status_code == 429:
                wait = int(r.headers.get('Retry-After', 10))
                print(f"    [429] wait {wait+5}s", flush=True)
                time.sleep(wait + 5)
                continue
            return r
        except requests.exceptions.ReadTimeout:
            sys.stdout.write("ReadTimeout\n")
            sys.stdout.flush()
            time.sleep(20)
        except requests.exceptions.ConnectTimeout:
            sys.stdout.write("ConnectTimeout\n")
            sys.stdout.flush()
            time.sleep(20)
        except requests.exceptions.ConnectionError as e:
            sys.stdout.write(f"ConnError: {str(e)[:100]}\n")
            sys.stdout.flush()
            time.sleep(10)
        except Exception as e:
            sys.stdout.write(f"{type(e).__name__}: {str(e)[:100]}\n")
            sys.stdout.flush()
            time.sleep(10)
    print(f"    [GAVE UP] {short_url}", flush=True)
    return None


def get_datasets(sess, cat, region, delay, universe):
    params = {
        'category': cat, 'delay': delay, 'instrumentType': 'EQUITY',
        'region': region, 'universe': universe, 'limit': 20,
    }
    r = api_get(sess, f"{BASE_URL}/data-sets", params)
    if r is None:
        print(f"  [{cat}] datasets: NO RESPONSE (all retries failed)")
        return []
    if r.status_code == 400:
        print(f"  [{cat}] datasets: 400 BAD REQUEST - {r.text[:300]}")
        return []
    if r.status_code != 200:
        print(f"  [{cat}] datasets: HTTP {r.status_code} - {r.text[:300]}")
        return []
    data = r.json()
    ids = [d['id'] for d in data.get('results', []) if d.get('id')]
    cnt = data.get('count', len(ids))
    print(f"  [{cat}] {len(ids)}/{cnt} datasets: {ids}")
    return ids


def get_fields(sess, ds_id, region, delay, universe):
    fields = []
    seen_ids = set()
    offset = 0
    limit = 50
    while True:
        params = {
            'dataset.id': ds_id, 'delay': delay, 'instrumentType': 'EQUITY',
            'region': region, 'universe': universe, 'limit': limit, 'offset': offset,
        }
        r = api_get(sess, f"{BASE_URL}/data-fields", params)
        if r is None or r.status_code != 200:
            break
        data = r.json()
        batch = data.get('results', [])
        if not batch:
            break

        # Dedup within this dataset
        new_count = 0
        for f in batch:
            fid = f.get('id', '')
            if fid and fid not in seen_ids:
                seen_ids.add(fid)
                fields.append(f)
                new_count += 1

        total = data.get('count', '?')
        print(f"      offset={offset}: +{new_count} new (unique: {len(fields)}/{total})", flush=True)

        if new_count == 0:
            print(f"      [STOP] No new fields, cycling detected", flush=True)
            break

        offset += limit

        # If we've got all the count says there are, stop
        if isinstance(total, int) and len(fields) >= total:
            print(f"      [DONE] Got all {total} fields", flush=True)
            break

    return fields


def main():
    print("=" * 55)
    print("WQ Brain Fields Scraper v6 (rate-limit aware)")
    print(f"Interval: {REQ_INTERVAL}s between requests")
    print("=" * 55)

    sess = requests.Session()
    sess.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'

    if not jwt_auth(sess):
        sys.exit(1)

    cats = ['model', 'analyst', 'fundamental', 'news', 'option', 'pv', 'sentiment', 'socialmedia']

    for delay, universe, label in [(1, "TOP3000", "D1"), (0, "TOP1000", "D0")]:
        print(f"\n{'#'*55}")
        print(f"# {label}: delay={delay}, universe={universe}")
        print(f"{'#'*55}")

        all_fields = []
        stats = {}

        for cat in cats:
            print(f"\n>>> {cat.upper()}")
            ds_ids = get_datasets(sess, cat, "USA", delay, universe)
            cat_total = 0

            for i, ds in enumerate(ds_ids, 1):
                flds = get_fields(sess, ds, "USA", delay, universe)
                all_fields.extend(flds)
                cat_total += len(flds)
                print(f"    [{i}/{len(ds_ids)}] {ds}: {len(flds)} fields")

            stats[cat] = cat_total
            print(f"  => {cat}: {cat_total} fields")

        # Dedup
        seen = set()
        unique = []
        for f in all_fields:
            fid = f.get('id', '')
            if fid and fid not in seen:
                seen.add(fid)
                unique.append(f)
        print(f"\n[Dedup] {len(all_fields)} -> {len(unique)}")

        # Save
        cache_path = os.path.join(CACHE_DIR, f"data_fields_cache_USA_{delay}_{universe}.json")
        if len(unique) > 50:
            if os.path.exists(cache_path):
                shutil.copy2(cache_path, cache_path + ".bak")
                print(f"  [Backup] {cache_path}.bak")
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(unique, f, ensure_ascii=False, indent=1)
            print(f"  [Saved] {len(unique)} fields -> {cache_path} ({os.path.getsize(cache_path):,} bytes)")
        else:
            print(f"  [SKIP] Only {len(unique)} fields")

        # Stats table
        print(f"\n{'Cat':15s} | {'Got':>7s}")
        print("-" * 28)
        for cat in cats:
            print(f"{cat:15s} | {stats.get(cat,0):>7d}")
        print(f"{'TOTAL':15s} | {len(unique):>7d}")

    print("\nAll done!")


if __name__ == "__main__":
    main()
