#!/usr/bin/env python3
"""
Hoplite Auto-Registration & LiteLLM Gateway Automation Pipeline
═════════════════════════════════════════════════════════════════════
1. GitHub OAuth + TOTP in Real Chrome
2. Workspace & GitHub App Setup (Automatic Project Creation)
3. Free Plan Checkout on Stripe (Card: 4874100085748500, 05/30, 674)
4. Pro Plan Upgrade Checkout (14-day free trial, $100 credits/mo)
5. Anti-Captcha automated solver for Stripe hCaptcha ($51.92 balance)
6. Extraction of Session Cookies + REST API Key Generation
7. Sandbox / Thread Runner Discovery
8. Full Profile Save (account_profiles.json, store.json, screenshots)
9. Hot-reload into LiteLLM Gateway key pool
═════════════════════════════════════════════════════════════════════
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import pyotp
import requests
from playwright.async_api import async_playwright, Page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("hoplite-pipeline")

BASE_DIR = Path(r"C:\Users\User\tmp\hoplite-gateway")
DATA_DIR = BASE_DIR / "data"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

STORE_FILE = DATA_DIR / "store.json"
KEYS_FILE = DATA_DIR / "hoplite_keys.json"
ACCOUNTS_FILE = DATA_DIR / "gh_accounts.json"
PROFILES_FILE = DATA_DIR / "account_profiles.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
ENV_FILE = BASE_DIR / ".env"

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CARD_NUM = "4874100085748500"
CARD_EXP = "05/30"
CARD_CVV = "674"
CARD_ZIP = "10001"
ANTI_KEY = "03ea83a89c837abf30695d43a93c0f29"

HOPLITE_API = "https://api.hoplite.sh"
HOPLITE_APP = "https://app.hoplite.sh"


def ts() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def load_store() -> dict:
    if STORE_FILE.exists():
        try:
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"keys": [], "settings": {"port": 8085}}


def save_store(store: dict):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def load_profiles() -> list:
    if PROFILES_FILE.exists():
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_profiles(profiles: list):
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)


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


def solve_hcaptcha(sitekey: str, pageurl: str) -> Optional[str]:
    logger.info(f"[CAPTCHA] Solving hCaptcha via Anti-Captcha (key: {ANTI_KEY[:8]}...)...")
    try:
        payload = {
            "clientKey": ANTI_KEY,
            "task": {
                "type": "HCaptchaTaskProxyless",
                "websiteURL": pageurl,
                "websiteKey": sitekey,
                "isInvisible": True
            }
        }
        r = requests.post("https://api.anti-captcha.com/createTask", json=payload, timeout=10).json()
        task_id = r.get("taskId")
        if not task_id:
            logger.error(f"[CAPTCHA] Failed to create task: {r}")
            return None
        logger.info(f"[CAPTCHA] Task created: {task_id}, polling...")

        for _ in range(25):
            time.sleep(3)
            res = requests.post(
                "https://api.anti-captcha.com/getTaskResult",
                json={"clientKey": ANTI_KEY, "taskId": task_id},
                timeout=10
            ).json()
            if res.get("status") == "ready":
                token = res.get("solution", {}).get("gRecaptchaResponse")
                logger.info(f"[CAPTCHA] SOLVED! Token: {token[:20]}...")
                return token
            if res.get("status") == "processing":
                continue
            logger.warning(f"[CAPTCHA] Unexpected status: {res}")
    except Exception as e:
        logger.warning(f"[CAPTCHA] Solver error: {e}")
    return None


async def fill_stripe_card(page: Page, login: str, label: str = "free") -> bool:
    logger.info(f"[*] Entering card details on Stripe Checkout ({label})...")
    try:
        await page.wait_for_selector('input#cardNumber, input[name="cardNumber"]', timeout=20000)
        await asyncio.sleep(1.5)

        # 1. Fill card details
        await page.locator('input#cardNumber, input[name="cardNumber"]').first.fill(CARD_NUM)
        await asyncio.sleep(0.5)
        await page.locator('input#cardExpiry, input[name="cardExpiry"]').first.fill(CARD_EXP)
        await asyncio.sleep(0.5)
        await page.locator('input#cardCvc, input[name="cardCvc"]').first.fill(CARD_CVV)
        await asyncio.sleep(0.5)

        name_i = page.locator('input#billingName, input[name="billingName"]')
        if await name_i.count() > 0:
            await name_i.first.fill(f"{login} User")

        c_sel = page.locator('select#billingCountry, select[name="billingCountry"]')
        if await c_sel.count() > 0:
            try:
                await c_sel.first.select_option(value="US")
            except Exception:
                pass

        z_inp = page.locator('input#billingPostalCode, input[name="billingPostalCode"]')
        if await z_inp.count() > 0:
            await z_inp.first.fill(CARD_ZIP)

        # Screenshot before submit
        await page.screenshot(path=str(SCREENSHOTS_DIR / f"stripe_{label}_{login}_{ts()}.png"))

        # 2. Check for hCaptcha
        hcap_sitekey = "24ed0064-62cf-4d42-9960-5dd1a41d4e29"
        for f in page.frames:
            if "hcaptcha" in f.url:
                m = re.search(r'sitekey=([a-zA-Z0-9_-]+)', f.url)
                if m:
                    hcap_sitekey = m.group(1)
                    break

        token = solve_hcaptcha(hcap_sitekey, page.url)
        if token:
            await page.evaluate(f"""() => {{
                ['h-captcha-response', 'g-recaptcha-response'].forEach(n => {{
                    let el = document.querySelector(`[name="${{n}}"]`);
                    if (!el) {{
                        el = document.createElement('textarea');
                        el.name = n;
                        el.style.display = 'none';
                        document.body.appendChild(el);
                    }}
                    el.value = "{token}";
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }});
                try {{ window.hcaptcha && window.hcaptcha.setData({{ response: "{token}" }}); }} catch(e) {{}}
            }}""")
            await asyncio.sleep(1)

        # 3. Submit payment
        sub = page.locator('button[data-testid="hosted-payment-submit-button"], button[type="submit"]')
        if await sub.count() > 0:
            btn_text = await sub.first.inner_text()
            logger.info(f"[+] Submitting payment ({label}): '{btn_text}'...")
            await sub.first.click()
            await asyncio.sleep(6)
            await page.screenshot(path=str(SCREENSHOTS_DIR / f"stripe_submitted_{label}_{login}_{ts()}.png"))
            return True
        else:
            logger.warning(f"[!] No submit button found on Stripe ({label})")
            await page.screenshot(path=str(SCREENSHOTS_DIR / f"stripe_no_submit_{label}_{login}_{ts()}.png"))
    except Exception as e:
        logger.warning(f"[!] Stripe fill exception ({label}): {e}")
        await page.screenshot(path=str(SCREENSHOTS_DIR / f"stripe_error_{label}_{login}_{ts()}.png"))
    return False


def create_api_key_via_rest(hop_cookies: dict, org_id, login: str) -> Optional[str]:
    """Directly calls Better-Auth REST API to generate an organization API key."""
    if not org_id:
        logger.warning("[API KEY] No org_id, skipping REST creation")
        return None
    logger.info(f"[API KEY] Generating via Better-Auth REST for org {org_id}...")
    cookie_header = "; ".join(f"{k}={v}" for k, v in hop_cookies.items())
    headers = {
        "Cookie": cookie_header,
        "Origin": "https://app.hoplite.sh",
        "Referer": "https://app.hoplite.sh/settings/api-keys",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    payload = {
        "name": f"{login}-gateway-key",
        "organizationId": org_id
    }
    try:
        r = requests.post(f"{HOPLITE_API}/api/auth/api-key/create", headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            key = data.get("key")
            if key:
                logger.info(f"🔥 [API KEY] CREATED: {key[:16]}...{key[-6:]} 🔥")
                return key
            else:
                logger.warning(f"[API KEY] Response OK but no key: {data}")
        else:
            logger.warning(f"[API KEY] Creation failed ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        logger.error(f"[API KEY] Creation error: {e}")
    return None


def extract_sandbox_info(api_key: str, hop_cookies: dict, org_id: str, project_id: str) -> dict:
    """Query Hoplite API for sandbox / thread runner / preview details."""
    sandbox_info = {
        "sandboxes": [],
        "preview_urls": [],
        "thread_runners": [],
        "active_servers": []
    }

    cookie_header = "; ".join(f"{k}={v}" for k, v in hop_cookies.items())
    auth_headers = {
        "Cookie": cookie_header,
        "Origin": "https://app.hoplite.sh",
        "User-Agent": "Mozilla/5.0"
    }
    api_headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

    # 1. Try to get threads (which may have sandbox/runner info)
    try:
        r = requests.get(f"{HOPLITE_API}/api/threads", headers=auth_headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            threads = data.get("threads", [])
            logger.info(f"[SANDBOX] Found {len(threads)} threads")
            for t in threads[:5]:
                tinfo = {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "status": t.get("status"),
                    "model": t.get("model"),
                    "preview_url": t.get("previewUrl"),
                    "preview_port": t.get("previewPort"),
                }
                sandbox_info["thread_runners"].append(tinfo)
                if t.get("previewUrl"):
                    sandbox_info["preview_urls"].append(t["previewUrl"])
    except Exception as e:
        logger.debug(f"[SANDBOX] Thread query error: {e}")

    # 2. Try sandbox endpoints
    for ep in ["/api/sandboxes", "/api/active-sandboxes", "/api/servers"]:
        try:
            r = requests.get(f"{HOPLITE_API}{ep}", headers=auth_headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data.get("sandboxes") or data.get("servers") or data.get("active", [])
                if isinstance(items, list) and items:
                    logger.info(f"[SANDBOX] {ep}: {len(items)} entries")
                    for item in items[:5]:
                        sandbox_info["sandboxes"].append({
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "status": item.get("status"),
                            "url": item.get("url") or item.get("previewUrl"),
                            "port": item.get("port") or item.get("previewPort"),
                        })
                        if item.get("url") or item.get("previewUrl"):
                            sandbox_info["preview_urls"].append(
                                item.get("url") or item.get("previewUrl")
                            )
        except Exception as e:
            logger.debug(f"[SANDBOX] {ep} error: {e}")

    # 3. Query projects for sandbox config
    if project_id:
        try:
            r = requests.get(f"{HOPLITE_API}/api/projects/{project_id}", headers=api_headers, timeout=10)
            if r.status_code == 200:
                proj = r.json().get("project", {})
                srv = proj.get("servers", []) or proj.get("sandboxes", [])
                if srv:
                    for s in srv:
                        sandbox_info["active_servers"].append({
                            "id": s.get("id"),
                            "name": s.get("name"),
                            "status": s.get("status"),
                            "url": s.get("url") or s.get("previewUrl"),
                            "port": s.get("port") or s.get("previewPort"),
                        })
        except Exception as e:
            logger.debug(f"[SANDBOX] Project query error: {e}")

    logger.info(f"[SANDBOX] Summary: {len(sandbox_info['sandboxes'])} sandboxes, "
                f"{len(sandbox_info['preview_urls'])} preview URLs, "
                f"{len(sandbox_info['thread_runners'])} thread runners")
    return sandbox_info


async def register_account(acc: dict, browser, headless: bool = True) -> Dict[str, Any]:
    email = acc["email"]
    password = acc["password"]
    totp_secret = acc["totp"]
    login = acc["login"]

    milestone_start = time.time()
    logger.info("=" * 60)
    logger.info(f"  STARTING AUTOREG: {login} ({email}) at {ts()}")
    logger.info("=" * 60)

    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = await context.new_page()

    # Telemetry abort to prevent network stalls
    await page.route(
        lambda u: any(x in u for x in ["datadoghq", "sentry.io", "dubcdn"]),
        lambda r: r.abort()
    )

    try:
        # ════════════════════════════════════════════════════════════════
        # Step 1: Login GitHub
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [1/8] GitHub login for {email}...")
        await page.goto("https://github.com/login", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)
        await page.fill('input[name="login"]', email)
        await page.fill('input[name="password"]', password)
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)

        if "two-factor" in page.url.lower() or await page.locator('input[name="app_otp"]').count() > 0:
            code = pyotp.TOTP(totp_secret).now()
            logger.info(f"[+] TOTP code {code} entered for {login}")
            await page.fill('input[name="app_otp"], input[id="otp"]', code)
            for _ in range(8):
                await asyncio.sleep(1)
                if "two-factor" not in page.url.lower():
                    break
        logger.info(f"[+] GitHub login OK ({login})")

        # ════════════════════════════════════════════════════════════════
        # Step 2: Open Hoplite & OAuth redirect
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [2/8] Opening Hoplite + GitHub OAuth...")
        await page.goto(f"{HOPLITE_APP}/login?plan=free&interval=monthly", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        # Wait for the page to fully render - check for any button with GitHub text
        btn = None
        for sel in ['button[aria-label="Continue with GitHub"]', 'button:has-text("GitHub")', 'button:has-text("github")', 'button:has-text("Continue")']:
            b = page.locator(sel)
            if await b.count() > 0:
                btn = b; break

        if btn:
            await btn.first.click()
            await asyncio.sleep(2)
        else:
            logger.warning("[!] No GitHub login button found on Hoplite")
            await page.screenshot(path=str(SCREENSHOTS_DIR / f"no_gh_btn_{login}_{ts()}.png"))

        # ════════════════════════════════════════════════════════════════
        # Step 3: OAuth Authorize
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [3/8] Waiting for OAuth consent...")
        oauth_ok = False
        popup = None

        # Handle popup - listen for new pages
        async def on_popup(p):
            nonlocal popup; popup = p

        page.on("popup", on_popup)

        for _ in range(30):
            await asyncio.sleep(1)

            # Check popup
            if popup:
                try:
                    await popup.wait_for_load_state("networkidle", timeout=10000)
                    p_url = popup.url.lower()
                    if "authorize" in p_url or "github.com/login" in p_url:
                        auth_btn = popup.locator('.js-oauth-authorize-btn, button[name="authorize"], #js-oauth-authorize-btn')
                        if await auth_btn.count() > 0:
                            await auth_btn.first.click()
                            await asyncio.sleep(3)
                            oauth_ok = True
                            logger.info("[+] OAuth consent approved via popup")
                            break
                except: pass
                continue

            # Check main page
            if "authorize" in page.url.lower() or "github.com/login/oauth" in page.url:
                await asyncio.sleep(2)
                await page.evaluate("""() => {
                    const b = document.querySelector('.js-oauth-authorize-btn, #js-oauth-authorize-btn, button[name="authorize"]');
                    if (b) { b.disabled = false; b.click(); }
                }""")
                await asyncio.sleep(4)
                oauth_ok = True
                logger.info("[+] OAuth consent approved")
                break
            if "hoplite.sh" in page.url and "github.com" not in page.url:
                oauth_ok = True
                logger.info("[+] Already on Hoplite (OAuth completed)")
                break

        if not oauth_ok:
            logger.warning("[!] OAuth consent may not have been reached")
            await page.screenshot(path=str(SCREENSHOTS_DIR / f"oauth_timeout_{login}_{ts()}.png"))

        await asyncio.sleep(3)

        # ════════════════════════════════════════════════════════════════
        # Step 4: Onboarding
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [4/8] Onboarding steps...")
        await page.screenshot(path=str(SCREENSHOTS_DIR / f"onboarding_start_{login}_{ts()}.png"))

        # Role selection
        r_btn = page.locator('button:has-text("Engineer")')
        if await r_btn.count() > 0:
            await r_btn.first.click()
            logger.info("[+] Role 'Engineer' selected")
            c1 = page.locator('button:has-text("Continue")')
            if await c1.count() > 0:
                await c1.first.click()
            await asyncio.sleep(2)

        # Workspace name
        o_inp = page.locator('input[placeholder*="Acme"]')
        if await o_inp.count() > 0:
            await o_inp.first.fill(f"{login}-org")
            t_btn = page.locator('button:has-text("Just me")')
            if await t_btn.count() > 0:
                await t_btn.first.click()
            c2 = page.locator('button:has-text("Continue")')
            if await c2.count() > 0:
                await c2.first.click()
            await asyncio.sleep(3)
            logger.info(f"[+] Workspace '{login}-org' created")

        # GitHub App Install
        body_text = await page.inner_text("body")
        if "No repositories yet" in body_text or "Install" in body_text:
            logger.info("[+] Installing GitHub App on repositories...")
            await page.goto("https://api.hoplite.sh/api/github/install?returnTo=%2Flogin", wait_until="domcontentloaded")
            await asyncio.sleep(4)
            inst = page.locator('button:has-text("Install"), button:has-text("Save"), input[value*="Install"]')
            if await inst.count() > 0:
                await inst.first.click()
                await asyncio.sleep(5)
                logger.info("[+] GitHub App install triggered")

        # Create project
        cp_btn = page.locator('button:has-text("Create 1 project"), button:has-text("Create project")')
        if await cp_btn.count() > 0:
            await cp_btn.first.click()
            await asyncio.sleep(4)
            logger.info("[+] Project created")

        # Skip CLI setup
        skip_cli = page.locator('button:has-text("Skip for now"), a:has-text("Skip for now")')
        if await skip_cli.count() > 0:
            await skip_cli.first.click()
            await asyncio.sleep(3)
            logger.info("[+] CLI setup skipped")

        # Skip team invite
        body_text = await page.inner_text("body")
        if "Bring Your Team" in body_text:
            skip_team = page.locator('button:has-text("Skip for now"), a:has-text("Skip for now")')
            if await skip_team.count() > 0:
                await skip_team.first.click()
                await asyncio.sleep(3)
                logger.info("[+] Team invite skipped")

        # Starter threads
        body_text = await page.inner_text("body")
        if "starter threads" in body_text.lower() or "Set Up Is All Complete" in body_text:
            thread_opt = page.locator('div:has-text("Sweep for common UX issues"), div:has-text("Tighten test coverage")')
            if await thread_opt.count() > 0:
                await thread_opt.first.click()
                await asyncio.sleep(1)
            cont_threads = page.locator('button:has-text("Continue")')
            if await cont_threads.count() > 0:
                await cont_threads.first.click()
                await asyncio.sleep(4)
                logger.info("[+] Starter threads dismissed")

        await page.screenshot(path=str(SCREENSHOTS_DIR / f"onboarding_done_{login}_{ts()}.png"))

        # ════════════════════════════════════════════════════════════════
        # Step 5: Free Plan -> Stripe Checkout
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [5/8] Free plan selection...")
        free_b = page.locator('button:has-text("Continue with Free")')
        if await free_b.count() > 0:
            await free_b.first.click()
            await asyncio.sleep(5)

        if "stripe.com" in page.url:
            logger.info("[+] On Stripe Checkout for Free plan")
            ok = await fill_stripe_card(page, login, label="free")
            if ok:
                for _ in range(30):
                    await asyncio.sleep(1)
                    if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                        break
                await asyncio.sleep(3)
                logger.info(f"[+] Free plan checkout complete: {page.url}")
            else:
                logger.warning("[!] Free plan card fill may have failed")
        else:
            logger.info("[+] No Stripe redirect for Free plan (may already be on Free)")

        await page.screenshot(path=str(SCREENSHOTS_DIR / f"free_plan_done_{login}_{ts()}.png"))

        # ════════════════════════════════════════════════════════════════
        # Step 6: Pro Plan Upgrade
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [6/8] Pro plan upgrade...")
        try:
            await page.goto(f"{HOPLITE_APP}/settings/workspace/billing", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(4)
            await page.screenshot(path=str(SCREENSHOTS_DIR / f"billing_page_{login}_{ts()}.png"))

            pro_upgrade = page.locator('button:has-text("Upgrade to Pro"), button:has-text("Start 14 days of Pro")')
            if await pro_upgrade.count() > 0:
                btn_text = await pro_upgrade.first.inner_text()
                logger.info(f"[+] Clicking '{btn_text}'...")
                await pro_upgrade.first.click()
                await asyncio.sleep(5)

                if "stripe.com" in page.url:
                    logger.info("[+] On Stripe Checkout for Pro plan")
                    ok = await fill_stripe_card(page, login, label="pro")
                    if ok:
                        for _ in range(30):
                            await asyncio.sleep(1)
                            if "hoplite.sh" in page.url and "stripe.com" not in page.url:
                                break
                        await asyncio.sleep(3)
                        logger.info(f"[+] Pro plan upgrade complete: {page.url}")
                    else:
                        logger.warning("[!] Pro plan card fill may have failed")
                else:
                    logger.info("[+] No Stripe redirect for Pro (may already be on trial)")
            else:
                logger.info("[+] No 'Upgrade to Pro' button found (may already be Pro)")
        except Exception as e:
            logger.debug(f"[!] Pro upgrade error: {e}")

        await page.screenshot(path=str(SCREENSHOTS_DIR / f"pro_plan_done_{login}_{ts()}.png"))

        # ════════════════════════════════════════════════════════════════
        # Step 7: Capture Cookies, Session, Org/Project IDs
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [7/8] Extracting session cookies & metadata...")
        cookies = await context.cookies()
        hop_cookies = {c["name"]: c["value"] for c in cookies if "hoplite" in c["domain"]}
        logger.info(f"[+] Hoplite cookies: {list(hop_cookies.keys())}")
        # Check if we have auth cookies
        auth_cookies = [k for k in hop_cookies if 'auth' in k.lower() or 'session' in k.lower() or 'token' in k.lower()]
        if not auth_cookies:
            logger.warning("[!] No auth cookies found - user may not be logged in")
            # Try to wait for OAuth redirect a bit more
            await asyncio.sleep(3)
            current_url = page.url
            logger.info(f"[!] Current URL: {current_url[:80]}")
            cookies2 = await context.cookies()
            hop_cookies2 = {c["name"]: c["value"] for c in cookies2 if "hoplite" in c["domain"]}
            if hop_cookies2:
                hop_cookies = hop_cookies2
                logger.info(f"[+] Retry cookies: {list(hop_cookies.keys())}")

        # Try to get session info via HTTP request with all cookies
        org_id = None
        user_id = None
        try:
            cookie_header = "; ".join(f"{k}={v}" for k, v in hop_cookies.items())
            r_sess = requests.get("https://api.hoplite.sh/api/auth/get-session", headers={
                "Cookie": cookie_header,
                "Origin": "https://app.hoplite.sh",
                "Referer": "https://app.hoplite.sh/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }, timeout=10)
            if r_sess.status_code == 200:
                sess_data = r_sess.json()
                if isinstance(sess_data, dict):
                    s = sess_data.get('session') or sess_data.get('data', {}).get('session') or sess_data
                    if isinstance(s, dict):
                        org_id = s.get('activeOrganizationId') or s.get('organizationId') or sess_data.get('organizationId')
                        user_id = s.get('userId') or s.get('user', {}).get('id') or sess_data.get('userId')
                logger.info(f'[+] Session: org_id={org_id}, user_id={user_id}')
            else:
                logger.warning(f'[!] Session HTTP {r_sess.status_code}: {r_sess.text[:200]}')
        except Exception as e:
            logger.warning(f'[!] Session error: {e}')

        # ════════════════════════════════════════════════════════════════
        # Step 8: Generate API Key
        # ════════════════════════════════════════════════════════════════
        logger.info(f"[{ts()}] [8/8] Generating API Key...")
        api_key = None
        if org_id:
            api_key = create_api_key_via_rest(hop_cookies, org_id, login)

        if not api_key:
            logger.info("[API KEY] REST creation failed, trying UI fallback...")
            await page.goto(f"{HOPLITE_APP}/settings/api-keys", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            # Check if we're logged in - look for login page
            if "Sign In" in await page.title() or "Login" in await page.title() or await page.locator('button:has-text("Sign In")').count() > 0:
                logger.warning("[!] Not logged in to Hoplite, can't access API keys page")
            else:
                await page.screenshot(path=str(SCREENSHOTS_DIR / f"api_keys_page_{login}_{ts()}.png"))
                # Try to find API key in page content
                page_html = await page.content()
                m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', page_html)
                if m:
                    api_key = m.group(0)
                    logger.info(f"[API KEY] Extracted from UI: {api_key[:16]}...{api_key[-6:]}")
                else:
                    # Try clicking create button
                    create_btn = page.locator('button:has-text("Create")')
                    if await create_btn.count() > 0:
                        await create_btn.first.click()
                        await asyncio.sleep(2)
                        name_input = page.locator('input[placeholder*="name"]')
                        if await name_input.count() > 0:
                            await name_input.first.fill(f"{login}-key")
                            confirm = page.locator('button:has-text("Create"):not(:has-text("Repository"))')
                            if await confirm.count() > 0:
                                await confirm.last.click()
                                await asyncio.sleep(3)
                                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                                if m2:
                                    api_key = m2.group(0)
                                    logger.info(f"[API KEY] Created via UI: {api_key[:16]}...{api_key[-6:]}")

        if api_key:
            # Query project ID
            pid = None
            try:
                r_p = requests.get(f"{HOPLITE_API}/api/projects",
                                   headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
                                   timeout=10)
                if r_p.status_code == 200:
                    ps = r_p.json().get("projects", [])
                    if ps:
                        pid = ps[0].get("id")
                        logger.info(f"[+] Project ID: {pid}")
            except Exception as e:
                logger.debug(f"[!] Project query error: {e}")

            # Extract sandbox info
            sandbox_info = extract_sandbox_info(api_key, hop_cookies, org_id or "", pid or "")

            # Build full profile
            profile = {
                "login": login,
                "email": email,
                "api_key": api_key,
                "project_id": pid or "",
                "org_id": org_id or "",
                "user_id": user_id or "",
                "cookies": hop_cookies,
                "sandbox_info": sandbox_info,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "ok"
            }

            # Save to account_profiles.json
            profiles = load_profiles()
            # Remove old entry for same login
            profiles = [p for p in profiles if p.get("login") != login]
            profiles.append(profile)
            save_profiles(profiles)
            logger.info(f"[+] Profile saved to {PROFILES_FILE.name}")

            # Add to store.json
            store = load_store()
            store["keys"].append({
                "id": f"hoplite_{login}_{int(time.time())}",
                "key": api_key,
                "projectId": pid or "proj_2857d93259a84fd9ac7dffe8dbae5330",
                "label": login,
                "status": "live",
                "credits_total": 100,
                "credits_used": 0,
                "cookies": hop_cookies,
                "sandbox_info": sandbox_info,
                "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
            save_store(store)
            sync_env_file(store["keys"], pid)

            # Save keys record
            recs = load_keys_record()
            recs.append({
                "login": login,
                "email": email,
                "key": api_key,
                "projectId": pid,
                "org_id": org_id,
                "sandbox_count": len(sandbox_info.get("sandboxes", [])),
                "preview_urls": sandbox_info.get("preview_urls", []),
                "status": "ok",
                "created_at": time.time()
            })
            save_keys_record(recs)

            elapsed = time.time() - milestone_start
            logger.info(f"✅ Account {login} FULLY REGISTERED in {elapsed:.0f}s")
            logger.info(f"   Key: {api_key[:16]}...{api_key[-6:]}")
            logger.info(f"   Org: {org_id}")
            logger.info(f"   Project: {pid}")
            logger.info(f"   Sandboxes: {len(sandbox_info.get('sandboxes', []))}")
            logger.info(f"   Preview URLs: {sandbox_info.get('preview_urls', [])}")

            await page.screenshot(path=str(SCREENSHOTS_DIR / f"success_{login}_{ts()}.png"))
            return {"email": email, "login": login, "key": api_key, "status": "ok", "error": None}

        logger.warning(f"[!] No API key obtained for {login}")
        await page.screenshot(path=str(SCREENSHOTS_DIR / f"no_key_{login}_{ts()}.png"))
        return {"email": email, "login": login, "key": None, "status": "no_key", "error": "Failed to create API key"}

    except Exception as e:
        logger.error(f"[!] Error in {login}: {e}")
        await page.screenshot(path=str(SCREENSHOTS_DIR / f"error_{login}_{ts()}.png"))
        return {"email": email, "login": login, "key": None, "status": "error", "error": str(e)}
    finally:
        await context.close()


async def run_batch(count: int = 3, headless: bool = True):
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    store = load_store()
    existing_labels = {k.get("label") for k in store.get("keys", [])}
    pending = [a for a in accounts if a["login"] not in existing_labels]
    # Skip accounts we've already attempted (to avoid broken OAuth state)
    attempted = ["TopDeckhandBlock", "GroundPhasePraise", "Hallpatrench"]
    pending = [a for a in pending if a["login"] not in attempted]

    logger.info(f"Total accounts: {len(accounts)}")
    logger.info(f"Already registered: {len(existing_labels)}")
    logger.info(f"Pending: {len(pending)}. Running batch of {min(count, len(pending))}...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        results = []
        for i, acc in enumerate(pending[:count]):
            logger.info(f"\n{'='*60}")
            logger.info(f"[Batch {i+1}/{min(count, len(pending))}] {acc['login']}")
            logger.info(f"{'='*60}")
            result = await register_account(acc, browser, headless=headless)
            results.append(result)
            await asyncio.sleep(4)

        await browser.close()

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("  BATCH SUMMARY")
        logger.info("=" * 60)
        ok = [r for r in results if r.get("status") == "ok"]
        failed = [r for r in results if r.get("status") != "ok"]
        logger.info(f"  Success: {len(ok)} / {len(results)}")
        for r in ok:
            logger.info(f"    ✅ {r['login']}: {r['key'][:16]}...{r['key'][-6:]}")
        for r in failed:
            logger.info(f"    ❌ {r['login']}: {r.get('error', 'unknown')}")
        logger.info("=" * 60)


def add_key_to_store(key: str, project_id: Optional[str] = None, label: str = "manual") -> bool:
    """Validate key against Hoplite API and add to store.json."""
    try:
        r = requests.get(f"{HOPLITE_API}/api/projects", headers={"X-Api-Key": key, "Content-Type": "application/json"}, timeout=10)
        if r.status_code != 200:
            logger.warning(f"[STORE] Key validation failed: {r.status_code}")
            return False
        store = load_store()
        store["keys"].append({
            "id": f"hoplite_{label}_{int(time.time())}",
            "key": key,
            "projectId": project_id or "proj_2857d93259a84fd9ac7dffe8dbae5330",
            "label": label,
            "status": "live",
            "credits_total": 100,
            "credits_used": 0,
            "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
        save_store(store)
        sync_env_file(store["keys"], project_id)
        logger.info(f"[STORE] Key {label} added to store")
        return True
    except Exception as e:
        logger.error(f"[STORE] Error adding key: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Hoplite Autoreg & LiteLLM Pipeline")
    parser.add_argument("--count", type=int, default=3, help="Number of accounts to register")
    parser.add_argument("--headful", action="store_true", help="Show browser window")
    args = parser.parse_args()
    asyncio.run(run_batch(count=args.count, headless=not args.headful))


if __name__ == "__main__":
    main()