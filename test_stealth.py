#!/usr/bin/env python3
"""Follow onboarding: Info -> Workspace -> Billing/Card -> API Key"""
import asyncio, json, pyotp, re, sys
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

acc = accounts[0]
print(f"[+] Target: {acc['login']} ({acc['email']})")

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        page = await ctx.new_page()

        print("[1] Opening login page...")
        await page.goto("https://app.hoplite.sh/login?plan=free&interval=monthly", wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(4)

        print("[2] Clicking GitHub button...")
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()

        print("[3] Waiting for redirect to GitHub...")
        for i in range(15):
            await asyncio.sleep(1)
            if "github.com" in page.url:
                break

        if "github.com/login" in page.url:
            print("[4] Submitting GitHub credentials...")
            await page.fill('input[name="login"]', acc['email'])
            await page.fill('input[name="password"]', acc['password'])
            await page.click('input[type="submit"]')
            await asyncio.sleep(4)

            if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
                print("[4b] Entering TOTP...")
                code = pyotp.TOTP(acc['totp']).now()
                otp = page.locator('input[name="app_otp"], input[id="otp"]')
                if await otp.count() > 0:
                    await otp.first.fill(code)
                    await asyncio.sleep(1)
                    sub = page.locator('button:has-text("Verify"), input[type="submit"]')
                    if await sub.count() > 0:
                        await sub.first.click()
                    await asyncio.sleep(5)

            if "authorize" in page.url.lower() or await page.locator('#js-oauth-authorize-btn').count() > 0:
                print("[4c] Authorizing OAuth...")
                a = page.locator('#js-oauth-authorize-btn, button:has-text("Authorize")')
                if await a.count() > 0:
                    await a.first.click()
                await asyncio.sleep(5)

        print("[5] Waiting for return to Hoplite...")
        for i in range(20):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break

        await asyncio.sleep(4)

        # Step 1: Personal Info
        role_btn = page.locator('button:has-text("Engineer")')
        if await role_btn.count() > 0:
            print("[6] Step 1: Selecting Engineer...")
            await role_btn.first.click()
            await asyncio.sleep(1)
            cont_btn = page.locator('button:has-text("Continue")')
            if await cont_btn.count() > 0:
                await cont_btn.first.click()
                await asyncio.sleep(3)

        # Step 2: Create Workspace
        org_input = page.locator('input[placeholder*="Acme"], input[name*="org"]')
        if await org_input.count() > 0:
            print("[7] Step 2: Workspace name & Just me...")
            await org_input.first.fill(f"{acc['login']}-org")
            await asyncio.sleep(0.5)
            team_btn = page.locator('button:has-text("Just me")')
            if await team_btn.count() > 0:
                await team_btn.first.click()
                await asyncio.sleep(0.5)
            cont_btn2 = page.locator('button:has-text("Continue")')
            if await cont_btn2.count() > 0:
                await cont_btn2.first.click()
                await asyncio.sleep(3)

        # Step 3: Check billing / plan / card
        print("[8] Checking billing page...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"[+] Billing URL: {page.url}")
        billing_text = await page.inner_text("body")
        print("\n=== BILLING PAGE TEXT ===")
        print(billing_text[:1000])
        billing_btns = await page.locator("button, a").all_inner_texts()
        print("\nBilling Buttons:", [b.strip() for b in billing_btns if b.strip()][:25])

        # Step 4: Check API Keys page
        print("\n[9] Checking API Keys page...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        print(f"[+] API Keys URL: {page.url}")
        keys_text = await page.inner_text("body")
        print("\n=== API KEYS PAGE TEXT ===")
        print(keys_text[:1000])
        keys_btns = await page.locator("button, a").all_inner_texts()
        print("\nAPI Keys Buttons:", [b.strip() for b in keys_btns if b.strip()][:25])

        # Try to extract key or click create
        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
        if m:
            print(f"\n[SUCCESS] FOUND KEY: {m.group(0)}")
        else:
            print("\n[-] No key in HTML yet. Trying Create API key button...")
            create_btn = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Generate")')
            if await create_btn.count() > 0:
                print("[+] Clicking Create button...")
                await create_btn.first.click()
                await asyncio.sleep(2)
                
                # Check modal
                modal_text = await page.inner_text("body")
                print("Modal text snippet:", modal_text[:400])
                
                name_inp = page.locator('input[placeholder*="name"], input[placeholder*="Name"]')
                if await name_inp.count() > 0:
                    await name_inp.first.fill(f"{acc['login']}-key")
                    await asyncio.sleep(1)
                    
                cf_btn = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm"), button:has-text("Save")')
                if await cf_btn.count() > 0:
                    await cf_btn.last.click()
                    await asyncio.sleep(3)
                    
                html2 = await page.content()
                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html2)
                if m2:
                    print(f"[SUCCESS] GENERATED KEY: {m2.group(0)}")
                else:
                    print("Still no key in DOM after modal confirm.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
