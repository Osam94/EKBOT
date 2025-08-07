import os
import asyncio
import tempfile
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PASSWORD = os.environ.get("PASSWORD", "EKMOB")
LOCAL_FOLDER = "archives"

os.makedirs(os.path.join(LOCAL_FOLDER, "покупка"), exist_ok=True)
os.makedirs(os.path.join(LOCAL_FOLDER, "продажа"), exist_ok=True)
user_states = {}

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Загрузить документы"), KeyboardButton(text="📥 Получить документы")],
    ],
    resize_keyboard=True
)
docs_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Документы покупки"), KeyboardButton(text="Документы продажи")],
        [KeyboardButton(text="⬅️ Назад")],
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

    # Главное меню
    if message.text == "📤 Загрузить документы":
        state.clear()
        state["mode"] = "upload"
        await message.answer("Какие документы загрузить?", reply_markup=docs_kb)
    elif message.text == "📥 Получить документы":
        state.clear()
        state["mode"] = "get"
        await message.answer("Какие документы получить?", reply_markup=docs_kb)

    # Выбор типа документа
    elif message.text in ("Документы покупки", "Документы продажи"):
        doc_type = "покупка" if "покупки" in message.text else "продажа"
        state["doc_type"] = doc_type

        if state.get("mode") == "upload":
            state["files"] = []
            state["awaiting_files"] = True
            state["awaiting_date"] = False
            await message.answer("Отправьте все файлы для загрузки.\nКогда закончите — напишите /done.", reply_markup=types.ReplyKeyboardRemove())
        elif state.get("mode") == "get":
            # Показать список дат (кнопками) для этого типа документа
            folder_path = os.path.join(LOCAL_FOLDER, doc_type)
            if not os.path.isdir(folder_path):
                await message.answer("Нет сохранённых дат.", reply_markup=main_kb)
                return
            dates = [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d))]
            if not dates:
                await message.answer("Нет архивов для этого типа документов.", reply_markup=main_kb)
            else:
                dates_kb = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text=d)] for d in sorted(dates)] + [[KeyboardButton(text="⬅️ Назад")]],
                    resize_keyboard=True
                )
                await message.answer("Выберите дату:", reply_markup=dates_kb)
                state["awaiting_date_select"] = True

    elif message.text == "⬅️ Назад":
        state.clear()
        await message.answer("Главное меню.", reply_markup=main_kb)
        return

    # Завершить загрузку файлов и попросить ввести дату
    elif message.text == "/done" and state.get("awaiting_files"):
        if not state.get("files"):
            await message.answer("Вы не загрузили файлы.")
            return
        state["awaiting_files"] = False
        state["awaiting_date"] = True
        await message.answer("Введите дату для сохранения документов (например, 21.08.2025):")
    # После ввода даты — сохраняем все файлы в соответствующую папку
    elif state.get("awaiting_date"):
        folder = os.path.join(LOCAL_FOLDER, state["doc_type"], message.text.strip())
        os.makedirs(folder, exist_ok=True)
        for file_info in state["files"]:
            dest = os.path.join(folder, file_info["filename"])
            os.replace(file_info["path"], dest)
        await message.answer(f"Документы сохранены в {folder}", reply_markup=main_kb)
        state.clear()
    # Получить файлы по дате
    elif state.get("awaiting_date_select"):
        if message.text == "⬅️ Назад":
            await message.answer("Главное меню.", reply_markup=main_kb)
            state.clear()
            return
        folder = os.path.join(LOCAL_FOLDER, state["doc_type"], message.text.strip())
        if not os.path.isdir(folder):
            await message.answer("Папка не найдена.")
            return
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        if not files:
            await message.answer("Нет файлов в этой папке.", reply_markup=main_kb)
        else:
            await message.answer(f"Отправляю все файлы за {message.text.strip()}:")
            for f in files:
                await message.answer_document(FSInputFile(os.path.join(folder, f)), caption=f)
        state.clear()
        await message.answer("Готово. Главное меню.", reply_markup=main_kb)
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
        await message.answer("Сначала выберите режим загрузки.")
        return
    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        await bot.download(message.document, destination=tmpfile.name)
        file_info = {"filename": message.document.file_name, "path": tmpfile.name}
        state.setdefault("files", []).append(file_info)
    await message.answer(f"Файл {message.document.file_name} загружен. Добавьте ещё или напишите /done.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
