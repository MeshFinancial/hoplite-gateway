#!/usr/bin/env python3
"""Inspect Stripe Checkout state after submit."""
import asyncio, json, pyotp, re, sys
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
acc = accounts[0]

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
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await ctx.new_page()

        # Login GitHub
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
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        await asyncio.sleep(5)

        # Starter Threads Continue
        c = page.locator('button:has-text("Continue")')
        if await c.count() > 0:
            await c.first.click()
            await asyncio.sleep(4)

        # Click Continue with Free
        free_btn = page.locator('button:has-text("Continue with Free")')
        if await free_btn.count() > 0:
            await free_btn.first.click()
            await asyncio.sleep(5)

        # On Stripe
        if "stripe.com" in page.url:
            await page.wait_for_selector('input#cardNumber', timeout=15000)
            await page.locator('input#cardNumber').fill(CARD_NUM)
            await page.locator('input#cardExpiry').fill(CARD_EXP)
            await page.locator('input#cardCvc').fill(CARD_CVV)
            
            n_inp = page.locator('input#billingName')
            if await n_inp.count() > 0:
                await n_inp.fill(f"{acc['login']} User")
                
            c_sel = page.locator('select#billingCountry')
            if await c_sel.count() > 0:
                try: await c_sel.select_option(value="US")
                except: pass
                
            z_inp = page.locator('input#billingPostalCode')
            if await z_inp.count() > 0:
                await z_inp.fill(CARD_ZIP)

            # Click submit
            sub = page.locator('button[data-testid="hosted-payment-submit-button"]')
            print("[+] Submitting payment...")
            await sub.click()
            
            # Wait 8s and capture full page text and screenshot
            await asyncio.sleep(8)
            print(f"[+] URL 8s after submit: {page.url}")
            
            text = await page.inner_text("body")
            print("\n=== STRIPE BODY TEXT AFTER SUBMIT ===")
            print(text[:1500])

            # Check if 3DS iframe exists
            for f in page.frames:
                if any(k in f.url for k in ["three_d_secure", "3ds", "challenge"]):
                    print(f"  3DS Frame: {f.url}")
                    
            await page.screenshot(path=r"C:\Users\User\tmp\hoplite-gateway\data\stripe_submit.png")
            print("Screenshot saved to data/stripe_submit.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
