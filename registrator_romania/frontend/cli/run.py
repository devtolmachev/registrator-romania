import asyncio
from datetime import date, datetime
import os
from pathlib import Path
import sys
from typing import Literal
from zoneinfo import ZoneInfo
import logging
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from registrator_romania.backend.database.api import UsersService
from registrator_romania.backend.strategies_registration import (
    StrategyWithoutProxy,
    database_prepared_correctly,
    prepare_database,
)
from registrator_romania.backend.utils import (
    filter_by_log_level,
    generate_fake_users_data,
    get_users_data_from_xslx,
)


async def main_async(
    mode: Literal["sync", "async"],
    async_requests_num: int,
    use_shuffle: bool,
    stop_time: datetime,
    start_time: datetime,
    registration_date: date,
    save_logs: bool,
    users_file: str,
    tip_formular: int,
):
    dt = datetime.now().astimezone(ZoneInfo("Europe/Moscow"))
    dirpath = f"registrations_{dt.strftime("%d.%m.%Y")}"

    if save_logs:
        logger.remove()
        logger.add(
            sys.stderr,
            filter=filter_by_log_level(loglevels=["INFO", "SUCCESS", "ERROR"]),
        )
        logger.add(
            Path().joinpath(dirpath, "errors.log"),
            filter=filter_by_log_level(loglevels=["ERROR"]),
        )
        logger.add(
            Path().joinpath(dirpath, "debug.log"),
            filter=filter_by_log_level(loglevels=["DEBUG"]),
        )
        logger.add(
            Path().joinpath(dirpath, "success.log"),
            filter=filter_by_log_level(loglevels=["SUCCESS"]),
        )

    users_data = get_users_data_from_xslx(path=users_file)

    async def start_registrations():
        # users_data = generate_fake_users_data(5)
        strategy = StrategyWithoutProxy(
            registration_date=registration_date,
            tip_formular=tip_formular,
            use_shuffle=use_shuffle,
            logging=save_logs,
            users_data=users_data,
            stop_when=stop_time,
            mode=mode,
            async_requests_num=async_requests_num,
        )
        await strategy.start()

    try:
        async with asyncio.timeout(10):
            correctly = await database_prepared_correctly(
                reg_dt=registration_date, users_data=users_data
            )
        if not correctly:
            await prepare_database(reg_dt=registration_date, users_data=users_data)
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        logger.exception(e)
    else:
        async with UsersService() as service:
            users_data = await service.get_users_by_reg_date(
                registration_date=registration_date
            )

    logging.getLogger("apscheduler").setLevel(level=logging.ERROR)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(start_registrations, "cron", start_date=start_time)
    scheduler.start()

    while True:
        await asyncio.sleep(60)
        dt_now = datetime.now().astimezone(ZoneInfo("Europe/Moscow"))
        if dt_now.hour == stop_time.hour and dt_now.minute >= stop_time.minute:
            break


def main():
    mode = os.environ["mode"]
    async_requests_num = os.environ["async_requests_num"]
    use_shuffle = os.environ["use_shuffle"]
    stop_time = os.environ["stop_time"]
    start_time = os.environ["start_time"]
    registration_date = os.environ["registration_date"]
    save_logs = os.environ["save_logs"]
    users_file = os.environ["users_file"]
    tip_formular = os.environ["tip_formular"]

    start_time = datetime.now().strptime(start_time, "%H:%M")
    stop_time = datetime.strptime(stop_time, "%H:%M")
    registration_date = datetime.strptime(registration_date, "%d.%m.%Y")
    use_shuffle = True if "yes" else False
    save_logs = True if "yes" else False

    start_time = (
        datetime.now()
        .astimezone(ZoneInfo("Europe/Moscow"))
        .replace(hour=start_time.hour, minute=start_time.minute)
    )
    stop_time = (
        datetime.now()
        .astimezone(ZoneInfo("Europe/Moscow"))
        .replace(hour=start_time.hour, minute=start_time.minute)
    )
    # return pprint(
    #     {
    #         "mode": mode,
    #         "async_requests_num": async_requests_num,
    #         "use_shuffle": use_shuffle,
    #         "stop_time": stop_time,
    #         "start_time": start_time.strftime("%H-%M"),
    #         "registration_date": registration_date,
    #         "save_logs": save_logs,
    #         "users_file": users_file,
    #         "tip_formular": tip_formular,
    #     }
    # )
    asyncio.run(
        # main_async(
        #     mode="sync",
        #     async_requests_num="10",
        #     use_shuffle=True,
        #     stop_time=datetime(
        #         2024,
        #         7,
        #         26,
        #         0,
        #         5,
        #         9,
        #         497745,
        #         tzinfo=zoneinfo.ZoneInfo(key="Europe/Moscow"),
        #     ),
        #     start_time=datetime(
        #         2024,
        #         7,
        #         26,
        #         0,
        #         5,
        #         40,
        #         976417,
        #         tzinfo=zoneinfo.ZoneInfo(key="Europe/Moscow"),
        #     ),
        #     registration_date=datetime(2024, 11, 20, 0, 0),
        #     save_logs=True,
        #     users_file="users.xlsx",
        #     tip_formular="2",
        # )
        main_async(
            mode=mode,
            async_requests_num=async_requests_num,
            use_shuffle=use_shuffle,
            stop_time=stop_time,
            start_time=start_time,
            registration_date=registration_date,
            save_logs=save_logs,
            users_file=users_file,
            tip_formular=tip_formular,
        )
    )


if __name__ == "__main__":
    main()
