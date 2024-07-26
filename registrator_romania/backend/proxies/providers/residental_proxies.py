import ua_generator

from registrator_romania.backend.net.aiohttp_ext import AiohttpSession
from registrator_romania.backend.proxies.providers.base import BaseProxyProvider


__all__ = [
    "ProxyCompass",
    "AdvancedMe"
]


class ProxyCompass(BaseProxyProvider):
    async def list_http_proxy(self):
        url = "https://proxycompass.com/wp-content/themes/proxycompass/proxy-list.php"
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "content-type": "application/json",
            "priority": "u=1, i",
            "referer": "https://proxycompass.com/ru/free-proxy/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-requested-with": "XMLHttpRequest",
        }

        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v

        async with AiohttpSession().generate(close_connector=True) as session:
            session._default_headers = headers

            async with session.get(url) as resp:
                response = await resp.json(content_type=resp.content_type)

            return [
                f"http://{o["host"]}:{o["port"]}"
                for o in response
                if o.get("http") == "1"
            ]


class AdvancedMe(BaseProxyProvider):
    async def list_http_proxy(self):
        url = "https://advanced.name/freeproxy/66a19c1e7155c?type=http"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.text()
                return [f"http://{line}" for line in response.splitlines()]
