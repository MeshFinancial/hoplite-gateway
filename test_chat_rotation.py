#!/usr/bin/env python3
import requests, time

url = 'http://localhost:8085/v1/chat/completions'
headers = {'Authorization': 'Bearer sk-hoplite-gateway', 'Content-Type': 'application/json'}

for i in [2, 3]:
    print(f"\n=== Request {i}/3 ===")
    payload = {
        'model': 'deepseek/deepseek-v4-flash-0731',
        'messages': [{'role': 'user', 'content': f'Reply with: OK_{i}'}]
    }
    t0 = time.time()
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        print(f"Status: {r.status_code} in {time.time()-t0:.2f}s")
        if r.status_code == 200:
            print("Content:", r.json()['choices'][0]['message']['content'].strip()[:80])
        else:
            print("Error:", r.text[:300])
    except Exception as e:
        print("Exception:", e)
