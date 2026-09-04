#!/usr/bin/env python3
"""Use persistent context to maintain session and extract API key."""
import asyncio, json, pyotp, re, sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(r"C:\Users\User\tmp\hoplite-gateway")
PROFILE_DIR = BASE_DIR / "data" / "chrome_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

with open(BASE_DIR / "data" / "gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

acc = accounts[0] # Violetpivary
print(f"[+] Target: {acc['login']} ({acc['email']})")

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

async def main():
    async with async_playwright() as p:
        # Launch persistent context
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # 1. Login GitHub if not already logged in
        print("[1] Opening GitHub...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        if "github.com/login" in page.url:
            print("[+] Logging in to GitHub...")
            await page.fill('input[name="login"]', acc['email'])
            await page.fill('input[name="password"]', acc['password'])
            await page.click('input[type="submit"]')
            await asyncio.sleep(4)

            if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
                print("[+] Submitting TOTP...")
                code = pyotp.TOTP(acc['totp']).now()
                await page.fill('input[name="app_otp"], input[id="otp"]', code)
                await asyncio.sleep(1)
                v = page.locator('button:has-text("Verify"), input[type="submit"]')
                if await v.count() > 0:
                    await v.first.click()
                await asyncio.sleep(4)
        print(f"[+] GitHub state URL: {page.url}")

        # 2. Open Hoplite
        print("[2] Opening Hoplite...")
        await page.goto("https://app.hoplite.sh/login?plan=free&interval=monthly", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # If on login, click GitHub
        btn = page.locator('button[aria-label="Continue with GitHub"], button:has-text("GitHub")')
        if await btn.count() > 0:
            print("[+] Clicking GitHub login on Hoplite...")
            await btn.first.click()
            # Wait for redirect
            for i in range(15):
                await asyncio.sleep(1)
                if "authorize" in page.url or "hoplite.sh" in page.url:
                    break
            await asyncio.sleep(3)

        if "authorize" in page.url.lower() or await page.locator('#js-oauth-authorize-btn').count() > 0:
            print("[+] Authorizing OAuth app...")
            a = page.locator('#js-oauth-authorize-btn, button:has-text("Authorize")')
            if await a.count() > 0:
                await a.first.click()
            await asyncio.sleep(5)

        # Wait for redirect to Hoplite app
        for _ in range(15):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break
        await asyncio.sleep(3)
        print(f"[3] Landed on Hoplite: {page.url}")

        # Onboarding Step 1: Engineer
        role_btn = page.locator('button:has-text("Engineer")')
        if await role_btn.count() > 0:
            print("[+] Selecting Engineer...")
            await role_btn.first.click()
            c1 = page.locator('button:has-text("Continue")')
            if await c1.count() > 0:
                await c1.first.click()
            await asyncio.sleep(3)

        # Onboarding Step 2: Workspace
        org_inp = page.locator('input[placeholder*="Acme"]')
        if await org_inp.count() > 0:
            print("[+] Entering Workspace name...")
            await org_inp.first.fill(f"{acc['login']}-org")
            t_btn = page.locator('button:has-text("Just me")')
            if await t_btn.count() > 0:
                await t_btn.first.click()
            c2 = page.locator('button:has-text("Continue")')
            if await c2.count() > 0:
                await c2.first.click()
            await asyncio.sleep(3)

        # Onboarding Step 3: Create project
        cp_btn = page.locator('button:has-text("Create 1 project"), button:has-text("Create project")')
        if await cp_btn.count() > 0:
            print(f"[+] Clicking {await cp_btn.first.inner_text()}...")
            await cp_btn.first.click()
            await asyncio.sleep(4)

        # Onboarding Step 4: Skip CLI setup
        skip_btn = page.locator('button:has-text("Skip for now"), a:has-text("Skip for now")')
        if await skip_btn.count() > 0:
            print("[+] Clicking Skip for now...")
            await skip_btn.first.click()
            await asyncio.sleep(4)

        print(f"[4] Current page URL: {page.url}")
        text_now = await page.inner_text("body")
        print("Page text preview:\n", text_now[:600])

        # 3. Check for API keys
        print("\n[5] Going to settings/api-keys...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        print(f"[+] API keys page: {page.url}")

        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
        if m:
            print(f"\n🔥🔥🔥 [SUCCESS] EXTRACTED KEY: {m.group(0)} 🔥🔥🔥")
        else:
            print("Checking Create button on API keys page...")
            cb = page.locator('button:has-text("Create"), button:has-text("New")')
            if await cb.count() > 0:
                print("[+] Clicking Create button...")
                await cb.first.click()
                await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"], input[placeholder*="Name"]')
                if await ni.count() > 0:
                    await ni.first.fill(f"{acc['login']}-key")
                confirm = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm"), button:has-text("Save")')
                if await confirm.count() > 0:
                    await confirm.last.click()
                    await asyncio.sleep(3)
                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                if m2:
                    print(f"\n🔥🔥🔥 [SUCCESS] GENERATED KEY: {m2.group(0)} 🔥🔥🔥")
                else:
                    print("Page after create:\n", (await page.inner_text("body"))[:600])

        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
