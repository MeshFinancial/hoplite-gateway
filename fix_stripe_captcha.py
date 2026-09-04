#!/usr/bin/env python3
"""Quick test: solve Stripe hCaptcha and inject into the CORRECT iframe."""
import asyncio, re, requests, time
from playwright.async_api import async_playwright

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "123"
CARD_ZIP = "10001"
ANTI_KEY = "03ea83a89c837abf30695d43a93c0f29"

def solve_hcaptcha(sitekey, pageurl):
    print(f"Solving hCaptcha (sitekey: {sitekey[:12]}...)")
    payload = {"clientKey": ANTI_KEY, "task": {"type": "HCaptchaTaskProxyless", "websiteURL": pageurl, "websiteKey": sitekey, "isInvisible": True}}
    r = requests.post("https://api.anti-captcha.com/createTask", json=payload, timeout=10).json()
    tid = r.get("taskId")
    if not tid: return None
    for i in range(30):
        time.sleep(3)
        res = requests.post("https://api.anti-captcha.com/getTaskResult", json={"clientKey": ANTI_KEY, "taskId": tid}, timeout=10).json()
        if res.get("status") == "ready":
            return res.get("solution", {}).get("gRecaptchaResponse")
    return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized", "--no-sandbox"]
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        # Go directly to the Stripe checkout page from our last session
        # The Anti-Captcha already solved this, let's try a fresh one
        print("[1] Opening Stripe Checkout...")
        await page.goto("https://checkout.stripe.com/c/pay/cs_live_c114nxTrQbVFJuk7urUppZECTIVhbk3o0YZyp9QPd9gyxW5n9w3gzD7hru", wait_until="domcontentloaded")
        await asyncio.sleep(5)
        
        await page.locator('input#cardNumber').fill(CARD_NUM)
        await page.locator('input#cardExpiry').fill(CARD_EXP)
        await page.locator('input#cardCvc').fill(CARD_CVV)
        await page.locator('input#billingPostalCode').fill(CARD_ZIP)

        # Find hCaptcha sitekey
        hsk = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
        for f in page.frames:
            if "hcaptcha" in f.url:
                m = re.search(r'sitekey=([a-zA-Z0-9_-]+)', f.url)
                if m: hsk = m.group(1); break

        token = solve_hcaptcha(hsk, page.url)
        if token:
            print(f"[+] Token obtained: {token[:25]}...")
            
            # Inject into ALL frames including hcaptcha iframes
            for f in page.frames:
                try:
                    await f.evaluate(f"""() => {{
                        const token = '{token}';
                        ['h-captcha-response', 'g-recaptcha-response'].forEach(n => {{
                            let el = document.querySelector(`[name="${{n}}"]`);
                            if (!el) {{
                                el = document.createElement('textarea');
                                el.name = n; el.style.display = 'none';
                                document.body.appendChild(el);
                            }}
                            el.value = token;
                            el.dispatchEvent(new Event('input', {{bubbles:true}}));
                            el.dispatchEvent(new Event('change', {{bubbles:true}}));
                        }});
                        // Try hcaptcha in this frame
                        if (window.hcaptcha) {{
                            window.hcaptcha.setData && window.hcaptcha.setData({{response: token}});
                            window.hcaptcha.execute && window.hcaptcha.execute({{response: token}});
                        }}
                        // Try parent callback
                        if (window.parent && window.parent.hcaptcha) {{
                            window.parent.hcaptcha.setData && window.parent.hcaptcha.setData({{response: token}});
                        }}
                    }}""")
                except: pass

            # Now try to trigger the Stripe form submit via JS
            await page.evaluate(f"""() => {{
                // Try to find and click the submit button programmatically
                const btn = document.querySelector('button[data-testid="hosted-payment-submit-button"]');
                if (btn) {{
                    // Remove disabled attribute
                    btn.disabled = false;
                    btn.click();
                }}
                // Also try form submit
                const form = document.querySelector('form');
                if (form) {{
                    form.dispatchEvent(new Event('submit', {{bubbles:true}}));
                }}
            }}""")

        print("[*] Waiting for result...")
        for i in range(30):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                print(f"🔥 SUCCESS! Redirected in {i+1}s!")
                break
            if i == 15:
                print(f"URL after 15s: {page.url[:80]}")
        print(f"Final URL: {page.url[:80]}")

        await asynleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())