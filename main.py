import os
import asyncio
import tempfile
import zipfile
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PASSWORD = os.environ.get("PASSWORD", "EKMOB")
LOCAL_FOLDER = "archives"

os.makedirs(LOCAL_FOLDER, exist_ok=True)
user_states = {}

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Выгрузить архив"), KeyboardButton(text="📥 Получить архив")],
    ],
    resize_keyboard=True
)

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
            await message.answer("Пароль принят ✅", reply_markup=main_kb)
        else:
            await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")
        return

    if message.text == "📤 Выгрузить архив":
        state["files"] = []
        state["awaiting_files"] = True
        state["awaiting_name"] = False
        await message.answer("Отправьте файлы (можно несколько).\nКогда все отправили — нажмите /done.")
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
        archive_path = os.path.join(LOCAL_FOLDER, archive_name)
        with zipfile.ZipFile(archive_path, "w") as zipf:
            for file_info in state["files"]:
                zipf.write(file_info["path"], arcname=file_info["filename"])
        for file_info in state["files"]:
            os.remove(file_info["path"])
        state.clear()
        await message.answer(f"Архив {archive_name} успешно создан и сохранён!", reply_markup=main_kb)
    elif message.text == "📥 Получить архив":
        files = [f for f in os.listdir(LOCAL_FOLDER) if f.endswith(".zip")]
        if not files:
            await message.answer("Нет zip-архивов на сервере.", reply_markup=main_kb)
        else:
            # Список архивов кнопками
            files_kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=name)] for name in files] + [[KeyboardButton(text="⬅️ Назад")]],
                resize_keyboard=True
            )
            await message.answer("Выберите архив для скачивания:", reply_markup=files_kb)
            state["awaiting_download"] = True
    elif state.get("awaiting_download"):
        archive_name = message.text.strip()
        if archive_name == "⬅️ Назад":
            await message.answer("Главное меню.", reply_markup=main_kb)
            state["awaiting_download"] = False
            return
        archive_path = os.path.join(LOCAL_FOLDER, archive_name)
        if not os.path.exists(archive_path):
            await message.answer("Архив не найден! Выберите из списка.", reply_markup=main_kb)
        else:
            await message.answer_document(FSInputFile(archive_path), caption=archive_name, reply_markup=main_kb)
        state["awaiting_download"] = False
    else:
        await message.answer("Выберите действие на клавиатуре 👇", reply_markup=main_kb)

@dp.message(lambda m: m.document is not None)
async def handle_upload(message: types.Message):
    user_id = message.from_user.id
    state = user_states.setdefault(user_id, {})
    if not state.get("authorized"):
        await message.answer("Сначала введите пароль.")
        return
    if not state.get("awaiting_files"):
        await message.answer("Сначала нажмите '📤 Выгрузить архив'.")
        return
    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        await bot.download(message.document, destination=tmpfile.name)
        file_info = {"filename": message.document.file_name, "path": tmpfile.name}
        state.setdefault("files", []).append(file_info)
    await message.answer(f"Файл {message.document.file_name} загружен. Добавьте ещё или нажмите /done.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
