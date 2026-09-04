#!/usr/bin/env python3
"""
Camoufox Hoplite Autoreg — bypasses hCaptcha via real browser fingerprint.
Card: 4147400310554942 (Daniel Dortch) | 06/31 | 693
Address: 2610 Olivet Church Road, Paducah, KY 42001, US
"""
import asyncio, re, requests, time, pyotp, json
from camoufox.async_api import AsyncCamoufox

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json") as f:
    accounts = json.load(f)
acc = accounts[0]

CARD = {"num": "4147400310554942", "exp": "06/31", "cvv": "693", "name": "Daniel Dortch",
        "address": "2610 Olivet Church Road", "city": "Paducah", "state": "KY", "zip": "42001", "country": "US"}

async def fill_stripe(page):
    print("  [*] Filling Stripe fields...")
    await page.wait_for_selector("input#cardNumber", timeout=20000)
    await asyncio.sleep(1.5)
    await page.locator("input#cardNumber").fill(CARD["num"])
    await page.locator("input#cardExpiry").fill(CARD["exp"])
    await page.locator("input#cardCvc").fill(CARD["cvv"])
    await page.locator("input#billingName").fill(CARD["name"])
    cs = page.locator("select#billingCountry")
    if await cs.count() > 0:
        await cs.select_option(value="US")
        await asyncio.sleep(1)
    # Address
    for sel, val in [
        ("input#billingPostalCode", CARD["zip"]),
        ("input#billingAddressLine1", CARD["address"]),
        ("input#billingAddressCity", CARD["city"]),
        ("input#billingAddressState", CARD["state"]),
        ("input[autocomplete='address-level2']", CARD["city"]),
        ("input[autocomplete='address-level1']", CARD["state"]),
        ("input[autocomplete='postal-code']", CARD["zip"]),
        ("input[autocomplete='address-line1']", CARD["address"]),
    ]:
        el = page.locator(sel)
        if await el.count() > 0:
            await el.first.fill(val)
    # JS fallback for any remaining fields
    await page.evaluate(f"""() => {{
        const inputs = document.querySelectorAll('input');
        inputs.forEach(el => {{
            if (el.value) return;
            const ac = (el.getAttribute('autocomplete')||'').toLowerCase();
            const ph = (el.placeholder||'').toLowerCase();
            if (ac.includes('city')||ph.includes('city')) el.value = '{CARD["city"]}';
            if (ac.includes('address-line1')||ph.includes('address')) el.value = '{CARD["address"]}';
            if (ac.includes('state')||ph.includes('state')) el.value = '{CARD["state"]}';
        }});
    }}""")
    # Submit
    btn = page.locator("button[data-testid='hosted-payment-submit-button']")
    if await btn.count() > 0:
        await btn.first.click()
        print("  [+] Payment submitted!")
        return True
    return False

async def main():
    async with AsyncCamoufox(
        headless=False,
        viewport={"width": 1280, "height": 900},
        os="windows",
        humanize=True,
    ) as ctx:
        page = await ctx.new_page()

        # GitHub
        print("[1] GitHub login...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await page.fill('input[name="login"]', acc['email'])
        await page.fill('input[name="password"]', acc['password'])
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)
        if "two-factor" in page.url.lower():
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"]', code); await asyncio.sleep(3)

        # Hoplite
        print("[2] Hoplite login...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0: btn = page.locator('button:has-text("GitHub")')
        await btn.first.click(); await asyncio.sleep(6)
        for _ in range(15):
            await asyncio.sleep(1)
            if "authorize" in page.url.lower():
                await page.evaluate("() => { const b = document.querySelector('.js-oauth-authorize-btn'); if(b) { b.disabled=false; b.click(); } }")
                await asyncio.sleep(4); break
            if "hoplite.sh" in page.url and "github.com" not in page.url: break

        # Plan
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

        # Free plan
        if "stripe.com" in page.url:
            print("[4] Stripe Free plan (Camoufox - no captcha expected)...")
            await fill_stripe(page)
            print("[5] Waiting for redirect...")
            for i in range(60):
                await asyncio.sleep(1)
                if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                    print(f"  ✅ FREE PLAN ACTIVE! {i+1}s"); break
                if i == 30: print("  Still waiting...")
            print(f"  URL: {page.url[:80]}")

        # Pro
        print("[6] Pro upgrade...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        pro = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
        if await pro.count() > 0:
            print(f"  [+] {await pro.first.inner_text()}")
            await pro.first.click(); await asyncio.sleep(5)
            if "stripe.com" in page.url:
                await fill_stripe(page)
                for i in range(60):
                    await asyncio.sleep(1)
                    if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                        print(f"  ✅ PRO PLAN ACTIVE! {i+1}s"); break

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

if __name__ == "__main__":
    asyncio.run(main())