#!/usr/bin/env python3
"""Navigate directly to GitHub App installation flow and approve."""
import asyncio, json, pyotp
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

acc = accounts[0] # Violetpivary

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"

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

        # 2. Open Hoplite
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

        # Skip step 1 & 2 if shown
        r_btn = page.locator('button:has-text("Engineer")')
        if await r_btn.count() > 0:
            await r_btn.first.click()
            c1 = page.locator('button:has-text("Continue")')
            if await c1.count() > 0:
                await c1.first.click()
            await asyncio.sleep(2)

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

        print(f"[4] On Hoplite step 3: {page.url}")

        # 3. Navigate directly to GitHub install URL
        print("[5] Navigating to https://api.hoplite.sh/api/github/install?returnTo=%2Flogin...")
        await page.goto("https://api.hoplite.sh/api/github/install?returnTo=%2Flogin", wait_until="domcontentloaded")
        await asyncio.sleep(5)
        print(f"[+] Landed on: {page.url}")

        # Check what is on GitHub installation page
        gh_text = await page.inner_text("body")
        print("\n=== GITHUB APP PAGE TEXT ===")
        print(gh_text[:800])

        gh_buttons = await page.locator("button, input[type='submit']").all_inner_texts()
        print("\nGitHub Buttons:", [b.strip() for b in gh_buttons if b.strip()])

        # Click Install & Authorize on GitHub
        inst = page.locator('button:has-text("Install"), button:has-text("Save"), input[value*="Install"]')
        if await inst.count() > 0:
            print(f"[+] Clicking {await inst.first.inner_text()}...")
            await inst.first.click()
            await asyncio.sleep(5)
            print(f"[+] URL after install button: {page.url}")

            # Sometimes password confirmation is needed
            if "sudo" in page.url or await page.locator('input[type="password"]').count() > 0:
                print("GitHub asking for password confirmation...")
                pw_inp = page.locator('input[type="password"]')
                if await pw_inp.count() > 0:
                    await pw_inp.first.fill(acc['password'])
                    await page.click('button:has-text("Confirm"), input[type="submit"]')
                    await asyncio.sleep(5)

            # Wait for return to Hoplite
            for _ in range(15):
                await asyncio.sleep(1)
                if "hoplite.sh" in page.url:
                    print(f"[+] Back on Hoplite! URL: {page.url}")
                    break

            await asyncio.sleep(4)
            print(f"[+] Current Hoplite URL: {page.url}")
            hop_text = await page.inner_text("body")
            print("\n=== HOPLITE POST-INSTALL TEXT ===")
            print(hop_text[:800])

            hop_btns = await page.locator("button, a").all_inner_texts()
            print("\nHoplite Buttons:", [b.strip() for b in hop_btns if b.strip()])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
