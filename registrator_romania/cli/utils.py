import asyncio
from registrator_romania.cli import run as run_cli


def start_loop(kw: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_cli.main_async(**kw))
