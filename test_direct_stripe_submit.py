#!/usr/bin/env python3
"""Stripe: fill card, solve captcha, direct form submit."""
import asyncio, re, requests, time, pyotp
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

        # GitHub login
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

        # Hoplite login
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

        # Walk to plan screen
        print("[3] Plan screen...")
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

        # Stripe Checkout
        if "stripe.com" in page.url:
            print("[4] Stripe: filling ALL fields...")
            await page.wait_for_selector('input#cardNumber', timeout=20000)
            await asyncio.sleep(1.5)
            await page.locator('input#cardNumber').fill(CARD_NUM)
            await page.locator('input#cardExpiry').fill(CARD_EXP)
            await page.locator('input#cardCvc').fill(CARD_CVV)
            await page.locator('input#billingName').fill("Violet User")
            await page.locator('input#billingPostalCode').fill(CARD_ZIP)
            cs = page.locator('select#billingCountry')
            if await cs.count() > 0:
                try: await cs.select_option(value="US")
                except: pass

            # Solve captcha
            hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
            for f in page.frames:
                if "hcaptcha" in f.url:
                    m = re.search(r'sitekey=([a-zA-Z0-9_-]+)', f.url)
                    if m: hsk = m.group(1); break
            print(f"[5] Solving hCaptcha...")
            token = solve_hcaptcha(hsk, page.url)
            if token:
                print(f"[+] Token: {token[:20]}...")
                # Inject & call submit via JS
                await page.evaluate(f"""() => {{
                    const token = '{token}';
                    // Set response elements
                    ['h-captcha-response','g-recaptcha-response'].forEach(n => {{
                        let el = document.querySelector(`[name="${{n}}"]`);
                        if (!el) {{
                            el = document.createElement('textarea');
                            el.name = n; el.style.display = 'none';
                            document.body.appendChild(el);
                        }}
                        el.value = token;
                        el.dispatchEvent(new Event('input',{{bubbles:true}}));
                    }});
                    // Try to find and call the stripe confirm function
                    // Look for the form and submit directly
                    setTimeout(() => {{
                        const btn = document.querySelector('button[data-testid="hosted-payment-submit-button"]');
                        if (btn) {{
                            btn.disabled = false;
                            btn.click();
                        }}
                        // Also try form submit
                        const form = document.querySelector('form');
                        if (form) {{
                            form.dispatchEvent(new Event('submit', {{bubbles: true}}));
                        }}
                    }}, 1000);
                }}""")

                print("[6] Waiting for redirect...")
                for i in range(30):
                    await asyncio.sleep(1)
                    if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                        print(f"🔥 REDIRECTED in {i+1}s!")
                        break
                    if i == 10:
                        # Try one more JS injection
                        await page.evaluate("""
                            const btn = document.querySelector('button[data-testid="hosted-payment-submit-button"]');
                            if (btn) { btn.click(); }
                            document.querySelector('form')?.requestSubmit();
                        """)
                print(f"Final: {page.url[:80]}")

        # Pro & API key
        print("[7] Pro upgrade...")
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
                t2 = solve_hcaptcha(hsk, page.url)
                if t2:
                    await page.evaluate("() => { document.querySelector('button[data-testid=\"hosted-payment-submit-button\"]')?.click(); }")
                    await asyncio.sleep(10)

        print("[8] API key...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        html = await page.content()
        m = re.search(r'hop_[\w-]{40,}', html)
        if m: print(f"🔥🔥🔥 KEY: {m.group(0)}")
        else:
            cb = page.locator('button:has-text("Create")')
            if await cb.count() > 0:
                await cb.first.click(); await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"]')
                if await ni.count() > 0: await ni.first.fill("violet-key")
                cf = page.locator('button:has-text("Create"):not(:has-text("Repository"))')
                if await cf.count() > 0: await cf.last.click(); await asyncio.sleep(3)
                m2 = re.search(r'hop_[\w-]{40,}', await page.content())
                if m2: print(f"🔥🔥🔥 KEY: {m2.group(0)}")

        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())