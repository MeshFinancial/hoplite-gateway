#!/usr/bin/env python3
"""Minimal Stripe hCaptcha solver test."""
import asyncio, re, requests, time, sys, json, pyotp
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json") as f:
    accounts = json.load(f)
acc = accounts[0]

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "123"
CARD_ZIP = "10001"
ANTI_KEY = "03ea83a89c837abf30695d43a93c0f29"

def solve_hcaptcha(sitekey, pageurl):
    payload = {"clientKey": ANTI_KEY, "task": {"type": "HCaptchaTaskProxyless", "websiteURL": pageurl, "websiteKey": sitekey, "isInvisible": True}}
    r = requests.post("https://api.anti-captcha.com/createTask", json=payload, timeout=10).json()
    tid = r.get("taskId")
    if not tid: return None
    for i in range(25):
        time.sleep(3)
        res = requests.post("https://api.anti-captcha.com/getTaskResult", json={"clientKey": ANTI_KEY, "taskId": tid}, timeout=10).json()
        if res.get("status") == "ready":
            return res.get("solution", {}).get("gRecaptchaResponse")
    return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized", "--no-sandbox"]
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await ctx.new_page()

        # 1. GitHub login
        print("[1] GitHub login...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await page.fill('input[name="login"]', acc['email'])
        await page.fill('input[name="password"]', acc['password'])
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)
        if "two-factor" in page.url.lower():
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"]', code)
            await asyncio.sleep(3)

        # 2. Hoplite login
        print("[2] Hoplite login...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0: btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        await asyncio.sleep(6)

        for _ in range(15):
            await asyncio.sleep(1)
            if "authorize" in page.url.lower():
                await page.evaluate("() => { const b = document.querySelector('.js-oauth-authorize-btn'); if(b) { b.disabled=false; b.click(); } }")
                await asyncio.sleep(4); break
            if "hoplite.sh" in page.url and "github.com" not in page.url: break

        # 3. Walk to plan screen
        print("[3] Walking to plan screen...")
        for step in range(10):
            await asyncio.sleep(2)
            txt = await page.inner_text("body")
            if "Set Up Is All Complete" in txt or "starter threads" in txt.lower():
                await page.locator('button:has-text("Continue")').first.click(); await asyncio.sleep(4); continue
            if "Choose Your Plan" in txt or "Continue with Free" in txt:
                await page.locator('button:has-text("Continue with Free")').first.click(); await asyncio.sleep(5); break
            sk = page.locator('button:has-text("Skip for now")')
            if await sk.count() > 0: await sk.first.click(); await asyncio.sleep(2); continue
            ct = page.locator('button:has-text("Continue")')
            if await ct.count() > 0: await ct.first.click(); await asyncio.sleep(3); continue
            break

        # 4. Stripe Checkout - fill card and solve captcha
        if "stripe.com" in page.url:
            print("[4] Stripe: filling card...")
            await page.wait_for_selector('input#cardNumber', timeout=20000)
            await asyncio.sleep(1)
            # Fill ALL card & address fields
            for sel, val in [
                ('input#cardNumber', CARD_NUM),
                ('input#cardExpiry', CARD_EXP),
                ('input#cardCvc', CARD_CVV),
                ('input#billingName', "Violet User"),
                ('input#billingPostalCode', CARD_ZIP),
                ('input#billingAddressLine1', "123 Main St"),
                ('input#billingAddressCity', "New York"),
                ('input#billingAddressState', "NY"),
            ]:
                el = page.locator(sel)
                if await el.count() > 0:
                    await el.first.fill(val)
                    print(f"  Filled: {sel}")
            # Country dropdown
            cs = page.locator('select#billingCountry, select[name="billingCountry"]')
            if await cs.count() > 0:
                try:
                    await cs.first.select_option(value="US")
                    print("  Country: US")
                except:
                    try:
                        await cs.first.select_option(label="United States")
                        print("  Country: United States")
                    except:
                        print("  [!] No US country option")

            # Find hCaptcha sitekey
            hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
            for f in page.frames:
                if "hcaptcha" in f.url:
                    m = re.search(r'sitekey=([a-zA-Z0-9_-]+)', f.url)
                    if m: hsk = m.group(1); break

            print(f"[5] Solving hCaptcha (sitekey: {hsk[:12]}...)...")
            token = solve_hcaptcha(hsk, page.url)
            if token:
                print(f"[+] Token: {token[:20]}...")

                # Inject via page.evaluate directly
                await page.evaluate(f"""() => {{
                    const token = '{token}';
                    // Set response elements
                    document.querySelectorAll('[name*="captcha"]').forEach(el => {{
                        el.value = token;
                        el.dispatchEvent(new Event('input', {{bubbles:true}}));
                        el.dispatchEvent(new Event('change', {{bubbles:true}}));
                    }});
                    // Try hcaptcha.render callback
                    if (window.hcaptcha) {{
                        try {{
                            window.hcaptcha.setData({{response: token}});
                            window.hcaptcha.execute({{response: token}});
                        }} catch(e) {{}}
                    }}
                    if (window.__hcaptcha__) {{
                        try {{
                            window.__hcaptcha__.setData({{response: token}});
                        }} catch(e) {{}}
                    }}
                    // Post message to frames
                    var frames = document.querySelectorAll('iframe');
                    for (var i = 0; i < frames.length; i++) {{
                        try {{
                            frames[i].contentWindow.postMessage({{
                                source: 'hcaptcha',
                                label: 'challenge-closed',
                                response: token,
                                expiration: 120
                            }}, '*');
                        }} catch(e) {{}}
                    }}
                }}""")

                await asyncio.sleep(2)

                # Click submit and wait
                sub = page.locator('button[data-testid="hosted-payment-submit-button"]')
                print(f"[6] Clicking submit...")
                await sub.first.click()

                print("[7] Waiting for redirect (up to 30s)...")
                for i in range(30):
                    await asyncio.sleep(1)
                    if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                        print(f"🔥 REDIRECTED in {i+1}s!")
                        break
                print(f"Final URL: {page.url[:80]}")

        # 5. Pro upgrade
        print("[8] Pro upgrade...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        pro = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
        if await pro.count() > 0:
            await pro.first.click(); await asyncio.sleep(5)
            if "stripe.com" in page.url:
                await page.locator('input#cardNumber').fill(CARD_NUM)
                await page.locator('input#cardExpiry').fill(CARD_EXP)
                await page.locator('input#cardCvc').fill(CARD_CVV)
                await page.locator('input#billingPostalCode').fill(CARD_ZIP)
                token2 = solve_hcaptcha(hsk, page.url)
                if token2:
                    await page.evaluate(f"() => {{ document.querySelectorAll('[name*=\"captcha\"]').forEach(el => {{ el.value = '{token2}'; el.dispatchEvent(new Event('input',{{bubbles:true}})); }}); }}")
                    await page.locator('button[data-testid="hosted-payment-submit-button"]').first.click()
                    await asyncio.sleep(10)

        # 6. API key
        print("[9] API key...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{{40,}}', html)
        if m: print(f"🔥🔥🔥 KEY: {m.group(0)}")
        else:
            cb = page.locator('button:has-text("Create")')
            if await cb.count() > 0:
                await cb.first.click(); await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"]')
                if await ni.count() > 0: await ni.first.fill("violet-key")
                cf = page.locator('button:has-text("Create"):not(:has-text("Repository"))')
                if await cf.count() > 0: await cf.last.click(); await asyncio.sleep(3)
                m2 = re.search(r'hop_[a-zA-Z0-9_-]{{40,}}', await page.content())
                if m2: print(f"🔥🔥🔥 KEY: {m2.group(0)}")

        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())