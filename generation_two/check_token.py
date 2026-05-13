import base64, json
from datetime import datetime

with open('auth.json', 'r') as f:
    storage = json.load(f)

for c in storage.get('cookies', []):
    if c.get('name') == 't':
        t = c['value']
        payload = json.loads(base64.b64decode(t.split('.')[1] + '=='))
        exp_dt = datetime.fromtimestamp(payload['exp'])
        now = datetime.now()
        hours_left = (exp_dt - now).total_seconds() / 3600
        print(f"Token exp: {exp_dt}")
        print(f"Now:       {now}")
        print(f"Hours left: {hours_left:.1f}h")
        if hours_left <= 0:
            print("TOKEN EXPIRED!")
        else:
            print("TOKEN VALID!")
        break
