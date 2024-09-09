import asyncio
from datetime import datetime, timedelta
import json
import os
from pprint import pprint
import re
import traceback
from typing import Any
import flet as ft
from loguru import logger

from registrator_romania.backend.api.api_romania import APIRomania
from registrator_romania.backend.strategies_registration import StrategyWithoutProxy
from registrator_romania.backend.utils import (
    generate_fake_users_data,
    get_users_data_from_xslx,
    get_users_data_from_csv,
    setup_loggers,
)


class AppHeader(ft.Container):
    ...

    def __init__(self):
        super().__init__(alignment=ft.alignment.center, padding=ft.padding.all(10))

        self.content = ft.Text(
            "Регистратор Румыния", weight=ft.FontWeight.W_600, size=30
        )


class TipFormularSelector(ft.Container):
    def __init__(self, tip_formulars: dict[str, int]):
        super().__init__(alignment=ft.alignment.center, padding=ft.padding.all(10))

        tip_formular_names = [tip_name.upper() for tip_name in tip_formulars]
        self.tip_formulars = tip_formulars
        dropdown_content = ft.Dropdown(
            options=[ft.dropdown.Option(t) for t in tip_formular_names],
            width=500,
            value=tip_formular_names[0],
        )

        self.content = dropdown_content

    @property
    def selected_tip_formular_id(self):
        dropdown: ft.Dropdown = self.content
        return self.tip_formulars[dropdown.value]

    def set_tip_formular(self, val: str):
        self.content.value = val
        self.page.update()

    def get_tip_formular(self):
        return self.content.value


class RegistrationDatePicker(ft.Container):
    def __init__(self, on_change_date):
        super().__init__(alignment=ft.alignment.center, padding=ft.padding.all(10))

        places = None
        self.date_picker_element = ft.DatePicker(
            first_date=datetime.now() - timedelta(365),
            last_date=datetime.now() + timedelta(365),
            on_change=on_change_date,
        )

        date_picker = self.date_picker_element

        btn = ft.ElevatedButton(
            "Выбрать дату регистрации",
            icon=ft.icons.CALENDAR_MONTH,
            on_click=lambda e: self.page.open(date_picker),
        )

        if date_picker.value:
            date = date_picker.value.strftime("%d.%m.%Y")
            text = f"Выбрана дата: {date}. Свободных мест: {places}"
        else:
            text = "Не выбрана дата"

        self.helper_text = ft.Ref[ft.Text]()
        self.content = ft.Container(
            ft.Column(controls=[btn, ft.Text(text, size=15, ref=self.helper_text)]),
        )

    def get_registration_date(self) -> datetime:
        if not self.date_picker_element:
            raise ValueError(self.date_picker_element)

        return self.date_picker_element.value

    def set_registration_date(self, val: datetime):
        self.date_picker_element.value = val
        self.page.update()


class ConfigManager(ft.Container):
    def __init__(self, file_picker: ft.FilePicker):
        super().__init__(padding=ft.padding.all(10))

        btn_load = ft.ElevatedButton(
            "Загрузить настройки из дампа настроек (JSON)",
            on_click=lambda _: file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["json"],
            ),
        )

        btn_upload = ft.ElevatedButton(
            "Дамп текущих настроек (JSON)",
            on_click=lambda _: file_picker.save_file(),
        )

        self.content = ft.Row([btn_load, btn_upload], alignment=ft.alignment.top_right)


class UsersFile(ft.Container):
    def __init__(self, file_picker: ft.FilePicker, update_users_event=None):
        super().__init__(padding=ft.padding.all(10))

        btn = ft.ElevatedButton(
            "Выбрать файл с пользователями",
            on_click=lambda _: file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["xlsx", "csv"],
                dialog_title="Выбрать таблицу с пользователями",
            ),
        )

        self._checkbox = ft.Ref[ft.Checkbox]()
        checkbox = ft.Checkbox(
            "Сгенерированные пользователи",
            on_change=self._checkbox_clicked,
            ref=self._checkbox,
        )
        self._input_text = ft.Ref[ft.TextField]()

        def random_users_change(e):
            if not text_field.value or int(text_field.value) > 40:
                text_field.value = ""
                self.page.update()
            else:
                self._users = generate_fake_users_data(int(text_field.value))
                update_users_event(int(text_field.value))

        text_field = ft.TextField(
            label="Количество пользователей",
            input_filter=ft.InputFilter(
                allow=True, regex_string=r"^[0-9]*$", replacement_string=""
            ),
            disabled=True,
            visible=False,
            ref=self._input_text,
            on_change=random_users_change,
        )

        self._fp = file_picker
        self._fp.on_result = self.on_pick_result
        self.content = ft.Column([btn, ft.Row([checkbox, text_field])])
        self._update_users_event = update_users_event

    def _checkbox_clicked(self, e):
        if self._checkbox.current.value:
            visible = True
            disabled = False
        else:
            visible = False
            disabled = True

        input_text = self._input_text.current
        input_text.visible = visible
        input_text.disabled = disabled
        self.page.update()

    def open_modal(self, text):
        modal = ft.AlertDialog(
            content=ft.Text(text),
            adaptive=True,
        )
        self.page.open(modal)

    def on_pick_result(self, e):
        if not self._fp.result.files:
            return

        file = self._fp.result.files[0]

        try:
            ext = os.path.splitext(file.path)[-1].strip(".")
            if ext == "xlsx":
                users = get_users_data_from_xslx(file.path)
            elif ext == "csv":
                users = get_users_data_from_csv(file.path)
            else:
                raise ValueError(
                    f"Неизвестное расширение файла - {file.name}\n\n"
                    f"Файл - {file.path}"
                )
        except Exception as exc:
            content = f"{exc}\n\n{traceback.format_exc()}"
            return self.open_modal(content)

        self._users = users
        self._update_users_event(len(users))
        self.content.text = file.name
        self.page.update()

    def get_users_data(self):
        return self._users

    def set_users_data(self, val: list[dict[str, Any]]):
        self._users = val
        self._update_users_event(len(val))
        self.content.text = "config dump"
        self.page.update()


class ProxyFile(ft.Container):
    def __init__(self, file_picker: ft.FilePicker):
        super().__init__(padding=ft.padding.all(10))

        btn = ft.ElevatedButton(
            "Выбрать файл с прокси",
            on_click=lambda _: file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["txt"],
            ),
        )
        self._fp = file_picker
        self._fp.on_result = self.on_pick_result
        self.content = btn

    def open_modal(self, text):
        modal = ft.AlertDialog(
            content=ft.Text(text),
            adaptive=True,
        )
        self.page.open(modal)

    def _validate_file_content(self, path: str):
        with open(path) as f:
            content = f.read()

        for line in content.splitlines():
            if not line:
                continue

            if not line.count("http"):
                raise ValueError(f"Неизвестная строка - {line}")

    def on_pick_result(self, e):
        file = self._fp.result.files[0]

        try:
            ext = os.path.splitext(file.path)[-1].strip(".")
            if ext == "txt":
                self._validate_file_content(file.path)
            else:
                raise ValueError(
                    f"Неизвестное расширение файла - {file.name}\n\n"
                    f"Файл - {file.path}"
                )
        except Exception as exc:
            return self.open_modal(str(exc))

        self._proxies_fp = file.path
        self.content.text = file.name
        self.page.update()

    def get_proxies_filepath(self):
        return self._proxies_fp

    def set_proxies_filepath(self, val: str):
        self._proxies_fp = val
        self.content.text = os.path.split(val)[-1]
        self.page.update()


class AditionalSettings(ft.Container):
    def __init__(self, people_count: int, updated_rpc_callback=None) -> None:
        super().__init__(padding=ft.padding.all(5), alignment=ft.alignment.center)

        self._count_of_peoples = people_count
        self._approximate_count_rps = 1
        self._ref_requests_rps_per_human = ft.Ref[ft.Slider]()
        self._ref_humans_per_second = ft.Ref[ft.Slider]()
        self._ref_modal = ft.Ref[ft.AlertDialog]()
        self._ref_text_rpc = ft.Ref[ft.Text]()
        self._ref_multiple_threads_count = ft.Ref[ft.Slider]()
        self._ref_time_pick_hour = ft.Ref[ft.TextField]()
        self._ref_time_pick_minute = ft.Ref[ft.TextField]()
        self._ref_time_pick_seconds = ft.Ref[ft.TextField]()

        self._alert_window = self._build_modal()

        self._updated_rpc_callback = updated_rpc_callback
        self.content = ft.TextButton(
            "Дополнительные настройки", on_click=self._on_click_button
        )

    def change_count_of_peoples(self, val: int):
        self._count_of_peoples = val

    def calculate_rpc(self):
        human_per_second = int(self._ref_humans_per_second.current.value)
        requests_per_second_per_human = int(
            self._ref_requests_rps_per_human.current.value
        )

        self._approximate_count_rps = human_per_second * requests_per_second_per_human
        self._updated_rpc_callback(int(self._approximate_count_rps))
        self._ref_text_rpc.current.value = self.rpc_display_field_text()

    def _calculate_rps(self, _):
        self.calculate_rpc()
        self.page.update()

    def rpc_display_field_text(self):
        return (
            "Примерное количество запросов в секунду - "
            f"{self._approximate_count_rps}"
        )

    def _build_modal(self):
        def on_change_hour_value(e):
            control = self._ref_time_pick_hour.current
            if not control.value:
                return

            if not control.value.isdigit() or int(control.value) not in range(24):
                control.value = ""
                self.page.update()

        def on_change_minutes_value(e):
            control = self._ref_time_pick_minute.current
            if not control.value:
                return

            if not control.value.isdigit() or int(control.value) not in range(60):
                control.value = ""
                self.page.update()

        def on_change_seconds_value(e):
            control = self._ref_time_pick_seconds.current
            if not control.value:
                return

            if not control.value.isdigit() or int(control.value) not in range(60):
                control.value = ""
                self.page.update()

        modal_content = ft.Container(
            padding=ft.padding.only(left=20, right=20),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                spacing=20,
                                controls=[
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "Сколько должно отправляться \nзапросов на регистрацию, \n"
                                                "в секунду, для каждого \nчеловека?"
                                            ),
                                            ft.Slider(
                                                1,
                                                min=1,
                                                max=20,
                                                divisions=100,
                                                label="{value}",
                                                ref=self._ref_requests_rps_per_human,
                                                on_change=self._calculate_rps,
                                            ),
                                        ],
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "Сколько человек в секунду \nнужно регистрировать?"
                                            ),
                                            ft.Slider(
                                                1,
                                                min=1,
                                                max=self._count_of_peoples,
                                                divisions=100,
                                                label="{value}",
                                                ref=self._ref_humans_per_second,
                                                on_change=self._calculate_rps,
                                            ),
                                        ],
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "Сколько потоков должна использовать "
                                                "программа? \nКаждый поток стартует "
                                                "через 1 \nсекунду от момента запуска "
                                                "предыдущего \nпотока"
                                            ),
                                            ft.Slider(
                                                1,
                                                min=1,
                                                max=20,
                                                divisions=100,
                                                label="{value}",
                                                ref=self._ref_multiple_threads_count,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                "Когда запускать процесс регистрации?"
                                            ),
                                            ft.Icon(
                                                ft.icons.QUESTION_MARK,
                                                tooltip=(
                                                    "Час запуска - Вы должны указать час, когда должен запуститься процесс регистраций (например 16)\n"
                                                    "Минуты запуска - Вы должны указать минуты, когда должен запуститься процесс регистраций (например 30)\n"
                                                    "Секунды запуска - Вы должны указать секунды, когда должен запуститься процесс регистраций (например 58)\n"
                                                ),
                                            ),
                                        ]
                                    ),
                                    ft.TextField(
                                        label="Час запуска",
                                        input_filter=ft.InputFilter(
                                            allow=True,
                                            regex_string=r"^[0-9]*$",
                                            replacement_string="",
                                        ),
                                        on_change=on_change_hour_value,
                                        ref=self._ref_time_pick_hour,
                                    ),
                                    ft.TextField(
                                        label="Минуты запуска",
                                        input_filter=ft.InputFilter(
                                            allow=True,
                                            regex_string=r"^[0-9]*$",
                                            replacement_string="",
                                        ),
                                        on_change=on_change_minutes_value,
                                        ref=self._ref_time_pick_minute,
                                    ),
                                    ft.TextField(
                                        label="Секунды запуска",
                                        input_filter=ft.InputFilter(
                                            allow=True,
                                            regex_string=r"^[0-9]*$",
                                            replacement_string="",
                                        ),
                                        on_change=on_change_seconds_value,
                                        ref=self._ref_time_pick_seconds,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.Text(
                        value=self.rpc_display_field_text(),
                        ref=self._ref_text_rpc,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        )
        return ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [ft.Text("Дополнительные настройки")],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            content=modal_content,
            actions=[
                ft.TextButton("Сохранить", on_click=self._apply_settings),
                ft.TextButton("Отменить", on_click=self._cancel_setting),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            ref=self._ref_modal,
        )

    def _cancel_setting(self, e):
        self.page.close(self._ref_modal.current)

    def _apply_settings(self, e):
        print(f"rpc: {self._approximate_count_rps}")
        self.page.close(self._ref_modal.current)

    def _on_click_button(self, e):
        self._build_modal()
        self.page.open(self._ref_modal.current)

    def get_additional_settings(self) -> dict:
        dt_now = datetime.now()
        multiple_registration_on = dt_now.replace(
            hour=int(self._ref_time_pick_hour.current.value),
            minute=int(self._ref_time_pick_minute.current.value),
            second=int(self._ref_time_pick_seconds.current.value),
        )

        requests_per_user = int(self._ref_humans_per_second.current.value)
        requests_on_user_per_second = int(
            self._ref_requests_rps_per_human.current.value
        )
        return {
            "multiple_registration_threads": int(
                self._ref_multiple_threads_count.current.value
            ),
            "multiple_registration_on": multiple_registration_on,
            "requests_on_user_per_second": requests_on_user_per_second,
            "requests_per_user": requests_per_user,
        }

    def set_additional_settings(self, val: dict) -> dict:
        self._ref_multiple_threads_count.current.value = str(
            val["multiple_registration_threads"]
        )
        self._ref_requests_rps_per_human.current.value = str(
            val["requests_on_user_per_second"]
        )
        self._ref_humans_per_second.current.value = str(val["requests_per_user"])

        multiple_registration_on = val["multiple_registration_on"]
        self._ref_time_pick_hour.current.value = str(multiple_registration_on.hour)
        self._ref_time_pick_minute.current.value = str(multiple_registration_on.minute)
        self._ref_time_pick_seconds.current.value = str(multiple_registration_on.second)

        self.calculate_rpc()
        self.page.update()


class StopWhenTimePicker(ft.Container):
    def __init__(self) -> None:
        super().__init__()

        picker = ft.TimePicker(
            help_text="Время когда приложение остановит процесс регистраций",
        )

        self.content = ft.ElevatedButton(
            "Задать время остановки", on_click=lambda _: self.page.open(picker)
        )
        self.picker = picker

    def get_stop_when(self):
        if not self.picker.value:
            raise ValueError(self.picker.value)
        return self.picker.value.hour, self.picker.value.minute

    def set_stop_when(self, val: datetime):
        self.picker.value = val


class AppContent(ft.Container):
    def __init__(
        self,
        tip_formulars: dict[str, int],
        file_picker: ft.FilePicker,
        file_picker2: ft.FilePicker,
        file_picker3: ft.FilePicker,
    ):
        super().__init__(
            alignment=ft.alignment.center,
            padding=ft.padding.all(70),
            expand=True,
        )
        self._api_romania = APIRomania(verifi_ssl=False)
        self.date_picker = RegistrationDatePicker(on_change_date=self.on_change_date)
        self.tip_formular_selector = TipFormularSelector(tip_formulars=tip_formulars)
        self.proxy_file = ProxyFile(file_picker2)
        self.config_manager = ConfigManager(file_picker3)
        self.additinal_settings = AditionalSettings(
            40, updated_rpc_callback=self._display_rpc
        )
        self.stop_picker = StopWhenTimePicker()

        def update_users_count(val):
            self.additinal_settings.change_count_of_peoples(val)
            self.additinal_settings.calculate_rpc()
            self._display_rpc()

        self.users_btn = UsersFile(
            file_picker,
            update_users_event=update_users_count,
        )

        self._rpc_text_field = ft.Text(self.additinal_settings.rpc_display_field_text())

        start_button = ft.ElevatedButton(
            "Начать процес регистраций",
            on_click=self.start_strategy,
        )

        self.text_monitor = ft.Ref[ft.Text]()
        self.content = ft.Column(
            controls=[
                ft.Column(
                    [
                        ft.Row(
                            controls=[self.date_picker, self.tip_formular_selector],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            controls=[self.users_btn, self.proxy_file],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            controls=[self.stop_picker],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ]
                ),
                ft.Column(
                    [
                        ft.Row(
                            controls=[self._rpc_text_field],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            controls=[self.additinal_settings, start_button],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            controls=[self.config_manager],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ]
                ),
            ],
            expand=True,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def dump_config(self, e: ft.FilePickerResultEvent):
        if not e.path and e.files:
            # load
            with open(e.files[0].path) as f:
                content = json.load(f)

            content["multiple_registration_on"] = datetime.strptime(
                content["multiple_registration_on"], "%d.%m.%Y %H:%M:%S"
            )
            content["registration_date"] = datetime.strptime(
                content["registration_date"], "%d.%m.%Y"
            )
            # pprint(content)
            self.additinal_settings.set_additional_settings(content)
            self.date_picker.set_registration_date(content["registration_date"])
            self.proxy_file.set_proxies_filepath(content["proxies_file"])
            self.users_btn.set_users_data(content["users_data"])
            self.tip_formular_selector.set_tip_formular(content["tip_formular"])
            self.stop_picker.set_stop_when(content["stop_when"])

        elif e.path and not e.files:
            # save
            config = self._get_config_dict()
            config["multiple_registration_on"] = config[
                "multiple_registration_on"
            ].strftime("%d.%m.%Y %H:%M:%S")
            config["stop_when"] = f"{config["stop_when"][0]}:{config["stop_when"][1]}"
            config["registration_date"] = config["registration_date"].strftime("%d.%m.%Y")
            with open(e.path, "w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

    def _display_rpc(self, *args):
        self._rpc_text_field.value = self.additinal_settings.rpc_display_field_text()
        self.page.update()

    async def start_strategy(self, e):
        try:
            return await self._run_registrations()
        except Exception as e:
            msg = f"{e}: {traceback.format_exc()}"
            return self.page.open(ft.AlertDialog(content=ft.Text(msg)))

        async def write_msg(message):
            self.text_monitor.current.controls.append(ft.Text(message))
            self.page.update()

        logger.add(write_msg)

        while True:
            # if len(self.text_monitor.current.controls) > 30:
            await asyncio.sleep(1)
            logger.info("jghfxgxgdxgd")

    def _get_config_dict(self):
        additional_kw = self.additinal_settings.get_additional_settings()
        reg_date = self.date_picker.get_registration_date()
        tip = self.tip_formular_selector.get_tip_formular()
        users_data = self.users_btn.get_users_data()
        proxy_filepath = self.proxy_file.get_proxies_filepath()
        stop_when = self.stop_picker.get_stop_when()

        obj = dict(
            mode="sync",
            use_shuffle=True,
            stop_when=stop_when,
            registration_date=reg_date,
            tip_formular=tip,
            logging=True,
            users_data=users_data,
            without_remote_database=True,
            proxies_file=proxy_filepath,
        )
        obj.update(additional_kw)
        return obj

    async def _run_registrations(self):
        config = self._get_config_dict()
        config["tip_formular"] = self.tip_formular_selector.selected_tip_formular_id
        strategy = StrategyWithoutProxy(**config)
        
        setup_loggers(config["registration_date"], save_logs=True)
        await strategy.start()

    async def on_change_date(self, e):
        date_picker_el = self.date_picker.date_picker_element
        api = self._api_romania

        tip_formular = self.tip_formular_selector.selected_tip_formular_id
        available_dates = await api.get_free_days(
            tip_formular=tip_formular,
            month=date_picker_el.value.month,
            year=date_picker_el.value.year,
        )

        date = date_picker_el.value.strftime("%d.%m.%Y")
        places = 0

        if date_picker_el.value.strftime("%Y-%m-%d") in available_dates:
            places = await api.get_free_places_for_date(
                tip_formular=tip_formular,
                month=date_picker_el.value.month,
                year=date_picker_el.value.year,
                day=date_picker_el.value.day,
            )

        text = f"Количество свободных мест на дату `{date}`: {places}"
        self.date_picker.helper_text.current.value = text
        self.page.update()


async def main(page: ft.Page):
    page.adaptive = True
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.title = "Регистратор Румыния"
    # page.show_semantics_debugger = True

    tip_formulars = {
        "BUCURESTI – FORMULAR PROGRAMARE ART. 11": 5,
        "GALAȚI – FORMULAR PROGRAMARE ART. 11": 3,
        "IAȘI – FORMULAR PROGRAMARE ART 11": 2,
        "SUCEAVA – FORMULAR PROGRAMARE ART 11": 1,
        "BUCURESTI – FORMULAR PROGRAMARE ART. 10": 4,
        "BUCURESTI – FORMULAR PROGRAMARE ART. 8, 8.1": 6,
        "BUCURESTI – FORMULAR PROGRAMARE ART. 27": 7,
    }
    file_picker = ft.FilePicker()
    file_picker2 = ft.FilePicker()
    file_picker3 = ft.FilePicker()
    app_content = AppContent(
        tip_formulars=tip_formulars,
        file_picker=file_picker,
        file_picker2=file_picker2,
        file_picker3=file_picker3,
    )

    file_picker3.on_result = app_content.dump_config

    page.overlay.extend([file_picker, file_picker2, file_picker3])
    page.add(AppHeader(), app_content)


if __name__ == "__main__":
    logger.add("test.log")
    ft.app(main, view=ft.AppView.FLET_APP)
