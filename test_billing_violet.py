#!/usr/bin/env python3
"""Click Continue on starter threads -> Enter card on Checkout -> API keys."""
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
    for frame in page.frames:
        try:
            num_sel = 'input[name="cardnumber"], input[placeholder*="Card number"], input[autocomplete="cc-number"], input[data-elements-stable-field-name="cardNumber"]'
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
            zip_sel = 'input[name="postal"], input[placeholder*="ZIP"]'
            if await frame.locator(zip_sel).count() > 0:
                await frame.fill(zip_sel, CARD_ZIP)
                await asyncio.sleep(0.5)
        except Exception:
            pass

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
        for b_text in ["Subscribe", "Start free", "Start trial", "Pay", "Confirm", "Save card", "Continue", "Upgrade", "Complete checkout"]:
            sub = page.locator(f'button:has-text("{b_text}")')
            if await sub.count() > 0:
                print(f"[+] Clicking '{b_text}'...")
                await sub.first.click()
                await asyncio.sleep(6)
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
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"], input[id="otp"]', code)
            await asyncio.sleep(1)
            v = page.locator('button:has-text("Verify"), input[type="submit"]')
            if await v.count() > 0:
                await v.first.click()
            await asyncio.sleep(4)

        # 2. Open Hoplite
        print("[2] Opening Hoplite...")
        await page.goto("https://app.hoplite.sh/login?plan=free&interval=monthly", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        print("[+] Clicked Continue with GitHub...")

        # Authorize if prompted
        for i in range(20):
            await asyncio.sleep(1)
            if "authorize" in page.url.lower():
                await asyncio.sleep(2)
                await page.evaluate("""() => {
                    const b = document.querySelector('#js-oauth-authorize-btn, .js-oauth-authorize-btn, button[name="authorize"]');
                    if (b) { b.disabled = false; b.click(); }
                    else { const form = document.querySelector('form[action*="authorize"]'); if (form) form.submit(); }
                }""")
                await asyncio.sleep(5)
                break
            if "hoplite.sh" in page.url and "github.com" not in page.url and "login" not in page.url:
                break

        for _ in range(15):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break
        await asyncio.sleep(4)

        # Loop through onboarding steps
        print("[3] Walking through onboarding screens...")
        for step in range(8):
            await asyncio.sleep(2)
            page_text = await page.inner_text("body")
            print(f"\n--- Screen {step+1} text snippet ---")
            print(page_text[:250].replace("\n", " "))
            
            # Check for "starter threads" / "Your Set Up Is All Complete" -> Click Continue
            if "Set Up Is All Complete" in page_text or "starter threads" in page_text:
                print("[+] On 'Starter Threads', clicking 'Continue'...")
                c_btn = page.locator('button:has-text("Continue")')
                if await c_btn.count() > 0:
                    await c_btn.first.click()
                    await asyncio.sleep(4)
                    continue

            # Check for "Bring Your Team" -> Skip for now
            if "Bring Your Team" in page_text:
                print("[+] On 'Bring Your Team', clicking 'Skip for now'...")
                st_btn = page.locator('button:has-text("Skip for now"), a:has-text("Skip for now")')
                if await st_btn.count() > 0:
                    await st_btn.first.click()
                    await asyncio.sleep(3)
                    continue

            # Check for "Import Your Local" -> Skip for now
            if "Import Your Local" in page_text:
                print("[+] On 'Import Your Local', clicking 'Skip for now'...")
                sl_btn = page.locator('button:has-text("Skip for now"), a:has-text("Skip for now")')
                if await sl_btn.count() > 0:
                    await sl_btn.first.click()
                    await asyncio.sleep(3)
                    continue

            # Check for Plan Selection / Checkout / Stripe
            if "plan" in page_text.lower() or "free" in page_text.lower() or "pro" in page_text.lower() or "checkout" in page.url or "stripe" in page.url:
                print("[+] Plan Selection / Checkout detected!")
                # Click Free plan button if present
                free_b = page.locator('button:has-text("Start free"), button:has-text("Free"), div:has-text("Free") button')
                if await free_b.count() > 0:
                    print("[+] Clicking Free plan...")
                    await free_b.first.click()
                    await asyncio.sleep(3)
                
                # Fill card
                await fill_card(page)
                await asyncio.sleep(3)

                # Then click Pro plan if present
                pro_b = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start pro"), button:has-text("Pro")')
                if await pro_b.count() > 0:
                    print("[+] Upgrading to Pro plan...")
                    await pro_b.first.click()
                    await asyncio.sleep(3)
                    await fill_card(page)
                    await asyncio.sleep(3)
                break

            # Fallback for generic Skip / Continue
            skip_any = page.locator('button:has-text("Skip for now"), a:has-text("Skip for now")')
            if await skip_any.count() > 0:
                print("[+] Clicking generic 'Skip for now'...")
                await skip_any.first.click()
                await asyncio.sleep(3)
            elif await page.locator('button:has-text("Continue")').count() > 0:
                print("[+] Clicking generic 'Continue'...")
                await page.locator('button:has-text("Continue")').first.click()
                await asyncio.sleep(3)
            else:
                break

        print(f"\n[4] Landed URL after onboarding: {page.url}")

        # Go to API Keys
        print("\n[5] Navigating to API keys...")
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
                html2 = await page.content()
                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html2)
                if m2:
                    print(f"\n🔥🔥🔥 [SUCCESS] GENERATED KEY: {m2.group(0)} 🔥🔥🔥")
                else:
                    print("Page body after create:\n", (await page.inner_text("body"))[:600])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
