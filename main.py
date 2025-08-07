import os
import shutil
import zipfile
import io

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2 import service_account

from config import TOKEN, PASSWORD

# === Google Drive ===
GDRIVE_FOLDER_NAME = "EKMOBOT"
SERVICE_ACCOUNT_FILE = "gdrive_creds.json"

SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

def get_folder_id_by_name(folder_name, parent_id=None):
    q = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    results = drive_service.files().list(q=q, fields="files(id, name)").execute()
    folders = results.get('files', [])
    return folders[0]['id'] if folders else None

def create_drive_folder(name, parent_id=None):
    file_metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        file_metadata['parents'] = [parent_id]
    folder = drive_service.files().create(body=file_metadata, fields='id').execute()
    return folder['id']

def upload_folder_to_drive(local_folder, gdrive_folder):
    folder_id = get_folder_id_by_name(gdrive_folder)
    if not folder_id:
        folder_id = create_drive_folder(gdrive_folder)
    # Создаем папку с датой внутри главной
    subfolder_name = os.path.basename(local_folder)
    subfolder_id = create_drive_folder(subfolder_name, folder_id)
    for filename in os.listdir(local_folder):
        file_path = os.path.join(local_folder, filename)
        file_metadata = {
            'name': filename,
            'parents': [subfolder_id]
        }
        media = MediaFileUpload(file_path, resumable=True)
        drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

def list_drive_folders():
    parent_id = get_folder_id_by_name(GDRIVE_FOLDER_NAME)
    if not parent_id:
        return []
    results = drive_service.files().list(
        q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name)").execute()
    folders = results.get('files', [])
    return [f['name'] for f in folders]

def download_folder_from_drive(folder_name, local_folder):
    parent_id = get_folder_id_by_name(GDRIVE_FOLDER_NAME)
    folder_id = get_folder_id_by_name(folder_name, parent_id)
    if not folder_id:
        return False
    os.makedirs(local_folder, exist_ok=True)
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder'",
        fields="files(id, name)").execute()
    files = results.get('files', [])
    for file in files:
        file_id = file['id']
        file_name = file['name']
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.FileIO(os.path.join(local_folder, file_name), 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
    return True

# === Telegram part ===

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
    folders = list_drive_folders()
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
    save_path = os.path.join("_temp", file.file_name)
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
    folder_path = os.path.join("_temp_folder", folder_name)
    os.makedirs(folder_path, exist_ok=True)
    for f in files:
        shutil.move(f, os.path.join(folder_path, os.path.basename(f)))
    # === Загружаем папку в Google Drive ===
    upload_folder_to_drive(folder_path, GDRIVE_FOLDER_NAME)
    shutil.rmtree(folder_path)
    temp_dir = "_temp"
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)
    await state.clear()
    await message.answer(
        f"Папка {folder_name} сохранена в облаке!\n\nВыберите действие:", reply_markup=menu_kb
    )

@dp.message(Steps.WAIT_CHOOSE_FOLDER)
async def send_folder_zip(message: Message, state: FSMContext):
    folder_name = message.text.strip()
    temp_download_dir = os.path.join("_download_temp", folder_name)
    if os.path.exists(temp_download_dir):
        shutil.rmtree(temp_download_dir)
    os.makedirs(temp_download_dir, exist_ok=True)
    success = download_folder_from_drive(folder_name, temp_download_dir)
    if not success:
        await message.answer("Папка не найдена в облаке.")
        return
    zip_path = f"{temp_download_dir}.zip"
    with zipfile.ZipFile(zip_path, 'w') as z:
        for filename in os.listdir(temp_download_dir):
            z.write(os.path.join(temp_download_dir, filename), arcname=filename)
    await bot.send_document(message.chat.id, FSInputFile(zip_path))
    os.remove(zip_path)
    shutil.rmtree(temp_download_dir)
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
