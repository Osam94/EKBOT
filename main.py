import os
import asyncio
import tempfile
import zipfile
import dropbox
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import FSInputFile

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")
PASSWORD = os.environ.get("PASSWORD", "EKMOB")

dbx = dropbox.Dropbox(DROPBOX_TOKEN)
DROPBOX_FOLDER = ""  # Для App folder — это корень приложения!

user_states = {}

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

def ensure_folder():
    # Для App Folder ничего делать не надо — он создаётся сам!
    pass

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать!\nВведите пароль:")

@dp.message()
async def text_handler(message: types.Message):
    user_id = message.from_user.id
    state = user_states.setdefault(user_id, {})
    if not state.get("authorized"):
        if message.text.strip() == PASSWORD:
            state["authorized"] = True
            await message.answer("Пароль принят ✅\nМеню:\n/upload — выгрузить архив\n/get — получить архив")
            ensure_folder()
        else:
            await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")
        return

    if message.text == "/upload":
        state["files"] = []
        state["awaiting_files"] = True
        state["awaiting_name"] = False
        await message.answer("Отправьте файлы (можно несколько). После /done — назовите архив (например, 21.08.2025.zip).")
    elif message.text == "/done" and state.get("awaiting_files"):
        if not state.get("files"):
            await message.answer("Вы не загрузили файлы.")
            return
        state["awaiting_files"] = False
        state["awaiting_name"] = True
        await message.answer("Введите имя архива (например, 21.08.2025.zip):")
    elif state.get("awaiting_name"):
        archive_name = message.text.strip()
        if not archive_name.endswith(".zip"):
            await message.answer("Имя архива должно оканчиваться на .zip!")
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, archive_name)
            with zipfile.ZipFile(archive_path, "w") as zipf:
                for file_info in state["files"]:
                    zipf.write(file_info["path"], arcname=file_info["filename"])
            # Загружаем архив на Dropbox (в App folder)
            with open(archive_path, "rb") as f:
                dbx.files_upload(f.read(), f"/{archive_name}", mode=dropbox.files.WriteMode("overwrite"))
        for file_info in state["files"]:
            os.remove(file_info["path"])
        state.clear()
        await message.answer(f"Архив {archive_name} успешно загружен в Dropbox!")
    elif message.text == "/get":
        # Получить список zip-архивов в App folder
        files = []
        try:
            entries = dbx.files_list_folder(DROPBOX_FOLDER).entries
            files = [e.name for e in entries if isinstance(e, dropbox.files.FileMetadata) and e.name.endswith(".zip")]
        except Exception as e:
            await message.answer("Ошибка чтения папки Dropbox.")
            return
        if not files:
            await message.answer("Нет zip-архивов на Dropbox.")
        else:
            msg = "Доступные архивы:\n" + "\n".join(files)
            await message.answer(msg + "\n\nВведите имя архива для скачивания (с .zip):")
            state["awaiting_download"] = True
    elif state.get("awaiting_download"):
        archive_name = message.text.strip()
        file_path = f"/{archive_name}"  # В App folder корень — это папка приложения!
        try:
            metadata, res = dbx.files_download(file_path)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmpfile:
                tmpfile.write(res.content)
                tmpfile_path = tmpfile.name
            await message.answer_document(FSInputFile(tmpfile_path), caption=archive_name)
            os.remove(tmpfile_path)
        except Exception as e:
            await message.answer("Архив не найден!")
        state["awaiting_download"] = False
    else:
        await message.answer("Выберите действие:\n/upload — выгрузить архив\n/get — получить архив")

@dp.message(lambda m: m.document is not None)
async def handle_upload(message: types.Message):
    user_id = message.from_user.id
    state = user_states.setdefault(user_id, {})
    if not state.get("authorized"):
        await message.answer("Сначала введите пароль.")
        return
    if not state.get("awaiting_files"):
        await message.answer("Сначала напишите /upload.")
        return
    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        await bot.download(message.document, destination=tmpfile.name)
        file_info = {"filename": message.document.file_name, "path": tmpfile.name}
        state.setdefault("files", []).append(file_info)
    await message.answer(f"Файл {message.document.file_name} загружен. Добавьте ещё или напишите /done.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
