#!/usr/bin/env python3
"""Complete onboarding by clicking 'Skip for now', then extract API key and setup billing."""
import asyncio, json, pyotp, re, sys
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

acc = accounts[0] # Violetpivary

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

async def fill_card(page):
    print("[*] Checking for card / Stripe inputs...")
    card_filled = False
    
    # Check iframes for Stripe
    for frame in page.frames:
        try:
            num_sel = 'input[name="cardnumber"], input[placeholder*="Card number"], input[autocomplete="cc-number"]'
            if await frame.locator(num_sel).count() > 0:
                print(f"[+] Found card number in iframe: {frame.url[:60]}")
                await frame.fill(num_sel, CARD_NUM)
                await asyncio.sleep(0.5)
                card_filled = True
                
            exp_sel = 'input[name="exp-date"], input[placeholder*="MM / YY"], input[placeholder*="MM/YY"], input[autocomplete="cc-exp"]'
            if await frame.locator(exp_sel).count() > 0:
                print("[+] Found expiry in iframe")
                await frame.fill(exp_sel, CARD_EXP)
                await asyncio.sleep(0.5)
                
            cvc_sel = 'input[name="cvc"], input[placeholder*="CVC"], input[placeholder*="CVV"], input[autocomplete="cc-csc"]'
            if await frame.locator(cvc_sel).count() > 0:
                print("[+] Found CVC in iframe")
                await frame.fill(cvc_sel, CARD_CVV)
                await asyncio.sleep(0.5)
                
            zip_sel = 'input[name="postal"], input[placeholder*="ZIP"], input[name="postalCode"]'
            if await frame.locator(zip_sel).count() > 0:
                await frame.fill(zip_sel, CARD_ZIP)
                await asyncio.sleep(0.5)
        except Exception as e:
            pass

    # Check top-level inputs
    try:
        top_card = page.locator('input[placeholder*="Card number"], input[name*="card"]')
        if await top_card.count() > 0:
            print("[+] Found card input on top page")
            await top_card.first.fill(CARD_NUM)
            card_filled = True
    except:
        pass

    if card_filled:
        print("[+] Card filled! Looking for submit/pay button...")
        for b_text in ["Subscribe", "Start free", "Start trial", "Pay", "Confirm", "Save card", "Continue", "Upgrade"]:
            sub = page.locator(f'button:has-text("{b_text}")')
            if await sub.count() > 0:
                print(f"[+] Clicking '{b_text}'...")
                await sub.first.click()
                await asyncio.sleep(5)
                break
    return card_filled

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
        await asyncio.sleep(4)

        if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
            print("[2] TOTP...")
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"], input[id="otp"]', code)
            await asyncio.sleep(1)
            v = page.locator('button:has-text("Verify"), input[type="submit"]')
            if await v.count() > 0:
                await v.first.click()
            await asyncio.sleep(4)

        # 2. Open Hoplite login
        print("[3] Open Hoplite...")
        await page.goto("https://app.hoplite.sh/login?plan=free&interval=monthly", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        await asyncio.sleep(5)

        if "authorize" in page.url.lower() or await page.locator('#js-oauth-authorize-btn').count() > 0:
            a = page.locator('#js-oauth-authorize-btn, button:has-text("Authorize")')
            if await a.count() > 0:
                await a.first.click()
            await asyncio.sleep(5)

        for _ in range(15):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break
        await asyncio.sleep(3)

        # Step 1 if shown
        r_btn = page.locator('button:has-text("Engineer")')
        if await r_btn.count() > 0:
            await r_btn.first.click()
            c1 = page.locator('button:has-text("Continue")')
            if await c1.count() > 0:
                await c1.first.click()
            await asyncio.sleep(2)

        # Step 2 if shown
        o_inp = page.locator('input[placeholder*="Acme"]')
        if await o_inp.count() > 0:
            await o_inp.first.fill("my-org")
            t_btn = page.locator('button:has-text("Just me")')
            if await t_btn.count() > 0:
                await t_btn.first.click()
            c2 = page.locator('button:has-text("Continue")')
            if await c2.count() > 0:
                await c2.first.click()
            await asyncio.sleep(3)

        # Step 3 if shown: Click "Create 1 project"
        create_proj_btn = page.locator('button:has-text("Create 1 project"), button:has-text("Create project")')
        if await create_proj_btn.count() > 0:
            print(f"[4] Clicking '{await create_proj_btn.first.inner_text()}'...")
            await create_proj_btn.first.click()
            await asyncio.sleep(4)

        # Step 4: Click "Skip for now" on CLI setup
        skip_btn = page.locator('button:has-text("Skip for now"), a:has-text("Skip for now"), button:has-text("Skip")')
        if await skip_btn.count() > 0:
            print("[5] Clicking 'Skip for now'...")
            await skip_btn.first.click()
            await asyncio.sleep(4)

        print(f"[6] URL after skipping CLI setup: {page.url}")
        text_dash = await page.inner_text("body")
        print("\n=== DASHBOARD / APP TEXT ===")
        print(text_dash[:800])

        # Step 5: Check Billing & Pay with card if needed
        print("\n[7] Navigating to Billing...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"[+] Billing URL: {page.url}")

        # Check for Free / Pro / Upgrade buttons
        upg_btn = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start free"), button:has-text("Upgrade")')
        if await upg_btn.count() > 0:
            print(f"[+] Found button: '{await upg_btn.first.inner_text()}', clicking...")
            await upg_btn.first.click()
            await asyncio.sleep(3)
            await fill_card(page)

        # Step 6: Go to API Keys
        print("\n[8] Navigating to API Keys page...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"[+] API Keys URL: {page.url}")

        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
        if m:
            print(f"\n🔥🔥🔥 [SUCCESS] EXTRACTED KEY: {m.group(0)} 🔥🔥🔥")
        else:
            print("[-] Checking Create API key button...")
            c_key_btn = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Generate")')
            if await c_key_btn.count() > 0:
                print(f"[+] Clicking Create key button: '{await c_key_btn.first.inner_text()}'...")
                await c_key_btn.first.click()
                await asyncio.sleep(2)

                name_i = page.locator('input[placeholder*="name"], input[placeholder*="Name"]')
                if await name_i.count() > 0:
                    await name_i.first.fill(f"{acc['login']}-key")
                    await asyncio.sleep(1)

                conf_btn = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm"), button:has-text("Save")')
                if await conf_btn.count() > 0:
                    await conf_btn.last.click()
                    await asyncio.sleep(3)

                html2 = await page.content()
                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html2)
                if m2:
                    print(f"\n🔥🔥🔥 [SUCCESS] GENERATED KEY: {m2.group(0)} 🔥🔥🔥")
                else:
                    body_k = await page.inner_text("body")
                    print("API Keys page body:\n", body_k[:800])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
