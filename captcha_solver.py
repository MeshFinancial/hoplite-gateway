#!/usr/bin/env python3
"""
Captcha Solver Helper for Hoplite Autoreg
Supports 2Captcha, Anti-Captcha, and CapSolver for hCaptcha and reCAPTCHA v2/v3.
Preloaded with user's verified active keys.
"""

import time
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger("captcha-solver")

# Preloaded verified keys with balances
CAPTCHA_KEYS = {
    "twocaptcha": [
        {"key": "bd9c67bafe49a8410846e953fd04ff49", "balance": 1034.32},
        {"key": "3d6b16424408f7b5b749889a7f15faf9", "balance": 57.42},
        {"key": "93a6d9febdebb6478e1df00e70e5f28d", "balance": 29.33},
        {"key": "ca0a75cf17cea899a47ca76e75db6735", "balance": 9.89},
        {"key": "6452c73ab281db0526ba83e724bb983c", "balance": 9.15},
    ],
    "anticaptcha": [
        {"key": "73531525aa745ed8fd1b4be8c6181c8d", "balance": 34.16},
        {"key": "03ea83a89c837abf30695d43a93c0f29", "balance": 25.33},
        {"key": "ca730f6b32064d93f875d102855ebe70", "balance": 5.54},
    ],
    "capsolver": [
        {"key": "CAP-66B5020737DCA5974EC946068AA9C8A6", "balance": 23.39},
    ]
}


class CaptchaSolver:
    def __init__(self, primary_provider: str = "twocaptcha", key: Optional[str] = None):
        self.provider = primary_provider
        self.key = key or CAPTCHA_KEYS["twocaptcha"][0]["key"]

    def get_balance(self) -> float:
        """Fetch current balance for active provider."""
        try:
            if self.provider == "twocaptcha":
                url = f"https://2captcha.com/res.php?key={self.key}&action=getbalance&json=1"
                r = requests.get(url, timeout=10).json()
                if r.get("status") == 1:
                    return float(r.get("request", 0))
            elif self.provider == "anticaptcha":
                url = "https://api.anti-captcha.com/getBalance"
                r = requests.post(url, json={"clientKey": self.key}, timeout=10).json()
                if r.get("errorId") == 0:
                    return float(r.get("balance", 0))
            elif self.provider == "capsolver":
                url = "https://api.capsolver.com/getBalance"
                r = requests.post(url, json={"clientKey": self.key}, timeout=10).json()
                if r.get("errorId") == 0:
                    return float(r.get("balance", 0))
        except Exception as e:
            logger.warning(f"Balance check error: {e}")
        return 0.0

    def solve_hcaptcha(self, sitekey: str, pageurl: str, rqdata: Optional[str] = None, timeout: int = 120) -> Optional[str]:
        """Solves hCaptcha challenge via 2Captcha."""
        logger.info(f"Solving hCaptcha on {pageurl} (sitekey: {sitekey[:12]}...)")
        try:
            # 1. Submit task
            submit_url = "https://2captcha.com/in.php"
            payload = {
                "key": self.key,
                "method": "hcaptcha",
                "sitekey": sitekey,
                "pageurl": pageurl,
                "json": 1
            }
            if rqdata:
                payload["data"] = rqdata

            r = requests.post(submit_url, data=payload, timeout=15).json()
            if r.get("status") != 1:
                logger.error(f"2Captcha submit error: {r.get('request')}")
                return None

            request_id = r.get("request")
            logger.info(f"2Captcha task queued, ID: {request_id}")

            # 2. Poll for solution
            poll_url = f"https://2captcha.com/res.php?key={self.key}&action=get&id={request_id}&json=1"
            start_time = time.time()
            time.sleep(5)

            while time.time() - start_time < timeout:
                time.sleep(3)
                poll_resp = requests.get(poll_url, timeout=15).json()
                if poll_resp.get("status") == 1:
                    token = poll_resp.get("request")
                    logger.info(f"[+] hCaptcha solved successfully! Token: {token[:20]}...")
                    return token
                if poll_resp.get("request") != "CAPCHA_NOT_READY":
                    logger.error(f"2Captcha poll error: {poll_resp.get('request')}")
                    return None

            logger.error("2Captcha solve timed out")
        except Exception as e:
            logger.error(f"hCaptcha solve exception: {e}")
        return None

    def solve_recaptcha_v3(self, sitekey: str, pageurl: str, action: str = "login", min_score: float = 0.9, timeout: int = 120) -> Optional[str]:
        """Solves Google reCAPTCHA v3 with high human score."""
        logger.info(f"Solving reCAPTCHA v3 on {pageurl} (action: {action})")
        try:
            submit_url = "https://2captcha.com/in.php"
            payload = {
                "key": self.key,
                "method": "userrecaptcha",
                "version": "v3",
                "action": action,
                "min_score": str(min_score),
                "googlekey": sitekey,
                "pageurl": pageurl,
                "json": 1
            }
            r = requests.post(submit_url, data=payload, timeout=15).json()
            if r.get("status") != 1:
                return None

            request_id = r.get("request")
            poll_url = f"https://2captcha.com/res.php?key={self.key}&action=get&id={request_id}&json=1"
            start_time = time.time()
            time.sleep(5)

            while time.time() - start_time < timeout:
                time.sleep(3)
                poll_resp = requests.get(poll_url, timeout=15).json()
                if poll_resp.get("status") == 1:
                    token = poll_resp.get("request")
                    logger.info(f"[+] reCAPTCHA v3 solved! Token: {token[:20]}...")
                    return token
                if poll_resp.get("request") != "CAPCHA_NOT_READY":
                    return None
        except Exception as e:
            logger.error(f"reCAPTCHA v3 exception: {e}")
        return None


if __name__ == "__main__":
    solver = CaptchaSolver()
    bal = solver.get_balance()
    print(f"Active 2Captcha Key: {solver.key[:8]}... Balance: ${bal:.2f}")
