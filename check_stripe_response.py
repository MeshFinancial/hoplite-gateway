#!/usr/bin/env python3
"""Capture exact Stripe Checkout error/status after submit."""
import asyncio, json, pyotp, re, sys
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
acc = accounts[0] # Violetpivary

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
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

        if "two-factor" in page.url.lower():
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"]', code)
            for _ in range(8):
                await asyncio.sleep(1)
                if "two-factor" not in page.url.lower():
                    break

        # 2. Open Hoplite & authorize
        print("[2] Opening Hoplite...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        await asyncio.sleep(5)

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

        # Click Continue with Free
        print("[3] Clicking Continue with Free...")
        free_btn = page.locator('button:has-text("Continue with Free")')
        if await free_btn.count() > 0:
            await free_btn.first.click()
            await asyncio.sleep(5)

        print(f"[4] Landed on Stripe: {page.url[:80]}...")

        # Fill card
        if "stripe.com" in page.url:
            await page.wait_for_selector('input#cardNumber', timeout=15000)
            await asyncio.sleep(1)
            await page.locator('input#cardNumber').fill(CARD_NUM)
            await page.locator('input#cardExpiry').fill(CARD_EXP)
            await page.locator('input#cardCvc').fill(CARD_CVV)
            
            n_inp = page.locator('input#billingName')
            if await n_inp.count() > 0:
                await n_inp.fill("John Doe")

            c_sel = page.locator('select#billingCountry')
            if await c_sel.count() > 0:
                try: await c_sel.select_option(value="US")
                except: pass

            z_inp = page.locator('input#billingPostalCode')
            if await z_inp.count() > 0:
                await z_inp.fill(CARD_ZIP)

            submit_btn = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"]')
            print("[+] Submitting payment on Stripe...")
            await submit_btn.first.click()

            # Wait 6 seconds and inspect errors
            await asyncio.sleep(6)
            
            # Extract any visible alert or error text
            alerts = await page.locator('.Alert, .FieldError, [role="alert"], [class*="error"], [class*="Alert"]').all_inner_texts()
            print("\n=== STRIPE ALERTS / ERRORS ===")
            for a in alerts:
                if a.strip():
                    print("  ALERT:", a.strip().replace("\n", " -- "))

            # Check button text/state
            btn_state = await submit_btn.first.inner_text()
            print(f"Submit button text now: '{btn_state.replace(chr(10), ' ')}'")

            # Check if 3DS iframe exists
            for f in page.frames:
                if any(k in f.url for k in ["3d_secure", "challenge", "hcaptcha"]):
                    print(f"  Frame found: {f.url[:80]}")

            # Extract cookies for hoplite
            cookies = await ctx.cookies()
            print(f"\nTotal cookies in browser: {len(cookies)}")
            hop_cookies = [c for c in cookies if "hoplite" in c["domain"]]
            print(f"Hoplite cookies ({len(hop_cookies)}):")
            for c in hop_cookies:
                print(f"  {c['name']} = {c['value'][:25]}... (domain: {c['domain']})")

            # Save screenshot
            await page.screenshot(path=r"C:\Users\User\tmp\hoplite-gateway\data\stripe_result.png")
            print("\nScreenshot saved to data/stripe_result.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
