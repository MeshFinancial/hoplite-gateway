#!/usr/bin/env python3
"""Test single account login & onboarding flow on Hoplite."""
import asyncio, json, pyotp, sys
from pathlib import Path
from playwright.async_api import async_playwright

DATA_DIR = Path(r"C:\Users\User\tmp\hoplite-gateway\data")
with open(DATA_DIR / "gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

# Use account 0
acc = accounts[0]
print(f"[+] Target account: {acc['login']} ({acc['email']})")

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()
        
        # 1. Open Hoplite login
        print("[1] Opening https://app.hoplite.sh/login...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        # 2. Click GitHub button
        print("[2] Finding and clicking GitHub button...")
        btn = page.locator('button[aria-label="Continue with GitHub"], button:has-text("GitHub")')
        await btn.first.click()
        print("[+] Clicked GitHub button, waiting for redirect to GitHub...")
        
        # 3. Wait for GitHub navigation (takes ~5-8s for PKCE exchange)
        reached_gh = False
        for i in range(20):
            await asyncio.sleep(1)
            print(f"    Waiting {i+1}s, url: {page.url[:60]}")
            if "github.com" in page.url:
                reached_gh = True
                print(f"[+] Reached GitHub: {page.url[:80]}")
                break
                
        if not reached_gh:
            print("[-] Did not reach GitHub. Current URL:", page.url)
            await browser.close()
            return

        # 4. Fill credentials on GitHub
        if "github.com/login" in page.url:
            print("[4] Submitting GitHub credentials...")
            await page.wait_for_selector('input[name="login"]', timeout=15000)
            await page.fill('input[name="login"]', acc['email'])
            await page.fill('input[name="password"]', acc['password'])
            await page.click('input[type="submit"]')
            await asyncio.sleep(4)
            print(f"[+] Post-login URL: {page.url[:70]}")
            
            # 5. Handle TOTP
            if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
                print("[5] Entering TOTP...")
                totp = pyotp.TOTP(acc['totp']).now()
                await page.fill('input[name="app_otp"], input[id="otp"]', totp)
                await asyncio.sleep(1)
                submit_btn = page.locator('button:has-text("Verify"), input[type="submit"]')
                if await submit_btn.count() > 0:
                    await submit_btn.first.click()
                print("[+] Submitted TOTP, waiting...")
                await asyncio.sleep(5)
                print(f"[+] URL after TOTP: {page.url[:70]}")
                
            # 6. Handle OAuth Authorization if shown
            if "authorize" in page.url.lower() or await page.locator('#js-oauth-authorize-btn').count() > 0:
                print("[6] Authorizing Hoplite OAuth app...")
                auth_btn = page.locator('#js-oauth-authorize-btn, button:has-text("Authorize")')
                if await auth_btn.count() > 0:
                    await auth_btn.first.click()
                await asyncio.sleep(5)
                print(f"[+] URL after OAuth authorize: {page.url[:70]}")
        
        # 7. Wait for redirect back to Hoplite
        print("[7] Waiting for redirect back to Hoplite...")
        for i in range(25):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                print(f"[+] Back on Hoplite at {i+1}s: {page.url}")
                break
                
        await asyncio.sleep(5)
        print(f"[8] Final landing URL: {page.url}")
        
        # Check text on page
        body_text = await page.inner_text("body")
        print("\n=== PAGE BODY TEXT ===")
        print(body_text[:1200])
        print("======================\n")
        
        # Check inputs and buttons
        inputs = await page.locator("input").all()
        print(f"Inputs found: {len(inputs)}")
        for inp in inputs:
            p_holder = await inp.get_attribute("placeholder") or ""
            name = await inp.get_attribute("name") or ""
            inp_type = await inp.get_attribute("type") or ""
            print(f"  Input: type='{inp_type}' name='{name}' placeholder='{p_holder}'")
            
        buttons = await page.locator("button, a").all_inner_texts()
        print("\nButtons & Links:")
        for b in [x.strip() for x in buttons if x.strip()][:25]:
            print(f"  - {b}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
