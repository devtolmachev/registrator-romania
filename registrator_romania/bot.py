"""Module contain functional for work with Telegram Bot."""

import aiofiles
from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile, FSInputFile, InputFile

from registrator_romania.config import get_config

cfg = get_config()
bot = Bot(cfg["BOT_TOKEN"])
dp = Dispatcher()


async def send_msg_into_chat(message: str, html: str = None) -> None:
    """Send message into chat telegram."""
    message = f"<b>THIS IS A LOG MSG 🔴 !</b>\n\n{message}"
    chat_id = get_config()["telegram_bot"]["chat_id"]
    if html:
        async with aiofiles.tempfile.NamedTemporaryFile("w") as f:
            await f.write(html)
            document = FSInputFile(f.name, filename=f"{f.name}.html")
            
            await bot.send_document(
                chat_id,
                document,   
                caption=message,
                parse_mode="HTML",
            )
        
    else:
        await bot.send_message(
            chat_id,
            message,
            parse_mode="HTML"
        )


async def send_screenshot_to_chat(screenshot: bytes) -> None:
    """Send screenshot to Telegram chat."""
    await bot.send_photo(
        get_config()["telegram_bot"]["chat_id"],
        BufferedInputFile(screenshot, "screenshot.png"),
    )
    await bot.session.close()
    del screenshot
