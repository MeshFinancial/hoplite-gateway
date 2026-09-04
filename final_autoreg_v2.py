#!/usr/bin/env python3
"""FINAL working autoreg - all fields, captcha, Pro + API key."""
import asyncio, re, requests, time, pyotp, json
from playwright.async_api import async_playwright

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json") as f:
    accounts = json.load(f)
acc = accounts[0]

CARD = {"num": "4874100085748500", "exp": "05/30", "cvv": "123", "zip": "10001"}
ANTI = "03ea83a89c837abf30695d43a93c0f29"

def captcha(sitekey, pageurl):
    r = requests.post("https://api.anti-captcha.com/createTask", json={"clientKey": ANTI, "task": {"type": "HCaptchaTaskProxyless", "websiteURL": pageurl, "websiteKey": sitekey, "isInvisible": True}}, timeout=10).json()
    tid = r.get("taskId")
    if not tid: return None
    for i in range(25):
        time.sleep(3)
        res = requests.post("https://api.anti-captcha.com/getTaskResult", json={"clientKey": ANTI, "taskId": tid}, timeout=10).json()
        if res.get("status") == "ready":
            print(f"  [+] Captcha solved in {(i+1)*3}s")
            return res.get("solution", {}).get("gRecaptchaResponse")
    return None

async def fill_all_stripe(page):
    print("  [*] Filling ALL Stripe fields...")
    await page.wait_for_selector("input#cardNumber", timeout=20000)
    await asyncio.sleep(1.5)

    # Fill card fields
    await page.locator("input#cardNumber").fill(CARD["num"])
    await page.locator("input#cardExpiry").fill(CARD["exp"])
    await page.locator("input#cardCvc").fill(CARD["cvv"])
    await page.locator("input#billingName").fill("Violet User")

    # Country FIRST (it affects which address fields appear)
    cs = page.locator("select#billingCountry, select[name='billingCountry']")
    if await cs.count() > 0:
        try:
            await cs.first.select_option(value="US")
            print("  Country: US")
        except:
            pass
    await asyncio.sleep(1)

    # Fill ALL address fields - try all possible selectors
    address_fields = {
        "input#billingPostalCode": CARD["zip"],
        "input#billingAddressLine1": "123 Main Street",
        "input#billingAddressLine2": "Apt 4B",
        "input#billingAddressCity": "New York",
        "input#billingAddressState": "NY",
        "input[name='billingAddressLine1']": "123 Main Street",
        "input[name='billingAddressLine2']": "Apt 4B",
        "input[name='billingAddressCity']": "New York",
        "input[name='billingAddressState']": "NY",
        "input[name='billingPostalCode']": CARD["zip"],
        "input[autocomplete='address-line1']": "123 Main Street",
        "input[autocomplete='address-line2']": "Apt 4B",
        "input[autocomplete='address-level2']": "New York",
        "input[autocomplete='address-level1']": "NY",
        "input[autocomplete='postal-code']": CARD["zip"],
        "input[placeholder*='City']": "New York",
        "input[placeholder*='Address']": "123 Main Street",
        "input[placeholder*='State']": "NY",
        "input[placeholder*='ZIP']": CARD["zip"],
        "input[placeholder*='Postal']": CARD["zip"],
        "input[id*='city']": "New York",
        "input[id*='address']": "123 Main Street",
        "input[id*='state']": "NY",
        "input[id*='zip']": CARD["zip"],
        "input[id*='postal']": CARD["zip"],
    }
    filled = set()
    for sel, val in address_fields.items():
        if sel in filled:
            continue
        el = page.locator(sel)
        if await el.count() > 0:
            await el.first.fill(val)
            print(f"    Filled: {sel}")
            filled.add(sel)

    # Also try to fill by label text
    await page.evaluate("""() => {
        const labels = document.querySelectorAll('label');
        labels.forEach(l => {
            const text = l.textContent.toLowerCase();
            const input = l.closest('div')?.querySelector('input') || l.nextElementSibling;
            if (!input || input.tagName !== 'INPUT') return;
            if (text.includes('city') && !input.value) input.value = 'New York';
            if (text.includes('address') && text.includes('line 1') && !input.value) input.value = '123 Main Street';
            if (text.includes('address') && text.includes('line 2') && !input.value) input.value = 'Apt 4B';
            if (text.includes('state') && !input.value) input.value = 'NY';
        });
    }""")

    # Solve hCaptcha
    hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
    for f in page.frames:
        if "hcaptcha" in f.url:
            m = re.search(r"sitekey=([a-zA-Z0-9_-]+)", f.url)
            if m: hsk = m.group(1); break
    token = captcha(hsk, page.url)
    if token:
        print(f"  [+] Captcha token: {token[:20]}...")
        await page.evaluate(f"""() => {{
            const t = '{token}';
            ["h-captcha-response","g-recaptcha-response"].forEach(n => {{
                let el = document.querySelector(`[name="${{n}}"]`);
                if (!el) {{
                    el = document.createElement("textarea");
                    el.name = n; el.style.display = "none";
                    document.body.appendChild(el);
                }}
                el.value = t;
                el.dispatchEvent(new Event("input", {{bubbles: true}}));
            }});
            // Click submit button
            setTimeout(() => {{
                const btn = document.querySelector("button[data-testid='hosted-payment-submit-button']");
                if (btn) {{ btn.disabled = false; btn.click(); }}
                document.querySelector("form")?.requestSubmit();
            }}, 1000);
        }}""")
        return True
    return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized", "--no-sandbox"]
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await ctx.new_page()

        # GitHub login
        print("[1] GitHub login...")
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

        # Hoplite login
        print("[2] Hoplite login...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0: btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()
        await asyncio.sleep(6)
        for _ in range(15):
            await asyncio.sleep(1)
            if "authorize" in page.url.lower():
                await page.evaluate("() => { const b = document.querySelector('.js-oauth-authorize-btn'); if(b) { b.disabled=false; b.click(); } }")
                await asyncio.sleep(4); break
            if "hoplite.sh" in page.url and "github.com" not in page.url: break

        # Walk to plan
        print("[3] Plan screen...")
        for step in range(10):
            await asyncio.sleep(2)
            txt = await page.inner_text("body")
            if "Set Up Is All Complete" in txt or "starter threads" in txt.lower():
                c = page.locator('button:has-text("Continue")')
                if await c.count() > 0: await c.first.click(); await asyncio.sleep(4); continue
            if "Choose Your Plan" in txt or "Continue with Free" in txt:
                fb = page.locator('button:has-text("Continue with Free")')
                if await fb.count() > 0: await fb.first.click(); await asyncio.sleep(5); break
            sk = page.locator('button:has-text("Skip for now")')
            if await sk.count() > 0: await sk.first.click(); await asyncio.sleep(2); continue
            ct = page.locator('button:has-text("Continue")')
            if await ct.count() > 0: await ct.first.click(); await asyncio.sleep(3); continue
            break

        # Free plan Stripe checkout
        if "stripe.com" in page.url:
            print("[4] Stripe Free plan checkout...")
            await fill_all_stripe(page)
            print("[5] Waiting for redirect (up to 60s)...")
            for i in range(60):
                await asyncio.sleep(1)
                if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                    print(f"  ✅ Redirected in {i+1}s!"); break
                if i == 30: print("  Still waiting...")
            print(f"  URL: {page.url[:80]}")

        # Pro upgrade
        print("[6] Pro upgrade...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        pro = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
        if await pro.count() > 0:
            print(f"  [+] Clicking '{await pro.first.inner_text()}'...")
            await pro.first.click(); await asyncio.sleep(5)
            if "stripe.com" in page.url:
                await fill_all_stripe(page)
                for i in range(60):
                    await asyncio.sleep(1)
                    if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                        print(f"  ✅ Pro redirect in {i+1}s!"); break

        # API key
        print("[7] API key...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        html = await page.content()
        m = re.search(r"hop_\w{40,}", html)
        if m:
            print(f"🔥🔥🔥 KEY: {m.group(0)}")
            requests.post("http://localhost:8085/api/keys", json={"key": m.group(0), "label": acc["login"]})
        else:
            cb = page.locator('button:has-text("Create")')
            if await cb.count() > 0:
                await cb.first.click(); await asyncio.sleep(2)
                ni = page.locator('input[placeholder*="name"]')
                if await ni.count() > 0: await ni.first.fill(f"{acc['login']}-key")
                cf = page.locator('button:has-text("Create"):not(:has-text("Repository"))')
                if await cf.count() > 0: await cf.last.click(); await asyncio.sleep(3)
                m2 = re.search(r"hop_\w{40,}", await page.content())
                if m2:
                    print(f"🔥🔥🔥 KEY: {m2.group(0)}")
                    requests.post("http://localhost:8085/api/keys", json={"key": m2.group(0), "label": acc["login"]})

        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())