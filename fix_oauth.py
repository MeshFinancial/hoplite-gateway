import sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix OAuth flow - proper waits + popup handling
old_oauth = '''        logger.info(f\"[{ts()}] [2/8] Opening Hoplite + GitHub OAuth...\")
        await page.goto(f\"{HOPLITE_APP}/login?plan=free&interval=monthly\", wait_until=\"domcontentloaded\", timeout=25000)
        await asyncio.sleep(4)

        btn = page.locator(\'button[aria-label=\"Continue with GitHub\"], button:has-text(\"GitHub\")\')
        if await btn.count() > 0:
            await btn.first.click()
        else:
            logger.warning(\"[!] No GitHub login button found on Hoplite\")
            await page.screenshot(path=str(SCREENSHOTS_DIR / f\"no_gh_btn_{login}_{ts()}.png\"))'''

new_oauth = '''        logger.info(f\"[{ts()}] [2/8] Opening Hoplite + GitHub OAuth...\")
        await page.goto(f\"{HOPLITE_APP}/login?plan=free&interval=monthly\", wait_until=\"networkidle\", timeout=30000)
        await asyncio.sleep(2)

        # Wait for the page to fully render - check for any button with GitHub text
        btn = None
        for sel in ['button[aria-label=\"Continue with GitHub\"]', 'button:has-text(\"GitHub\")', 'button:has-text(\"github\")', 'button:has-text(\"Continue\")']:
            b = page.locator(sel)
            if await b.count() > 0:
                btn = b; break

        if btn:
            await btn.first.click()
            await asyncio.sleep(2)
        else:
            logger.warning(\"[!] No GitHub login button found on Hoplite\")
            await page.screenshot(path=str(SCREENSHOTS_DIR / f\"no_gh_btn_{login}_{ts()}.png\"))'''

if old_oauth in c:
    c = c.replace(old_oauth, new_oauth)
    print('OAUTH_FIXED')
else:
    print('OAUTH_NOT_FOUND')

# Fix the OAuth consent wait - also handle popup
old_consent = '''        logger.info(f\"[{ts()}] [3/8] Waiting for OAuth consent...\")
        oauth_ok = False
        for _ in range(30):
            await asyncio.sleep(1)
            if \"authorize\" in page.url.lower():
                await asyncio.sleep(2)
                await page.evaluate(\"\"\"() => {
                    const b = document.querySelector('.js-oauth-authorize-btn, #js-oauth-authorize-btn, button[name=\"authorize\"]');
                    if (b) { b.disabled = false; b.click(); }
                }\"\"\")
                await asyncio.sleep(4)
                oauth_ok = True
                logger.info(\"[+] OAuth consent approved\")
                break
            if \"hoplite.sh\" in page.url and \"github.com\" not in page.url:
                oauth_ok = True
                break'''

new_consent = '''        logger.info(f\"[{ts()}] [3/8] Waiting for OAuth consent...\")
        oauth_ok = False
        popup = None

        # Handle popup - listen for new pages
        async def on_popup(p):
            nonlocal popup; popup = p

        page.on(\"popup\", on_popup)

        for _ in range(30):
            await asyncio.sleep(1)

            # Check popup
            if popup:
                try:
                    await popup.wait_for_load_state(\"networkidle\", timeout=10000)
                    p_url = popup.url.lower()
                    if \"authorize\" in p_url or \"github.com/login\" in p_url:
                        auth_btn = popup.locator(\'.js-oauth-authorize-btn, button[name=\"authorize\"], #js-oauth-authorize-btn\')
                        if await auth_btn.count() > 0:
                            await auth_btn.first.click()
                            await asyncio.sleep(3)
                            oauth_ok = True
                            logger.info(\"[+] OAuth consent approved via popup\")
                            break
                except: pass
                continue

            # Check main page
            if \"authorize\" in page.url.lower() or \"github.com/login/oauth\" in page.url:
                await asyncio.sleep(2)
                await page.evaluate(\"\"\"() => {
                    const b = document.querySelector('.js-oauth-authorize-btn, #js-oauth-authorize-btn, button[name=\"authorize\"]');
                    if (b) { b.disabled = false; b.click(); }
                }\"\"\")
                await asyncio.sleep(4)
                oauth_ok = True
                logger.info(\"[+] OAuth consent approved\")
                break
            if \"hoplite.sh\" in page.url and \"github.com\" not in page.url:
                oauth_ok = True
                logger.info(\"[+] Already on Hoplite (OAuth completed)\")
                break'''

if old_consent in c:
    c = c.replace(old_consent, new_consent)
    print('CONSENT_FIXED')
else:
    print('CONSENT_NOT_FOUND')

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('DONE')