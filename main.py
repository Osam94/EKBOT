import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode
from google.oauth2 import service_account
from googleapiclient.discovery import build
from aiogram import F
import asyncio

# --- Конфигурация ---

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PASSWORD = os.environ.get("PASSWORD", "EKMOB")

# Google Drive — используем json из переменной окружения
SCOPES = ['https://www.googleapis.com/auth/drive']
creds_json = os.environ.get('GDRIVE_CREDS_JSON')
if not creds_json:
    raise RuntimeError("GDRIVE_CREDS_JSON env var not set!")

creds_dict = json.loads(creds_json)
creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# --- Хранение авторизации пользователей в памяти ---
user_passwords = {}

# --- Telegram bot setup ---
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# --- Команда старт ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Добро пожаловать!\nВведите пароль:")

@dp.message(F.text)
async def ask_password(message: Message):
    if message.from_user.id not in user_passwords:
        if message.text.strip() == PASSWORD:
            user_passwords[message.from_user.id] = True
            await message.answer("Пароль принят ✅\n\nМеню:\n1. Выгрузить папку — /upload\n2. Получить папку — /get")
        else:
            await message.answer("❌ Неверный пароль! Попробуйте ещё раз.")
        return

    # Основное меню (после авторизации)
    if message.text.strip() == "/upload":
        await message.answer("Отправьте мне папку одним архивом (.zip), имя архива = дата (например, 21.08.2025.zip):")
    elif message.text.strip() == "/get":
        # Список доступных папок с Google Drive
        files = drive_service.files().list(q="mimeType='application/zip'", fields="files(id, name)").execute().get("files", [])
        if not files:
            await message.answer("Нет сохранённых папок.")
            return
        menu = "\n".join([f"- {f['name']}" for f in files])
        await message.answer(f"Доступные папки:\n{menu}\n\nВведите название нужной папки (без .zip):")
        user_passwords[message.from_user.id] = {"stage": "choose_folder", "folders": files}
    elif message.text.strip().endswith(".zip"):
        # Проверка: пользователь хочет скачать архив
        folder_name = message.text.strip()
        files = drive_service.files().list(q=f"name='{folder_name}'", fields="files(id, name)").execute().get("files", [])
        if files:
            file_id = files[0]["id"]
            request = drive_service.files().get_media(fileId=file_id)
            file_path = f"/tmp/{folder_name}"
            with open(file_path, "wb") as f:
                downloader = googleapiclient.http.MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            await message.answer_document(FSInputFile(file_path), caption=f"Папка {folder_name}")
            os.remove(file_path)
        else:
            await message.answer("Папка не найдена!")
    else:
        await message.answer("Выберите действие:\n/upload — выгрузить папку\n/get — получить папку")

# --- Приём архива .zip и загрузка на Google Drive ---
@dp.message(F.document)
async def handle_upload(message: Message):
    if message.from_user.id not in user_passwords:
        await message.answer("Сначала введите пароль!")
        return

    file = message.document
    if not file.file_name.endswith(".zip"):
        await message.answer("Принимаются только архивы .zip с датой в имени файла!")
        return

    # Скачиваем архив во временную папку
    file_path = f"/tmp/{file.file_name}"
    await bot.download(file, destination=file_path)

    # Загружаем архив в Google Drive
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(file_path, mimetype='application/zip')
    drive_service.files().create(
        body={"name": file.file_name},
        media_body=media,
        fields="id"
    ).execute()
    os.remove(file_path)
    await message.answer("Папка успешно загружена!")

# --- Запуск бота ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
