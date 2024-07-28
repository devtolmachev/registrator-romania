import asyncio
from datetime import datetime, timedelta
import functools
import os
import ssl
from pathlib import Path
import platform
import random
import sys
from typing import Literal
from zoneinfo import ZoneInfo
import aiofiles
from loguru import logger
from pandas import DataFrame, date_range

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
)
from registrator_romania.frontend.telegram_bot.alerting import (
    send_msg_into_chat,
)
from registrator_romania.backend.net import AIOHTTP_NET_ERRORS

ssl._create_default_https_context = ssl._create_unverified_context


class StrategyWithoutProxy:
    """Strategy of registrations.

    Args:
        registration_dates (list[datetime, datetime]): range of dates to
            make registrations
        tip_formular (int): tip formular value
        users_data (list[dict], optional): list of users data (dict)
            to registrate. Defaults to None.
        stop_when (tuple[int, int], optional): time to stop process
            registrations. Defaults to None.
        mode (Literal["sync", "async"], optional): mode of registration
            process. Defaults to "sync".
        async_requests_num (int, optional): if mode equals "async" which
            requests should be asynchronously. Defaults to 10.
        use_shuffle (bool, optional): use `random.shuffle` of users data list,
            after each registrations. Defaults to True.
        logging (bool, optional): whether to call `logger.`. Defaults to True.
        residental_proxy_url (str, optional): url to get proxy from external
            pool, it param will passed to make registration api call.
            Defaults to None.
    """

    def __init__(
        self,
        registration_dates: list[datetime, datetime],
        tip_formular: int,
        users_data: list[dict] = None,
        stop_when: tuple[int, int] = None,
        mode: Literal["async", "sync"] = "sync",
        async_requests_num: int = 10,
        use_shuffle: bool = True,
        logging: bool = True,
        residental_proxy_url: str = None,
    ) -> None:
        assert len(registration_dates) == 2 and all(
            isinstance(r, datetime) for r in registration_dates
        ), "Param registration_dates must be list of 2 datetime objects"
        if not stop_when:
            stop_when = [9, 2]

        self._api = APIRomania()
        self._db = UsersService()
        self._users_data = users_data or []
        self._registration_dates = registration_dates
        self._tip_formular = int(tip_formular)
        self._stop_when = stop_when
        self._mode = mode
        self._async_requests_num = int(async_requests_num)
        self._use_shuffle = use_shuffle
        self._logging = logging
        self._residental_proxy_url = residental_proxy_url

    async def start(self):
        """Enrypoint of the strategy. Configure it in __init__ method, and
        call this method to start.

        At first we try to get unregister users from API, and write result to
        remote database, then we create task to update users list (removes the
        registered users), and at end we start registrations
        """
        if self._users_data:
            try:
                unregistered_users = await self.get_unregisterer_users()
                if unregistered_users:
                    self._users_data = unregistered_users.copy()
            except Exception as e:
                if self._logging:
                    logger.exception(e)

            await self.add_users_to_db()

        self.update_users_data_task = asyncio.create_task(
            self.update_users_list()
        )
        while not self._users_data:
            await asyncio.sleep(1)
        await self.start_registration()

    def _get_dt_now(self) -> datetime:
        return datetime.now().astimezone(tz=ZoneInfo("Europe/Moscow"))

    def _get_registration_dates(self) -> list[datetime]:
        """Get list of dates, to make registrations"""
        return (
            date_range(
                start=self._registration_dates[0],
                end=self._registration_dates[-1],
            )
            .to_pydatetime()
            .tolist()
        )

    async def async_registrations(
        self, users_data: list[dict], queue: asyncio.Queue
    ):
        """Send requests to API for registrate users.

        How it works? At start creates list of tasks, to registrate users.
        The list is split into `async_requests_num` chunks, and run by asyncio
        gather. Into task function we create list of `asyncio.create_task`
        for registration of registration dates, and do:

        >>> for task in in tasks:
        ...    html = await task
        ...    await self.post_registrate(html, ...)

        Args:
            users_data (list[dict]): users data to registrate
            queue (asyncio.Queue): success registration will put into queue
        """
        api = self._api
        reg_dts = self._get_registration_dates()
        proxy = self._residental_proxy_url

        async def registrate(user_data: dict):
            """Make registration(s).

            Call API to registrate user on registration dates

            Args:
                user_data (dict): user data
            """
            tasks = [
                asyncio.create_task(
                    api.make_registration(
                        user_data=user_data,
                        registration_date=reg_dt,
                        tip_formular=self._tip_formular,
                        proxy=proxy,
                    )
                )
                for reg_dt in reg_dts
            ]

            for task in tasks:
                html = await task
                await self.post_registrate(
                    user_data=user_data, html=html, queue=queue
                )

        tasks = [registrate(user_data) for user_data in users_data]
        for chunk in divide_list(tasks, divides=self._async_requests_num):
            try:
                async with asyncio.timeout(10):
                    await asyncio.gather(*chunk, return_exceptions=True)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self._logging:
                    logger.exception(e)
                continue

    async def post_registrate(
        self, user_data: dict, html: str, queue: asyncio.Queue
    ):
        """This func we call after request to registration.

        Args:
            user_data (dict): user data we tried to register
            html (str): response of api to make registration
            queue (asyncio.Queue): into queue we put success registration
        """
        first_name = user_data["Prenume Pasaport"]
        last_name = user_data["Nume Pasaport"]
        api = self._api

        if not isinstance(html, str):
            return

        if api.is_success_registration(html):
            try:
                async with asyncio.timeout(5):
                    async with self._db as db:
                        await db.remove_user(user_data)
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.exception(e)

            msg = f"successfully registrate {first_name} {last_name}"
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

    async def sync_registrations(
        self, users_data: list[dict], queue: asyncio.Queue
    ):
        """Sync registration.

        We do registrations sequentially for each user.

        Args:
            users_data (list[dict]): users data to registrate
            queue (asyncio.Queue): success registration will put into queue
        """
        api = self._api
        reg_dts = self._get_registration_dates()
        proxy = self._residental_proxy_url

        for user_data in users_data:
            try:
                tasks = [
                    api.make_registration(
                        user_data,
                        registration_date=reg_dt,
                        tip_formular=self._tip_formular,
                        proxy=proxy,
                    )
                    for reg_dt in reg_dts
                ]
                htmls = await asyncio.gather(*tasks, return_exceptions=True)

                for html in htmls:
                    await self.post_registrate(user_data, html, queue)
            except AIOHTTP_NET_ERRORS:
                pass
            except Exception as e:
                if self._logging:
                    logger.exception(e)

    async def start_registration(self):
        """Start main registration proccess.

        Proccess stop at time which passed to __init__ method as `stop_time`
        or if all users successfully registrate.
        """
        successfully_registered = []
        queue = asyncio.Queue()

        now = self._get_dt_now()
        dirname = f"registrations_{now.strftime("%d.%m.%Y")}"
        if not os.path.exists(dirname):
            Path(dirname).mkdir(exist_ok=True)

        while True:
            now = self._get_dt_now()
            await asyncio.sleep(1.5)

            try:
                users_for_registrate = [
                    u
                    for u in self._users_data.copy()
                    if u not in successfully_registered
                ]
                if self._use_shuffle:
                    random.shuffle(users_for_registrate)

                logger.debug(
                    f"Start registrations, we have {len(users_for_registrate)} "
                    "users to registrate"
                )
                if self._mode == "sync":
                    await self.sync_registrations(
                        users_data=users_for_registrate, queue=queue
                    )

                elif self._mode == "async":
                    await self.async_registrations(
                        users_data=users_for_registrate, queue=queue
                    )

                while not queue.empty():
                    user_data, html = await queue.get()
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

            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.exception(e)
            finally:
                if (
                    len(successfully_registered) >= len(self._users_data.copy())
                    or not users_for_registrate
                ):
                    break

                if (
                    now.hour == self._stop_when[0]
                    and now.minute >= self._stop_when[1]
                ):
                    break

        try:
            fn = f"successfully-registered.csv"
            path = Path().joinpath(dirname, fn)

            df = DataFrame(successfully_registered)
            df.to_csv(str(path), index=False)
        except Exception as e:
            logger.exception(e)

    async def update_users_list(self):
        """Update proxy list from remote db."""
        while True:
            try:
                users_data = self._users_data.copy()
                new_users_data = []

                async with self._db as db:
                    for reg_dt in self._get_registration_dates():
                        new_users_data.extend(
                            [
                                us
                                for us in await db.get_users_by_reg_date(reg_dt)
                                
                                if us not in new_users_data
                            ]
                        )

                self._users_data = new_users_data.copy()
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.exception(e)
            await asyncio.sleep(3)

    async def get_unregisterer_users(
        self, days: int = 3
    ) -> list[dict[str, str] | None]:
        """Get unregistered users from target API.

        Args:
            days (int, optional): days to range. Defaults to 3.

        Returns:
            list[dict[str, str] | None]: list of unregistered users
        """
        api = self._api
        users_data = self._users_data.copy()
        start_date = self._registration_dates[0] - timedelta(days=days)
        stop_date = self._registration_dates[-1]

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
        except AIOHTTP_NET_ERRORS:
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
        try:
            async with self._db as db:
                tasks = [
                    db.add_user(user_data, registration_date=reg_dt)
                    for reg_dt in self._get_registration_dates()
                    for user_data in self._users_data.copy()
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                ...
                # for reg_dt in self._get_registration_dates():
                #     for user_data in self._users_data:
                #         await db.add_user(user_data, registration_date=reg_dt)
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.exception(e)


async def prepare_database(reg_dt: datetime, users_data: list[dict]):
    async with UsersService() as service:
        users_from_db = await service.get_users_by_reg_date(
            registration_date=reg_dt
        )

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
        users_from_db = await service.get_users_by_reg_date(
            registration_date=reg_dt
        )

        if all(u in users_from_db for u in users_data):
            return True
        return False


async def main():
    tip = 3
    reg_date = datetime(year=2024, month=11, day=10)
    registration_dates = [reg_date, reg_date + timedelta(days=5)]

    data = generate_fake_users_data(50)

    if not await database_prepared_correctly(reg_date, data):
        await prepare_database(reg_date, data)
    async with UsersService() as service:
        data = await service.get_users_by_reg_date(reg_date)

    strategy = StrategyWithoutProxy(
        registration_dates=registration_dates,
        tip_formular=tip,
        users_data=data,
        mode="sync",
        residental_proxy_url="https://brd-customer-hl_24f51215-zone-residential_proxy1:s2qqflcv6l2o@brd.superproxy.io:22225",
        async_requests_num=2,
    )
    await strategy.start()


if __name__ == "__main__":
    asyncio.run(main())
