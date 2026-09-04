#!/usr/bin/env python3
"""
Hoplite Auto-Registration: PRO Subscription + Visible GUI Browser (headless=False)
- No stealth overrides, regular Google Chrome GUI
- Logs in with GitHub + TOTP
- Navigates through onboarding
- Selects Pro Plan ("Start 14 days of Pro") / Free -> Pro
- Enters card details on Stripe Checkout (4874100085748500, 05/30, 808)
- Submits payment and waits for return to Hoplite
- Generates and extracts API key from /settings/api-keys
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("hoplite-pro")

BASE_DIR = Path(r"C:\Users\User\tmp\hoplite-gateway")
DATA_DIR = BASE_DIR / "data"

with open(DATA_DIR / "gh_accounts.json", "r", encoding="utf-8") as f:
    accounts = json.load(f)

# Use account 0
acc = accounts[0]
import pyotp

print(f"[+] Running for account: {acc['login']} ({acc['email']})")

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


async def fill_stripe_card_visible(page):
    logger.info("[*] Waiting for Stripe Checkout elements...")
    await page.wait_for_selector('input#cardNumber, input[name="cardNumber"]', timeout=25000)
    await asyncio.sleep(1.5)

    # 1. Card number
    logger.info("[+] Entering card number...")
    card_inp = page.locator('input#cardNumber, input[name="cardNumber"]').first
    await card_inp.click()
    await card_inp.type(CARD_NUM, delay=35)
    await asyncio.sleep(0.5)

    # 2. Expiry
    logger.info("[+] Entering expiry...")
    exp_inp = page.locator('input#cardExpiry, input[name="cardExpiry"]').first
    await exp_inp.click()
    await exp_inp.type(CARD_EXP, delay=35)
    await asyncio.sleep(0.5)

    # 3. CVC
    logger.info("[+] Entering CVC...")
    cvc_inp = page.locator('input#cardCvc, input[name="cardCvc"]').first
    await cvc_inp.click()
    await cvc_inp.type(CARD_CVV, delay=35)
    await asyncio.sleep(0.5)

    # 4. Name
    name_inp = page.locator('input#billingName, input[name="billingName"]')
    if await name_inp.count() > 0:
        logger.info("[+] Entering cardholder name...")
        await name_inp.first.click()
        await name_inp.first.fill(f"{acc['login']} User")
        await asyncio.sleep(0.5)

    # 5. Country: select US
    c_sel = page.locator('select#billingCountry, select[name="billingCountry"]')
    if await c_sel.count() > 0:
        try:
            logger.info("[+] Selecting Country: US...")
            await c_sel.first.select_option(value="US")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"Country select: {e}")

    # 6. Postal code
    zip_inp = page.locator('input#billingPostalCode, input[name="billingPostalCode"]')
    if await zip_inp.count() > 0:
        logger.info("[+] Entering ZIP: 10001...")
        await zip_inp.first.click()
        await zip_inp.first.type(CARD_ZIP, delay=35)
        await asyncio.sleep(0.5)

    # 7. Submit button
    submit_btn = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"]')
    if await submit_btn.count() > 0:
        btn_txt = (await submit_btn.first.inner_text()).replace('\n', ' ')
        logger.info(f"[+] Clicking payment submit: '{btn_txt}'...")
        await submit_btn.first.click()
        logger.info("[*] Payment submitted! Waiting for redirect back to Hoplite...")
        for i in range(30):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                logger.info(f"[+] Redirected to Hoplite in {i+1}s: {page.url}")
                return True
        logger.info(f"URL after 30s: {page.url}")
    return False


async def main():
    async with async_playwright() as p:
        # Launch real Chrome with GUI (NOT headless, standard window)
        logger.info("[1/8] Launching Chrome GUI (visible window)...")
        browser = await p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=False,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # Step 1: GitHub login
        logger.info("[2/8] Logging in to GitHub...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await page.fill('input[name="login"]', acc['email'])
        await page.fill('input[name="password"]', acc['password'])
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)

        if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
            logger.info("[+] Entering GitHub 2FA TOTP...")
            code = pyotp.TOTP(acc['totp']).now()
            await page.fill('input[name="app_otp"], input[id="otp"]', code)
            for _ in range(8):
                await asyncio.sleep(1)
                if "two-factor" not in page.url.lower():
                    break
        logger.info(f"[+] GitHub state: {page.url[:60]}")

        # Step 2: Open Hoplite
        logger.info("[3/8] Opening Hoplite login...")
        await page.goto("https://app.hoplite.sh/login", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        btn = page.locator('button[aria-label="Continue with GitHub"], button:has-text("GitHub")')
        if await btn.count() > 0:
            logger.info("[+] Clicking 'Continue with GitHub'...")
            await btn.first.click()
            await asyncio.sleep(5)

        # Step 3: OAuth Authorize if shown
        for _ in range(12):
            await asyncio.sleep(1)
            if "authorize" in page.url.lower():
                logger.info("[+] Authorizing OAuth app on GitHub...")
                await asyncio.sleep(2)
                await page.evaluate("""() => {
                    const b = document.querySelector('.js-oauth-authorize-btn, #js-oauth-authorize-btn, button[name="authorize"]');
                    if (b) { b.disabled = false; b.click(); }
                }""")
                await asyncio.sleep(4)
                break
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break

        await asyncio.sleep(3)

        # Step 4: Step through any onboarding screens
        logger.info("[4/8] Handling onboarding steps...")
        for _ in range(5):
            await asyncio.sleep(2)
            txt = await page.inner_text("body")

            if "Engineer" in txt:
                logger.info("Selecting Engineer...")
                await page.click('button:has-text("Engineer")')
                await asyncio.sleep(1)
                await page.click('button:has-text("Continue")')
                await asyncio.sleep(3)
                continue

            if "Create Your Workspace" in txt:
                logger.info("Setting workspace name...")
                await page.fill('input[placeholder*="Acme"]', f"{acc['login']}-org")
                await page.click('button:has-text("Just me")')
                await page.click('button:has-text("Continue")')
                await asyncio.sleep(3)
                continue

            if "Create 1 project" in txt:
                logger.info("Clicking 'Create 1 project'...")
                await page.click('button:has-text("Create 1 project")')
                await asyncio.sleep(3)
                continue

            if "Skip for now" in txt:
                logger.info("Clicking 'Skip for now'...")
                await page.click('button:has-text("Skip for now")')
                await asyncio.sleep(3)
                continue

            # Starter threads screen
            if "starter threads" in txt.lower() or "Set Up Is All Complete" in txt:
                logger.info("Selecting starter thread...")
                thread_item = page.locator('div:has-text("Sweep for common UX issues"), div:has-text("Tighten test coverage")')
                if await thread_item.count() > 0:
                    await thread_item.first.click()
                    await asyncio.sleep(1)
                logger.info("Clicking Continue to plan selection...")
                cont_btn = page.locator('button:has-text("Continue")')
                if await cont_btn.count() > 0:
                    await cont_btn.first.click()
                    await asyncio.sleep(4)
                continue

            # If we reach Choose Your Plan
            if "Choose Your Plan" in txt or "Start 14 days of Pro" in txt:
                break

        logger.info(f"[5/8] On Plan screen: {page.url}")

        # Step 5: Choose Pro Plan
        logger.info("[5/8] Selecting PRO PLAN ('Start 14 days of Pro')...")
        pro_btn = page.locator('button:has-text("Start 14 days of Pro")')
        if await pro_btn.count() > 0:
            logger.info("[+] Clicking 'Start 14 days of Pro'...")
            await pro_btn.first.click()
            await asyncio.sleep(5)
        else:
            logger.info("Checking for 'Continue with Free' first...")
            free_btn = page.locator('button:has-text("Continue with Free")')
            if await free_btn.count() > 0:
                await free_btn.first.click()
                await asyncio.sleep(5)

        # Step 6: Fill Stripe Checkout
        logger.info(f"[6/8] Current URL: {page.url}")
        if "stripe.com" in page.url:
            logger.info("[+] On Stripe Checkout! Filling card...")
            await fill_stripe_card_visible(page)
            await asyncio.sleep(4)

        logger.info(f"[7/8] Post-payment URL: {page.url}")

        # If still not upgraded to Pro, open billing page and upgrade
        try:
            logger.info("[*] Checking billing page to confirm Pro status...")
            await page.goto("https://app.hoplite.sh/settings/workspace/billing", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(4)
            b_txt = await page.inner_text("body")
            logger.info(f"Billing text preview: {b_txt[:300].replace(chr(10), ' ')}")

            upg = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
            if await upg.count() > 0:
                logger.info("[+] Clicking Upgrade to Pro from billing page...")
                await upg.first.click()
                await asyncio.sleep(4)
                if "stripe.com" in page.url:
                    await fill_stripe_card_visible(page)
                    await asyncio.sleep(4)
        except Exception as e:
            logger.debug(f"Billing check error: {e}")

        # Step 7: Navigate to API keys
        logger.info("[8/8] Navigating to /settings/api-keys...")
        await page.goto("https://app.hoplite.sh/settings/api-keys", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        logger.info(f"[+] Landed on: {page.url}")

        html = await page.content()
        m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)
        if m:
            logger.info(f"🔥🔥🔥 [SUCCESS] EXTRACTED KEY: {m.group(0)} 🔥🔥🔥")
            key = m.group(0)
            sys.path.insert(0, str(BASE_DIR))
            from autoreg_pipeline import add_key_to_store
            add_key_to_store(key, label=acc["login"])
        else:
            logger.info("Looking for 'Create' / 'New API Key' button...")
            cb = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Generate")')
            if await cb.count() > 0:
                logger.info(f"[+] Clicking '{await cb.first.inner_text()}'...")
                await cb.first.click()
                await asyncio.sleep(2)

                ni = page.locator('input[placeholder*="name"], input[placeholder*="Name"]')
                if await ni.count() > 0:
                    await ni.first.fill(f"{acc['login']}-pro-key")
                    await asyncio.sleep(1)

                conf = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm"), button:has-text("Save")')
                if await conf.count() > 0:
                    await conf.last.click()
                    await asyncio.sleep(3)

                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                if m2:
                    logger.info(f"🔥🔥🔥 [SUCCESS] GENERATED KEY: {m2.group(0)} 🔥🔥🔥")
                    key = m2.group(0)
                    sys.path.insert(0, str(BASE_DIR))
                    from autoreg_pipeline import add_key_to_store
                    add_key_to_store(key, label=acc["login"])
                else:
                    k_body = await page.inner_text("body")
                    logger.info("API keys body:\n" + k_body[:600])

        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
