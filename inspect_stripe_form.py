#!/usr/bin/env python3
"""Inspect Stripe Checkout page form structure."""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        page = await browser.new_page()
        await page.goto("https://checkout.stripe.com/c/pay/cs_live_c1kTfbENIsIQDRD1UYWM5ErPuDeDJ4gkpmBxVs", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_selector("input#cardNumber", timeout=15000)
        await asyncio.sleep(3)
        
        info = await page.evaluate("""
            () => {
                const form = document.querySelector('form');
                const btn = document.querySelector('button[data-testid="hosted-payment-submit-button"]');
                const allBtns = document.querySelectorAll('button');
                return {
                    formExists: !!form,
                    formAction: form ? form.action : '',
                    formId: form ? form.id : '',
                    btnExists: !!btn,
                    btnText: btn ? btn.innerText.trim() : '',
                    btnDisabled: btn ? btn.disabled : null,
                    btnType: btn ? btn.type : '',
                    allButtons: Array.from(allBtns).map(b => ({
                        text: b.innerText.trim().substring(0, 50),
                        type: b.type,
                        disabled: b.disabled,
                        id: b.id,
                        testid: b.getAttribute('data-testid')
                    })),
                    totalForms: document.querySelectorAll('form').length
                };
            }
        """)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())