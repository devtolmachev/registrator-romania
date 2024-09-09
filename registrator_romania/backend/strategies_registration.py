import asyncio
from datetime import datetime, timedelta
import functools
import logging
import os
from pprint import pprint
from queue import Queue
import re
import ssl
from pathlib import Path
import platform
import random
import sys
from threading import Thread
import threading
import time
from typing import Literal
from zoneinfo import ZoneInfo
import aiofiles
from loguru import logger
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

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
    get_users_data_from_xslx,
)
from registrator_romania.backend.utils import get_dt_moscow
from registrator_romania.frontend.telegram_bot.alerting import (
    send_msg_into_chat,
)
from registrator_romania.backend.net import AIOHTTP_NET_ERRORS

# ssl._create_default_https_context = ssl._create_unverified_context


class StrategyWithoutProxy:
    def __init__(
        self,
        registration_date: datetime,
        tip_formular: int,
        debug: bool = False,
        users_data: list[dict] = None,
        stop_when: tuple[int, int] = None,
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
        requests_on_user_per_second: int = None,
    ) -> None:
        if not stop_when:
            stop_when = [9, 2]
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
            html = await api.make_registration(
                user_data=user_data,
                registration_date=reg_dt,
                tip_formular=self._tip_formular,
                proxy=proxy,
            )
            await self.post_registrate(user_data=user_data, html=html, queue=queue)

        tasks = [registrate(user_data) for user_data in users_data]
        for chunk in divide_list(tasks, divides=self._async_requests_num):
            try:
                await asyncio.gather(*chunk, return_exceptions=True)
            except Exception as e:
                if self._logging:
                    logger.exception(e)
                continue

    async def _start_multiple_registrator(self, dirname: str):
        users_data = self._users_data.copy()
        
        if not users_data:
            return
        
        if self._requests_per_user:
            users_data = users_data[0:self._requests_per_user-1]
            random.shuffle(users_data)

        queue = asyncio.Queue()
        proxies = None
        if self._proxies_file_path:
            with open(self._proxies_file_path) as f:
                src_list_proxies = f.read().splitlines()
                proxies = iter(src_list_proxies)

        async def registrate(user_data: dict):
            nonlocal queue, proxies

            proxy = None
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
                        str(
                            random.randrange(start=int(start_port), stop=int(stop_port))
                        ),
                        proxy,
                    )

            api = APIRomania(debug=self._api._debug, verifi_ssl=False)
            try:
                html = await api.make_registration(
                    user_data=user_data,
                    registration_date=self._registration_date,
                    tip_formular=self._tip_formular,
                    proxy=proxy,
                    timeout=10,
                )
                await self.post_registrate(user_data=user_data, html=html, queue=queue)
                await api._connections_pool.close()
            except Exception:
                pass

        if self._requests_on_user_per_second:
            tasks = [
                asyncio.create_task(registrate(user_data=user_data))
                for user_data in users_data
                for _ in [user_data] * self._requests_on_user_per_second
            ]
        else:
            tasks = [
                asyncio.create_task(registrate(user_data=user_data))
                for user_data in users_data
            ]
        random.shuffle(tasks)

        results = []

        if self._requests_per_user:
            results.extend(
                await asyncio.gather(
                    *tasks, return_exceptions=True
                )
            )
            logger.info(f"{results}")
        else:
            for chunk in divide_list(tasks, divides=30):
                results.extend(await asyncio.gather(*chunk, return_exceptions=True))
                logger.info(f"{results}")

        await self._save_successfully_registration_from_queue(
            queue=queue, dirname=dirname
        )

    async def schedule_multiple_registrations(self, dirname: str):
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._start_multiple_registrator(dirname=dirname))

        def start_threads():
            threads: list[Thread] = []
            for _ in range(self._multiple_registration_threads):
                th = Thread(target=run_in_thread)
                th.start()
                threads.append(th)
                time.sleep(1)
                logger.debug(f"Thread {th.name} started")

            for th in threads:
                th.join()
                logger.debug(f"Thread {th.name} finished")

            logger.debug("All threads finished")
            scheduler.remove_job(job_id=job.id)

        scheduler = BackgroundScheduler()
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

        now = self._get_dt_now()
        dirname = f"registrations_{reg_dt.strftime("%d.%m.%Y")}"

        if self._proxies_file_path:
            proxies = self._get_proxies_from_proxy_list()

            try:
                places = await asyncio.gather(
                    *[
                        api.get_free_places_for_date(
                            tip_formular=self._tip_formular,
                            month=reg_dt.month,
                            day=reg_dt.day,
                            year=reg_dt.year,
                            proxy=p,
                        )
                        for p in proxies
                    ],
                    return_exceptions=True,
                )
            except BaseException as e:
                logger.exception(e)

        if self._multiple_registration_on:
            try:
                await self.schedule_multiple_registrations(dirname=dirname)
            except Exception as e:
                if self._logging:
                    logger.exception(e)

        while True:
            logger.debug("Start cycle")
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
            successfully_registered.append(user_data)

            if not self._api.is_success_registration(html):
                continue

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
    tip = 2
    reg_date = datetime(year=2024, month=12, day=3)
    logger.add("logs.log")

    data = generate_fake_users_data(40)
    # data = get_users_data_from_xslx("users.xlsx")
    # async with UsersService() as service:
    #     data = await service.get_users_by_reg_date(reg_date)

    # if not await database_prepared_correctly(reg_date, data):
    #     await prepare_database(reg_date, data)

    multiple_requests = datetime.now()
    strategy = StrategyWithoutProxy(
        registration_date=reg_date,
        tip_formular=tip,
        users_data=data,
        mode="sync",
        # residental_proxy_url="http://brd-customer-hl_24f51215-zone-residential_proxy1:s2qqflcv6l2o@brd.superproxy.io:22225",
        residental_proxy_url=None,
        async_requests_num=2,
        multiple_registration_on=multiple_requests,
        multiple_registration_threads=10,
        without_remote_database=True,
        proxies_file="proxies.txt",
        # stop_when=multiple_requests + timedelta(seconds=15)
    )
    res = await strategy.get_unregisterer_users()
    ...


if __name__ == "__main__":
    asyncio.run(main())
