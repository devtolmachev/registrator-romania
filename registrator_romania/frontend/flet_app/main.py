import asyncio
from datetime import datetime, timedelta
import os
import re
import traceback
import flet as ft
from loguru import logger

from registrator_romania.backend.api.api_romania import APIRomania
from registrator_romania.backend.utils import (
    get_users_data_from_xslx,
    get_users_data_from_csv,
)


class DefaultContainer(ft.Container): ...


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
            options=[ft.dropdown.Option(t) for t in tip_formular_names], width=500
        )

        self.content = dropdown_content

    @property
    def selected_tip_formular_id(self):
        dropdown: ft.Dropdown = self.content
        return self.tip_formulars[dropdown.value]


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


class UsersFile(ft.Container):
    def __init__(self, file_picker: ft.FilePicker):
        super().__init__(padding=ft.padding.all(10))

        btn = ft.ElevatedButton(
            "Выбрать файл с пользователями",
            on_click=lambda _: file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["xlsx", "csv"],
                dialog_title="Выбрать таблицу с пользователями",
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

    def on_pick_result(self, e):
        file = self._fp.result.files[0]

        try:
            ext = os.path.splitext(file.path)[-1].strip(".")
            if ext == "xlsx":
                get_users_data_from_xslx(file.path)
            elif ext == "csv":
                get_users_data_from_csv(file.path)
            else:
                raise ValueError(
                    f"Неизвестное расширение файла - {file.name}\n\n"
                    f"Файл - {file.path}"
                )
        except Exception as exc:
            content = f"{exc}\n\n{traceback.format_exc()}"
            return self.open_modal(content)

        self.content.text = file.name
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

        self.content.text = file.name
        self.page.update()


class AppContent(ft.Container):
    def __init__(
        self,
        tip_formulars: dict[str, int],
        file_picker: ft.FilePicker,
        file_picker2: ft.FilePicker,
    ):
        super().__init__(
            alignment=ft.alignment.center,
            padding=ft.padding.only(top=10, bottom=10, left=70, right=70),
        )
        self._api_romania = APIRomania()
        self.date_picker = RegistrationDatePicker(on_change_date=self.on_change_date)
        self.tip_formular_selector = TipFormularSelector(tip_formulars=tip_formulars)
        self.users_btn = UsersFile(file_picker)
        self.proxy_file = ProxyFile(file_picker2)

        start_button = ft.ElevatedButton(
            "Начать процес регистраций",
            on_click=self.start_strategy,
        )

        self.text_monitor = ft.Ref[ft.Text]()
        self.content = ft.Column(
            controls=[
                ft.Row(
                    controls=[self.date_picker, self.tip_formular_selector],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    controls=[self.users_btn, self.proxy_file],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    controls=[start_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Column(
                    ref=self.text_monitor,
                    # expand=1, auto_scroll=True, padding=50
                )
            ],
            spacing=30,
        )

    async def start_strategy(self, e):
        # self.text_monitor.current.visible = True

        async def write_msg(message):
            self.text_monitor.current.controls.append(ft.Text(message))
            self.page.update()

        logger.add(write_msg)

        while True:
            # if len(self.text_monitor.current.controls) > 30:
            await asyncio.sleep(1)
            logger.info("jghfxgxgdxgd")

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

    api = APIRomania()
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
    page.overlay.extend([file_picker, file_picker2])
    page.add(
        AppHeader(),
        AppContent(
            tip_formulars=tip_formulars,
            file_picker=file_picker,
            file_picker2=file_picker2,
        ),
    )
    ...


if __name__ == "__main__":
    ft.app(main, view=ft.AppView.FLET_APP)
