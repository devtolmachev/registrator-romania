import asyncio
from datetime import date, datetime
import json
import random
import string
import traceback
from typing import Optional
from zoneinfo import ZoneInfo

import aiofiles
import bs4
import dateutil
import dateutil.parser
from loguru import logger
import openpyxl
import pandas as pd
import ua_generator
import aiohttp
from aiohttp.client_exceptions import ClientHttpProxyError
from pypasser import reCaptchaV3

from registrator_romania.bot import send_msg_into_chat
from registrator_romania.proxy import AiohttpSession, aiohttp_session


SITE_TOKEN = "6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT"
BASE_URL = "https://programarecetatenie.eu"
URL_GENERAL = f"{BASE_URL}/programare_online"
URL_PLACES = f"{BASE_URL}/status_zii"
URL_DATES = f"{BASE_URL}/status_zile"
CAPTCHA_URL = (
    "https://www.google.com/recaptcha/api2/anchor?ar=1"
    f"&k={SITE_TOKEN}&co=aHR0cHM6Ly9wcm9ncmFtYXJlY2V0YX"
    "RlbmllLmV1OjQ0Mw..&hl=ru&v=DH3nyJMamEclyfe-nztbfV8S"
    "&size=invisible&cb=ulevyud5loaq"
)


def get_headers():
    ua = ua_generator.generate()
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9"
            ",image/avif,image/webp,image/apng,*/*;q=0.8,application"
            "/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://programarecetatenie.eu",
        "Referer": "https://programarecetatenie.eu/programare_online",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    }
    for key, value in ua.headers.get().items():
        headers[key] = value

    return headers


async def get_captcha_response() -> str:
    """Async get and return `g-recaptcha-response` field."""
    return await asyncio.to_thread(reCaptchaV3, CAPTCHA_URL)


@aiohttp_session()
async def check_places(
    session: aiohttp.ClientSession, dt: date, tip: int
) -> Optional[tuple[int, date]]:
    form = aiohttp.FormData()
    form.add_field("azi", dt.strftime("%Y-%m-%d"))
    form.add_field("tip_formular", str(tip))

    session._default_headers = get_headers()
    async with session.post(URL_PLACES, data=form) as resp:
        try:
            response = await resp.json(content_type=None)
            if response.get("numar_ramase"):
                return int(response["numar_ramase"]), dt
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            AttributeError,
        ) as e:
            msg = f"{e}: {await resp.text()}.\n{traceback.format_exc()}"
            logger.error(msg)
            return None


async def registrate(
    users_data: list[dict],
    tip_formular: int,
    reg_dt: date,
    proxies: str | None = None,
    _session: aiohttp.ClientSession | None = None,
):
    # Request body
    # {
    #     "tip_formular": "3",
    #     "nume_pasaport": "jvggcjgcg",
    #     "data_nasterii": "2020-06-18",
    #     "prenume_pasaport": "hfchfchf",
    #     "locul_nasterii": "jhvjgvjg",
    #     "prenume_mama": "tgcgdx",
    #     "prenume_tata": "dgcgxgd",
    #     "email": "ghvgxd@gmail.com",
    #     "numar_pasaport": "U545354",
    #     "data_programarii": "2024-10-16",
    #     "gdpr": "1",
    #     "honeypot": "",
    #     "g-recaptcha-response": "03AFcWeA5TPbxUp8c9ZAkwNIreC1H47-aWrqdINKi6v7Thi3uOPmtEeBUxiLgzY5-kvQ8g6dYHEamVx9zq7D6q7rcKl7qIC_ZsC1oElYaH19q0MPpgUHbrK6g3ZJkAqvqIGoGhJXVoFDcCxTT7W3d9vRmMEI7QaOuNTGxrmgbIPS6z7RdOjFwSJ4n4HqWmXq2vCJWyOlwXL9jC-535vYnCEdZek76BiR1F_SCPUdCdXs3kHdXhDQLVlSl9TEBIFmrVB3Z5TS7BoD0IXWg9oBBpjc1bpZ1kaeIZrTgMSDqI6WcWWJ4CyAB3FHYbm-68pabrsBppUl68zfsUcQkOv3qEj3ciMfKsqk8OK6kpqPcWk50DdQy3Ysu50ED6XpDLdKwDRa5_d8vNhn52noe8dxdLhQYiLS7xPIB_D6lQlrEfU8mI-Vslja25hpUJODXlqArN0SlfVAzH7bQiSP7UzSAeMEOzQAWex_G5fD2elt7pGXCtvrFHUwmUy7L4yc0bYoqyJ5CQqLR6t0_R72Bv-IGQ1NI6IlAam5vnPJNpANgkVSnSaAPV_rRBPZXqawGKmrIwsYeSmVCHtG-SPd6pz_L_6IVGaNNov9PsJXKRuxjcJBLuaakkQJgIfYQiQmWIzzC50uaZOTi8mgSx8C6a71z23U2P3HiD5Bao_Blagy0UJ12c9dNXO0uPzJlYlDalHF29ULLx6QVAa_s0",
    # }

    @aiohttp_session()
    async def reg(
        session: aiohttp.ClientSession,
        user_data: dict,
        proxy: str | None = None,
    ):
        if _session:
            session = _session

        session._default_headers = get_headers()

        data = {
            "tip_formular": tip_formular,
            "nume_pasaport": user_data["Nume Pasaport"].strip(),
            "data_nasterii": user_data["Data nasterii"].strip(),
            "prenume_pasaport": user_data["Prenume Pasaport"].strip(),
            "locul_nasterii": user_data["Locul naşterii"].strip(),
            "prenume_mama": user_data["Prenume Mama"].strip(),
            "prenume_tata": user_data["Prenume Tata"].strip(),
            "email": user_data["Adresa de email"].strip(),
            "numar_pasaport": user_data["Serie și număr Pașaport"].strip(),
            "data_programarii": reg_dt.strftime("%Y-%m-%d"),
            "gdpr": "1",
            "honeypot": "",
            "g-recaptcha-response": await get_captcha_response(),
        }

        try:
            async with session.post(
                URL_GENERAL, data=data, proxy=proxy
            ) as resp:
                return (await resp.text(), user_data)
        except ClientHttpProxyError:
            async with session.post(URL_GENERAL, data=data) as resp:
                return (await resp.text(), user_data)

    tasks = []
    proxy_iterator = iter(proxies)
    for user_data in users_data:
        try:
            p = next(proxy_iterator)
        except StopIteration:
            proxy_iterator = iter(proxies)
            p = next(proxy_iterator)

        tasks.append(reg(user_data, p))

    return await asyncio.gather(*tasks, return_exceptions=True)


def get_dt(tz: Optional[ZoneInfo] = None) -> datetime:
    if not tz:
        tz = ZoneInfo("Europe/Moscow")

    return datetime.now().astimezone(tz=tz)


def is_success(html_code: str) -> bool:
    r"""
    Return True if html response have paragraph `Felicitări`
    otherwise False.
    """
    if "<p>Felicitări!</p>" in html_code:
        return True
    return False


def get_error(html_code: str) -> str:
    r"""
    Return text of error in <p class="alert alert-danger"> tag
    """
    s = bs4.BeautifulSoup(html_code, "lxml")
    alert_tag = s.find("p", class_="alert alert-danger")
    if not alert_tag:
        return ""
    return alert_tag.text


def is_busy(html_code: str) -> bool:
    if '<p class="alert alert-danger">NU mai este loc</p>' in html_code:
        return True
    return False


class Transliterator:
    def __init__(self, language):
        if language == "tr":
            self.translit_dict = {
                "Ş": "S",
                "ş": "s",
                "İ": "I",
                "ı": "i",
                "Ğ": "G",
                "ğ": "g",
                "Ç": "C",
                "ç": "c",
                "Ö": "O",
                "ö": "o",
                "Ü": "U",
                "ü": "u",
            }
        else:
            self.translit_dict = {}

    def transliterate(self, text):
        return "".join(self.translit_dict.get(char, char) for char in text)


def get_users_data():
    keys = [
        "Prenume Pasaport",
        "Nume Pasaport",
        "Data nasterii",
        "Locul naşterii",
        "Prenume Mama",
        "Prenume Tata",
        "Adresa de email",
        "Serie și număr Pașaport",
    ]
    with open("users.txt") as f:
        data = f.read()

    objs = []
    for values in data.split("\n\n"):
        obj = {}
        for k, v in zip(keys, values.split("\n")):
            v = v.split(":")[-1].strip()
            v = Transliterator("tr").transliterate(v)
            if k == "Data nasterii":
                try:
                    dt = datetime.strptime(v, "%Y-%m-%d")
                except Exception:
                    dt = datetime.strptime(v, "%d-%m-%Y")
                v = dt.strftime("%Y-%m-%d")

            obj[k] = v
        obj["Adresa de email"] = obj["Adresa de email"].lower()
        objs.append(obj)

    return prepare_users_data(objs)


def prepare_users_data(users_data: list[dict]):
    keys = [
        "Prenume Pasaport",
        "Nume Pasaport",
        "Data nasterii",
        "Locul naşterii",
        "Prenume Mama",
        "Prenume Tata",
        "Adresa de email",
        "Serie și număr Pașaport",
    ]
    objs = []
    for us_data in users_data:
        obj = {}
        for k, v in us_data.items():
            # Replace values like `Doğum tarihi:09.09.1976`
            v = v.split(":")[-1].strip()
            # Change turkey letters on english letters
            v = Transliterator("tr").transliterate(v)

            if k == "Data nasterii":
                try:
                    dt = dateutil.parser.parse(v, dayfirst=False)
                except dateutil.parser.ParserError:
                    dt = dateutil.parser.parse(v, dayfirst=True)

                # We need to format date like `1976-09-09`
                v = dt.strftime("%Y-%m-%d")
                assert datetime.strptime(v, "%Y-%m-%d")

            obj[k] = v

        # Tranform case
        obj["Nume Pasaport"] = obj["Nume Pasaport"].upper()
        obj["Prenume Pasaport"] = obj["Prenume Pasaport"].upper()
        obj["Adresa de email"] = obj["Adresa de email"].lower()
        objs.append(obj)

    assert all(k in obj for k in keys for obj in objs)
    return objs


def get_users_data_from_xslx():
    keys = [
        "Prenume Pasaport",
        "Nume Pasaport",
        "Data nasterii",
        "Locul naşterii",
        "Prenume Mama",
        "Prenume Tata",
        "Adresa de email",
        "Serie și număr Pașaport",
    ]

    w = openpyxl.load_workbook("users.xlsx")
    sheet = w.active
    data = []
    for row in sheet.iter_rows(min_row=0, max_row=None, values_only=True):
        if not data:
            assert row
            row = keys.copy()

        data.append(row)
    df = pd.DataFrame(data)
    df.columns = df.iloc[0]
    df.drop(df.index[0], inplace=True)
    objs_raw = df.to_dict("records")
    return prepare_users_data(objs_raw)


def error_handler(f):
    async def wrapper(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            logger.exception(e)
            return await wrapper(*args, **kwargs)

    return wrapper


def generate_fake_users_data(n: int = 20):
    def random_string(n: int = 5):
        return "".join(random.choice(string.ascii_uppercase) for _ in range(n))

    return [
        {
            "Nume Pasaport": f"P{random_string(2)}IR",
            "Prenume Pasaport": f"{random_string(2)}DRI",
            "Data nasterii": f"199{random.randint(0, 9)}-10-1{random.randint(0, 9)}",
            "Locul naşterii": f"SI{random_string(1)}RI",
            "Prenume Mama": f"REC{random_string(1)}YE",
            "Prenume Tata": "SABRI",
            "Adresa de email": f"{random_string()}@gmail.com",
            "Serie și număr Pașaport": f"U{random.randint(10_000_000, 10_999_999)}",
        }
        for _ in range(n)
    ]


async def start_registration_process(dt: date, tip_formular: int):
    users_data = generate_fake_users_data()
    users_data = get_users_data_from_xslx()

    # while True:
    #     try:
    #         free_places = await check_places(dt, tip_formular)
    #     except Exception as e:
    #         logger.exception(e)
    #     else:
    #         not_places = free_places is None

    #         if not_places is False:
    #             logger.info(
    #                 f"script found {free_places} free places for date: {dt}"
    #             )
    #             break

    #         logger.info(f"Script not found free places for date: {dt}")
    #         await asyncio.sleep(random.uniform(0.5, 1))

    #     finally:
    #         if get_dt().hour == 9 and get_dt().minute >= 2:
    #             return

    logger.info(
        f"Try to make an appointments. General count of users - {len(users_data)}"
    )

    p = Proxysio()
    proxyies = await p.list_proxy(scheme="http")
    logger.debug(f"Proxies: {proxyies}")
    loop = asyncio.get_running_loop()
    session = AiohttpSession().generate()

    tasks = []
    while True:
        dt_now = get_dt()
        error = 0
        try:
            results = await registrate(
                users_data, tip_formular, dt, proxies=proxyies, _session=session
            )

            for result in results:
                if not isinstance(result, tuple):
                    continue

                html, user_data = result

                if not isinstance(html, str):
                    continue

                name = user_data["Nume Pasaport"]
                fn = f"user_{name}.html"
                async with aiofiles.open(fn, "w", encoding="utf-8") as f:
                    await f.write(html)

                if is_success(html) is False:
                    error += 1
                    text_error = get_error(html)
                    logger.error(
                        f"Registration for {name} was failed. Error:\n"
                        f"{text_error}.\nBusy status {is_busy(html)}.\n"
                        f"Date: {dt}\nTip formular: {tip_formular}"
                    )
                else:
                    us_data = json.dumps(
                        user_data, ensure_ascii=False, indent=2
                    )
                    msg = (
                        f"Registration for {name} was successfully.\n"
                        f"{us_data}\n"
                    )
                    logger.success(msg)
                    tasks.append(
                        loop.create_task(send_msg_into_chat(msg, file=fn))
                    )
                    users_data.remove(user_data)
            await asyncio.sleep(1.5)

        except Exception as e:
            logger.exception(e)
            error += 1

        finally:
            if dt_now.hour == 9 and dt_now.minute >= 1:
                break
            if not error:
                break

    for task in tasks:
        task: asyncio.Task

        if task.done():
            try:
                exception = task.exception()
                logger.exception(exception)
            except asyncio.CancelledError as exc:
                logger.exception(exc)
        else:
            try:
                await task
            except Exception as e:
                logger.exception(e)


async def is_registrate(dt: datetime, user_data: dict, tip_formular: int):
    dt_str = dt.strftime("%Y-%m-%d")
    data = {
        "draw": "3",
        "columns[0][data]": "tip_formular",
        "columns[0][name]": "",
        "columns[0][searchable]": "true",
        "columns[0][orderable]": "false",
        "columns[0][search][value]": str(tip_formular),
        "columns[0][search][regex]": "false",
        "columns[1][data]": "email",
        "columns[1][name]": "",
        "columns[1][searchable]": "true",
        "columns[1][orderable]": "false",
        "columns[1][search][value]": "",
        "columns[1][search][regex]": "false",
        "columns[2][data]": "nume_pasaport",
        "columns[2][name]": "",
        "columns[2][searchable]": "true",
        "columns[2][orderable]": "false",
        "columns[2][search][value]": user_data["Nume Pasaport"].strip(),
        "columns[2][search][regex]": "false",
        "columns[3][data]": "prenume_pasaport",
        "columns[3][name]": "",
        "columns[3][searchable]": "true",
        "columns[3][orderable]": "false",
        "columns[3][search][value]": user_data["Prenume Pasaport"].strip(),
        "columns[3][search][regex]": "false",
        "columns[4][data]": "data_nasterii",
        "columns[4][name]": "",
        "columns[4][searchable]": "true",
        "columns[4][orderable]": "false",
        "columns[4][search][value]": "",
        "columns[4][search][regex]": "false",
        "columns[5][data]": "data_programarii",
        "columns[5][name]": "",
        "columns[5][searchable]": "true",
        "columns[5][orderable]": "false",
        "columns[5][search][value]": f"{dt_str} AND {dt_str}",
        "columns[5][search][regex]": "false",
        "columns[6][data]": "ora_programarii",
        "columns[6][name]": "",
        "columns[6][searchable]": "true",
        "columns[6][orderable]": "false",
        "columns[6][search][value]": "",
        "columns[6][search][regex]": "false",
        "columns[7][data]": "numar_pasaport",
        "columns[7][name]": "",
        "columns[7][searchable]": "true",
        "columns[7][orderable]": "false",
        "columns[7][search][value]": "",
        "columns[7][search][regex]": "false",
        "start": "0",
        "length": "500",
        "search[value]": "",
        "search[regex]": "false",
    }

    @aiohttp_session()
    async def send(session: aiohttp.ClientSession):
        url = "https://programarecetatenie.eu/verificare_programare?ajax=true"
        resp = await session.post(url, data=data)
        response = await resp.json(content_type=None)
        registrated_users = [u for u in response["data"]]
        if user_data["Nume Pasaport"] in [
            u["nume_pasaport"] for u in registrated_users
        ] and user_data["Prenume Pasaport"] in [
            u["prenume_pasaport"] for u in registrated_users
        ]:
            return True
        return False

    try:
        return await send(), user_data
    except Exception as e:
        logger.exception(e)
        return False, user_data


async def check_registrations(dt: datetime, tip_formular: int):
    users_data = get_users_data_from_xslx()

    tasks = [
        is_registrate(dt=dt, user_data=user_data, tip_formular=tip_formular)
        for user_data in users_data
    ]

    for res in await asyncio.gather(*tasks, return_exceptions=True):
        if not isinstance(res, tuple):
            logger.exception(res)
            continue

        result, us_data = res
        if result:
            js = json.dumps(us_data, indent=2, ensure_ascii=False)
            message = (
                "Registration for user was successfully for "
                f"tip formular {tip_formular} and {dt}!!!\n{js}"
            )
            try:
                await send_msg_into_chat(message)
            except Exception:
                return


@error_handler
async def main():
    dt_now = get_dt()
    # dt = date(dt_now.year, 9, 17)
    dt = date(dt_now.year, 11, dt_now.day)

    # 4 - articolul 10. 3 for artcolul 11
    tip_formular = 4

    await start_registration_process(dt, tip_formular)
    try:
        await check_registrations(dt, tip_formular)
    except Exception as e:
        logger.exception(e)


if __name__ == "__main__":
    asyncio.run(main())
