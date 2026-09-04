#!/usr/bin/env python3
"""Quick test: dump all Stripe fields to find city selector."""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True, args=["--no-sandbox"]
        )
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await ctx.new_page()
        await page.goto("https://checkout.stripe.com/c/pay/cs_live_c1zTTKtmwdPg6e8JKkwhN7vxpooAzQa7Bd9kxw", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_selector("input#cardNumber", timeout=15000)
        await asyncio.sleep(2)
        cs = page.locator("select#billingCountry")
        if await cs.count() > 0:
            await cs.select_option(value="US")
            await asyncio.sleep(2)
        fields = await page.evaluate("""
            () => {
                const inputs = document.querySelectorAll("input, select");
                return Array.from(inputs).map(function(i) {
                    return {
                        tag: i.tagName,
                        id: i.id || "",
                        name: i.name || "",
                        placeholder: i.placeholder || "",
                        autocomplete: i.getAttribute("autocomplete") || "",
                        type: i.type || "",
                        value: (i.value || "").substring(0, 20)
                    };
                });
            }
        """)
        for f in fields:
            tag = f["tag"]
            fid = f["id"]
            fname = f["name"]
            fph = f["placeholder"]
            fac = f["autocomplete"]
            ftype = f["type"]
            fval = f["value"]
            print(f"  {tag:6} id={fid:30} name={fname:25} ph={fph:20} ac={fac:20} type={ftype:10} val={fval}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())