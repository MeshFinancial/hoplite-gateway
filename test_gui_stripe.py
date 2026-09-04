#!/usr/bin/env python3
"""Run real Chrome with GUI (headless=False) to pass Stripe hCaptcha and complete checkout."""
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
        # Launch real Chrome with GUI (NOT headless)
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--start-maximized"
            ]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await ctx.new_page()

        # Login GitHub
        print("[1] Logging in to GitHub...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await page.fill('input[name="login"]', acc['email'])
        await page.fill('input[name="password"]', acc['password'])
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)

        if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
            print("[+] Entering TOTP...")
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"], input[id="otp"]', code)
            for _ in range(8):
                await asyncio.sleep(1)
                if "two-factor" not in page.url.lower():
                    break

        # Open Hoplite
        print("[2] Opening Hoplite...")
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
            print("[+] Clicking Continue on starter threads...")
            await c.first.click()
            await asyncio.sleep(4)

        # Click Continue with Free
        print("[3] Clicking Continue with Free...")
        free_btn = page.locator('button:has-text("Continue with Free")')
        if await free_btn.count() > 0:
            await free_btn.first.click()
            await asyncio.sleep(5)

        # Fill Stripe Checkout
        if "stripe.com" in page.url:
            print("[4] On Stripe Checkout! Filling card...")
            await page.wait_for_selector('input#cardNumber', timeout=15000)
            await asyncio.sleep(1)
            
            # Type naturally with slight delays
            await page.locator('input#cardNumber').type(CARD_NUM, delay=30)
            await asyncio.sleep(0.5)
            await page.locator('input#cardExpiry').type(CARD_EXP, delay=30)
            await asyncio.sleep(0.5)
            await page.locator('input#cardCvc').type(CARD_CVV, delay=30)
            await asyncio.sleep(0.5)

            name_inp = page.locator('input#billingName')
            if await name_inp.count() > 0:
                await name_inp.fill(f"{acc['login']} User")
                await asyncio.sleep(0.5)

            c_sel = page.locator('select#billingCountry')
            if await c_sel.count() > 0:
                try: await c_sel.select_option(value="US")
                except: pass
                await asyncio.sleep(0.5)

            zip_inp = page.locator('input#billingPostalCode')
            if await zip_inp.count() > 0:
                await zip_inp.type(CARD_ZIP, delay=30)
                await asyncio.sleep(0.5)

            sub = page.locator('button[data-testid="hosted-payment-submit-button"]')
            print(f"[+] Clicking submit button: '{await sub.inner_text()}'...")
            await sub.click()

            print("[*] Waiting for payment confirmation and redirect to Hoplite...")
            for i in range(25):
                await asyncio.sleep(1)
                if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                    print(f"[+] Redirected to Hoplite at {i+1}s: {page.url}")
                    break

        await asyncio.sleep(4)
        print(f"[5] Landed on: {page.url}")

        # Check for API keys
        print("[6] Going to settings/api-keys...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"[+] API keys page: {page.url}")

        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
        if m:
            print(f"\n🔥🔥🔥 [SUCCESS] EXTRACTED KEY: {m.group(0)} 🔥🔥🔥")
        else:
            cb = page.locator('button:has-text("Create"), button:has-text("New")')
            if await cb.count() > 0:
                print("[+] Clicking Create API key button...")
                await cb.first.click()
                await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"], input[placeholder*="Name"]')
                if await ni.count() > 0:
                    await ni.first.fill(f"{acc['login']}-key")
                conf = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm"), button:has-text("Save")')
                if await conf.count() > 0:
                    await conf.last.click()
                    await asyncio.sleep(3)
                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                if m2:
                    print(f"\n🔥🔥🔥 [SUCCESS] GENERATED KEY: {m2.group(0)} 🔥🔥🔥")
                else:
                    k_text = await page.inner_text("body")
                    print("Body after create:\n", k_text[:600])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
