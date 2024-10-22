import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import copy
from datetime import datetime, timedelta
import inspect
import logging
from multiprocessing import Process
from multiprocessing.synchronize import Lock
import multiprocessing
from multiprocessing.managers import ListProxy
import os
import re
from pathlib import Path
import random
import sys
from threading import Thread
import threading
import time
from typing import Literal
from zoneinfo import ZoneInfo
import aiofiles
import aiohttp
from loguru import logger
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
import traceback

try:
    import uvloop as floop
except ImportError:
    import winloop as floop

from registrator_romania.backend.api.api_romania import APIRomania
from registrator_romania.backend.database.api import (
    UsersService,
    get_async_engine,
)
from registrator_romania.backend.database.sqlalchemy_models import Base
from registrator_romania.backend.net.aiohttp_ext import AiohttpSession
from registrator_romania.backend.proxies.autopool import AutomaticProxyPool

from registrator_romania.backend.proxies.providers.server_proxies import *
from registrator_romania.backend.proxies.providers.residental_proxies import *

from registrator_romania.backend.utils import (
    divide_list,
    filter_by_log_level,
    generate_fake_users_data,
    get_current_info,
    get_users_data_from_xslx,
    setup_loggers,
)
from registrator_romania.backend.utils import get_dt_moscow
from registrator_romania.backend.net import AIOHTTP_NET_ERRORS

# ssl._create_default_https_context = ssl._create_unverified_context


def run_multiple(
    instance: "StrategyWithoutProxy",
    dirname: str,
    lst: ListProxy,
    locks: dict[str, Lock],
    waiters: ListProxy,
    q: multiprocessing.Queue
):
    if sys.platform not in ["win32", "cygwin"]:
        asyncio.set_event_loop_policy(floop.EventLoopPolicy())

    async def run_multiple_async():
        start = time.time()
        while time.time() - start < 1000:
            try:
                res = await instance._start_multiple_registrator(dirname, lst, locks, waiters, q)
            except Exception as e:
                logger.exception(e)
        return res

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_multiple_async())


class StrategyWithoutProxy:
    def __init__(
        self,
        registration_date: datetime,
        tip_formular: int,
        debug: bool = False,
        users_data: list[dict] = None,
        stop_when: tuple[int, int, int] = None,
        mode: Literal["async", "sync"] = "sync",
        async_requests_num: int = 10,
        use_shuffle: bool = True,
        logging: bool = True,
        residental_proxy_url: str = None,
        multiple_registration_on: datetime = None,
        multiple_registration_threads: int = 7,
        without_remote_database: bool = False,
        proxies_file: str = None,
        only_multiple: bool = True,
        requests_per_user: int = None,
        requests_on_user_per_second: int = 5,
        enable_repeat_protection: bool = True,
    ) -> None:
        setup_loggers(registration_date=registration_date)
        init_args = inspect.currentframe().f_locals.copy()
        msg = (
            f"Initialize class.\nInit arguments: {init_args}"
        )
        logger.debug(msg)

        if not stop_when:
            stop_when = [9, 2, 0]
        self._api = APIRomania(debug=debug)
        self._db = UsersService()
        self._users_data = users_data or []
        self._registration_date = registration_date
        self._tip_formular = int(tip_formular)
        self._stop_when = stop_when
        self._mode = mode
        self._async_requests_num = int(async_requests_num)
        self._use_shuffle = use_shuffle
        self._logging = logging
        self._residental_proxy_url = residental_proxy_url
        self._multiple_registration_on = multiple_registration_on
        self._multiple_registration_threads = multiple_registration_threads
        self._without_remote_database = without_remote_database
        self._requests_per_user = requests_per_user
        self._requests_on_user_per_second = requests_on_user_per_second

        self._alock = asyncio.Lock()
        self._lock = threading.Lock()

        self._proxies_file_path = proxies_file
        self._only_multiple = only_multiple

        self._g_recaptcha_responses = []
        
        self._enable_repeat_protection = enable_repeat_protection
        self._scheduler = BackgroundScheduler()
        
        self._multiple_done = False
        
    async def start(self):
        if self._users_data:
            logger.debug("get unregister users")
            try:
                async with asyncio.timeout(10):
                    unregistered_users = await self.get_unregisterer_users()
                    if unregistered_users:
                        self._users_data = unregistered_users.copy()
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                if self._logging:
                    logger.exception(e)

            if self._without_remote_database is False:
                try:
                    logger.debug("add users to database")
                    async with asyncio.timeout(10):
                        await self.add_users_to_db()
                except asyncio.TimeoutError:
                    pass

        self.update_users_data_task = asyncio.create_task(self.update_users_list())

        while not self._users_data:
            logger.debug("wait for strategy add users from database")
            await asyncio.sleep(1)
        await self.start_registration()

    def _get_dt_now(self) -> datetime:
        return get_dt_moscow()

    async def async_registrations(self, users_data: list[dict], queue: asyncio.Queue):
        api = self._api
        reg_dt = self._registration_date
        proxy = self._residental_proxy_url

        async def registrate(user_data: dict):
            proxy = self.get_proxy()

            if user_data.get("registration_date"):
                reg_dt = user_data.pop("registration_date")

            api = APIRomania(debug=self._api._debug, verifi_ssl=False)
            html = await api.make_registration(
                user_data=user_data,
                registration_date=reg_dt,
                tip_formular=self._tip_formular,
                proxy=proxy,
            )
            await self.post_registrate(user_data=user_data, html=html, queue=queue)

            await api._connections_pool.close()

        tasks = [registrate(user_data) for user_data in users_data]
        for chunk in divide_list(tasks, divides=self._async_requests_num):
            try:
                await asyncio.gather(*chunk, return_exceptions=True)
            except Exception as e:
                if self._logging:
                    logger.exception(e)
                continue

    def get_proxy(self):
        if not self._proxies_file_path:
            return
        
        with open(self._proxies_file_path) as f:
            src_list_proxies = f.read().splitlines()
            proxies = iter(src_list_proxies)

        try:
            proxy = next(proxies)
        except StopIteration:
            proxies = iter(src_list_proxies)
            proxy = src_list_proxies[0]

        proxies_range = re.search(r"<(\d+-\d+)>", proxy)
        if proxies_range:
            proxies_range = proxies_range.group(1)
            start_port, stop_port = proxies_range.split("-")
            proxy = re.sub(
                r"<\d+-\d+>",
                str(random.randrange(start=int(start_port), stop=int(stop_port))),
                proxy,
            )

        return proxy

    async def _start_multiple_registrator(
        self, dirname: str, lst: ListProxy, locks: dict[str, Lock], process_waiters: ListProxy, q: multiprocessing.Queue
    ):
        users_data = self._users_data.copy()

        if not users_data:
            return

        if self._requests_per_user:
            users_data = users_data[0 : self._requests_per_user - 1]
            random.shuffle(users_data)

        queue = asyncio.Queue()
        temp_q = asyncio.Queue()

        async def registrate(user_data: dict):
            nonlocal registered_users, temp_q, queue

            try:
                proxy = await asyncio.to_thread(self.get_proxy)
            except Exception:
                proxy = None

            api = APIRomania(debug=self._api._debug, verifi_ssl=False)
            
            if user_data in lst:
                return

            async def wait_for_registration(queue: asyncio.Queue, user_id: str):
                try:
                    logger.debug(f"wait for registration for user_id: {user_id} (wait queue)")
                    async with asyncio.timeout(60):
                        while True:
                            if inspect.iscoroutinefunction(queue.get):
                                us_id = await queue.get()
                            else:
                                us_id = await asyncio.to_thread(queue.get)
                                
                            if us_id == user_id:
                                logger.debug(f"wait for registration for user_id: {user_id} (wait queue) - done")
                                return
                except asyncio.TimeoutError:
                    return

            curr_task = api._current_info()
            user_id = self._get_user_id(user_data)
            # lock = locks[user_id]

            try: 
                # # process data synchronization
                # async with asyncio.timeout(10):
                #     await asyncio.to_thread(lock.acquire)
                
                if self._enable_repeat_protection:
                    # try:
                    if process_waiters.count(user_id) >= 5:
                        msg = (
                            f"process lock. curr_task: {curr_task}. "
                            f"user_id: {user_id}. wait for another "
                            "tasks finish attempt"
                        )
                        logger.debug(msg)
                        await wait_for_registration(q, user_id)

                    if user_id in registered_users or user_data in lst:
                        msg = (
                            f"process lock. curr_task: {curr_task}. "
                            f"user_id: {user_id}. already registered"
                        )
                        logger.debug(msg)
                        return

                    msg = (
                        f"process lock. curr_task: {curr_task}. "
                        f"user_id: {user_id}. try to registrate"
                    )
                    logger.debug(msg)
                    process_waiters.append(user_id)
                    
                    # finally:
                    #     async with asyncio.timeout(10):
                    #         try:
                    #             msg =(
                    #                 f"release lock for user_id: {user_id}"
                    #             )
                    #             logger.debug(msg)
                    #             # await asyncio.to_thread(lock.release)
                    #         except ValueError:
                    #             pass

                g_recaptcha_response = None
                try:
                    g_recaptcha_response = random.choice(self._g_recaptcha_responses)
                    try:
                        self._g_recaptcha_responses.remove(g_recaptcha_response)
                    except ValueError:
                        pass
                    if not g_recaptcha_response:
                        g_recaptcha_response = None
                except Exception:
                    pass

                logger.debug(f"make registration for user_id: {user_id}")
                html = await api.make_registration(
                    user_data=user_data,
                    registration_date=self._registration_date,
                    tip_formular=self._tip_formular,
                    proxy=proxy,
                    timeout=10,
                    queue=queue,
                    g_recaptcha_response=None,
                )

                if not isinstance(html, str):
                    logger.error(f"response from server is not html (not string): {html}")
                    return

                elif api.is_success_registration(html):
                    registered_users.add(user_id)
                    if user_data not in lst:
                        lst.append(user_data)

                elif api.get_error_registration_as_text(html):
                    error = api.get_error_registration_as_text(html)
                    if error.count("Deja a fost înregistrată o programare"):
                        registered_users.add(user_id)
                        if user_data not in lst:
                            lst.append(user_data)

                await api._connections_pool.close()
                await self.post_registrate(user_data=user_data, html=html, queue=queue)
                
            except AIOHTTP_NET_ERRORS as e:
                logger.debug(f"AIOHTTP_NET_ERRORS: {e}")
                return
            
            except Exception as e:
                logger.exception(e)
                
            finally:
                if user_id in process_waiters:
                    try:
                        process_waiters.remove(user_id)
                    except Exception:
                        pass
                
                try:
                    if self._enable_repeat_protection:
                        async with asyncio.timeout(3):
                            await asyncio.to_thread(q.put_nowait, user_id)
                except Exception:
                    pass

        loop = asyncio.get_running_loop()
        if self._requests_on_user_per_second:
            tasks = [
                asyncio.eager_task_factory(loop, registrate(user_data=user_data))
                for user_data in users_data
                for _ in [user_data] * self._requests_on_user_per_second
            ]
        else:
            tasks = [
                asyncio.eager_task_factory(loop, registrate(user_data=user_data))
                for user_data in users_data
            ]
        random.shuffle(tasks)
        registered_users = set()

        timeout = 30
        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(*tasks, return_exceptions=True)
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            cur_info = get_current_info()
            msg = (
                f"[{cur_info}] - error in asyncio.gather: "
                f"{e.__class__.__name__}: {e}.\ntraceback: "
                f"{traceback.format_exc()}"
            )
            
            logger.error(msg)
            for task in tasks:
                try:
                    task.cancel()
                except Exception:
                    pass

        await self._save_successfully_registration_from_queue(
            queue=queue, dirname=dirname
        )
        
    def _get_user_id(self, user_data: dict) -> str:
        return f"{user_data['Nume Pasaport']} {user_data['Prenume Pasaport']} {user_data['Adresa de email']}"

    async def schedule_multiple_registrations(self, dirname: str):
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._start_multiple_registrator(dirname=dirname))

        def start_threads():
            instance = copy.copy(self)

            pr_manager = multiprocessing.Manager()
            lst = pr_manager.list()
            locks = {}
            waiters_list = pr_manager.list()
            q = multiprocessing.Queue()
            
            for us_data in self._users_data:
                locks[self._get_user_id(us_data)] = multiprocessing.Lock()

            process: list[Process] = []
            
            pr_args = (instance, dirname, lst, locks, waiters_list, q)
            num = 0
            while True:
                # OLD METHOD
                # for num in range(self._multiple_registration_threads):
                #     num += 1
                    
                #     pr = Process(target=run_multiple, args=pr_args)
                #     pr.start()
                    
                #     process.append(pr)
                #     logger.debug(f"Process {pr.name} started ({num})")

                # for pr in process:
                #     pr.join()
                #     logger.debug(f"Process {pr.name} finished")
                
                # NEW METHOD
                try:
                    pr = Process(target=run_multiple, args=pr_args)
                    pr.start()
                    num += 1
                    
                    process.append(pr)
                    logger.debug(f"Process {pr.name} started ({num})")
                    time.sleep(random.uniform(0.1, 1))
                except Exception as e:
                    logger.exception(e)
                
                now = self._get_dt_now()
                if now.hour == self._stop_when[0] and now.minute >= self._stop_when[1]:
                    break
            
            for pr in process:
                try:
                    pr.terminate()
                except Exception as e:
                    logger.exception(e)
                    pr.kill()
            
            [pr.kill() for pr in process]
            logger.debug("All processes finished")
            scheduler.remove_job(job_id=job.id)
            return

            # threads: list[Thread] = []
            # for _ in range(self._multiple_registration_threads):
            #     th = Thread(target=run_in_thread)
            #     th.start()
            #     threads.append(th)
            #     time.sleep(1)
            #     logger.debug(f"Thread {th.name} started")

            # for th in threads:
            #     th.join()
            #     logger.debug(f"Thread {th.name} finished")

            # logger.debug("All threads finished")
            # scheduler.remove_job(job_id=job.id)

        scheduler = self._scheduler
        job = scheduler.add_job(
            start_threads,
            "cron",
            start_date=self._multiple_registration_on,
            timezone=ZoneInfo("Europe/Moscow"),
            max_instances=1,
        )
        scheduler.start()
        logging.getLogger("apscheduler").setLevel(logging.ERROR)

    async def post_registrate(self, user_data: dict, html: str, queue: asyncio.Queue):
        first_name = user_data["Prenume Pasaport"]
        last_name = user_data["Nume Pasaport"]
        api = self._api

        if not isinstance(html, str):
            return

        if api.is_success_registration(html):
            if self._without_remote_database is False:
                try:
                    async with asyncio.timeout(5):
                        async with self._db as db:
                            await db.remove_user(user_data)
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    logger.exception(e)

            msg = f"successfully registrate {first_name} {last_name}"
            try:
                self._users_data.remove(user_data)
            except:
                pass
            if self._logging:
                logger.success(msg)
            await queue.put((user_data.copy(), html))

        else:
            error = api.get_error_registration_as_text(html)

            if not isinstance(error, str):
                return

            if error.count("Deja a fost înregistrată o programare"):
                await queue.put((user_data.copy(), html))

                try:
                    self._users_data.remove(user_data)
                except:
                    pass

                if self._without_remote_database is False:
                    try:
                        async with asyncio.timeout(5):
                            async with self._db as db:
                                await db.remove_user(user_data)
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        logger.exception(e)

            msg = f"{first_name} {last_name} - {error}"
            if self._logging:
                logger.error(msg)

    async def sync_registrations(self, users_data: list[dict], queue: asyncio.Queue):
        api = self._api
        reg_dt = self._registration_date
        proxy = self._residental_proxy_url
        proxies = None

        if self._proxies_file_path:
            with open(self._proxies_file_path) as f:
                src_list_proxies = f.read().splitlines()
                if proxy:
                    src_list_proxies.append(proxy)
                proxies = iter(src_list_proxies)

        for user_data in users_data:
            if proxies:
                try:
                    proxy = next(proxies)
                except StopIteration:
                    proxies = iter(src_list_proxies)
                    proxy = src_list_proxies[0]

            proxies_range = re.search(r"<(\d+-\d+)>", proxy)
            if proxies_range:
                proxies_range = proxies_range.group(1)
                start_port, stop_port = proxies_range.split("-")
                proxy = re.sub(
                    r"<\d+-\d+>",
                    str(random.randrange(start=int(start_port), stop=int(stop_port))),
                    proxy,
                )

            try:
                html = await api.make_registration(
                    user_data,
                    registration_date=reg_dt,
                    tip_formular=self._tip_formular,
                    proxy=proxy,
                )
                await self.post_registrate(user_data, html, queue)
            except AIOHTTP_NET_ERRORS:
                pass
            except Exception as e:
                if self._logging:
                    logger.exception(e)

    def _get_proxies_from_proxy_list(self) -> list[str] | list:
        if self._proxies_file_path:
            proxies = []
            with open(self._proxies_file_path) as f:
                src_list_proxies = f.read().splitlines()

            for proxy in src_list_proxies:
                proxies_range = re.search(r"<(\d+-\d+)>", proxy)
                if proxies_range:
                    proxies_range = proxies_range.group(1)
                    start_port, stop_port = proxies_range.split("-")
                    proxy = re.sub(
                        r"<\d+-\d+>",
                        str(
                            random.randrange(start=int(start_port), stop=int(stop_port))
                        ),
                        proxy,
                    )

                proxies.append(proxy)

            return proxies
        else:
            return []

    async def start_registration(self):
        api = self._api
        reg_dt = self._registration_date
        successfully_registered = []
        queue = asyncio.Queue()
        enable_checking_free_places = False

        now = self._get_dt_now()
        dirname = f"registrations_{reg_dt.strftime("%d.%m.%Y")}"

        if self._proxies_file_path and enable_checking_free_places:
            proxies = self._get_proxies_from_proxy_list()

            try:
                success = False
                proxies_iter = iter(proxies)

                last_err = None
                proxy = next(proxies_iter)
                for i in range(5):
                    i += 1

                    logger.debug(
                        f"try to get free places on {reg_dt.date()}. " f"attempt {i}/5"
                    )

                    try:
                        places = await api.get_free_places_for_date(
                            tip_formular=self._tip_formular,
                            month=reg_dt.month,
                            day=reg_dt.day,
                            year=reg_dt.year,
                            proxy=proxy,
                        )
                    except BaseException as e:
                        last_err = e
                        logger.debug(
                            "error when try to get free places. "
                            f"{e.__class__.__name__}: {e}"
                        )

                        try:
                            proxy = next(proxies_iter)
                        except:
                            proxy = proxies[0]

                        await asyncio.sleep(1)
                    else:
                        success = True
                        break

                if not success:
                    raise last_err

            except BaseException as e:
                logger.exception(e)

        if self._multiple_registration_on:
            try:
                await self.schedule_multiple_registrations(dirname=dirname)
            except Exception as e:
                if self._logging:
                    logger.exception(e)

        async def append_g_recaptcha_response():
            tasks = []

            async def append():
                await asyncio.sleep(random.uniform(0.5, 2))
                try:
                    proxy = await asyncio.to_thread(self.get_proxy)
                except Exception:
                    proxy = None

                retry = False
                try:
                    g_recaptcha_response = await self._api.get_recaptcha_token(
                        proxy=proxy, timeout=10
                    )
                except Exception:
                    retry = True

                if retry or not g_recaptcha_response:
                    try:
                        g_recaptcha_response = await self._api.get_captcha_token(
                            proxy=proxy, timeout=10
                        )
                    except Exception:
                        g_recaptcha_response = None

                if g_recaptcha_response and g_recaptcha_response not in self._g_recaptcha_responses:
                    self._g_recaptcha_responses.append(g_recaptcha_response)

            while True:
                if len(tasks) >= 50:
                    try:
                        async with asyncio.timeout(10):
                            res = await asyncio.gather(*tasks, return_exceptions=True)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
                    except Exception as e:
                        logger.exception(e)

                    tasks = []
                    await asyncio.sleep(1)

                tasks.append(append())

        # if self._multiple_registration_on:
        #     loop = asyncio.get_running_loop()
        #     asyncio.eager_task_factory(loop=loop, coro=append_g_recaptcha_response())

        while True:
            logger.debug("Start cycle [THE ONLY DEBUG MESSAGE]")
            now = self._get_dt_now()
            await asyncio.sleep(1.5)
            users_for_registrate = self._users_data.copy()

            if (
                len(successfully_registered) >= len(self._users_data.copy())
                or not users_for_registrate
            ):
                break

            if now.hour == self._stop_when[0] and now.minute >= self._stop_when[1]:
                break

            if self._only_multiple:
                continue

            try:
                try:
                    async with asyncio.timeout(5):
                        places = await api.get_free_places_for_date(
                            tip_formular=self._tip_formular,
                            month=reg_dt.month,
                            day=reg_dt.day,
                            year=reg_dt.year,
                        )
                        if not places:
                            logger.debug(f"{places} places")
                            continue
                except asyncio.TimeoutError:
                    pass

                users_for_registrate = [
                    u
                    for u in self._users_data.copy()
                    if u not in successfully_registered
                ]
                if self._use_shuffle:
                    random.shuffle(users_for_registrate)
                logger.debug(
                    f"Start registration, we have {len(users_for_registrate)} users for registrate"
                )

                if self._mode == "sync":
                    await self.sync_registrations(
                        users_data=users_for_registrate, queue=queue
                    )

                elif self._mode == "async":
                    await self.async_registrations(
                        users_data=users_for_registrate, queue=queue
                    )

                successfully_registered.extend(
                    await self._save_successfully_registration_from_queue(
                        queue=queue, dirname=dirname
                    )
                )

            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.exception(e)
        if successfully_registered:
            await self._save_success_registrations_in_csv(
                dirname=dirname, success_registrations=successfully_registered
            )

    async def _save_success_registrations_in_csv(
        self, dirname: str, success_registrations: list
    ):
        try:
            fn = "successfully-registered.csv"
            path = Path().joinpath(dirname, fn)

            with self._lock:
                async with self._alock:
                    if not os.path.exists(path):
                        df = pd.DataFrame(success_registrations)
                        df.to_csv(str(path), index=False)
                    else:
                        df1 = pd.read_csv(path)
                        df2 = pd.DataFrame(success_registrations)
                        df = pd.concat([df1, df2], ignore_index=True)
                        df.to_csv(path, index=False)

        except Exception as e:
            logger.exception(e)

    async def _save_successfully_registration_from_queue(
        self, queue: asyncio.Queue, dirname: str
    ):
        """Save html about successfully registrations in dirname.

        Args:
            queue (asyncio.Queue): asyncio queue that contains registrations data
            dirname (str): dirname where html files will be save

        Returns:
            list[Optional[dict]]: list with users data which registered
            successfully
        """
        successfully_registered = []
        while not queue.empty():
            user_data, html = await queue.get()

            if (
                not self._api.is_success_registration(html)
                or user_data in successfully_registered
            ):
                continue

            successfully_registered.append(user_data)
            first_name, last_name = (
                user_data["Prenume Pasaport"],
                user_data["Nume Pasaport"],
            )

            fn = f"success-{first_name}_{last_name}.html"
            path = Path().joinpath(dirname, fn)
            Path(dirname).mkdir(exist_ok=True)

            async with aiofiles.open(str(path), "w") as f:
                await f.write(html)

        return successfully_registered

    async def update_users_list(self):
        if self._without_remote_database is True:
            return
        while True:
            try:
                async with self._db as db:
                    self._users_data = await db.get_users_by_reg_date(
                        self._registration_date
                    )
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(3)

    async def get_unregisterer_users(
        self, days: int = 3
    ) -> list[dict[str, str] | None]:
        api = self._api
        users_data = self._users_data.copy()
        start_date = self._registration_date - timedelta(days=days)
        stop_date = self._registration_date

        try:
            response = await api.see_registrations(
                tip_formular=str(self._tip_formular),
                data_programarii=[
                    start_date,
                    stop_date,
                ],
            )
            if not response:
                return users_data
        except AIOHTTP_NET_ERRORS as e:
            return users_data

        registered_users = response["data"]
        registered_names = [
            (obj["nume_pasaport"].lower(), obj["prenume_pasaport"].lower())
            for obj in registered_users
        ]

        unregistered_users = []
        for user in users_data:
            names = (
                user["Nume Pasaport"].lower(),
                user["Prenume Pasaport"].lower(),
            )
            if names not in registered_names:
                unregistered_users.append(user)

        return unregistered_users

    async def get_registerer_users(self, days: int = 0):
        api = self._api
        users_data = self._users_data.copy()
        start_date = self._registration_date - timedelta(days=days)
        stop_date = self._registration_date

        response = await api.see_registrations(
            tip_formular=str(self._tip_formular),
            data_programarii=[
                start_date,
                stop_date,
            ],
            proxy=self.get_proxy()
        )

        registered_users = response["data"]
        registered_names = [
            (obj["nume_pasaport"].lower(), obj["prenume_pasaport"].lower())
            for obj in registered_users
        ]

        registered_users = []
        for user in users_data:
            names = (
                user["Nume Pasaport"].lower(),
                user["Prenume Pasaport"].lower(),
            )
            if names in registered_names and user not in registered_users:
                registered_users.append(user)

        return registered_users

    async def add_users_to_db(self):
        if self._without_remote_database is True:
            return

        try:
            async with self._db as db:
                for user_data in self._users_data:
                    await db.add_user(
                        user_data, registration_date=self._registration_date
                    )
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.exception(e)



reqs = 0
resps = 0
start = None

def run_multiple_registrations_rust(reg_date: datetime, tip_formular, user_data: dict, stop_when: int, proxies: list[str] = None):
    dirname = f"registrations_{reg_date.strftime("%d.%m.%Y")}"
    Path(dirname).mkdir(exist_ok=True)
    from bindings2 import APIRomania as BindingsApiRomania
    
    if not proxies:
        api = BindingsApiRomania(proxy=None)
        api_store = {None: api}
    else:
        api_store = {
        proxy: BindingsApiRomania(proxy=proxy)
        for proxy in proxies
    }
    
    
    def call_registrator_stop_on_user(user_data):
        nonlocal registrator_tasks
        fn, ln = user_data["Nume Pasaport"], user_data["Prenume Pasaport"]
        logger.success(f"[SUCCESS USER] callback trigger that indicates that the user has registered: [{fn}] [{ln}]")
        registrator_tasks[fn] = "finished"
    
    
    registrator_tasks = {}
    async def registrate_user(user_data: dict):
        nonlocal registrator_tasks
        global reqs, start
        
        registrator_tasks[user_data["Nume Pasaport"]] = "pending"
        loop = asyncio.get_event_loop()
        loop.set_task_factory(asyncio.eager_task_factory)
        if not start:
            start = time.time()
        
        success = False
        fn, ln = user_data["Nume Pasaport"], user_data["Prenume Pasaport"]
        proxy = None
        tasks = []
        while not success:
            now = time.time()
            if registrator_tasks[user_data["Nume Pasaport"]] == "finished":
                for task in asyncio.all_tasks():
                    try:
                        task.set_exception(Exception)
                    except Exception:
                        pass
                success = True
                return

            if proxies:
                proxy = random.choice(proxies)
                
            try:
                t = loop.create_task(process(fn, ln, proxy, user_data))
                tasks.append(t)
            except RuntimeError as e:
                print(f"RuntimeError: {e}")
                continue
            
            if now >= stop_when:
                break
            
            took = now - start
            logger.info(f"От начала прошло (секунды): {took}. Запросов отправлено: {reqs}. Ответов получено: {resps}")
            await asyncio.sleep(1.5)
            if len(tasks) >= 100:
                api_store[proxy] = BindingsApiRomania(proxy=proxy)
                logger.debug(f"отправили {reqs} запросов, ждем когда освободятся ресурсы")
                await asyncio.sleep(5)
                tasks.clear()
                # await asyncio.sleep(10)
        
        await asyncio.gather(*tasks, return_exceptions=True)

        
    
    async def process(fn, ln, proxy, user_data):
        global reqs, start, resps
        th = threading.current_thread()
        
        api = api_store[proxy]
        reqs += 1

        try:
            logger.debug(f"[{th.name}] посылаем запрос на регистрацию для {fn} {ln}")
            try:
                # res = api.make_registration_sync(user_data, tip_formular, reg_date.strftime("%Y-%m-%d"))
                res = await api.make_registration(user_data, tip_formular, reg_date.strftime("%Y-%m-%d"))
            except Exception as e:
                res = e
            # res = await asyncio.sleep(1.5)
            resps += 1

            if not isinstance(res, str):
                logger.error(f"response from server is not html (not string): {res} ({res.__class__.__name__})")
                return
            
            if APIRomania.is_success_registration(res):
                call_registrator_stop_on_user(user_data)
                msg = f"successfully registrate {fn} {ln}"
                logger.success(msg)
                path = Path().joinpath(dirname, f"success_{fn}-{ln}.html")
                with open(path.__str__(), "w") as f:
                    f.write(res)
                
            else:
                error = APIRomania.get_error_registration_as_text(res)
                if not error:
                    error = f"raw html: {res}"
                logger.error(f"{fn} {ln} - {error}")
        except Exception as e:
            logger.exception(e)
    
    async def start_task(user_data: dict):
        try:
            await registrate_user(user_data)
        except Exception as e:
            logger.exception(e)

    asyncio.set_event_loop_policy(floop.EventLoopPolicy())
    loop = asyncio.new_event_loop()
    loop.run_until_complete(start_task(user_data))
    loop.stop()
    loop.close()


class BindingStrategy(StrategyWithoutProxy):
    
    def __init__(self, *args, **kwargs):
        self._parallel_threads = kwargs.pop("parallel_threads", 1)
        super().__init__(*args, **kwargs)
    
    async def schedule_multiple_registrations(self, dirname: str = None):
        proxies = None
        if self._proxies_file_path:
            proxies = []
            with open(self._proxies_file_path) as f:
                for line in f.read().splitlines():
                    proxies_range = re.search(r"<(\d+-\d+)>", line)
                    if proxies_range:
                        proxies_range = proxies_range.group(1)
                        start_port, stop_port = proxies_range.split("-")
                        line = re.sub(
                            r"<\d+-\d+>",
                            str(random.randrange(start=int(start_port), stop=int(stop_port))),
                            line,
                        )
                        
                    proxies.append(line)
                    
        users_data = [
            user_data
            for _user_data in self._users_data 
            for user_data in [_user_data] * self._parallel_threads
        ]
        
        stop_when = datetime.now().replace(hour=self._stop_when[0], minute=self._stop_when[1], second=self._stop_when[2]).timestamp()
        
        params = [
            (self._registration_date, self._tip_formular, user_data, stop_when, proxies)
            for user_data in users_data
        ]
        for i in range(10):
            random.shuffle(params)
        
        def run():
            try:
                with ThreadPoolExecutor(max_workers=32) as pool:
                    futures = pool.map(lambda p: run_multiple_registrations_rust(*p), params)
                    for future in futures:
                        try:
                            future.result()
                        except Exception:
                            pass
            except Exception as e:
                logger.exception(e)
            finally:
                print("finally")
                scheduler.remove_job(job.id)
                self._multiple_done = True
        
        scheduler = self._scheduler
        job = scheduler.add_job(
            run,
            "cron",
            start_date=self._multiple_registration_on,
            timezone=ZoneInfo("Europe/Moscow"),
            max_instances=1,
        )
        scheduler.start()
        logging.getLogger("apscheduler").setLevel(logging.ERROR)
        
    async def start_registration(self):
        await self.schedule_multiple_registrations()
        while True:
            await asyncio.sleep(5)
            logger.debug("Start cycle [THE ONLY DEBUG MESSAGE]")
            if self._multiple_done:
                break


async def prepare_database(reg_dt: datetime, users_data: list[dict]):
    async with UsersService() as service:
        users_from_db = await service.get_users_by_reg_date(registration_date=reg_dt)

        if all(u in users_from_db for u in users_data):
            return

        for user in users_data:
            if user not in users_from_db:
                await service.add_user(user, registration_date=reg_dt)

        for user in users_from_db:
            if user not in users_data:
                await service.remove_user(user)


async def database_prepared_correctly(reg_dt: datetime, users_data: list[dict]):
    async with UsersService() as service:
        users_from_db = await service.get_users_by_reg_date(registration_date=reg_dt)

        if all(u in users_from_db for u in users_data):
            return True
        return False


async def main():
    # ISAI - 2
    
    reg_date = datetime(year=2025, month=2, day=19)
    # data = generate_fake_users_data(5)
    data = get_users_data_from_xslx("users.xlsx")
    data = generate_fake_users_data(80)
    tip = 4
    # tip = 2
    multiple_requests = datetime.now().replace(hour=15, minute=24, second=49)
    multiple_requests = datetime.now()

    # strategy = BindingStrategy(
    #     registration_date=reg_date,
    #     tip_formular=tip,
    #     users_data=data,
    #     mode="sync",
    #     async_requests_num=2,
    #     multiple_registration_on=multiple_requests,
    #     multiple_registration_threads=5,
    #     without_remote_database=True,
    #     # proxies_file="proxies.txt",
    #     stop_when=[22, 42],
    #     requests_on_user_per_second=5,
    # )
    # await strategy.start()
    # return
    # logger.add("logs.log", level="DEBUG")


    # tip = 2

    # data = get_users_data_from_xslx("users.xlsx")
    # data = get_users_data_from_xslx("/home/daniil/Downloads/Telegram Desktop/users (3).xlsx")
    # async with UsersService() as service:
    #     data = await service.get_users_by_reg_date(reg_date)

    # if not await database_prepared_correctly(reg_date, data):
    #     await prepare_database(reg_date, data)

    # multiple_requests = datetime.now() - timedelta(seconds=3)
    strategy = BindingStrategy(
        registration_date=reg_date,
        tip_formular=tip,
        users_data=data,
        mode="sync",
        # residental_proxy_url="http://brd-customer-hl_24f51215-zone-residential_proxy1:s2qqflcv6l2o@brd.superproxy.io:22225",
        residental_proxy_url=None,
        async_requests_num=2,
        multiple_registration_on=multiple_requests,
        multiple_registration_threads=5,
        without_remote_database=True,
        # proxies_file="proxies.txt",
        stop_when=[20, 22],
        requests_on_user_per_second=1,
    )
    res = await strategy.start()
    
    # res = await strategy.get_registerer_users(0)
    # print(res, len(res), len(data))
    ...


if __name__ == "__main__":
    asyncio.run(main())
