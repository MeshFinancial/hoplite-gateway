#!/usr/bin/env python3
"""
Complete Stripe payment using Anti-Captcha solver, then Pro upgrade, then API key extraction.
"""
import asyncio, json, pyotp, re, sys, requests, time
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
acc = accounts[0] # Violetpivary

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

ANTI_KEY = "03ea83a89c837abf30695d43a93c0f29"

def solve_hcaptcha(sitekey, pageurl):
    print(f"[*] Solving hCaptcha via Anti-Captcha (sitekey: {sitekey[:12]}...)...")
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
    task_id = r.get("taskId")
    if not task_id:
        print("[-] Anti-Captcha createTask error:", r)
        return None
        
    for i in range(25):
        time.sleep(3)
        res = requests.post("https://api.anti-captcha.com/getTaskResult", json={"clientKey": ANTI_KEY, "taskId": task_id}, timeout=10).json()
        if res.get("status") == "ready":
            token = res.get("solution", {}).get("gRecaptchaResponse")
            print(f"[+] hCaptcha SOLVED in {(i+1)*3}s! Token: {token[:20]}...")
            return token
    return None

async def complete_stripe_checkout(page):
    print("[*] Waiting for Stripe form...")
    await page.wait_for_selector('input#cardNumber', timeout=20000)
    await asyncio.sleep(1)

    # 1. Fill card details
    print("[+] Entering card details...")
    await page.locator('input#cardNumber').fill(CARD_NUM)
    await page.locator('input#cardExpiry').fill(CARD_EXP)
    await page.locator('input#cardCvc').fill(CARD_CVV)

    name_i = page.locator('input#billingName')
    if await name_i.count() > 0:
        await name_i.fill(f"{acc['login']} User")

    c_sel = page.locator('select#billingCountry')
    if await c_sel.count() > 0:
        try: await c_sel.select_option(value="US")
        except: pass

    z_inp = page.locator('input#billingPostalCode')
    if await z_inp.count() > 0:
        await z_inp.fill(CARD_ZIP)

    # 2. Check for hCaptcha on page/frames
    hcap_sitekey = None
    for f in page.frames:
        if "hcaptcha.com" in f.url or "hcaptcha" in f.url:
            m = re.search(r'sitekey=([a-zA-Z0-9_-]+)', f.url)
            if m:
                hcap_sitekey = m.group(1)
                print(f"[+] Found hCaptcha sitekey: {hcap_sitekey}")
                break

    if not hcap_sitekey:
        hcap_sitekey = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"

    # Solve hCaptcha in parallel or before submit
    token = solve_hcaptcha(hcap_sitekey, page.url)

    if token:
        print("[+] Injecting hCaptcha response token into Stripe...")
        await page.evaluate(f"""() => {{
            // Set textareas/inputs
            const names = ['h-captcha-response', 'g-recaptcha-response'];
            names.forEach(n => {{
                let el = document.querySelector(`[name="${{n}}"]`);
                if (!el) {{
                    el = document.createElement('textarea');
                    el.name = n;
                    el.style.display = 'none';
                    document.body.appendChild(el);
                }}
                el.value = "{token}";
            }});

            // Trigger hcaptcha callback if available
            if (window.hcaptcha && typeof window.hcaptcha.execute === 'function') {{
                try {{ window.hcaptcha.setData({{ response: "{token}" }}); }} catch(e) {{}}
            }}
        }}""")

    # 3. Click Submit
    submit_btn = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"]')
    print(f"[+] Clicking Submit: '{await submit_btn.first.inner_text()}'...")
    await submit_btn.first.click()

    # 4. Wait for redirect back to Hoplite
    print("[*] Waiting for payment confirmation and redirect to Hoplite...")
    for i in range(35):
        await asyncio.sleep(1)
        if "hoplite.sh" in page.url and "stripe.com" not in page.url:
            print(f"[🔥🔥🔥] SUCCESS! Redirected back to Hoplite in {i+1}s: {page.url}")
            return True

    print("URL after 35s:", page.url)
    return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await ctx.new_page()

        # Login GitHub
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

        # Open Hoplite
        print("[2] Opening Hoplite...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        await asyncio.sleep(5)

        # Starter Threads Continue if shown
        for _ in range(5):
            c = page.locator('button:has-text("Continue")')
            if await c.count() > 0:
                print("[+] Clicking Continue on starter threads...")
                await c.first.click()
                await asyncio.sleep(4)
                break
            await asyncio.sleep(1)

        # Click Continue with Free
        print("[3] Clicking Continue with Free...")
        free_btn = page.locator('button:has-text("Continue with Free")')
        if await free_btn.count() > 0:
            await free_btn.first.click()
            await asyncio.sleep(5)

        # Complete Stripe Checkout
        if "stripe.com" in page.url:
            ok = await complete_stripe_checkout(page)
            print(f"Stripe checkout result: {ok}")

        # Post-checkout: Pro upgrade if available
        if "hoplite.sh" in page.url:
            print("\n[4] Checking Pro plan upgrade on Hoplite...")
            await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(4)
            pro_b = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
            if await pro_b.count() > 0:
                print("[+] Upgrading to Pro...")
                await pro_b.first.click()
                await asyncio.sleep(5)
                if "stripe.com" in page.url:
                    await complete_stripe_checkout(page)

            # Extract cookies and API key
            print("\n[5] Extracting cookies and API key...")
            cookies = await ctx.cookies()
            hop_cookies = {c["name"]: c["value"] for c in cookies if "hoplite" in c["domain"]}
            print(f"Extracted {len(hop_cookies)} Hoplite cookies!")

            # Go to API keys
            await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(4)
            html = await page.content()
            m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
            if m:
                print(f"🔥🔥🔥 [SUCCESS] KEY: {m.group(0)} 🔥🔥🔥")
            else:
                cb = page.locator('button:has-text("Create"), button:has-text("New")')
                if await cb.count() > 0:
                    await cb.first.click()
                    await asyncio.sleep(2)
                    ni = page.locator('input[placeholder*="name"]')
                    if await ni.count() > 0:
                        await ni.first.fill(f"{acc['login']}-key")
                    conf = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm")')
                    if await conf.count() > 0:
                        await conf.last.click()
                        await asyncio.sleep(3)
                    m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                    if m2:
                        print(f"🔥🔥🔥 [SUCCESS] GENERATED KEY: {m2.group(0)} 🔥🔥🔥")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
