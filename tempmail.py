from __future__ import annotations

import json
import secrets
import urllib.request


class TempmailError(Exception):
    pass


class TempmailInbox:
    def __init__(self, api_base: str = "https://api.mail.tm"):
        self.api_base = api_base.rstrip("/")
        self._cached_domain: str | None = None

    def get_domain(self) -> str:
        if self._cached_domain:
            return self._cached_domain
        try:
            req = urllib.request.Request(f"{self.api_base}/domains", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                members = data.get("hydra:member", [])
                if members and isinstance(members[0], dict):
                    dom = members[0].get("domain")
                    if isinstance(dom, str):
                        self._cached_domain = dom
                        return dom
        except Exception:
            pass
        self._cached_domain = "fldubai.com"
        return self._cached_domain

    def provision(self) -> str:
        domain = self.get_domain()
        username = f"usr_{secrets.token_hex(5)}"
        email = f"{username}@{domain}"
        pw = f"P@{secrets.token_hex(6)}"

        try:
            payload = json.dumps({"address": email, "password": pw}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_base}/accounts",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode())
                addr = res.get("address")
                return str(addr) if addr else email
        except Exception:
            return email
