#!/usr/bin/env python3
"""Inspect https://app.hoplite.sh/settings/api-keys in detail."""
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

        # Starter Threads Continue
        c = page.locator('button:has-text("Continue")')
        if await c.count() > 0:
            await c.first.click()
            await asyncio.sleep(3)

        # Navigate to API Keys page
        print("[3] Navigating to https://app.hoplite.sh/settings/api-keys...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(5)
        print(f"[+] Final URL: {page.url}")

        text = await page.inner_text("body")
        print("\n=== API KEYS PAGE FULL TEXT ===")
        print(text)

        buttons = await page.locator("button, a").all()
        print(f"\nTotal buttons/links: {len(buttons)}")
        for i, b in enumerate(buttons):
            t = (await b.inner_text()).strip().replace("\n", " ")
            tag = await b.evaluate("el => el.tagName")
            cls = await b.get_attribute("class") or ""
            print(f"  [{i}] <{tag} class='{cls[:30]}'> text='{t}'")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
