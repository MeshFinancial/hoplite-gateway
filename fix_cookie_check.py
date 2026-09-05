import sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix: start with a different account index
old = 'acc = accounts[0]'
new = 'acc = accounts[0]  # pick zero-th pending account'

if old in c:
    # The autoreg script uses accounts[0] hardcoded, but the batch runner iterates
    # Let me just modify the run_batch to skip accounts that failed before
    pass

# Fix: add explicit cookie check after OAuth
old2 = '''        # ════════════════════════════════════════════════════════════════
        # Step 7: Capture Cookies, Session, Org/Project IDs
        # ════════════════════════════════════════════════════════════════
        logger.info(f\"[{ts()}] [7/8] Extracting session cookies & metadata...\")
        cookies = await context.cookies()
        hop_cookies = {c[\"name\"]: c[\"value\"] for c in cookies if \"hoplite\" in c[\"domain\"]}
        logger.info(f\"[+] Hoplite cookies: {list(hop_cookies.keys())}\")'''

new2 = '''        # ════════════════════════════════════════════════════════════════
        # Step 7: Capture Cookies, Session, Org/Project IDs
        # ════════════════════════════════════════════════════════════════
        logger.info(f\"[{ts()}] [7/8] Extracting session cookies & metadata...\")
        cookies = await context.cookies()
        hop_cookies = {c[\"name\"]: c[\"value\"] for c in cookies if \"hoplite\" in c[\"domain\"]}
        logger.info(f\"[+] Hoplite cookies: {list(hop_cookies.keys())}\")
        # Check if we have auth cookies
        auth_cookies = [k for k in hop_cookies if 'auth' in k.lower() or 'session' in k.lower() or 'token' in k.lower()]
        if not auth_cookies:
            logger.warning(\"[!] No auth cookies found - user may not be logged in\")
            # Try to wait for OAuth redirect a bit more
            await asyncio.sleep(3)
            current_url = page.url
            logger.info(f\"[!] Current URL: {current_url[:80]}\")
            cookies2 = await context.cookies()
            hop_cookies2 = {c[\"name\"]: c[\"value\"] for c in cookies2 if \"hoplite\" in c[\"domain\"]}
            if hop_cookies2:
                hop_cookies = hop_cookies2
                logger.info(f\"[+] Retry cookies: {list(hop_cookies.keys())}\")'''

if old2 in c:
    c = c.replace(old2, new2)
    print('COOKIE_CHECK_FIXED')
else:
    print('COOKIE_CHECK_NOT_FOUND')

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('DONE')