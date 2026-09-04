#!/usr/bin/env python3
"""Automate Stripe Checkout: Enter Card -> Submit -> Redirect to Hoplite -> Extract API Key."""
import asyncio, json, pyotp, re, sys
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
acc = accounts[0] # Violetpivary

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

async def fill_stripe_card(page):
    print("[*] On Stripe Checkout page. Waiting for inputs...")
    # Stripe Checkout might be in page or in an iframe
    await asyncio.sleep(4)
    card_found = False

    # Check top-level page first
    num_sel = 'input#cardNumber, input[name="cardNumber"], input[placeholder*="Card number"]'
    if await page.locator(num_sel).count() > 0:
        print("[+] Filling card number on Stripe page...")
        await page.locator(num_sel).first.fill(CARD_NUM)
        await asyncio.sleep(0.5)
        card_found = True

        exp_sel = 'input#cardExpiry, input[name="cardExpiry"], input[placeholder*="MM / YY"]'
        if await page.locator(exp_sel).count() > 0:
            print("[+] Filling expiry...")
            await page.locator(exp_sel).first.fill(CARD_EXP)
            await asyncio.sleep(0.5)

        cvc_sel = 'input#cardCvc, input[name="cardCvc"], input[placeholder*="CVC"]'
        if await page.locator(cvc_sel).count() > 0:
            print("[+] Filling CVC...")
            await page.locator(cvc_sel).first.fill(CARD_CVV)
            await asyncio.sleep(0.5)

        name_sel = 'input#billingName, input[name="billingName"]'
        if await page.locator(name_sel).count() > 0:
            print("[+] Filling name...")
            await page.locator(name_sel).first.fill(f"{acc['login']} User")
            await asyncio.sleep(0.5)

        zip_sel = 'input#billingPostalCode, input[name="billingPostalCode"]'
        if await page.locator(zip_sel).count() > 0:
            print("[+] Filling ZIP...")
            await page.locator(zip_sel).first.fill(CARD_ZIP)
            await asyncio.sleep(0.5)

    # Check frames if not found on top page
    if not card_found:
        print("[*] Checking iframes for Stripe...")
        for f in page.frames:
            if await f.locator(num_sel).count() > 0:
                print(f"[+] Found card number in frame: {f.url[:50]}")
                await f.locator(num_sel).first.fill(CARD_NUM)
                await asyncio.sleep(0.5)
                exp = f.locator('input#cardExpiry, input[name="cardExpiry"]')
                if await exp.count() > 0:
                    await exp.first.fill(CARD_EXP)
                cvc = f.locator('input#cardCvc, input[name="cardCvc"]')
                if await cvc.count() > 0:
                    await cvc.first.fill(CARD_CVV)
                card_found = True
                break

    # Click submit button
    print("[*] Looking for submit button on Stripe Checkout...")
    submit_btn = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"], button:has-text("Subscribe"), button:has-text("Start trial"), button:has-text("Pay"), button:has-text("Save card")')
    if await submit_btn.count() > 0:
        print(f"[+] Clicking submit button: '{await submit_btn.first.inner_text()}'...")
        await submit_btn.first.click()
        print("[+] Submitted payment! Waiting for redirect...")
        await asyncio.sleep(8)
        return True
    else:
        print("[-] Submit button not found on Stripe page.")
    return card_found

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

        # 1. Login GitHub
        print("[1] GitHub login...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await page.fill('input[name="login"]', acc['email'])
        await page.fill('input[name="password"]', acc['password'])
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)

        if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"], input[id="otp"]', code)
            for _ in range(8):
                await asyncio.sleep(1)
                if "two-factor" not in page.url.lower():
                    break
        print(f"[+] GitHub logged in: {page.url}")

        # 2. Open Hoplite
        print("[2] Opening Hoplite...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        print("[+] Clicked Continue with GitHub...")

        # Authorize if needed
        for _ in range(15):
            await asyncio.sleep(1)
            if "authorize" in page.url.lower():
                await asyncio.sleep(2)
                await page.evaluate("() => { const b = document.querySelector('.js-oauth-authorize-btn, #js-oauth-authorize-btn'); if(b) { b.disabled=false; b.click(); } }")
                await asyncio.sleep(4)
                break
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break
        await asyncio.sleep(3)

        # Starter Threads Continue
        for _ in range(10):
            await asyncio.sleep(1)
            c = page.locator('button:has-text("Continue")')
            if await c.count() > 0:
                print("[+] Clicking Continue on starter threads...")
                await c.first.click()
                await asyncio.sleep(4)
                break

        print(f"[3] Landed on Plan screen: {page.url}")

        # 3. Click "Continue with Free"
        print("[4] Clicking 'Continue with Free'...")
        free_btn = page.locator('button:has-text("Continue with Free")')
        if await free_btn.count() > 0:
            await free_btn.first.click()
            print("[+] Clicked 'Continue with Free'!")
            await asyncio.sleep(5)

        print(f"[5] Landed URL after click: {page.url}")

        # 4. Fill Stripe Checkout
        if "stripe.com" in page.url:
            print("[6] On Stripe Checkout! Filling card...")
            await fill_stripe_card(page)

            # Wait for redirect back to Hoplite
            print("[*] Waiting for redirect back to Hoplite after payment...")
            for _ in range(30):
                await asyncio.sleep(1)
                if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                    print(f"[+] Returned to Hoplite: {page.url}")
                    break
            await asyncio.sleep(4)

        print(f"[7] Current URL on Hoplite: {page.url}")
        hoplite_text = await page.inner_text("body")
        print("\n=== PAGE TEXT AFTER PAYMENT ===")
        print(hoplite_text[:800])

        # 5. Navigate to settings/api-keys
        print("\n[8] Navigating to API keys...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"[+] API keys URL: {page.url}")

        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
        if m:
            print(f"\n🔥🔥🔥 [SUCCESS] EXTRACTED KEY: {m.group(0)} 🔥🔥🔥")
        else:
            print("[+] Checking Create button on API keys...")
            cb = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Generate")')
            if await cb.count() > 0:
                print(f"[+] Clicking: '{await cb.first.inner_text()}'...")
                await cb.first.click()
                await asyncio.sleep(2)

                ni = page.locator('input[placeholder*="name"], input[placeholder*="Name"]')
                if await ni.count() > 0:
                    await ni.first.fill(f"{acc['login']}-key")
                    await asyncio.sleep(1)

                conf = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm"), button:has-text("Save")')
                if await conf.count() > 0:
                    await conf.last.click()
                    await asyncio.sleep(3)

                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                if m2:
                    print(f"\n🔥🔥🔥 [SUCCESS] GENERATED KEY: {m2.group(0)} 🔥🔥🔥")
                else:
                    k_body = await page.inner_text("body")
                    print("Page body after create:\n", k_body[:600])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
