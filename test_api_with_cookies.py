#!/usr/bin/env python3
"""Extract full cookies and test direct Better Auth API endpoints."""
import asyncio, json, pyotp, requests
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)
acc = accounts[0]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Login GitHub
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
        await page.fill('input[name="login"]', acc['email'])
        await page.fill('input[name="password"]', acc['password'])
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)
        if "two-factor" in page.url.lower():
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"]', code)
            await asyncio.sleep(3)

        # Login Hoplite
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() > 0:
            await btn.first.click()
            await asyncio.sleep(6)

        # Get all cookies
        cookies = await ctx.cookies()
        hop_cookies = {c["name"]: c["value"] for c in cookies if "hoplite" in c["domain"]}
        print("Captured Hoplite Cookies:")
        print(json.dumps(hop_cookies, indent=2))

        # Save cookies to disk
        with open(r"C:\Users\User\tmp\hoplite-gateway\data\violet_cookies.json", "w") as f:
            json.dump(hop_cookies, f, indent=2)

        # Test Better-Auth API via requests
        session_cookie = hop_cookies.get("__Secure-better-auth.session_token")
        cookie_header = "; ".join(f"{k}={v}" for k, v in hop_cookies.items())
        headers = {
            "Cookie": cookie_header,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # 1. Test get-session
        print("\n[1] Testing /api/auth/get-session...")
        r_sess = requests.get("https://api.hoplite.sh/api/auth/get-session", headers=headers, timeout=10)
        print("get-session status:", r_sess.status_code)
        print("get-session body:", r_sess.text[:400])

        # 2. Test activate trial
        print("\n[2] Testing /api/billing/subscription/trial...")
        r_trial = requests.post("https://api.hoplite.sh/api/billing/subscription/trial", headers=headers, json={}, timeout=10)
        print("trial status:", r_trial.status_code)
        print("trial body:", r_trial.text[:400])

        # 3. Test list / create API key via Better Auth
        print("\n[3] Testing /api/auth/api-key/create...")
        r_key = requests.post("https://api.hoplite.sh/api/auth/api-key/create", headers=headers, json={"name": "violet-api-key"}, timeout=10)
        print("key create status:", r_key.status_code)
        print("key create body:", r_key.text[:400])

        # 4. Test projects
        print("\n[4] Testing /api/projects...")
        r_proj = requests.get("https://api.hoplite.sh/api/projects", headers=headers, timeout=10)
        print("projects status:", r_proj.status_code)
        print("projects body:", r_proj.text[:400])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
