from aiogram import Bot, Dispatcher
from registrator_romania.shared import get_config


cfg = get_config()
bot = Bot(cfg["BOT_TOKEN"])
dp = Dispatcher()
