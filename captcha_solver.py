#!/usr/bin/env python3
"""Captcha solver abstraction — Anti-Captcha, 2captcha, CapSolver."""
import requests, time, logging

logger = logging.getLogger("captcha")

class CaptchaSolver:
    def __init__(self, primary_provider: str = "anticaptcha", key: str = "03ea83a89c837abf30695d43a93c0f29"):
        self.key = key
        self.provider = primary_provider
        self.base_url = {
            "anticaptcha": "https://api.anti-captcha.com",
            "2captcha": "https://api.2captcha.com",
            "capsolver": "https://api.capsolver.com",
        }.get(primary_provider, "https://api.anti-captcha.com")

    def get_balance(self) -> float:
        try:
            r = requests.post(f"{self.base_url}/getBalance", json={"clientKey": self.key}, timeout=10)
            return r.json().get("balance", 0.0)
        except Exception as e:
            logger.warning(f"Balance check failed: {e}")
            return 0.0

    def solve_hcaptcha(self, sitekey: str, pageurl: str) -> str | None:
        payload = {
            "clientKey": self.key,
            "task": {
                "type": "HCaptchaTaskProxyless",
                "websiteURL": pageurl,
                "websiteKey": sitekey,
                "isInvisible": True,
            },
        }
        try:
            r = requests.post(f"{self.base_url}/createTask", json=payload, timeout=10)
            task_id = r.json().get("taskId")
            if not task_id:
                logger.error(f"CreateTask failed: {r.text[:200]}")
                return None
            for _ in range(25):
                time.sleep(3)
                res = requests.post(f"{self.base_url}/getTaskResult", json={"clientKey": self.key, "taskId": task_id}, timeout=10).json()
                if res.get("status") == "ready":
                    token = res["solution"].get("gRecaptchaResponse")
                    logger.info(f"hCaptcha solved: {token[:20]}...")
                    return token
            return None
        except Exception as e:
            logger.error(f"hCaptcha solver error: {e}")
            return None

    def solve_turnstile(self, sitekey: str, pageurl: str) -> str | None:
        payload = {
            "clientKey": self.key,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": pageurl,
                "websiteKey": sitekey,
            },
        }
        try:
            r = requests.post(f"{self.base_url}/createTask", json=payload, timeout=10)
            task_id = r.json().get("taskId")
            if not task_id:
                return None
            for _ in range(25):
                time.sleep(3)
                res = requests.post(f"{self.base_url}/getTaskResult", json={"clientKey": self.key, "taskId": task_id}, timeout=10).json()
                if res.get("status") == "ready":
                    return res["solution"].get("token")
            return None
        except Exception as e:
            logger.error(f"Turnstile solver error: {e}")
            return None