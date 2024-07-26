from registrator_romania.backend.net.aiohttp_ext import AiohttpSession
from registrator_romania.backend.proxies.providers.base import BaseProxyProvider
from registrator_romania.backend.utils import is_host_port


__all__ = [
    "ProxyMaster",
    "FreeProxies",
    "FreeProxiesList",
    "GeoNode",
    "ImRavzanProxyList",
    "LionKingsProxy",
    "TheSpeedX"
]


class ProxyMaster(BaseProxyProvider):
    """
    Github - https://github.com/MuRongPIG/Proxy-Master
    """

    async def list_http_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks4://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class FreeProxies(BaseProxyProvider):
    """
    Github - https://github.com/Anonym0usWork1221/Free-Proxies
    """

    async def list_http_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks4_proxies.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks4://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/socks5_proxies.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class FreeProxiesList(BaseProxyProvider):
    """
    GitHub - https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt
    """

    async def list_http_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks4://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class GeoNode(BaseProxyProvider):
    async def list_http_proxy(self) -> list[str]:
        url = "https://proxylist.geonode.com/api/proxy-list?protocols=http&limit=500&sort_by=lastChecked&sort_type=desc"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.json()
                return [
                    f"http://{obj["ip"]}:{obj["port"]}"
                    for obj in response["data"]
                ]

    async def list_socks4_proxy(self) -> list[str]:
        url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks4&limit=500&sort_by=lastChecked&sort_type=desc"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.json()
                return [
                    f"socks4://{obj["ip"]}:{obj["port"]}"
                    for obj in response["data"]
                ]

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://proxylist.geonode.com/api/proxy-list?protocols=socks5&limit=500&sort_by=lastChecked&sort_type=desc"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                response = await resp.json()
                return [
                    f"socks5://{obj["ip"]}:{obj["port"]}"
                    for obj in response["data"]
                ]


class ImRavzanProxyList(BaseProxyProvider):
    """
    https://raw.githubusercontent.com/im-razvan/proxy_list/main/http.txt
    """

    async def list_http_proxy(self):
        url = "https://raw.githubusercontent.com/im-razvan/proxy_list/main/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"http://{p.strip()}" for p in proxies.splitlines()]

    async def list_socks4_proxy(self) -> list:
        return []

    async def list_socks5_proxy(self) -> list[str]:
        url = "https://raw.githubusercontent.com/im-razvan/proxy_list/main/socks5.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [f"socks5://{p.strip()}" for p in proxies.splitlines()]


class LionKingsProxy(BaseProxyProvider):
    """
    https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/free.txt
    """

    async def list_http_proxy(self):
        url = "https://raw.githubusercontent.com/saisuiu/Lionkings-Http-Proxys-Proxies/main/free.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [
                    f"http://{p.strip()}"
                    for p in proxies.splitlines()
                    if is_host_port(p.strip())
                ]


class TheSpeedX(BaseProxyProvider):
    """
    https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt
    """

    async def list_http_proxy(self):
        url = "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
        async with AiohttpSession().generate(close_connector=True) as session:
            async with session.get(url) as resp:
                proxies = await resp.text()
                return [
                    f"http://{p.strip()}"
                    for p in proxies.splitlines()
                    if is_host_port(p.strip())
                ]
