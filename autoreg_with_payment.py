#!/usr/bin/env python3
"""
Hoplite.sh Full Auto-Registration Pipeline with Plan Selection & Payment Card Automation.
- Uses accounts from gh_accounts.json
- Handles GitHub OAuth + TOTP + App Authorization
- Selects Free Plan -> Enters Test Card (4874100085748500, 05/30, 808) -> Completes
- Upgrades to Pro Plan with the same card
- Extracts/Creates API Key -> Provisions Project -> Updates store.json & .env
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

import pyotp
import requests
from playwright.async_api import async_playwright, Page, Frame

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("hoplite-reg")

BASE_DIR = Path(r"C:\Users\User\tmp\hoplite-gateway")
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STORE_FILE = DATA_DIR / "store.json"
KEYS_FILE = DATA_DIR / "hoplite_keys.json"
ACCOUNTS_FILE = DATA_DIR / "gh_accounts.json"
ENV_FILE = BASE_DIR / ".env"

CARD_NUMBER = "4874100085748500"
CARD_EXPIRY = "05/30"
CARD_CVV = "808"
CARD_ZIP = "10001"

HOPLITE_API = "https://api.hoplite.sh"
HOPLITE_APP = "https://app.hoplite.sh"


def load_store() -> dict:
    if STORE_FILE.exists():
        try:
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "keys": [],
        "settings": {
            "port": 8085,
            "default_model": "claude-sonnet-5",
            "gateway_key": "sk-hoplite-gateway",
            "max_concurrent": 3
        }
    }


def save_store(store: dict):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def load_keys_record() -> list:
    if KEYS_FILE.exists():
        try:
            with open(KEYS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_keys_record(records: list):
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def sync_env_file(keys: list, project_id: Optional[str] = None):
    api_keys = [k["key"] for k in keys if k.get("status") == "live" and k.get("key")]
    env_content = [
        "# Hoplite Gateway Configuration",
        f"HOPLITE_API_BASE={HOPLITE_API}",
        f"GATEWAY_API_KEY=sk-hoplite-gateway",
        f"PORT=8085",
        f"MAX_CONCURRENT=5",
        f"HOPLITE_API_KEYS={','.join(api_keys)}",
    ]
    if project_id:
        env_content.append(f"HOPLITE_PROJECT_ID={project_id}")
    elif keys and keys[0].get("projectId"):
        env_content.append(f"HOPLITE_PROJECT_ID={keys[0]['projectId']}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(env_content) + "\n")


def verify_and_provision_key(key: str, label: str = "custom") -> Dict[str, Any]:
    headers = {"X-Api-Key": key, "Content-Type": "application/json"}
    try:
        r = requests.get(f"{HOPLITE_API}/api/model-providers", headers=headers, timeout=15)
        if r.status_code != 200:
            return {"valid": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}

    project_id = None
    project_name = None
    try:
        r = requests.get(f"{HOPLITE_API}/api/projects", headers=headers, timeout=15)
        if r.status_code == 200:
            ps = r.json().get("projects", [])
            if ps:
                project_id = ps[0].get("id")
                project_name = ps[0].get("name")
        if not project_id:
            logger.info(f"Creating project for {label}...")
            r_c = requests.post(
                f"{HOPLITE_API}/api/projects",
                headers=headers,
                json={"name": f"{label}/workspace", "defaultBranch": "main"},
                timeout=15
            )
            if r_c.status_code in (200, 201):
                p_data = r_c.json().get("project", {})
                project_id = p_data.get("id")
                project_name = p_data.get("name")
    except Exception as e:
        logger.warning(f"Provisioning error: {e}")

    return {
        "valid": True,
        "key": key,
        "projectId": project_id or "proj_2857d93259a84fd9ac7dffe8dbae5330",
        "projectName": project_name,
        "status": "live",
        "error": None
    }


def add_key_to_store(key: str, project_id: Optional[str] = None, label: str = "custom"):
    prov = verify_and_provision_key(key, label)
    if not prov.get("valid"):
        logger.error(f"Cannot add invalid key: {prov.get('error')}")
        return False

    pid = project_id or prov.get("projectId")
    store = load_store()
    existing = next((k for k in store["keys"] if k["key"] == key), None)
    if existing:
        existing["status"] = "live"
        existing["projectId"] = pid
        existing["label"] = label
        existing["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    else:
        store["keys"].append({
            "id": f"hoplite_{label}_{int(time.time())}",
            "key": key,
            "projectId": pid,
            "label": label,
            "status": "live",
            "credits_total": 0,
            "credits_used": 0,
            "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
    save_store(store)

    records = load_keys_record()
    rec = next((r for r in records if r.get("key") == key), None)
    if rec:
        rec["status"] = "ok"
        rec["projectId"] = pid
    else:
        records.append({
            "login": label,
            "email": f"{label}@authed",
            "key": key,
            "projectId": pid,
            "status": "ok",
            "created_at": time.time()
        })
    save_keys_record(records)
    sync_env_file(store["keys"], pid)
    logger.info(f"[+] Key saved! Project: {pid}")
    return True


async def handle_stripe_card_input(page: Page) -> bool:
    """Detects and fills Stripe or custom card inputs across all frames."""
    logger.info("Checking for credit card inputs...")
    card_filled = False

    # Check all frames (Stripe renders inside iframes)
    for frame in page.frames:
        try:
            # Check for card number field
            card_num_sel = 'input[name="cardnumber"], input[placeholder*="Card number"], input[autocomplete="cc-number"], input[data-elements-stable-field-name="cardNumber"]'
            if await frame.locator(card_num_sel).count() > 0:
                logger.info(f"Found card number input in frame: {frame.url[:60]}")
                await frame.fill(card_num_sel, CARD_NUMBER)
                await asyncio.sleep(0.5)
                card_filled = True

            # Expiry
            exp_sel = 'input[name="exp-date"], input[placeholder*="MM / YY"], input[placeholder*="MM/YY"], input[autocomplete="cc-exp"]'
            if await frame.locator(exp_sel).count() > 0:
                logger.info("Found expiry input in frame")
                await frame.fill(exp_sel, CARD_EXPIRY)
                await asyncio.sleep(0.5)

            # CVC
            cvc_sel = 'input[name="cvc"], input[placeholder*="CVC"], input[placeholder*="CVV"], input[autocomplete="cc-csc"]'
            if await frame.locator(cvc_sel).count() > 0:
                logger.info("Found CVC input in frame")
                await frame.fill(cvc_sel, CARD_CVV)
                await asyncio.sleep(0.5)

            # Postal code / ZIP if present
            zip_sel = 'input[name="postal"], input[placeholder*="ZIP"], input[name="postalCode"]'
            if await frame.locator(zip_sel).count() > 0:
                logger.info("Found postal code input in frame")
                await frame.fill(zip_sel, CARD_ZIP)
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.debug(f"Frame check error: {e}")

    # Also check top-level page
    try:
        num_input = page.locator('input[placeholder*="Card number"], input[name*="card"]')
        if await num_input.count() > 0:
            logger.info("Found card input on main page")
            await num_input.first.fill(CARD_NUMBER)
            card_filled = True
    except Exception:
        pass

    if card_filled:
        logger.info("[+] Card details entered successfully!")
        # Find and click Submit / Pay / Start trial / Subscribe button
        for btn_text in ["Subscribe", "Start free", "Start trial", "Pay", "Confirm", "Save card", "Continue"]:
            submit_btn = page.locator(f'button:has-text("{btn_text}")')
            if await submit_btn.count() > 0:
                logger.info(f"Clicking payment button: '{btn_text}'")
                await submit_btn.first.click()
                await asyncio.sleep(5)
                return True
    return card_filled


async def register_single_account(acc: dict, browser) -> Dict[str, Any]:
    email = acc["email"]
    password = acc["password"]
    totp_secret = acc["totp"]
    login = acc["login"]

    logger.info("=" * 60)
    logger.info(f"REGISTERING: {login} ({email})")
    logger.info("=" * 60)

    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    page = await context.new_page()

    # Route filter for telemetry to prevent hangs
    await page.route(
        lambda u: any(x in u for x in ["datadoghq", "sentry.io", "dubcdn", "telemetry"]),
        lambda r: r.abort()
    )

    try:
        # 1. Open Hoplite login with plan=free
        logger.info("[1/7] Opening login page...")
        await page.goto(f"{HOPLITE_APP}/login?plan=free&interval=monthly", wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(4)

        # 2. Click Continue with GitHub
        logger.info("[2/7] Clicking GitHub button...")
        btn = page.locator('button[aria-label="Continue with GitHub"]')
        if await btn.count() == 0:
            btn = page.locator('button:has-text("GitHub")')
        await btn.first.click()

        # 3. Wait for GitHub navigation (PKCE handshake)
        logger.info("[3/7] Waiting for redirect to GitHub...")
        reached_gh = False
        for _ in range(15):
            await asyncio.sleep(1)
            if "github.com" in page.url:
                reached_gh = True
                break

        if reached_gh and "github.com/login" in page.url:
            logger.info("[4/7] Submitting GitHub credentials...")
            await page.wait_for_selector('input[name="login"]', timeout=12000)
            await page.fill('input[name="login"]', email)
            await page.fill('input[name="password"]', password)
            await page.click('input[type="submit"]')
            await asyncio.sleep(4)

            # TOTP 2FA
            if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
                logger.info("[4b/7] Entering TOTP...")
                code = pyotp.TOTP(totp_secret).now()
                otp_field = page.locator('input[name="app_otp"], input[id="otp"]')
                if await otp_field.count() > 0:
                    await otp_field.first.fill(code)
                    await asyncio.sleep(1)
                    v_btn = page.locator('button:has-text("Verify"), input[type="submit"]')
                    if await v_btn.count() > 0:
                        await v_btn.first.click()
                    await asyncio.sleep(5)

            # OAuth Consent / Authorize
            if "authorize" in page.url.lower() or await page.locator('#js-oauth-authorize-btn').count() > 0:
                logger.info("[4c/7] Authorizing Hoplite OAuth app...")
                auth_btn = page.locator('#js-oauth-authorize-btn, button:has-text("Authorize")')
                if await auth_btn.count() > 0:
                    await auth_btn.first.click()
                await asyncio.sleep(5)

        # 4. Wait for redirect back to Hoplite
        logger.info("[5/7] Waiting for redirect to Hoplite app...")
        for _ in range(20):
            await asyncio.sleep(1)
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                break

        await asyncio.sleep(4)
        logger.info(f"Landed on: {page.url}")

        # 5. Handle Plan Selection & Payment Form
        logger.info("[6/7] Checking for plan selection / payment form...")
        # Check if plan buttons exist
        free_plan_btn = page.locator('button:has-text("Start free"), button:has-text("Free"), div:has-text("Free") button')
        if await free_plan_btn.count() > 0:
            logger.info("Clicking Free plan button...")
            await free_plan_btn.first.click()
            await asyncio.sleep(3)

        # Handle Card entry if payment form appears
        await handle_stripe_card_input(page)
        await asyncio.sleep(3)

        # 6. Check if Pro plan upgrade is requested
        pro_btn = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start pro"), button:has-text("Pro")')
        if await pro_btn.count() > 0:
            logger.info("Pro plan button found. Checking if upgrade needed...")
            # If on billing page
            if "billing" in page.url or "pricing" in page.url:
                await pro_btn.first.click()
                await asyncio.sleep(2)
                await handle_stripe_card_input(page)

        # 7. Navigate to API Keys Settings
        logger.info("[7/7] Navigating to API keys settings...")
        await page.goto(f"{HOPLITE_APP}/settings/api-keys", wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(4)

        # Extract or Create Key
        html = await page.content()
        match = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html)

        if not match:
            logger.info("No existing key visible. Attempting to create new key...")
            create_btn = page.locator('button:has-text("Create"), button:has-text("New API Key"), button:has-text("Generate")')
            if await create_btn.count() > 0:
                await create_btn.first.click()
                await asyncio.sleep(2)

                name_input = page.locator('input[placeholder*="name"], input[placeholder*="Name"], input[name="name"]')
                if await name_input.count() > 0:
                    await name_input.first.fill(f"{login}-key")
                    await asyncio.sleep(1)

                confirm_btn = page.locator('button:has-text("Create"):not(:has-text("Repository")), button:has-text("Confirm"), button:has-text("Save")')
                if await confirm_btn.count() > 0:
                    await confirm_btn.last.click()
                    await asyncio.sleep(3)

                html2 = await page.content()
                match = re.search(r'hop_[a-zA-Z0-9_-]{40,}', html2)

        if match:
            key = match.group(0)
            logger.info(f"[SUCCESS] Extracted key: {key[:16]}...{key[-6:]}")
            add_key_to_store(key, label=login)
            return {"email": email, "login": login, "key": key, "status": "ok", "error": None}
        else:
            logger.warning(f"[-] No API key string extracted for {login}")
            return {"email": email, "login": login, "key": None, "status": "no_key", "error": "No key found in DOM"}

    except Exception as e:
        logger.error(f"[-] Exception for {login}: {e}")
        return {"email": email, "login": login, "key": None, "status": "error", "error": str(e)}
    finally:
        await context.close()


async def main():
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    logger.info(f"Loaded {len(accounts)} accounts from {ACCOUNTS_FILE}")

    # Filter out already registered accounts
    store = load_store()
    existing_keys = {k.get("label") for k in store.get("keys", [])}
    records = load_keys_record()
    for r in records:
        if r.get("key") and r.get("status") == "ok":
            existing_keys.add(r.get("login"))

    pending = [a for a in accounts if a["login"] not in existing_keys]
    logger.info(f"Total pending accounts to register: {len(pending)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        for i, acc in enumerate(pending[:10]):  # Batch of 10
            logger.info(f"\n[{i+1}/{min(10, len(pending))}] Starting account: {acc['login']}")
            res = await register_single_account(acc, browser)
            if res.get("key"):
                logger.info(f"[+] Successfully registered: {acc['login']}")
            else:
                logger.warning(f"[-] Account {acc['login']} finished without key: {res.get('error')}")
            await asyncio.sleep(4)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
