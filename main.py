import os
import asyncio
import pandas as pd
import tempfile

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PASSWORD = os.environ.get("PASSWORD", "EKMOB")
DATA_FILE = "data.csv"

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
user_states = {}

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📁 Загрузить CSV"), KeyboardButton(text="🔍 Найти")],
        [KeyboardButton(text="📋 Показать всё")],
    ],
    resize_keyboard=True
)

COLUMNS = ["Номер отправления", "Наименование товара"]

def save_filtered_csv(file_path):
    df = pd.read_csv(file_path, dtype=str).fillna("")
    df = df[[col for col in COLUMNS if col in df.columns]]
    df.to_csv(DATA_FILE, index=False)
    return len(df)

def search_rows(query):
    if not os.path.exists(DATA_FILE):
        return []
    df = pd.read_csv(DATA_FILE, dtype=str).fillna("")
    query = query.lower()
    results = []
    for _, row in df.iterrows():
        if (
            query in str(row["Номер отправления"]).lower()
            or query in str(row["Наименование товара"]).lower()
        ):
            results.append(row)
    return results

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать! Введите пароль:")

@dp.message(F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    state = user_states.setdefault(user_id, {})
    if not state.get("authorized"):
        await message.answer("Сначала введите пароль.")
        return
    if not state.get("awaiting_csv"):
        await message.answer("Сначала выберите 'Загрузить CSV' в меню.")
        return
    doc = message.document
    if not doc.file_name.lower().endswith(".csv"):
        await message.answer("Пожалуйста, отправьте именно CSV-файл.")
        return
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmpfile:
        await bot.download(doc, destination=tmpfile.name)
        count = save_filtered_csv(tmpfile.name)
        os.remove(tmpfile.name)
    await message.answer(f"CSV-файл загружен и обработан! Всего строк: {count}", reply_markup=main_kb)
    state["awaiting_csv"] = False

@dp.message()
async def main_menu(message: types.Message):
    user_id = message.from_user.id
    state = user_states.setdefault(user_id, {})
    if not state.get("authorized"):
        if message.text.strip() == PASSWORD:
            state["authorized"] = True
            await message.answer("Пароль принят ✅", reply_markup=main_kb)
        else:
            await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")
        return

    if state.get("awaiting_csv"):
        await message.answer("Пожалуйста, отправьте CSV-файл или отмените загрузку.")
        return

    if message.text == "📁 Загрузить CSV":
        await message.answer("Отправьте CSV-файл (только один, он заменит старый).", reply_markup=types.ReplyKeyboardRemove())
        state["awaiting_csv"] = True
        return
    elif message.text == "🔍 Найти":
        await message.answer("Введите номер отправления или часть названия товара:")
        state["awaiting_query"] = True
        return
    elif message.text == "📋 Показать всё":
        if not os.path.exists(DATA_FILE):
            await message.answer("Файл данных не загружен.")
            return
        df = pd.read_csv(DATA_FILE, dtype=str).fillna("")
        if df.empty:
            await message.answer("В файле нет данных.")
            return
        text = ""
        for i, row in df.iterrows():
            text += f'{row["Номер отправления"]} | {row["Наименование товара"]}\n'
            if i % 20 == 19:
                await message.answer(text)
                text = ""
        if text:
            await message.answer(text)
        return

    # Поиск по запросу
    if state.get("awaiting_query"):
        results = search_rows(message.text)
        if not results:
            await message.answer("Ничего не найдено.")
        else:
            text = ""
            for i, row in enumerate(results):
                text += f'{row["Номер отправления"]} | {row["Наименование товара"]}\n'
                if i % 20 == 19:
                    await message.answer(text)
                    text = ""
            if text:
                await message.answer(text)
        state["awaiting_query"] = False
        await message.answer("Что дальше?", reply_markup=main_kb)
        return

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
