#!/usr/bin/env python3
"""Investigate Stripe Checkout network responses on card submission."""
import asyncio, json, pyotp, sys
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
        page = await ctx.new_page()

        # Capture network responses on Stripe
        async def on_response(resp):
            if "stripe.com" in resp.url and resp.request.method in ["POST", "PUT"]:
                try:
                    text = await resp.text()
                    print(f"\n[STRIPE RESPONSE] {resp.request.method} {resp.url[:80]} -> {resp.status}")
                    print(f"Body: {text[:600]}")
                except Exception:
                    pass

        page.on("response", on_response)

        # Login GitHub
        print("[1] GitHub login...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
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
                print("[+] Clicking Continue...")
                await c.first.click()
                await asyncio.sleep(3)
                break
            await asyncio.sleep(1)

        # Click Continue with Free
        print("[3] Clicking Continue with Free...")
        free_btn = page.locator('button:has-text("Continue with Free")')
        if await free_btn.count() > 0:
            await free_btn.first.click()
            await asyncio.sleep(5)

        print(f"[4] URL: {page.url[:80]}")

        if "stripe.com" in page.url:
            print("[5] On Stripe Checkout. Filling form...")
            await page.wait_for_selector('input#cardNumber', timeout=20000)
            await asyncio.sleep(1)
            await page.locator('input#cardNumber').fill(CARD_NUM)
            await page.locator('input#cardExpiry').fill(CARD_EXP)
            await page.locator('input#cardCvc').fill(CARD_CVV)

            name_i = page.locator('input#billingName')
            if await name_i.count() > 0:
                await name_i.fill("Violet User")

            c_sel = page.locator('select#billingCountry')
            if await c_sel.count() > 0:
                try: await c_sel.select_option(value="US")
                except: pass

            z_inp = page.locator('input#billingPostalCode')
            if await z_inp.count() > 0:
                await z_inp.fill(CARD_ZIP)

            submit_btn = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"]')
            print(f"[6] Clicking submit: '{await submit_btn.first.inner_text()}'...")
            await submit_btn.first.click()

            print("[7] Waiting 15s for network requests...")
            await asyncio.sleep(15)

            # Check if any error text appeared on page
            err_els = await page.locator('[role="alert"], .FieldError, .Alert, p[class*="Error"]').all_inner_texts()
            print("\nErrors visible on Stripe page:")
            for e in err_els:
                if e.strip():
                    print("  ->", e.strip().replace("\n", " -- "))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
