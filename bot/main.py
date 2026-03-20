from __future__ import annotations

import asyncio
import io
import os
import re
from typing import Optional
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from dotenv import load_dotenv
import aiohttp


load_dotenv()


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
BOT_API_KEY = os.environ.get("BOT_API_KEY")
BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://localhost:8000")


if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
if not BOT_API_KEY:
    raise RuntimeError("BOT_API_KEY is required")


def parse_caption(caption: str | None) -> tuple[list[str], str | None]:
    """
    Поддержка метаданных из подписи:
    - теги: #tag1 #tag2
    - категория: category: природа  (или Категория: природа)
    """

    if not caption:
        return [], None

    tags = re.findall(r"#([0-9A-Za-zА-Яа-я_-]{1,50})", caption)

    m = re.search(r"(?:category|категория)\s*:\s*(.+)", caption, flags=re.IGNORECASE)
    category = None
    if m:
        category = m.group(1).strip()
    return tags, category


async def download_largest_photo(bot: Bot, message: Message) -> tuple[bytes, str, str]:
    # message.photo: list of PhotoSize
    photo_sizes = message.photo or []
    if not photo_sizes:
        raise ValueError("No photo sizes")

    largest = photo_sizes[-1]
    file = await bot.get_file(largest.file_id)
    data = await bot.download_file(file.file_path)
    content = await data.read()

    def detect_mime(b: bytes) -> tuple[str, str]:
        # JPEG: FF D8 FF
        if len(b) >= 3 and b[:3] == b"\xff\xd8\xff":
            return "image/jpeg", "jpg"
        # PNG signature
        if b.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png", "png"
        # WEBP: RIFF....WEBP
        if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "image/webp", "webp"
        return "application/octet-stream", "bin"

    mime_type, ext = detect_mime(content)
    filename = f"telegram_{largest.file_unique_id}.{ext}"
    return content, filename, mime_type


async def backend_bot_upload(
    session: aiohttp.ClientSession,
    *,
    telegram_user_id: str,
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    tags: list[str],
    category: str | None,
) -> None:
    form = aiohttp.FormData()
    form.add_field("telegram_user_id", telegram_user_id)
    form.add_field("file", file_bytes, filename=filename, content_type=mime_type)
    if category:
        form.add_field("category", category)
    if tags:
        # backend принимает либо JSON-массив, либо CSV.
        form.add_field("tags", ",".join(tags))

    headers = {"X-Bot-Token": BOT_API_KEY}
    url = f"{BACKEND_BASE_URL}/api/bot/upload/"
    async with session.post(url, data=form, headers=headers) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise RuntimeError(f"Upload failed: {resp.status} {text}")


async def backend_bot_search(
    session: aiohttp.ClientSession, *, q: str, limit: int = 5
) -> list[dict]:
    params = {"q": q, "page_size": str(limit)}
    headers = {"X-Bot-Token": BOT_API_KEY}
    url = f"{BACKEND_BASE_URL}/api/bot/search/?{urlencode(params)}"
    async with session.get(url, headers=headers) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise RuntimeError(f"Search failed: {resp.status} {text}")
        data = await resp.json()
        return data.get("results") or []


async def backend_bot_export(
    session: aiohttp.ClientSession, *, q: str, limit: int = 200
) -> bytes:
    params = {"q": q, "limit": str(limit)}
    headers = {"X-Bot-Token": BOT_API_KEY}
    url = f"{BACKEND_BASE_URL}/api/bot/export/?{urlencode(params)}"
    async with session.get(url, headers=headers) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise RuntimeError(f"Export failed: {resp.status} {text}")
        return await resp.read()


async def backend_get_photo_file(session: aiohttp.ClientSession, photo_id: str) -> tuple[bytes, str]:
    url = f"{BACKEND_BASE_URL}/api/photos/{photo_id}/file/"
    async with session.get(url) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise RuntimeError(f"File fetch failed: {resp.status} {text}")
        data = await resp.read()
        # Вернем имя файла как basename по url (упрощение).
        return data, f"{photo_id}.bin"


async def handle_photo_upload(message: Message, bot: Bot, session: aiohttp.ClientSession) -> None:
    telegram_user_id = str(message.from_user.id)
    tags, category = parse_caption(message.caption)

    async with ChatActionSender.upload_chat_action(bot=bot, chat_id=message.chat.id):
        file_bytes, filename, mime_type = await download_largest_photo(bot, message)
        await backend_bot_upload(
            session,
            telegram_user_id=telegram_user_id,
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
            tags=tags,
            category=category,
        )

    await message.answer("Фото загружено. Спасибо!")


async def download_photo_by_file_id(
    bot: Bot, file_id: str, file_unique_id: str
) -> tuple[bytes, str, str]:
    file = await bot.get_file(file_id)
    data = await bot.download_file(file.file_path)
    content = await data.read()

    def detect_mime(b: bytes) -> tuple[str, str]:
        if len(b) >= 3 and b[:3] == b"\xff\xd8\xff":
            return "image/jpeg", "jpg"
        if b.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png", "png"
        if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "image/webp", "webp"
        return "application/octet-stream", "bin"

    mime_type, ext = detect_mime(content)
    filename = f"telegram_{file_unique_id}.{ext}"
    return content, filename, mime_type


async def cmd_start(message: Message, bot: Bot) -> None:
    await message.answer(
        "Привет! Отправьте фото в чат — я сохраню его в общий архив.\n\n"
        "Команды:\n"
        "/search <ключевые слова> — поиск по тегам/названию\n"
        "/export <ключевые слова> — архив zip по выборке\n"
        "/qr <ссылка> — QR-код с сезонной темой"
    )


async def cmd_search(message: Message, bot: Bot) -> None:
    q = (message.text or "").split(maxsplit=1)[1] if len((message.text or "").split(maxsplit=1)) > 1 else ""
    q = q.strip()
    if not q:
        await message.answer("Использование: /search <ключевые слова>")
        return

    async with aiohttp.ClientSession() as session:
        async with ChatActionSender.upload_chat_action(bot=bot, chat_id=message.chat.id):
            items = await backend_bot_search(session, q=q, limit=5)

        if not items:
            await message.answer("Ничего не найдено.")
            return

        for p in items:
            # Скачиваем картинку обратно, чтобы отправить в Telegram.
            try:
                photo_bytes, filename = await backend_get_photo_file(session, str(p["id"]))
                await message.answer_photo(
                    photo=InputFile(io.BytesIO(photo_bytes), filename=filename),
                    caption=f"{p.get('original_name')}\nКатегория: {p.get('category', {}).get('name') or '—'}",
                )
            except Exception as e:
                await message.answer(f"Ошибка выдачи фото {p.get('id')}: {e}")


async def cmd_export(message: Message, bot: Bot) -> None:
    q = (message.text or "").split(maxsplit=1)[1] if len((message.text or "").split(maxsplit=1)) > 1 else ""
    q = q.strip()
    if not q:
        await message.answer("Использование: /export <ключевые слова>")
        return

    async with aiohttp.ClientSession() as session:
        async with ChatActionSender.upload_chat_action(bot=bot, chat_id=message.chat.id):
            zip_bytes = await backend_bot_export(session, q=q, limit=200)

    await message.answer_document(
        document=InputFile(io.BytesIO(zip_bytes), filename="photos_export.zip"),
        caption="Экспорт готов.",
    )


async def cmd_qr(message: Message, bot: Bot) -> None:
    q = (message.text or "").split(maxsplit=1)[1] if len((message.text or "").split(maxsplit=1)) > 1 else ""
    q = q.strip()
    if not q:
        await message.answer("Использование: /qr <ссылка>")
        return

    async with aiohttp.ClientSession() as session:
        async with ChatActionSender.upload_chat_action(bot=bot, chat_id=message.chat.id):
            params = f"data={urlencode(q)}&season=auto"
            url = f"{BACKEND_BASE_URL}/api/qr/?{params}"
            async with session.get(url) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    await message.answer(f"Ошибка QR: {resp.status} {text}")
                    return
                qr_bytes = await resp.read()

    await message.answer_photo(
        photo=InputFile(io.BytesIO(qr_bytes), filename="qr.png"),
        caption="QR готов.",
    )


async def main() -> None:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    session = aiohttp.ClientSession()

    media_groups: dict[str, list[dict]] = {}
    media_group_tasks: dict[str, asyncio.Task] = {}

    async def process_media_group(group_id: str) -> None:
        # Даем альбому "дойти" (обычно Telegram присылает части в течение пары секунд).
        await asyncio.sleep(1)
        items = media_groups.pop(group_id, [])
        media_group_tasks.pop(group_id, None)
        if not items:
            return

        # Берем теги/категорию из первой подписи в группе (обычно caption приходит только на первой карточке).
        caption = ""
        for it in items:
            if it.get("caption"):
                caption = it["caption"]
                break

        tags, category = parse_caption(caption)
        telegram_user_id = str(items[0]["telegram_user_id"])

        for it in items:
            file_id = it["file_id"]
            file_unique_id = it["file_unique_id"]
            chat_id = it["chat_id"]

            try:
                async with ChatActionSender.upload_chat_action(bot=bot, chat_id=chat_id):
                    file_bytes, filename, mime_type = await download_photo_by_file_id(
                        bot, file_id, file_unique_id
                    )
                    await backend_bot_upload(
                        session,
                        telegram_user_id=telegram_user_id,
                        file_bytes=file_bytes,
                        filename=filename,
                        mime_type=mime_type,
                        tags=tags,
                        category=category,
                    )
            except Exception:
                # Продолжаем обрабатывать остальные фото в альбоме.
                continue

        # Сообщаем пользователю (один раз на альбом).
        first_chat_id = items[0]["chat_id"]
        await bot.send_message(first_chat_id, "Альбом загружен.")

    # Команды
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_search, Command("search"))
    dp.message.register(cmd_export, Command("export"))
    dp.message.register(cmd_qr, Command("qr"))

    # Любое сообщение с фото — upload (поддержка media groups)
    @dp.message(F.photo)
    async def photo_handler(message: Message):
        try:
            if message.media_group_id:
                group_id = message.media_group_id
                largest = (message.photo or [])[-1]
                if not largest:
                    return

                media_groups.setdefault(group_id, []).append(
                    {
                        "file_id": largest.file_id,
                        "file_unique_id": largest.file_unique_id,
                        "caption": message.caption or "",
                        "telegram_user_id": message.from_user.id,
                        "chat_id": message.chat.id,
                    }
                )

                # Даем остальным фото группы "дойти" до этого хендлера.
                if group_id not in media_group_tasks:
                    media_group_tasks[group_id] = asyncio.create_task(
                        process_media_group(group_id)
                    )
                await asyncio.sleep(0)  # yield control
                return

            await handle_photo_upload(message, bot, session)
        except Exception as e:
            await message.answer(f"Ошибка загрузки: {e}")

    try:
        await dp.start_polling(bot)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())

