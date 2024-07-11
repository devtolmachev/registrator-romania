import asyncio
import calendar
from datetime import datetime, date
from pprint import pprint
import time
from typing import Required, TypedDict
from loguru import logger

import aiohttp
import bs4
from pyjsparser import parse
import ua_generator
from pypasser import reCaptchaV3
from registrator_romania import bot
from registrator_romania.new_request_registrator import (
    generate_fake_users_data,
    get_users_data_from_xslx,
)
from registrator_romania.proxy import (
    AIOHTTP_NET_ERRORS,
    AiohttpSession,
    FreeProxies,
    FreeProxiesList,
    GeoNode,
    ImRavzanProxyList,
    LionKingsProxy,
    ProxyMaster,
    AutomaticProxyPool,
)


UserData = TypedDict(
    "UserData",
    {
        "Nume Pasaport": Required[str],
        "Prenume Pasaport": Required[str],
        "Data nasterii": Required[str],
        "Locul naşterii": Required[str],
        "Prenume Mama": Required[str],
        "Prenume Tata": Required[str],
        "Adresa de email": Required[str],
        "Serie și număr Pașaport": Required[str],
    },
)


async def get_proxy_pool(start: bool = True, debug: bool = False):
    proxies_classes = (
        GeoNode(),
        FreeProxies(),
        FreeProxiesList(),
        ImRavzanProxyList(),
        LionKingsProxy(),
        ProxyMaster(),
    )
    proxies = [
        proxy
        for proxy_class in proxies_classes
        for proxy in await proxy_class.list_proxy()
    ]

    if debug:
        logger.debug(f"Total raw proxies - {len(proxies)}")

    pool = AutomaticProxyPool(proxies=proxies, debug=debug)
    if start:
        await pool
    return pool


class APIRomania:
    BASE_URL = "https://programarecetatenie.eu"
    SITE_TOKEN = "6LcnPeckAAAAABfTS9aArfjlSyv7h45waYSB_LwT"
    MAIN_URL = f"{BASE_URL}/programare_online"
    STATUS_DAYS_URL = f"{BASE_URL}/status_zile"
    STATUS_PLACES_URL = f"{BASE_URL}/status_zii"
    REGISTRATIONS_LIST_URL = f"{BASE_URL}/verificare_programare?ajax=true"
    CAPTCHA_URL = (
        "https://www.google.com/recaptcha/api2/anchor?ar=1"
        f"&k={SITE_TOKEN}&co=aHR0cHM6Ly9wcm9ncmFtYXJlY2V0YX"
        "RlbmllLmV1OjQ0Mw..&hl=ru&v=DH3nyJMamEclyfe-nztbfV8S"
        "&size=invisible&cb=ulevyud5loaq"
    )

    def __init__(self, debug: bool = False) -> None:
        self._sessionmaker = AiohttpSession()
        self._connections_pool = self._sessionmaker.generate_connector()
        self._proxy_pool: AutomaticProxyPool = None
        self._debug = debug
        self._main_html = None

    async def get_proxy_pool(self):
        if not self._proxy_pool:
            self._proxy_pool = await get_proxy_pool(
                start=True, debug=self._debug
            )

        return self._proxy_pool

    async def get_captcha_token(self):
        """Async get and return data for `g-recaptcha-response` field."""
        return await asyncio.to_thread(reCaptchaV3, self.CAPTCHA_URL)

    def get_error_registration_as_text(self, html_code: str) -> bool:
        r"""
        Return text of error in <p class="alert alert-danger"> tag
        """
        s = bs4.BeautifulSoup(html_code, "lxml")
        alert_tag = s.find("p", class_="alert alert-danger")
        if not alert_tag:
            return ""
        return alert_tag.text

    def is_success_registration(self, html_code: str) -> bool:
        r"""
        Return True if html response have paragraph `Felicitări`
        otherwise False.
        """
        if "<p>Felicitări!</p>" in html_code:
            return True
        return False

    @property
    def headers_main_url(self) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_registrations_list_url(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/verificare_programare",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_dates_url(self) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_places_url(self) -> dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    @property
    def headers_registration_url(self) -> dict[str, str]:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,my;q=0.6",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Origin": "https://programarecetatenie.eu",
            "Referer": "https://programarecetatenie.eu/programare_online",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        for k, v in ua_generator.generate().headers.get().items():
            headers[k] = v
        return headers

    async def _get_main_html(self):
        if self._main_html:
            return self._main_html

        session = self._sessionmaker.generate(connector=self._connections_pool)
        session._default_headers = self.headers_main_url

        async with session:
            proxies = [None]
            while True:
                try:
                    for proxy in proxies:
                        async with session.get(
                            self.MAIN_URL, proxy=proxy
                        ) as resp:
                            reason = resp.reason.lower()

                            if reason.count("forbidden") and proxies == [None]:
                                pool = await self.get_proxy_pool()
                                url = self.MAIN_URL
                                headers = self.headers_main_url
                                proxies = await pool.collect_valid_proxies(
                                    url=url, headers=headers
                                )
                                continue

                            return await resp.text()

                except AIOHTTP_NET_ERRORS:
                    await asyncio.sleep(1.5)
                    continue

    async def _get_default_disabled_weekdays(
        self, year: int, month: int, tip_formular: int
    ) -> list[int]:
        html = await self._get_main_html()
        soup = bs4.BeautifulSoup(html, "lxml")
        tag_script = soup.find_all("script")[-2]
        js_script = tag_script.text

        parsed = parse(js_script)

        obj = {}
        func_body = parsed["body"][0]["expression"]["arguments"][0]["body"]
        cases = func_body["body"][14]["consequent"]["body"][3]["expression"][
            "arguments"
        ][0]["properties"][6]["value"]["body"]["body"][0]["cases"]

        for case in cases:
            k = case["test"]["value"]
            v = [
                int(element["value"])
                for element in case["consequent"][0]["declarations"][0]["init"][
                    "elements"
                ]
            ]
            obj[str(k)] = v

        return obj[str(tip_formular)]

    async def _get_disabled_days(
        self, year: int, month: int, tip_formular: int
    ):
        session = self._sessionmaker.generate(connector=self._connections_pool)
        session._default_headers = self.headers_dates_url

        month = f"0{month}" if len(str(month)) == 1 else str(month)
        form_data = aiohttp.FormData()
        form_data.add_field("azi", f"{year}-{month}")
        form_data.add_field("tip_formular", str(tip_formular))
        async with session:
            async with session.post(
                self.STATUS_DAYS_URL, data=form_data
            ) as resp:
                raw = await resp.read()
                response = await resp.json(content_type=resp.content_type)

        return [
            date.day
            for date_string in response["data"]
            for date in [datetime.strptime(date_string, "%Y-%m-%d")]
            if date.month == int(month) and date.year == int(year)
        ]

    async def get_free_days(
        self, month: int, tip_formular: int, year: int = None
    ):
        if not year:
            year = datetime.now().year

        weekdays_disable = await self._get_default_disabled_weekdays(
            year=year, month=month, tip_formular=tip_formular
        )
        days_disable = await self._get_disabled_days(
            year=year, month=month, tip_formular=tip_formular
        )

        dates = []
        for day in range(1, int(calendar.monthrange(year, month)[1]) + 1):
            dt = date(year, month, day)
            weekday_num = 0 if dt.isoweekday() == 7 else dt.isoweekday()
            if weekday_num not in weekdays_disable and day not in days_disable:
                dates.append(dt.strftime("%Y-%m-%d"))
        return dates

    async def get_free_places_for_date(
        self, tip_formular: int, month: int, day: int, year: int = None
    ):
        if not year:
            year = datetime.now().year
        month = f"0{month}" if len(str(month)) == 1 else str(month)

        session = self._sessionmaker.generate(self._connections_pool)
        session._default_headers = self.headers_places_url

        form_data = aiohttp.FormData()
        form_data.add_field("azi", f"{year}-{month}-{day}")
        form_data.add_field("tip_formular", tip_formular)

        async with session:
            async with session.post(
                self.STATUS_PLACES_URL, data=form_data
            ) as resp:
                raw = await resp.read()
                response = await resp.json(content_type=resp.content_type)

        return response["numar_ramase"]

    async def make_registration(
        self,
        user_data: UserData,
        registration_date: datetime,
        tip_formular: int,
        proxy: str = None,
    ):
        session = self._sessionmaker.generate(self._connections_pool)
        session._default_headers = self.headers_registration_url

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
            "data_programarii": registration_date.strftime("%Y-%m-%d"),
            "gdpr": "1",
            "honeypot": "",
            "g-recaptcha-response": await self.get_captcha_token(),
        }

        try:
            async with session:
                async with session.post(
                    self.MAIN_URL, data=data, proxy=proxy
                ) as resp:
                    raw = await resp.read()
                    return await resp.text()
        except AIOHTTP_NET_ERRORS:
            pass

    async def see_registrations(
        self,
        tip_formular: str = "",
        email: str = "",
        nume: str = "",
        prenume: str = "",
        data_nasterii: str = "",
        numar_pasaport: str = "",
        limit: int = 500,
        data_programarii: list[datetime] = None,
    ):
        if data_programarii:
            dt_start, dt_end = map(
                lambda dt: dt.strftime("%Y-%m-%d"), data_programarii
            )
        else:
            dt_start, dt_end = ("", "")
        data = {
            "draw": "4",
            "columns[0][data]": "tip_formular",
            "columns[0][name]": "",
            "columns[0][searchable]": "true",
            "columns[0][orderable]": "false",
            "columns[0][search][value]": tip_formular,
            "columns[0][search][regex]": "false",
            "columns[1][data]": "email",
            "columns[1][name]": "",
            "columns[1][searchable]": "true",
            "columns[1][orderable]": "false",
            "columns[1][search][value]": email,
            "columns[1][search][regex]": "false",
            "columns[2][data]": "nume_pasaport",
            "columns[2][name]": "",
            "columns[2][searchable]": "true",
            "columns[2][orderable]": "false",
            "columns[2][search][value]": nume,
            "columns[2][search][regex]": "false",
            "columns[3][data]": "prenume_pasaport",
            "columns[3][name]": "",
            "columns[3][searchable]": "true",
            "columns[3][orderable]": "false",
            "columns[3][search][value]": prenume,
            "columns[3][search][regex]": "false",
            "columns[4][data]": "data_nasterii",
            "columns[4][name]": "",
            "columns[4][searchable]": "true",
            "columns[4][orderable]": "false",
            "columns[4][search][value]": data_nasterii,
            "columns[4][search][regex]": "false",
            "columns[5][data]": "data_programarii",
            "columns[5][name]": "",
            "columns[5][searchable]": "true",
            "columns[5][orderable]": "false",
            "columns[5][search][value]": f"{dt_start} AND {dt_end}",
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
            "columns[7][search][value]": numar_pasaport,
            "columns[7][search][regex]": "false",
            "start": "0",
            "length": limit,
            "search[value]": "",
            "search[regex]": "false",
        }

        session = self._sessionmaker.generate(self._connections_pool)
        session._default_headers = self.headers_registrations_list_url
        async with session:
            async with session.post(
                self.REGISTRATIONS_LIST_URL, data=data
            ) as resp:
                raw = await resp.read()
                return await resp.json(content_type=resp.content_type)


async def registration(
    tip_formular: int, year: int, month: int, registration_date: datetime
):
    api = APIRomania()
    users_data = get_users_data_from_xslx()
    # pool = await api.get_proxy_pool()
    proxies = []
    while True:
        await asyncio.sleep(2)
        places = await api.get_free_places_for_date(
            tip_formular=tip_formular,
            month=month,
            day=registration_date.day,
            year=year,
        )
        if not places:
            continue

        errors = 0
        for us in users_data:
            try:
                html = await api.make_registration(
                    us,
                    registration_date=registration_date,
                    tip_formular=tip_formular,
                )
                fn = f"{us["Nume Pasaport"]}-{time.time()}.html"
                
                with open(fn, "w") as f:
                    f.write(html)
                    
                asyncio.get_event_loop().create_task(
                    bot.send_msg_into_chat(
                        f"Успешная регистрация для {us["Nume Pasaport"]}!", fn
                    )
                )
                users_data.remove(us)
            except Exception as e:
                logger.exception(e)
                errors += 1
        
        if not users_data:
            return


async def main():
    year = 2024
    month = 11
    tip_formular = 3
    registration_date = datetime(year=year, month=month, day=datetime.now().day)

    await registration(tip_formular, year, month, registration_date)
    # api = APIRomania()
    # pool = await api.get_proxy_pool()
    # days = await api.get_free_days(
    #     month=month, year=year, tip_formular=tip_formular
    # )
    # print(days)
    # users_data = get_users_data_from_xslx()
    # pprint(users_data)
    ...


if __name__ == "__main__":
    asyncio.run(main())
