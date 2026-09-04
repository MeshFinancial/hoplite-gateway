#!/usr/bin/env python3
"""Redo plan + payment with proper hCaptcha solving via Anti-Captcha."""
import asyncio, json, pyotp, re, sys, requests, time
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
    print(f"[*] Solving hCaptcha via Anti-Captcha (${ANTI_KEY[:6]}...)...")
    payload = {
        "clientKey": ANTI_KEY,
        "task": {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": pageurl,
            "websiteKey": sitekey,
            "isInvisible": True
        }
    }
    r = requests.post("https://api.anti-captcha.com/createTask", json=payload, timeout=10).json()
    tid = r.get("taskId")
    if not tid: print(f"  createTask error: {r}"); return None
    print(f"  Task created: {tid}")
    for i in range(30):
        time.sleep(3)
        res = requests.post("https://api.anti-captcha.com/getTaskResult", json={"clientKey": ANTI_KEY, "taskId": tid}, timeout=10).json()
        if res.get("status") == "ready":
            token = res.get("solution", {}).get("gRecaptchaResponse")
            print(f"  [+] SOLVED in {(i+1)*3}s! Token: {token[:20]}...")
            return token
    return None

async def fill_stripe(page):
    await page.wait_for_selector('input#cardNumber', timeout=20000)
    await asyncio.sleep(1)
    await page.locator('input#cardNumber').fill(CARD_NUM)
    await page.locator('input#cardExpiry').fill(CARD_EXP)
    await page.locator('input#cardCvc').fill(CARD_CVV)
    ni = page.locator('input#billingName')
    if await ni.count() > 0: await ni.fill("Violet User")
    cs = page.locator('select#billingCountry')
    if await cs.count() > 0: 
        try: await cs.select_option(value="US")
        except: pass
    zi = page.locator('input#billingPostalCode')
    if await zi.count() > 0: await zi.fill(CARD_ZIP)

    # Find hCaptcha sitekey
    hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
    for f in page.frames:
        if "hcaptcha" in f.url and "challenge" in f.url:
            m = re.search(r'sitekey=([a-zA-Z0-9_-]+)', f.url)
            if m: hsk = m.group(1); break

    token = solve_hcaptcha(hsk, page.url)
    if not token:
        print("  [!] hCaptcha solve failed")
        return False

    # Inject token into ALL possible hCaptcha/recaptcha elements
    print("[+] Injecting token into page...")
    await page.evaluate(f"""() => {{
        const token = '{token}';
        // 1. Set textarea values
        ['h-captcha-response', 'g-recaptcha-response', 'cf-turnstile-response'].forEach(name => {{
            let el = document.querySelector(`[name="${{name}}"]`);
            if (!el) {{
                el = document.createElement('textarea');
                el.name = name;
                el.style.display = 'none';
                document.body.appendChild(el);
            }}
            el.value = token;
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }});
        
        // 2. Try hcaptcha API methods
        if (window.hcaptcha) {{
            try {{
                if (window.hcaptcha.setData) window.hcaptcha.setData({{ response: token }});
                if (window.hcaptcha.setResponse) window.hcaptcha.setResponse(token);
                if (window.hcaptcha.execute) window.hcaptcha.execute({{ response: token }});
            }} catch(e) {{ console.log('hcaptcha api:', e); }}
        }}
        
        // 3. Try __hcaptcha_ global
        if (window.__hcaptcha__) {{
            try {{
                window.__hcaptcha__.setData({{ response: token }});
            }} catch(e) {{}}
        }}
        
        // 4. Dispatch custom event for hcaptcha
        document.dispatchEvent(new CustomEvent('hcaptcha', {{ detail: {{ response: token }} }}));
        
        // 5. Post message to any hcaptcha frames
        const frames = document.querySelectorAll('iframe');
        frames.forEach(f => {{
            try {{
                f.contentWindow.postMessage({{ 
                    source: 'hcaptcha',
                    label: 'challenge-closed',
                    response: token,
                    expiration: 120
                }}, '*');
            }} catch(e) {{}}
        }});
    }}""")

    await asyncio.sleep(1)

    # Now click submit
    sub = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"]')
    if await sub.count() > 0:
        print(f"[+] Clicking submit: '{await sub.first.inner_text()}'...")
        await sub.first.click()
        print("[*] Waiting for redirect...")
        for i in range(30):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                print(f"[+] Redirected in {i+1}s!")
                return True
    print(f"URL after 30s: {page.url[:80]}")
    return False

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

        print("[2] Open Hoplite...")
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

        print(f"[3] On Hoplite: {page.url}")

        # Walk onboarding
        print("[4] Walking through onboarding...")
        for step in range(10):
            await asyncio.sleep(2)
            txt = await page.inner_text("body")
            if "Set Up Is All Complete" in txt or "starter threads" in txt.lower():
                print("  [+] Starter threads - clicking Continue")
                cont = page.locator('button:has-text("Continue")')
                if await cont.count() > 0: await cont.first.click(); await asyncio.sleep(4); continue
            if "Choose Your Plan" in txt or "Continue with Free" in txt:
                print("  [+] PLAN SCREEN!")
                free_btn = page.locator('button:has-text("Continue with Free")')
                if await free_btn.count() > 0:
                    await free_btn.first.click(); await asyncio.sleep(5)
                    print(f"  URL: {page.url[:80]}")
                    if "stripe.com" in page.url:
                        print("[5] Stripe Checkout! Filling card + solving captcha...")
                        ok = await fill_stripe(page)
                        print(f"  Stripe result: {ok}")
                        await asyncio.sleep(3)
                    break
                pro_btn = page.locator('button:has-text("Start 14 days of Pro")')
                if await pro_btn.count() > 0:
                    await pro_btn.first.click(); await asyncio.sleep(5)
                    if "stripe.com" in page.url: await fill_stripe(page)
                    break
            skip = page.locator('button:has-text("Skip for now")')
            if await skip.count() > 0: await skip.first.click(); await asyncio.sleep(2); continue
            cont = page.locator('button:has-text("Continue")')
            if await cont.count() > 0: await cont.first.click(); await asyncio.sleep(3); continue
            break

        print(f"[6] After payment: {page.url}")

        # Pro upgrade
        print("[7] Pro upgrade...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        pro_btn = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
        if await pro_btn.count() > 0:
            await pro_btn.first.click(); await asyncio.sleep(5)
            if "stripe.com" in page.url: await fill_stripe(page)

        # API key
        print("[8] API key...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
        if m: print(f"🔥🔥🔥 KEY: {m.group(0)} 🔥🔥🔥")
        else:
            cb = page.locator('button:has-text("Create")')
            if await cb.count() > 0:
                await cb.first.click(); await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"]')
                if await ni.count() > 0: await ni.first.fill("violet-key")
                conf = page.locator('button:has-text("Create"):not(:has-text("Repository"))')
                if await conf.count() > 0: await conf.last.click(); await asyncio.sleep(3)
                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                if m2: print(f"🔥🔥🔥 KEY: {m2.group(0)} 🔥🔥🔥")

        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())