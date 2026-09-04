#!/usr/bin/env python3
"""
Final Stripe Autoreg - proper fingerprint evasion, ALL fields, no hCaptcha trigger.
Uses Chrome persistent profile with real user data.
"""
import asyncio, re, requests, time, pyotp, uuid, json
from pathlib import Path
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json") as f:
    accounts = json.load(f)
acc = accounts[0]

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "123"
CARD_ZIP = "10001"
ANTI_KEY = "03ea83a89c837abf30695d43a93c0f29"

PROFILE_DIR = Path(r"C:\Users\User\tmp\hoplite-gateway\data\chrome_profile")
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

def solve_hcaptcha(sitekey, pageurl):
    payload = {"clientKey": ANTI_KEY, "task": {"type": "HCaptchaTaskProxyless", "websiteURL": pageurl, "websiteKey": sitekey, "isInvisible": True}}
    r = requests.post("https://api.anti-captcha.com/createTask", json=payload, timeout=10).json()
    tid = r.get("taskId")
    if not tid: return None
    for i in range(25):
        time.sleep(3)
        res = requests.post("https://api.anti-captcha.com/getTaskResult", json={"clientKey": ANTI_KEY, "taskId": tid}, timeout=10).json()
        if res.get("status") == "ready":
            return res.get("solution", {}).get("gRecaptchaResponse")
    return None

async def fill_stripe_fields(page):
    """Fill ALL Stripe Checkout fields."""
    fields = [
        ('input#cardNumber', CARD_NUM),
        ('input#cardExpiry', CARD_EXP),
        ('input#cardCvc', CARD_CVV),
        ('input#billingName', "Violet User"),
        ('input#billingPostalCode', CARD_ZIP),
        ('input#billingAddressLine1', "123 Main Street"),
        ('input#billingAddressCity', "New York"),
        ('input#billingAddressState', "NY"),
    ]
    for sel, val in fields:
        el = page.locator(sel)
        if await el.count() > 0:
            await el.first.fill(val)
            print(f"  ✓ {sel}")

    cs = page.locator('select#billingCountry, select[name="billingCountry"]')
    if await cs.count() > 0:
        try:
            await cs.first.select_option(value="US")
            print("  ✓ Country: US")
        except:
            try:
                await cs.first.select_option(label="United States")
                print("  ✓ Country: United States")
            except:
                pass

async def main():
    async with async_playwright() as p:
        # Use persistent context for real browser profile
        print("[*] Launching Chrome with persistent profile (anti-fingerprint)...")
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=False,
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--start-maximized",
                f"--window-size=1280,900"
            ]
        )

        # Anti-detection init script
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            window.chrome = {runtime: {}};
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({state: Notification.permission}) :
                    originalQuery(parameters)
            );
        """)

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # GitHub login (skip if already logged in)
        print("[1] GitHub login...")
        await page.goto("https://github.com/", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        if "github.com/login" in page.url or await page.locator('input[name="login"]').count() > 0:
            await page.goto("https://github.com/login", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await page.fill('input[name="login"]', acc['email'])
            await page.fill('input[name="password"]', acc['password'])
            await page.click('input[type="submit"]')
            await asyncio.sleep(3)
            if "two-factor" in page.url.lower():
                code = pyotp.TOTP(acc['totp']).now()
                await page.fill('input[name="app_otp"]', code)
                await asyncio.sleep(3)
        else:
            print("  [+] Already logged in to GitHub")

        # Hoplite login (skip if already authenticated)
        print("[2] Hoplite login...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        # Check if already logged in (no GitHub button)
        if await page.locator('button[aria-label="Continue with GitHub"]').count() > 0:
            await page.locator('button[aria-label="Continue with GitHub"]').first.click()
            await asyncio.sleep(6)
            for _ in range(15):
                await asyncio.sleep(1)
                if "authorize" in page.url.lower():
                    await page.evaluate("() => { const b = document.querySelector('.js-oauth-authorize-btn'); if(b) { b.disabled=false; b.click(); } }")
                    await asyncio.sleep(4); break
                if "hoplite.sh" in page.url and "github.com" not in page.url: break
        else:
            print("  [+] Already logged into Hoplite")

        # Walk to plan screen
        print("[3] Walking to Plan screen...")
        for step in range(10):
            await asyncio.sleep(2)
            txt = await page.inner_text("body")
            if "Set Up Is All Complete" in txt or "starter threads" in txt.lower():
                await page.locator('button:has-text("Continue")').first.click(); await asyncio.sleep(4); continue
            if "Choose Your Plan" in txt or "Continue with Free" in txt:
                await page.locator('button:has-text("Continue with Free")').first.click(); await asyncio.sleep(5); break
            sk = page.locator('button:has-text("Skip for now")')
            if await sk.count() > 0: await sk.first.click(); await asyncio.sleep(2); continue
            ct = page.locator('button:has-text("Continue")')
            if await ct.count() > 0: await ct.first.click(); await asyncio.sleep(3); continue
            break

        # Stripe Checkout
        if "stripe.com" in page.url:
            print("[4] Stripe Checkout reached! Filling ALL fields...")
            await page.wait_for_selector('input#cardNumber', timeout=20000)
            await asyncio.sleep(1.5)
            await fill_stripe_fields(page)

            # Check if hCaptcha iframes exist
            hcap_frames = [f for f in page.frames if "hcaptcha" in f.url]
            if hcap_frames:
                print(f"[5] hCaptcha detected! Solving via Anti-Captcha...")
                hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
                for f in hcap_frames:
                    m = re.search(r'sitekey=([a-zA-Z0-9_-]+)', f.url)
                    if m: hsk = m.group(1); break
                token = solve_hcaptcha(hsk, page.url)
                if token:
                    await page.evaluate(f"""() => {{
                        const t = '{token}';
                        ['h-captcha-response','g-recaptcha-response'].forEach(n => {{
                            let el = document.querySelector(`[name="${{n}}"]`);
                            if (!el) {{
                                el = document.createElement('textarea');
                                el.name = n; el.style.display = 'none';
                                document.body.appendChild(el);
                            }}
                            el.value = t;
                        }});
                        // Direct form submit bypasses hCaptcha callback
                        const form = document.querySelector('form');
                        if (form) {{
                            HTMLFormElement.prototype.submit.call(form);
                        }}
                        // Also try button click as fallback
                        setTimeout(() => {{
                            const btn = document.querySelector('button[data-testid="hosted-payment-submit-button"]');
                            if (btn) {{ btn.disabled = false; btn.click(); }}
                        }}, 2000);
                    }}""")
                print("[6] WAITING for payment. Check Chrome window!")
                print("    If hCaptcha appears, solve it manually.")
                print("    If card is filled, click Save button.")
                for i in range(60):
                    await asyncio.sleep(1)
                    if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                        print(f"🔥 REDIRECTED in {i+1}s!"); break
                    if i == 30:
                        print("    Still waiting... Check Chrome window")
                print(f"  URL: {page.url[:80]}")
            else:
                print("[5] No hCaptcha detected! Clicking submit directly...")
                sub = page.locator('button[data-testid="hosted-payment-submit-button"]')
                if await sub.count() > 0:
                    await sub.first.click(); await asyncio.sleep(10)

        # Pro upgrade
        print("[7] Pro upgrade...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        pro = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
        if await pro.count() > 0:
            await pro.first.click(); await asyncio.sleep(5)
            if "stripe.com" in page.url:
                await fill_stripe_fields(page)
                t2 = solve_hcaptcha(hsk, page.url)
                if t2:
                    await page.evaluate("document.querySelector('button[data-testid=\"hosted-payment-submit-button\"]')?.click()")
                await asyncio.sleep(10)

        # API key
        print("[8] API key...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        html = await page.content()
        m = re.search(r'hop_\w{40,}', html)
        if m: print(f"🔥🔥🔥 KEY: {m.group(0)}")
        else:
            cb = page.locator('button:has-text("Create")')
            if await cb.count() > 0:
                await cb.first.click(); await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"]')
                if await ni.count() > 0: await ni.first.fill("violet-key")
                cf = page.locator('button:has-text("Create"):not(:has-text("Repository"))')
                if await cf.count() > 0: await cf.last.click(); await asyncio.sleep(3)
                m2 = re.search(r'hop_\w{40,}', await page.content())
                if m2: print(f"🔥🔥🔥 KEY: {m2.group(0)}")

        await asyncio.sleep(10)
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())