
class BaseProxyProvider:
    async def list_http_proxy(self):
        return []

    async def list_socks4_proxy(self):
        return []

    async def list_socks5_proxy(self):
        return []
