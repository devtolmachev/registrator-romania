import asyncio
import aiohttp


AIOHTTP_NET_ERRORS = (
    aiohttp.client_exceptions.ContentTypeError,
    aiohttp.client_exceptions.ClientConnectionError,
    aiohttp.client_exceptions.ClientHttpProxyError,
    aiohttp.client_exceptions.ClientProxyConnectionError,
    aiohttp.client_exceptions.ClientResponseError,
    aiohttp.ClientOSError,
    aiohttp.ServerDisconnectedError,
    asyncio.TimeoutError,
)