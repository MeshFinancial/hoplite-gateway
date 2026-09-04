#!/usr/bin/env python3
"""
ULTIMATE HOPLITE AUTOREG — Stripe + hCaptcha bypass via Anti-Captcha + Pro + API Key.
All fields filled, captcha solved, payment submitted via direct Stripe API.
"""
import asyncio, re, requests, time, pyotp, json, uuid
from pathlib import Path
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

async def fill_stripe(page):
    await page.wait_for_selector("input#cardNumber", timeout=20000)
    await asyncio.sleep(1.5)
    await page.locator("input#cardNumber").fill(CARD_NUM)
    await page.locator("input#cardExpiry").fill(CARD_EXP)
    await page.locator("input#cardCvc").fill(CARD_CVV)
    await page.locator("input#billingName").fill("Violet User")
    await page.locator("input#billingPostalCode").fill(CARD_ZIP)
    cs = page.locator("select#billingCountry")
    if await cs.count() > 0:
        try: await cs.select_option(value="US")
        except: pass

    hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
    for f in page.frames:
        if "hcaptcha" in f.url:
            m = re.search(r"sitekey=([a-zA-Z0-9_-]+)", f.url)
            if m: hsk = m.group(1); break

    token = solve_hcaptcha(hsk, page.url)
    if token:
        print(f"  [+] Captcha solved! Token: {token[:20]}...")
        await page.evaluate(f"""
            const t = '{token}';
            ["h-captcha-response","g-recaptcha-response"].forEach(n => {{
                let el = document.querySelector(`[name="${{n}}"]`);
                if (!el) {{
                    el = document.createElement("textarea");
                    el.name = n; el.style.display = "none";
                    document.body.appendChild(el);
                }}
                el.value = t;
            }});
            // Submit via Stripe confirm API
            setTimeout(() => {{
                const btn = document.querySelector("button[data-testid='hosted-payment-submit-button']");
                if (btn) {{ btn.disabled = false; btn.click(); }}
                document.querySelector("form")?.requestSubmit();
            }}, 1000);
        """)
        return True
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
            await page.fill('input[name="app_otp"]', code); await asyncio.sleep(3)

        # 2. Hoplite login
        print("[2] Hoplite login...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0: btn = page.locator('button:has-text("GitHub")')
        await btn.first.click(); await asyncio.sleep(6)
        for _ in range(15):
            await asyncio.sleep(1)
            if "authorize" in page.url.lower():
                await page.evaluate("() => { const b = document.querySelector('.js-oauth-authorize-btn'); if(b) { b.disabled=false; b.click(); } }")
                await asyncio.sleep(4); break
            if "hoplite.sh" in page.url and "github.com" not in page.url: break

        # 3. Walk to plan
        print("[3] Plan screen...")
        for step in range(10):
            await asyncio.sleep(2)
            txt = await page.inner_text("body")
            if "Set Up Is All Complete" in txt or "starter threads" in txt.lower():
                c = page.locator('button:has-text("Continue")')
                if await c.count() > 0: await c.first.click(); await asyncio.sleep(4); continue
            if "Choose Your Plan" in txt or "Continue with Free" in txt:
                fb = page.locator('button:has-text("Continue with Free")')
                if await fb.count() > 0: await fb.first.click(); await asyncio.sleep(5); break
            sk = page.locator('button:has-text("Skip for now")')
            if await sk.count() > 0: await sk.first.click(); await asyncio.sleep(2); continue
            ct = page.locator('button:has-text("Continue")')
            if await ct.count() > 0: await ct.first.click(); await asyncio.sleep(3); continue
            break

        # 4. Stripe Free plan
        if "stripe.com" in page.url:
            print("[4] Stripe Free plan checkout...")
            await fill_stripe(page)
            print("[5] Waiting up to 60s for redirect...")
            for i in range(60):
                await asyncio.sleep(1)
                if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                    print(f"  ✅ Redirected in {i+1}s!"); break
                if i == 30: print("  Still waiting... Chrome window is visible")
            print(f"  URL: {page.url[:80]}")

        # 5. Pro upgrade
        print("[6] Pro plan upgrade...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        pro = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
        if await pro.count() > 0:
            print(f"  [+] Clicking '{await pro.first.inner_text()}'...")
            await pro.first.click(); await asyncio.sleep(5)
            if "stripe.com" in page.url:
                await fill_stripe(page)
                for i in range(60):
                    await asyncio.sleep(1)
                    if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                        print(f"  ✅ Pro redirect in {i+1}s!"); break

        # 6. API key
        print("[7] API key extraction...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        html = await page.content()
        m = re.search(r'hop_\w{40,}', html)
        if m:
            print(f"🔥🔥🔥 KEY: {m.group(0)}")
            # Save to store
            import requests as req
            r = req.post("http://localhost:8085/api/keys", json={"key": m.group(0), "label": acc["login"]})
            print(f"  Added to gateway pool: {r.status_code}")
        else:
            cb = page.locator('button:has-text("Create")')
            if await cb.count() > 0:
                await cb.first.click(); await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"]')
                if await ni.count() > 0: await ni.first.fill(f"{acc['login']}-key")
                cf = page.locator('button:has-text("Create"):not(:has-text("Repository"))')
                if await cf.count() > 0: await cf.last.click(); await asyncio.sleep(3)
                m2 = re.search(r'hop_\w{40,}', await page.content())
                if m2: print(f"🔥🔥🔥 KEY: {m2.group(0)}")

        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())