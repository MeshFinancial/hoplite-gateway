#!/usr/bin/env python3
"""Click 'Continue with Free', enter card details, submit, and extract API key."""
import asyncio, json, pyotp, re, sys
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
acc = accounts[0]

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

async def fill_stripe_card(page):
    print("[*] Inspecting page and frames for card inputs...")
    card_found = False

    # Wait 3s for payment modal / Stripe iframe to load
    await asyncio.sleep(3)

    print(f"[+] Total frames on page: {len(page.frames)}")
    for f in page.frames:
        print(f"  Frame: {f.url[:80]}")
        try:
            # Check for card number field inside Stripe iframe
            num_sel = 'input[name="cardnumber"], input[placeholder*="Card number"], input[autocomplete="cc-number"], input[data-elements-stable-field-name="cardNumber"]'
            if await f.locator(num_sel).count() > 0:
                print(f"[+] Found card number input in frame: {f.url[:60]}")
                await f.fill(num_sel, CARD_NUM)
                await asyncio.sleep(0.5)
                card_found = True

            exp_sel = 'input[name="exp-date"], input[placeholder*="MM / YY"], input[placeholder*="MM/YY"], input[autocomplete="cc-exp"]'
            if await f.locator(exp_sel).count() > 0:
                print("[+] Found expiry input in frame")
                await f.fill(exp_sel, CARD_EXP)
                await asyncio.sleep(0.5)

            cvc_sel = 'input[name="cvc"], input[placeholder*="CVC"], input[placeholder*="CVV"], input[autocomplete="cc-csc"]'
            if await f.locator(cvc_sel).count() > 0:
                print("[+] Found CVC input in frame")
                await f.fill(cvc_sel, CARD_CVV)
                await asyncio.sleep(0.5)

            zip_sel = 'input[name="postal"], input[placeholder*="ZIP"], input[name="postalCode"]'
            if await f.locator(zip_sel).count() > 0:
                print("[+] Found postal/ZIP input in frame")
                await f.fill(zip_sel, CARD_ZIP)
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  Frame check error: {e}")

    # Check top-level page for direct inputs
    try:
        top_inputs = await page.locator('input').all()
        print(f"[+] Top-level inputs: {len(top_inputs)}")
        for inp in top_inputs:
            n = await inp.get_attribute("name") or ""
            p = await inp.get_attribute("placeholder") or ""
            print(f"  Top input: name='{n}' placeholder='{p}'")
            if any(k in n.lower() or k in p.lower() for k in ["card", "number"]):
                await inp.fill(CARD_NUM)
                card_found = True
            elif any(k in n.lower() or k in p.lower() for k in ["exp", "mm"]):
                await inp.fill(CARD_EXP)
            elif any(k in n.lower() or k in p.lower() for k in ["cvc", "cvv", "security"]):
                await inp.fill(CARD_CVV)
            elif any(k in n.lower() or k in p.lower() for k in ["zip", "postal"]):
                await inp.fill(CARD_ZIP)
    except Exception as e:
        print(f"Top input error: {e}")

    # Click Pay / Submit / Subscribe
    print("[*] Looking for payment submit button...")
    for btn_text in ["Save card", "Start free", "Start trial", "Pay", "Subscribe", "Confirm", "Continue", "Submit"]:
        sub = page.locator(f'button:has-text("{btn_text}")')
        if await sub.count() > 0:
            print(f"[+] Clicking payment button: '{btn_text}'...")
            await sub.first.click()
            await asyncio.sleep(5)
            break

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
            await asyncio.sleep(4)

        # Check what appears
        print(f"[5] URL after clicking Free: {page.url}")
        text_after_free = await page.inner_text("body")
        print("\n=== TEXT AFTER CLICKING FREE ===")
        print(text_after_free[:1200])

        # Fill card
        await fill_stripe_card(page)
        await asyncio.sleep(4)

        # 4. Check if Pro upgrade is available or shown
        print("\n[6] Checking for Pro plan option...")
        pro_btn = page.locator('button:has-text("Start 14 days of Pro"), button:has-text("Upgrade to Pro")')
        if await pro_btn.count() > 0:
            print("[+] Clicking Pro plan...")
            await pro_btn.first.click()
            await asyncio.sleep(3)
            await fill_stripe_card(page)
            await asyncio.sleep(4)

        # 5. Navigate to settings/api-keys
        print("\n[7] Navigating to API keys...")
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
                print(f"[+] Clicking Create: '{await cb.first.inner_text()}'...")
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
