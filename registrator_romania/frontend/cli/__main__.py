import asyncio
from datetime import datetime
import os
import platform
import subprocess
import shlex
import sys
import click

from registrator_romania.backend.utils import get_users_data_from_xslx


TARGET_URL = "https://programarecetatenie.eu/programare_online"


HELP_MODE_OPTION = """
Значение по умолчанию: sync

Здесь вы задаете режим регистрации пользователей.

sync - процесс регистрации будет синхронным. То есть, сначала регистрируется 
пользователь №1, после него регистрируется пользователь №2

async - процесс регистрации будет асинхронным. То есть, запросы на регистрацию
отправляются сразу, не последовательно. 

К примеру: пока ты кипятишь чайник ты можешь, сразу достать конфеты из шкафчика,
и поставить пряники на стол, и если ты так и поступишь, это будет асинхронный 
режим. А вот если ты будешь ждать пока вскипит чайник, чтобы достать конфеты,
и потом достать еду - это будет синхронный режим.

Представь что у скрипта 50 рук, и он при асинхронном режиме будет 
использовать все 50 рук для отправки запросов. Но если режим будет синхронным, 
то скрипт будет инвалидом (как и его разработчик), и пока он не разберется с 1 
пользователем, до 2 он не дойдет.


ПРИМЕЧАНИЕ:
Асинхронный режим более быстрый и современный, но он содержит определенные 
риски, например слишком быстрая отправка запросов - чтобы этим риском управлять,
можно задать параметр --containers и --async+requests_num.
----------------------------------------------------------
Помните что из-за слишком большого количество асинхронных запросов, целевой 
сервер, куда отправляются запросы, может заблокировать ваш IP адресс.
"""

HELP_CONTAINERS = """
Значение по умолчанию: 5.

Тут вы задаете, сколько должно работать docker контейнеров. Чем их больше, 
тем мощнее работает скрипт. Если выставленно слишком много контейнеров, 
компьютер или модем с интернетом, может не выдержать нагрузки.
"""

HELP_ASYNC_REQUESTS_NUM = """
Влияет на скрипт только при асинхронном режиме работы.
Значение по умолчанию: 10

Тут вы задаете количество пользователей, которое должно регистрироваться 
асинхронно.
"""

HELP_USE_SHUFFLE = """
Значение по умолчанию: yes

Может быть либо yes, либо no.

Должен ли перемешиваться список в случайном порядке, в начале цикла, который
начинает попытки делать регистрации.
"""


HELP_STOP_WHEN = """
Значение по умолчанию: 09:02
Может быть только временем в формате <час>:<минута>

Когда скрипт должен самостоятельно выключиться.
"""


HELP_START_TIME = """
Значение по умолчанию: 07:30
Может быть только временем в формате <час>:<минута>

Самое раннее время, когда скрипт должен включиться самостоятельно.
"""

registration_date = (
    datetime.now().replace(month=datetime.now().month + 4).date()
)

HELP_REGISTRATION_DATE = f"""
Значение по умолчанию: <текущее число>.<номер текущего месяца + 4>.<текущий год>
Сегодня значение по умолчанию: {registration_date}

На каке число будут регистрироваться пользователи.
"""


HELP_SAVE_LOGS = """
Значение по умолчанию: yes

Должны ли сохраняться лог файлы. Лог файлы сохраняются по пути 
registration_<значение в параметре registration_date>/logs/

Ошибки записываются в errors.log
Отладочная информация в debug.log
"""

HELP_USERS_FILE = """
Параметр обязательный. Значения по умолчанию нет

Путь до файла с расширением .xlsx, с пользователями, которых нужно 
зарегистрировать.
"""

HELP_TIP_FORMULAR = f"""
По умолчанию: 4

Значение этого параметра можно получить на html страничке сайта {TARGET_URL}.
Инструкция по получению этого значения прилагается в видео файле доступный по
пути - docs/tip_formular.mp4

Инструкция по этому параметру заполялась 26.07.2024 числа.
"""


async def run_docker_compose(containers: int, env_vars: dict):
    command = f"docker compose -f docker-compose-v0.yml up --build --scale app={containers}"
    shell = True
    shell = False

    if platform.system() != "Windows":
        shell = False
        # command = command.split()  # For sync process

    command_list = command if shell else shlex.split(command)

    env = os.environ.copy()
    env.update(env_vars)

    async def read_stream(stream, output_func):
        while True:
            line = await stream.readline()
            if not line:
                break
            output_func(line.decode())

    process = await asyncio.create_subprocess_exec(
        *command_list,
        shell=shell,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        text=False,
    )

    async def read_stream(stream, stderr: bool = False):
        while True:
            line = await stream.readline()
            if not line:
                break
            print(
                line.decode(),
                file=None if not stderr else sys.stderr,
                end="",
            )

    await asyncio.gather(
        read_stream(process.stdout, stderr=False),
        read_stream(process.stderr, stderr=True),
    )

    await process.wait()

    # with subprocess.Popen(
    #     command,
    #     shell=shell,
    #     stdout=subprocess.PIPE,
    #     stderr=subprocess.PIPE,
    #     env=env,
    #     text=True,
    # ) as process:
    #     try:
    #         for line in iter(process.stderr.readline, ""):
    #             print(line, end="")
    #         process.stderr.close()
    #         process.wait()
    #     except subprocess.CalledProcessError as e:
    #         print(f"Error: {e.stderr}")


@click.command()
@click.option("--mode", default="sync", help=HELP_MODE_OPTION)
@click.option("--containers", default=5, help=HELP_CONTAINERS)
@click.option("--async_requests_num", default=10, help=HELP_ASYNC_REQUESTS_NUM)
@click.option("--use_shuffle", default="yes", help=HELP_USE_SHUFFLE)
@click.option("--stop_time", default="09:02", help=HELP_STOP_WHEN)
@click.option("--start_time", default="07:30", help=HELP_START_TIME)
@click.option(
    "--registration_date",
    default=str(registration_date),
    help=HELP_REGISTRATION_DATE,
)
@click.option("--save_logs", default="yes", help=HELP_SAVE_LOGS)
@click.option("--users_file", help=HELP_USERS_FILE)
@click.option("--tip_formular", help=HELP_TIP_FORMULAR)
def main(
    mode: str,
    containers: int,
    async_requests_num: int,
    use_shuffle: str,
    stop_time: str,
    start_time: str,
    registration_date: str,
    save_logs: str,
    users_file: str,
    tip_formular: int,
):
    assert str(
        tip_formular
    ).isdigit(), "Параметр tip_formular должен быть числом!"
    yes_no = ["yes", "no"]
    assert (
        use_shuffle in yes_no
    ), "Параметр use_shuffle, должен быть либо yes, либо no"
    assert (
        save_logs in yes_no
    ), "Параметр use_shuffle, должен быть либо yes, либо no"
    assert str(
        async_requests_num
    ).isdigit(), "Параметр async_requests_num, должен быть целым числом!"
    assert str(
        containers
    ).isdigit(), "Параметр containers, должен быть целым числом!"

    assert mode in [
        "sync",
        "async",
    ], "Параметр mode должен быть либо async, либо sync"

    users_data = get_users_data_from_xslx(path=users_file)
    assert users_data, "Файл с пользователями неверный, произошла ошибка. Проверьте файл и повторите попытку"

    env = {
        "mode": mode,
        "async_requests_num": str(async_requests_num),
        "use_shuffle": use_shuffle,
        "stop_time": stop_time,
        "start_time": start_time,
        "registration_date": registration_date,
        "save_logs": save_logs,
        "users_file": users_file,
        "tip_formular": tip_formular,
    }
    asyncio.run(run_docker_compose(containers=int(containers), env_vars=env))


if __name__ == "__main__":
    main()
