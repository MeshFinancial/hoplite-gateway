#!/usr/bin/env python3
"""Create a repo on GitHub for the account, then import it into Hoplite."""
import asyncio, json, pyotp, sys, random, string
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

acc = accounts[0] # Violetpivary
print(f"[+] Target: {acc['login']} ({acc['email']})")

repo_name = "".join(random.choices(string.ascii_lowercase, k=8))
print(f"[+] Random repo name: {repo_name}")

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

        # 1. Login to GitHub directly
        print("[1] Logging in to GitHub directly...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        await page.fill('input[name="login"]', acc['email'])
        await page.fill('input[name="password"]', acc['password'])
        await page.click('input[type="submit"]')
        await asyncio.sleep(4)

        if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
            print("[2] Submitting TOTP...")
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"], input[id="otp"]', code)
            await asyncio.sleep(1)
            v = page.locator('button:has-text("Verify"), input[type="submit"]')
            if await v.count() > 0:
                await v.first.click()
            await asyncio.sleep(4)

        print(f"[3] Logged in to GitHub! URL: {page.url}")

        # 2. Create new repo on GitHub
        print(f"[4] Creating repository: {repo_name}...")
        await page.goto("https://github.com/new", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # Fill repo name
        name_inp = page.locator('input[data-testid="repository-name-input"], input[aria-label="Repository name"], input[name="repository[name]"]')
        if await name_inp.count() > 0:
            await name_inp.first.fill(repo_name)
            await asyncio.sleep(1)

        # Check "Add a README file"
        readme_check = page.locator('input[type="checkbox"]#repository_auto_init, input[name="repository[auto_init]"], input[aria-describedby*="readme"]')
        if await readme_check.count() > 0:
            await readme_check.first.check()
            await asyncio.sleep(1)

        # Submit create repo
        create_repo_btn = page.locator('button:has-text("Create repository"), input[value="Create repository"]')
        if await create_repo_btn.count() > 0:
            await create_repo_btn.first.click()
            await asyncio.sleep(5)
            print(f"[+] Repo created! Current URL: {page.url}")

        # 3. Now navigate to Hoplite login
        print("[5] Going to Hoplite login...")
        await page.goto("https://app.hoplite.sh/login?plan=free&interval=monthly", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)

        # Click GitHub button
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        await asyncio.sleep(5)

        # Authorize if needed
        if "authorize" in page.url.lower() or await page.locator('#js-oauth-authorize-btn').count() > 0:
            print("[6] Authorizing Hoplite OAuth...")
            a = page.locator('#js-oauth-authorize-btn, button:has-text("Authorize")')
            if await a.count() > 0:
                await a.first.click()
            await asyncio.sleep(5)

        # Wait for redirect to Hoplite
        for _ in range(15):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break
        await asyncio.sleep(4)
        print(f"[7] On Hoplite! URL: {page.url}")

        # Personal Info if present
        role_btn = page.locator('button:has-text("Engineer")')
        if await role_btn.count() > 0:
            print("[8] Personal Info: selecting Engineer...")
            await role_btn.first.click()
            await asyncio.sleep(1)
            c1 = page.locator('button:has-text("Continue")')
            if await c1.count() > 0:
                await c1.first.click()
                await asyncio.sleep(3)

        # Workspace if present
        org_inp = page.locator('input[placeholder*="Acme"]')
        if await org_inp.count() > 0:
            print("[9] Workspace name...")
            await org_inp.first.fill(f"{acc['login']}-org")
            await asyncio.sleep(0.5)
            t_btn = page.locator('button:has-text("Just me")')
            if await t_btn.count() > 0:
                await t_btn.first.click()
            c2 = page.locator('button:has-text("Continue")')
            if await c2.count() > 0:
                await c2.first.click()
                await asyncio.sleep(3)

        print(f"[10] Step 3 page text...")
        text3 = await page.inner_text("body")
        print("\n=== STEP 3 TEXT ===")
        print(text3[:1200])

        buttons3 = await page.locator("button, a").all_inner_texts()
        print("\nButtons on Step 3:", [b.strip() for b in buttons3 if b.strip()][:25])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
