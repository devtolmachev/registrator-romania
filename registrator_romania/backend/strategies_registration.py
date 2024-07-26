import asyncio
from datetime import datetime, timedelta
import functools
import os
from pathlib import Path
import platform
import random
import sys
from typing import Literal
from zoneinfo import ZoneInfo
import aiofiles
from loguru import logger
from pandas import DataFrame

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
    ) -> None:
        if not stop_when:
            stop_when = [9, 2]

        self._api = APIRomania(debug=debug)
        self._db = UsersService()
        self._sessiongenerator = AiohttpSession()
        self._users_data = users_data or []
        self._registration_date = registration_date
        self._tip_formular = int(tip_formular)
        self._stop_when = stop_when
        self._mode = mode
        self._async_requests_num = int(async_requests_num)
        self._use_shuffle = use_shuffle
        self._logging = logging

    async def start(self):
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

    async def async_registrations(
        self, users_data: list[dict], queue: asyncio.Queue
    ):
        api = self._api
        reg_dt = self._registration_date

        tasks = [
            (
                api.make_registration(
                    user_data=user_data,
                    registration_date=reg_dt,
                    tip_formular=self._tip_formular,
                    queue=queue,
                ),
                user_data,
            )
            for user_data in users_data
        ]

        for chunk in divide_list(tasks, divides=self._async_requests_num):
            try:
                await asyncio.gather(
                    *[i[0] for i in chunk], return_exceptions=True
                )
            except Exception as e:
                if self._logging:
                    logger.exception(e)
                continue

    async def post_registrate(
        self, user_data: dict, html: str, queue: asyncio.Queue
    ):
        first_name = user_data["Prenume Pasaport"]
        last_name = user_data["Nume Pasaport"]
        api = self._api

        if not isinstance(html, str):
            return

        if api.is_success_registration(html):
            async with self._db as db:
                await db.remove_user(user_data)

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
                async with self._db as db:
                    await db.remove_user(user_data)

            msg = f"{first_name} {last_name} - {error}"
            if self._logging:
                logger.error(msg)

    async def sync_registrations(
        self, users_data: list[dict], queue: asyncio.Queue
    ):
        api = self._api
        reg_dt = self._registration_date

        for user_data in users_data:
            try:
                html = await api.make_registration(
                    user_data,
                    registration_date=reg_dt,
                    tip_formular=self._tip_formular,
                )
                await self.post_registrate(user_data, html, queue)

            except Exception as e:
                if self._logging:
                    logger.exception(e)

    async def start_registration(self):
        api = self._api
        reg_dt = self._registration_date
        successfully_registered = []
        queue = asyncio.Queue()

        now = self._get_dt_now()
        dirname = f"registrations_{now.strftime("%d.%m.%Y")}"

        while True:
            now = self._get_dt_now()
            await asyncio.sleep(1.5)
            places = await api.get_free_places_for_date(
                tip_formular=self._tip_formular,
                month=reg_dt.month,
                day=reg_dt.day,
                year=reg_dt.year,
            )
            if not places:
                logger.debug(f"{places} places")
                continue

            users_for_registrate = [
                u
                for u in self._users_data.copy()
                if u not in successfully_registered
            ]
            if self._use_shuffle:
                random.shuffle(users_for_registrate)

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
                Path().mkdir(dirname, exist_ok=True)

                async with aiofiles.open(str(path), "w") as f:
                    await f.write(html)

            if len(successfully_registered) >= len(self._users_data.copy()):
                break

            if (
                now.hour == self._stop_when[0]
                and now.minute >= self._stop_when[1]
            ):
                break

        fn = f"successfully-registered.csv"
        path = Path().joinpath(dirname, fn)

        df = DataFrame(successfully_registered)
        df.to_csv(str(path), index=False)

    async def update_users_list(self):
        while True:
            async with self._db as db:
                self._users_data = await db.get_users_by_reg_date(
                    self._registration_date
                )
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
        async with self._db as db:
            for user_data in self._users_data:
                await db.add_user(
                    user_data, registration_date=self._registration_date
                )


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
    tip = 1
    reg_date = datetime(year=2024, month=9, day=2)

    data = generate_fake_users_data(5)
    # async with UsersService() as service:
    #     data = await service.get_users_by_reg_date(reg_date)
    # if not await database_prepared_correctly(reg_date, data):
    #     await prepare_database(reg_date, data)

    strategy = StrategyWithoutProxy(
        registration_date=reg_date,
        tip_formular=tip,
        users_data=data,
        mode="sync",
    )
    await strategy.start()


if __name__ == "__main__":
    asyncio.run(main())