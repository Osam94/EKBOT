import os
import shutil
import zipfile
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from config import TOKEN, PASSWORD, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_data = {}

menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Выгрузить папку")],
        [KeyboardButton(text="Получить папку")],
    ],
    resize_keyboard=True
)

class Steps(StatesGroup):
    WAIT_PASSWORD = State()
    WAIT_FILES = State()
    WAIT_FOLDER_NAME = State()
    WAIT_CHOOSE_FOLDER = State()

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_data.get(user_id, {}).get('authorized'):
        await message.answer("С возвращением! Выберите действие:", reply_markup=menu_kb)
    else:
        await state.set_state(Steps.WAIT_PASSWORD)
        await message.answer("Привет! 🔒 Введите пароль для доступа:")

@dp.message(Steps.WAIT_PASSWORD)
async def password_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text.strip() == PASSWORD:
        user_data[user_id] = {"authorized": True}
        await state.clear()
        await message.answer("Доступ разрешён! Выберите действие:", reply_markup=menu_kb)
    else:
        await message.answer("❌ Неверный пароль! Попробуйте снова:")

@dp.message(F.text == "Выгрузить папку")
async def upload_folder(message: Message, state: FSMContext):
    await state.update_data(files=[])
    await state.set_state(Steps.WAIT_FILES)
    await message.answer(
        "Пришлите ОДНОЙ или НЕСКОЛЬКИМИ отправками ВСЕ файлы для новой папки.\n"
        "Когда закончите — напишите название папки (дату), например: 21.08.2025"
    )

@dp.message(F.text == "Получить папку")
async def get_folder(message: Message, state: FSMContext):
    folders = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    if not folders:
        await message.answer("Нет сохранённых папок.")
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f)] for f in folders],
        resize_keyboard=True
    )
    await state.set_state(Steps.WAIT_CHOOSE_FOLDER)
    await message.answer("Выберите папку для скачивания:", reply_markup=kb)

@dp.message(Steps.WAIT_FILES, F.document)
async def save_file(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    file = message.document
    save_path = os.path.join(DATA_DIR, "_temp", file.file_name)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    await bot.download(file, destination=save_path)
    files.append(save_path)
    await state.update_data(files=files)
    await message.answer(f"Файл {file.file_name} получен. Отправьте остальные или введите название папки.")

@dp.message(Steps.WAIT_FILES)
async def folder_name_handler(message: Message, state: FSMContext):
    folder_name = message.text.strip()
    data = await state.get_data()
    files = data.get("files", [])
    if not files:
        await message.answer("Сначала отправьте хотя бы один файл.")
        return
    folder_path = os.path.join(DATA_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    for f in files:
        shutil.move(f, os.path.join(folder_path, os.path.basename(f)))
    temp_dir = os.path.join(DATA_DIR, "_temp")
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)
    await state.clear()
    await message.answer(
        f"Папка {folder_name} сохранена!\n\nВыберите действие:", reply_markup=menu_kb
    )

@dp.message(Steps.WAIT_CHOOSE_FOLDER)
async def send_folder_zip(message: Message, state: FSMContext):
    folder_name = message.text.strip()
    folder_path = os.path.join(DATA_DIR, folder_name)
    if not os.path.isdir(folder_path):
        await message.answer("Папка не найдена.")
        return
    zip_path = f"{folder_path}.zip"
    with zipfile.ZipFile(zip_path, 'w') as z:
        for filename in os.listdir(folder_path):
            z.write(os.path.join(folder_path, filename), arcname=filename)
    await bot.send_document(message.chat.id, FSInputFile(zip_path))
    os.remove(zip_path)
    await state.clear()
    await message.answer("Выберите действие:", reply_markup=menu_kb)

@dp.message()
async def fallback_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not user_data.get(user_id, {}).get('authorized'):
        await state.set_state(Steps.WAIT_PASSWORD)
        await message.answer("🔒 Введите пароль для доступа:")
    else:
        await message.answer("Используйте кнопки меню.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
