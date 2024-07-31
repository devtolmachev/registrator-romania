import asyncio
from datetime import datetime, timedelta
from multiprocessing import Process
import os
from pprint import pprint
import shlex
import sys
from zoneinfo import ZoneInfo
import click
from loguru import logger

from registrator_romania.backend.utils import (
    generate_fake_users_data,
    get_users_data_from_xslx,
)
from registrator_romania.backend.utils import get_dt_moscow
from registrator_romania.cli.utils import start_loop


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

registration_date = (get_dt_moscow() + timedelta(days=4)).date()

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


HELP_PROXY_PROVIDER_URL = """
Передайте в этот параметр ссылку по которой будет доступен proxy для 
регистраций.

"""

HELP_PROCESSES = """
По умолчанию: no

Передайте в этот параметр `yes` чтобы запускать процессы без docker.

"""

HELP_FAKE_USERS = """
По умолчанию: no

Передайте в этот параметр число, чтобы сгенерировать фейковых пользователей 
с определенным количеством, для регистраций, не затрагивая пользователей 
в файле. 
(Параметр --users_file все равно должен быть указан)

"""


HELP_WITHOUT_REMOTE_DATABASE = """
По умолчанию: no

Передайте в этот параметр yes, тогда скрипт принудительно не будет 
синхронизировать список с удаленной базой данных.
"""


HELP_MULTIPLE_REQUESTING_ON = """
По умолчанию: no

Передайте в этот параметр время по МСК (в формате час:минута:секунда),
в которое в отдельном потоке будут моментально регистрироваться все 
пользователи без задержек.
"""


async def run_docker_compose(containers: int, env_vars: dict):
    command = (
        "docker compose -f docker-compose-v0.yml up "
        f"--scale app={containers} "
    )
    command += "--build"

    command_list = shlex.split(command)

    env = os.environ.copy()
    env.update(env_vars)
    new_env = {str(k): str(v) for k, v in env.items()}
    process = await asyncio.create_subprocess_exec(
        *command_list,
        shell=False,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=new_env,
        text=False,
    )

    async def read_stream(stream: asyncio.StreamReader, stderr: bool = False):
        while True:
            line = await stream.readline()
            if not line:
                break
            print(
                line.decode(),
                file=sys.stdout if not stderr else sys.stderr,
                end="",
            )

    await asyncio.gather(
        read_stream(process.stdout, stderr=False),
        read_stream(process.stderr, stderr=True),
    )

    await process.wait()


def run_as_processes(process_count: int, params: dict):
    mode = params["mode"]
    async_requests_num = params["async_requests_num"]
    use_shuffle = params["use_shuffle"]
    stop_time = params["stop_time"]
    start_time = params["start_time"]
    registration_date = params["registration_date"]
    save_logs = params["save_logs"]
    users_file = params["users_file"]
    tip_formular = params["tip_formular"]
    proxy_provider_url = params["proxy_provider_url"]
    without_remote_database = params["without_remote_database"]
    multiple_requesting_on = params["multiple_requesting_on"]
    users_data = params["users_data"]

    start_time = datetime.now().strptime(start_time, "%H:%M")
    stop_time = datetime.strptime(stop_time, "%H:%M")
    registration_date = datetime.strptime(registration_date, "%d.%m.%Y")
    use_shuffle = True if "yes" else False
    save_logs = True if "yes" else False
    proxy_provider_url = None if not proxy_provider_url else proxy_provider_url
    without_remote_database = False if without_remote_database == "no" else True
    multiple_requesting_on = (
        False
        if multiple_requesting_on == "no"
        else datetime.strptime(multiple_requesting_on, "%H:%M:%S")
    )

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

    kw = {
        "proxy_provider_url": proxy_provider_url,
        "mode": mode,
        "async_requests_num": async_requests_num,
        "use_shuffle": use_shuffle,
        "stop_time": stop_time,
        "start_time": start_time,
        "registration_date": registration_date,
        "save_logs": save_logs,
        "users_file": users_file,
        "tip_formular": tip_formular,
        "without_remote_database": without_remote_database,
        "multiple_requesting_on": multiple_requesting_on,
        "users_data": users_data
    }

    processes: list[Process] = []

    for num in range(1, process_count + 1):
        process = Process(target=start_loop, args=(kw,))
        process.start()
        logger.info(f"Process №{num} started")
        processes.append(process)

    for pr in processes:
        pr.join()

    print("All processes is stopped")


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
@click.option("--processes", default="no", help=HELP_PROCESSES)
@click.option(
    "--proxy_provider_url",
    required=True,
    default="",
    help=HELP_PROXY_PROVIDER_URL,
)
@click.option(
    "--fake_users",
    default="no",
    help=HELP_FAKE_USERS,
)
@click.option(
    "--without_remote_database",
    default="no",
    help=HELP_WITHOUT_REMOTE_DATABASE,
)
@click.option(
    "--multiple_requesting_on",
    default="no",
    help=HELP_WITHOUT_REMOTE_DATABASE,
)
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
    proxy_provider_url: str,
    processes: str,
    fake_users: str,
    without_remote_database: str,
    multiple_requesting_on: str,
):
    assert str(
        tip_formular
    ).isdigit(), "Параметр tip_formular должен быть числом!"
    assert (
        fake_users == "no" or fake_users.isdigit()
    ), "Параметр fake_users должен быть либо `no`, либо числом!"
    yes_no = ["yes", "no"]
    assert (
        use_shuffle in yes_no
    ), "Параметр use_shuffle, должен быть либо yes, либо no"
    assert (
        save_logs in yes_no
    ), "Параметр use_shuffle, должен быть либо yes, либо no"

    assert (
        without_remote_database in yes_no
    ), "Параметр  without_remote_database, должен быть либо yes, либо no"

    assert str(
        async_requests_num
    ).isdigit(), "Параметр async_requests_num, должен быть целым числом!"
    assert str(
        containers
    ).isdigit(), "Параметр containers, должен быть целым числом!"
    
    try:
        datetime.strptime(multiple_requesting_on, "%H:%M:%S")
    except:
        if multiple_requesting_on != "no":
            raise ValueError(
                "Параметр multiple_requesting_on должен быть либо no, либо "
                "временем (например 08:59:55)"
            )
    assert mode in [
        "sync",
        "async",
    ], "Параметр mode должен быть либо async, либо sync"

    if fake_users == "no":
        users_data = get_users_data_from_xslx(path=users_file)
        assert users_data, "Файл с пользователями неверный, произошла ошибка. Проверьте файл и повторите попытку"
    else:
        users_data = generate_fake_users_data(n=int(fake_users))

    env = {
        "proxy_provider_url": proxy_provider_url,
        "mode": mode,
        "async_requests_num": str(async_requests_num),
        "use_shuffle": use_shuffle,
        "stop_time": stop_time,
        "start_time": start_time,
        "registration_date": registration_date,
        "save_logs": save_logs,
        "users_file": users_file,
        "tip_formular": str(tip_formular),
        "without_remote_database": without_remote_database,
        "multiple_requesting_on": multiple_requesting_on,
        "users_data": users_data
    }

    assert processes in [
        "yes",
        "no",
    ], "Параметр `processes` должен быть либо `yes`, либо `no`"
    use_process = True if processes == "yes" else None

    if not use_process:
        asyncio.run(
            run_docker_compose(containers=int(containers), env_vars=env)
        )
    else:
        run_as_processes(process_count=int(containers), params=env)

    stop_time = (
        datetime.now()
        .astimezone(ZoneInfo("Europe/Moscow"))
        .replace(
            hour=int(stop_time.split(":")[0]),
            minute=int(stop_time.split(":")[1]),
        )
    )

    async def wait():
        while True:
            await asyncio.sleep(30)
            curr_dt = datetime.now().astimezone(ZoneInfo("Europe/Moscow"))
            if (
                curr_dt.hour == stop_time.hour
                and curr_dt.minute <= stop_time.minute
            ):
                break

    loop = asyncio.new_event_loop()
    loop.run_until_complete(wait())


if __name__ == "__main__":
    main()
