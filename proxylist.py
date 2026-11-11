from __future__ import annotations


class ProxyPool:
    def __init__(self, proxies: list[str], validate: bool = True):
        self.proxies = proxies
        self.idx = 0

    def next(self) -> str | None:
        if not self.proxies:
            return None
        p = self.proxies[self.idx % len(self.proxies)]
        self.idx += 1
        return p
