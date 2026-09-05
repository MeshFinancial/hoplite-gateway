import sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

# Change the batch runner to skip broken accounts
old = '''    pending = [a for a in accounts if a[\"login\"] not in existing_labels]'''
new = '''    pending = [a for a in accounts if a[\"login\"] not in existing_labels]
    # Skip accounts we've already attempted (to avoid broken OAuth state)
    attempted = [\"TopDeckhandBlock\", \"GroundPhasePraise\", \"Hallpatrench\"]
    pending = [a for a in pending if a[\"login\"] not in attempted]'''

if old in c:
    c = c.replace(old, new)
    print('SKIP_FIXED')
else:
    print('SKIP_NOT_FOUND')

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('DONE')