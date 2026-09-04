#!/usr/bin/env python3
"""Inspect Stripe Checkout form fields, errors, and country dropdown."""
import asyncio, json, pyotp, re, sys
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
acc = accounts[0]

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

async def fill_stripe_checkout(page):
    print("[*] On Stripe Checkout. Waiting for form...")
    await page.wait_for_selector('input#cardNumber, input[name="cardNumber"]', timeout=20000)
    await asyncio.sleep(2)

    # 1. Fill card number
    print("[+] Filling card number...")
    await page.locator('input#cardNumber, input[name="cardNumber"]').first.fill(CARD_NUM)
    await asyncio.sleep(1)

    # 2. Fill expiry
    print("[+] Filling expiry...")
    await page.locator('input#cardExpiry, input[name="cardExpiry"]').first.fill(CARD_EXP)
    await asyncio.sleep(0.5)

    # 3. Fill CVC
    print("[+] Filling CVC...")
    await page.locator('input#cardCvc, input[name="cardCvc"]').first.fill(CARD_CVV)
    await asyncio.sleep(0.5)

    # 4. Fill Name
    name_inp = page.locator('input#billingName, input[name="billingName"]')
    if await name_inp.count() > 0:
        print("[+] Filling name...")
        await name_inp.first.fill(f"{acc['login']} User")
        await asyncio.sleep(0.5)

    # 5. Check Country dropdown
    country_sel = page.locator('select#billingCountry, select[name="billingCountry"]')
    if await country_sel.count() > 0:
        print("[+] Selecting Country: US...")
        try:
            await country_sel.first.select_option(value="US")
        except:
            try:
                await country_sel.first.select_option(label="Соединенные Штаты")
            except:
                pass
        await asyncio.sleep(1)

    # 6. Fill ZIP
    zip_inp = page.locator('input#billingPostalCode, input[name="billingPostalCode"]')
    if await zip_inp.count() > 0:
        print("[+] Filling ZIP: 10001...")
        await zip_inp.first.fill(CARD_ZIP)
        await asyncio.sleep(0.5)

    # 7. Print errors before click if any
    errors = await page.locator('.FieldError, .Alert, [role="alert"], span.error').all_inner_texts()
    print("Field errors before submit:", errors)

    # 8. Submit
    submit_btn = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"]')
    print(f"[+] Clicking submit: '{await submit_btn.first.inner_text()}'...")
    await submit_btn.first.click()
    print("[+] Clicked submit! Waiting 15s...")

    for i in range(15):
        await asyncio.sleep(1)
        if "hoplite.sh" in page.url and "stripe.com" not in page.url:
            print(f"[+] Redirected back to Hoplite in {i+1}s: {page.url}")
            return True
        # Check for error text
        errs = await page.locator('.FieldError, .Alert, [role="alert"]').all_inner_texts()
        if errs:
            print(f"  Stripe error at {i+1}s: {errs}")

    print(f"URL after 15s: {page.url}")
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

        if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
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

        # Fill Stripe Checkout
        if "stripe.com" in page.url:
            await fill_stripe_checkout(page)

        # If redirected back to Hoplite, check API keys
        if "hoplite.sh" in page.url:
            print("\n[4] Navigating to API keys...")
            await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(4)
            print(f"[+] API keys URL: {page.url}")

            html = await page.content()
            m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
            if m:
                print(f"\n🔥🔥🔥 [SUCCESS] EXTRACTED KEY: {m.group(0)} 🔥🔥🔥")
            else:
                cb = page.locator('button:has-text("Create"), button:has-text("New")')
                if await cb.count() > 0:
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

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
