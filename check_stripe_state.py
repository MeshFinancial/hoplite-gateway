#!/usr/bin/env python3
"""Check Stripe Checkout page state after payment submission."""
import asyncio, json
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=False, os="windows") as ctx:
        page = await ctx.new_page()
        await page.set_viewport_size({"width": 1280, "height": 900})
        
        # Go to the last Stripe checkout URL
        await page.goto("https://checkout.stripe.com/c/pay/cs_live_c1ej3B4TToVuMXL25manAOKLlLnaV3z9mYMPu7", wait_until="domcontentloaded")
        await asyncio.sleep(5)
        
        # Fill card with card #1: Brian Garcia
        await page.locator("input#cardNumber").fill("372526583853001")
        await page.locator("input#cardExpiry").fill("01/29")
        await page.locator("input#cardCvc").fill("0544")
        await page.locator("input#billingName").fill("Brian Garcia")
        await page.locator("input#billingPostalCode").fill("84770")
        cs = page.locator("select#billingCountry")
        if await cs.count() > 0:
            await cs.select_option(value="US")
            await asyncio.sleep(1)
        
        # Submit
        btn = page.locator("button[data-testid='hosted-payment-submit-button']")
        if await btn.count() > 0:
            await btn.first.click()
            print("[+] Submitted!")
        
        await asyncio.sleep(8)
        
        # Check page state
        state = await page.evaluate("""() => {
            const alerts = [];
            document.querySelectorAll('[role="alert"], .Alert, .FieldError, [class*="error"], p, span').forEach(el => {
                if (el.textContent.trim()) alerts.push(el.textContent.trim().substring(0, 100));
            });
            return {
                url: window.location.href.substring(0, 80),
                title: document.title,
                bodyText: document.body.innerText.substring(0, 500),
                alerts: alerts.filter(a => a.length > 0),
                frames: document.querySelectorAll('iframe').length,
                buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                    text: b.innerText.trim().substring(0, 50),
                    disabled: b.disabled
                }))
            };
        }""")
        print("\n=== PAGE STATE ===")
        print(f"URL: {state['url']}")
        print(f"Title: {state['title']}")
        print(f"Body: {state['bodyText'][:500]}")
        print(f"Alerts: {state['alerts']}")
        print(f"Frames: {state['frames']}")
        for b in state['buttons']:
            print(f"  Button: '{b['text']}' disabled={b['disabled']}")

        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())