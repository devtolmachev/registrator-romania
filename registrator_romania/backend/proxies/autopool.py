from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import datetime
import multiprocessing
import os
import queue
import random
import time
import traceback
from typing import Type

import aiohttp.client_exceptions
import httpx
from loguru import logger
import aiohttp
from apscheduler.schedulers.background import BackgroundScheduler

from registrator_romania.backend.net.aiohttp_ext import AiohttpSession
from registrator_romania.backend.net.httpx_ext import HTTPX_NET_ERRORS
from registrator_romania.backend.proxies import providers
from registrator_romania.backend.utils import divide_list


AIOHTTP_NET_ERRORS = (
    aiohttp.client_exceptions.ContentTypeError,
    aiohttp.client_exceptions.ClientConnectionError,
    aiohttp.client_exceptions.ClientHttpProxyError,
    aiohttp.client_exceptions.ClientProxyConnectionError,
    aiohttp.client_exceptions.ClientResponseError,
    aiohttp.client_exceptions.ClientPayloadError,
    aiohttp.ClientOSError,
    aiohttp.ServerDisconnectedError,
    asyncio.TimeoutError,
)


async def check_proxy(
    proxy: str,
    queue: multiprocessing.Queue = None,
    connector: aiohttp.TCPConnector = None,
    timeout: int = None,
    close_connector: bool = False,
) -> dict:
    url = "https://api.ipify.org"

    # async with AiohttpSession().generate(
    #     close_connector=close_connector,
    #     connector=connector,
    #     total_timeout=timeout or 15,
    # ) as session:
    async with httpx.AsyncClient(proxy=httpx.Proxy(proxy)) as session:
        try:
            start = datetime.datetime.now()
            # async with session.get(url, proxy=proxy) as resp:
            resp = await session.get(url)
            result = (
                resp.text,
                proxy,
                datetime.datetime.now() - start,
            )
            if queue:
                await asyncio.to_thread(queue.put, result, block=False)
            return result
        except (AIOHTTP_NET_ERRORS, HTTPX_NET_ERRORS):
            return tuple()
        except UnicodeError:
            return tuple()
        except Exception as e:
            tb = traceback.format_exc()
            msg = f"check_proxy got an error {e} with traceback:\n{tb}"
            # logger.exception(msg)
            print(f"{e.__class__.__name__}: {e}")
            return tuple()


def run_th(proxies: list[str], q: multiprocessing.Queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = [check_proxy(p, queue=q, close_connector=True) for p in proxies]
    results = loop.run_until_complete(
        asyncio.gather(*tasks, return_exceptions=True)
    )
    loop.close()
    return results


class AutomaticProxyPool:
    def __init__(
        self,
        proxies: list[str],
        sources_classes: list[Type],
        debug: bool = False,
        second_check: bool = False,
        second_check_url: str = None,
        second_check_headers: dict = None,
    ) -> None:
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(self._add_new_proxies, "interval", minutes=10)
        self._scheduler.start()

        self._process: multiprocessing.Process = None
        self._queue = multiprocessing.Queue()
        self._event = multiprocessing.Event()
        self._pool = AiohttpSession().generate_connector()
        self._proxies = []
        self._proxies_reports = {}
        self.debug = debug
        self._append_pool_task: asyncio.Task = None
        self._src_proxies_list = proxies
        self._do_second_check = second_check
        self._timeout_proxies = {}
        self._last_proxy_used: str = None
        self._proxy_for = {
            "url": "",
            "headers": {},
            "best_proxy": "",
            "proxies": [],
        }
        self._lock = asyncio.Lock()
        self._urls: list[dict[str, dict[str, str]]] = {}
        
        # Example:
        # [{"https://url1.com": {"proxy": "https://proxy:8080", "timeout": 2}}]
        # (timeout in seconds)
        
        self._sources_cls = [] if not sources_classes else sources_classes
        self._second_check_url = second_check_url or "https://api.ipify.org"
        self._second_check_headers = second_check_headers or {"Accept": "*/*"}

    @property
    def last_proxy_used(self):
        return self._last_proxy_used

    def _add_new_proxies(self):
        async def add_new_proxies_async():
            proxies_classes = self._sources_cls
            for proxy_class in proxies_classes:
                try:
                    proxies = await proxy_class.list_http_proxy()
                except Exception:
                    continue
                else:
                    self._src_proxies_list.extend(
                        [
                            proxy
                            for proxy in proxies
                            if proxy not in self.proxies
                        ]
                    )

        loop = asyncio.new_event_loop()
        loop.run_until_complete(add_new_proxies_async())
        loop.close()

    def __aiter__(self):
        return self

    def __await__(self):
        self.start_background()
        return self._append_pool().__await__()

    def __del__(self):
        print(
            "Unstopped background proccess filter "
            f"proxies: {self._process.name}. Stopping at now..."
        )
        self.drop_background()
        self._scheduler.remove_all_jobs()
        del self._scheduler

    async def _append_pool(self):
        async def send_request(proxy: str):
            if proxy in self.proxies:
                return

            async with AiohttpSession().generate(
                connector=self._pool, total_timeout=5
            ) as session:
                session._default_headers = self._second_check_headers

                if self.debug:
                    logger.debug(f"append_pool: {proxy}")

                try:
                    if self._do_second_check:
                        start = datetime.datetime.now()
                        async with session.get(
                            self._second_check_url, proxy=proxy
                        ):
                            stop = datetime.datetime.now()
                            if self.debug:
                                logger.debug(
                                    "Second check was successfully: "
                                    f"{proxy} - {start - stop}"
                                )
                    self._proxies.append(proxy)
                    self.proxy_working(proxy)
                except AIOHTTP_NET_ERRORS:
                    pass
                except Exception as e:
                    logger.exception(e)

        async def background():
            try:
                while True:
                    tasks = []
                    async for proxy, time in self:
                        task = asyncio.create_task(send_request(proxy))
                        tasks.append(task)
                        await asyncio.sleep(0.250)

                    await asyncio.gather(*tasks)
                    self.start_background()
            except asyncio.CancelledError:
                print("Background task was cancelled")
                pass

        self._append_pool_task = asyncio.get_event_loop().create_task(
            background()
        )
        await asyncio.sleep(0.250)
        return self

    async def __anext__(self):
        while True:
            if self._event.is_set():
                raise StopAsyncIteration

            try:
                result = await asyncio.to_thread(self._queue.get_nowait)
            except queue.Empty:
                if self._event.is_set():
                    raise StopAsyncIteration

            except Exception:
                logger.critical(traceback.format_exc())

            else:
                if isinstance(result, tuple):
                    time = result[2]
                    proxy = result[1]
                    if self.debug:
                        logger.debug(f"__anext__(): return proxy - {proxy}")

                    return proxy, time

                if result == "finish":
                    raise StopAsyncIteration

    def restart_background(self):
        self.drop_background()
        self.start_background()

    def restart_background(self):
        self.drop_background()
        self.start_background()

    def drop_background(self):
        if self._process:
            if self._process.is_alive():
                self._process.kill()
            self._process.close()
        if self._queue:
            self._queue.close()

        del self._queue
        del self._process
        self._queue = multiprocessing.Queue()
        self._process = None

    def start_background(self):
        def run(
            q: multiprocessing.Queue,
            proxies: list[str],
            event: multiprocessing.Event,
        ):
            divides = 700
            # proxies [0, 0, 0, 0, 0, 0]
            # divides: 2, chunks [[0, 0], [0, 0], [0, 0]]
            chunks = divide_list(proxies, divides=divides)

            for chunk in divide_list(chunks, divides=2):
                try:
                    with ThreadPoolExecutor(
                        max_workers=os.cpu_count() * 2.5
                    ) as e:
                        e.map(run_th, chunk, [q for _ in chunk])

                    time.sleep(1.5)
                except KeyboardInterrupt:
                    e.shutdown(wait=True, cancel_futures=True)

            event.set()
            q.put("finish")

        self._event.clear()
        self._process = multiprocessing.Process(
            target=run, args=(self._queue, self._src_proxies_list, self._event)
        )
        self._process.start()

    @property
    def proxies(self):
        return self._proxies

    def set_proxies_for_url(self, list_of_proxies: list[str]):
        self._proxy_for["proxies"] = list_of_proxies

    def sort_proxies_by_timeout(self, proxies: list[dict[str, str | int]]):
        filtered = list(sorted(proxies, key=lambda p: p["timeout"]))
        return filtered

    async def get_session(self, timeout: int = 5) -> aiohttp.ClientSession:
        if not self.proxies:
            raise ValueError("Proxies list empty")
        session = AiohttpSession().generate(
            connector=self._pool, total_timeout=timeout
        )
        self_class = self

        async def _request(*args, **kwargs):
            # Get proxy and url from parameters before do request
            proxy = kwargs.get("proxy")
            url = args[1]

            if not proxy and proxy != "False":  # If bool(proxy) == False
                async with session._lock:
                    proxy = self_class.get_best_proxy_by_timeout()
                    kwargs["proxy"] = proxy

                    if not self_class._urls.get(url):
                        # If we not have any proxies for this site, we are
                        # collect them
                        proxies = []
                        try:
                            proxies = await self_class.collect_valid_proxies(
                                url=url,
                                headers=session._default_headers,
                            )
                        except Exception as e:
                            logger.exception(e)

                        if proxies:
                            # Set the most speed proxy
                            proxies = self_class.sort_proxies_by_timeout(
                                proxies
                            )
                            proxy = proxies.pop(0)["proxy"]
                            self_class._urls[url] = proxies

                            kwargs["proxy"] = proxy

                    elif self_class._urls[url]:
                        proxy = self_class._urls[url].pop(0)["proxy"]
                        kwargs["proxy"] = proxy

            if self_class.debug and proxy:
                logger.debug(f"Do request on {url} with proxy {proxy}")

            if proxy and proxy != "False":
                async with session._lock:
                    self_class._last_proxy_used = proxy

            if proxy == "False" and kwargs.get("proxy"):
                del kwargs["proxy"]

            start = datetime.datetime.now()
            try:
                result = await session._request_(*args, **kwargs)
                if kwargs.get("proxy") is None:
                    return result

                stop = datetime.datetime.now()

                if proxy:
                    self_class._timeout_proxies[proxy] = stop - start

                    if url not in self_class._urls:
                        self_class._urls[url] = []
                    try:
                        list_proxies_for_url = self_class._urls[url].copy()
                        proxy_record = [
                            record
                            for record in list_proxies_for_url
                            if record["proxy"] == proxy
                        ]

                        if not proxy_record:
                            proxy_record = {
                                "proxy": proxy,
                                "timeout": (stop - start).microseconds,
                            }
                            list_proxies_for_url.append(proxy_record)
                            i = -1
                        else:
                            proxy_record = proxy_record[0]
                            i = list_proxies_for_url.index(proxy_record)

                        list_proxies_for_url[i] = {
                            "proxy": proxy,
                            "timeout": (stop - start).microseconds,
                        }
                        new_list = self_class.sort_proxies_by_timeout(
                            proxies=list_proxies_for_url
                        )
                        async with session._lock:
                            self_class._urls[url] = new_list
                    except (ValueError, ValueError):
                        pass
                    except RuntimeError:
                        pass

                if proxy and result.status != 200:
                    self_class.proxy_not_working(proxy=proxy)
                elif proxy and proxy in self_class.proxies:
                    self_class.proxy_working(proxy=proxy)

                return result
            except AIOHTTP_NET_ERRORS as e:
                if proxy and proxy in self_class.proxies:
                    self_class.proxy_not_working(proxy=proxy)
                    if self_class._timeout_proxies.get(proxy):
                        del self_class._timeout_proxies[proxy]

                if url in self_class._urls:
                    try:
                        async with session._lock:
                            proxy_record = [
                                record
                                for record in self_class._urls[url]
                                if record["proxy"] == proxy
                            ]

                            if proxy_record:
                                i = self_class._urls[url].index(proxy_record[0])
                                del self_class._urls[url][i]
                    except RuntimeError:
                        pass

                raise e
            finally:
                if proxy != "False" and session._lock.locked():
                    try:
                        session._lock.release()
                    except Exception:
                        pass

        session._request_ = session._request
        session._request = _request
        session._lock = asyncio.Lock()

        return session

    async def collect_valid_proxies(self, url: str, headers: dict[str, str]):
        session = AiohttpSession().generate(
            connector=self._pool, close_connector=False, total_timeout=4
        )
        session._default_headers = headers
        proxies = self.proxies

        async def send_req(proxy: str):
            start = datetime.datetime.now()
            try:
                async with session.get(url, proxy=proxy) as resp:
                    await resp.text()
                    if resp.status == 200:
                        return True, proxy, datetime.datetime.now() - start
            except Exception as e:
                return False, proxy

        async with session:
            results = await asyncio.gather(
                *[send_req(proxy) for proxy in proxies]
            )
        proxies = [
            (result[1], result[2]) for result in results if result and result[0]
        ]
        return [
            {"proxy": proxy[0], "timeout": proxy[1].microseconds}
            for proxy in sorted(proxies, key=lambda part: part[1])
        ]

    def proxy_not_working(self, proxy: str):
        if proxy not in self.proxies:
            return

        if not self._proxies_reports.get(proxy):
            self._proxies_reports[proxy] = 0

        self._proxies_reports[proxy] += 1

        if self._proxies_reports[proxy] >= 30:
            del self._proxies_reports[proxy]
            self._proxies.remove(proxy)

    def proxy_working(self, proxy: str):
        if proxy not in self.proxies:
            return
        if not self._proxies_reports.get(proxy):
            self._proxies_reports[proxy] = 0
            return

        self._proxies_reports[proxy] -= 1

        if self._proxies_reports[proxy] < 0:
            self._proxies_reports[proxy] = 0

    def get_best_proxy(self):
        if not self._proxies_reports:
            return random.choice(self.proxies)
        proxies_stats = list(self._proxies_reports.copy().items())
        random.shuffle(proxies_stats)
        return min(proxies_stats, key=lambda x: x[1])[0]

    def get_best_proxy_by_timeout(self):
        if not self._timeout_proxies:
            return self.get_best_proxy()
        proxies_stats = list(self._timeout_proxies.copy().items())
        random.shuffle(proxies_stats)
        return min(proxies_stats, key=lambda x: x[1])[0]


async def filter_proxies(
    proxies: list[str], debug: bool = False, second_check: bool = True
):
    provides_proxies = providers.__all__
    f = AutomaticProxyPool(
        proxies,
        debug=debug,
        second_check=second_check,
        sources_classes=provides_proxies,
    )
    await f
    return f
