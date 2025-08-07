import os
import json
import asyncio
import tempfile
import zipfile
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import FSInputFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PASSWORD = os.environ.get("PASSWORD", "EKMOB")
SCOPES = ['https://www.googleapis.com/auth/drive']

# Google Drive авторизация через переменную окружения
creds_json = os.environ.get('GDRIVE_CREDS_JSON')
if not creds_json:
    raise RuntimeError("GDRIVE_CREDS_JSON env var not set!")

creds_dict = json.loads(creds_json)
creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

user_states = {}  # user_id: {"files": [...], "awaiting_name": bool}

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать!\nВведите пароль:")

@dp.message()
async def text_handler(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_states:
        user_states[user_id] = {}

    state = user_states[user_id]
    # Авторизация по паролю
    if not state.get("authorized"):
        if message.text.strip() == PASSWORD:
            state["authorized"] = True
            await message.answer("Пароль принят ✅\n\nМеню:\n/upload — выгрузить архив\n/get — получить архив")
        else:
            await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")
        return

    # Получение архива
    if message.text == "/upload":
        state["files"] = []
        state["awaiting_files"] = True
        state["awaiting_name"] = False
        await message.answer("Отправьте мне файлы (можно несколько). После загрузки напишите /done.")
    elif message.text == "/done" and state.get("awaiting_files"):
        if not state.get("files"):
            await message.answer("Вы не отправили ни одного файла!")
            return
        state["awaiting_files"] = False
        state["awaiting_name"] = True
        await message.answer("Теперь напишите, как назвать архив (пример: 21.08.2025.zip):")
    elif state.get("awaiting_name"):
        archive_name = message.text.strip()
        if not archive_name.endswith(".zip"):
            await message.answer("Название архива должно заканчиваться на .zip!")
            return
        # Архивируем файлы во временную папку
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, archive_name)
            with zipfile.ZipFile(archive_path, "w") as zipf:
                for file_info in state["files"]:
                    zipf.write(file_info["path"], arcname=file_info["filename"])
            # Загружаем на Google Drive
            media = MediaFileUpload(archive_path, mimetype='application/zip')
            drive_service.files().create(
                body={"name": archive_name, "mimeType": "application/zip"},
                media_body=media,
                fields="id"
            ).execute()
        # Удаляем временные файлы
        for file_info in state["files"]:
            os.remove(file_info["path"])
        state.clear()
        await message.answer(f"Архив {archive_name} успешно создан и загружен на Google Диск!")
    elif message.text == "/get":
        # Показываем ВСЕ zip-архивы на вашем Google Диске
        files = drive_service.files().list(q="mimeType='application/zip'", fields="files(id, name)").execute().get("files", [])
        if not files:
            await message.answer("Нет архивов .zip на Google Диске.")
        else:
            text = "Доступные архивы:\n" + "\n".join([f"- {f['name']}" for f in files])
            await message.answer(text + "\n\nНапишите имя архива для скачивания (с .zip):")
            state["awaiting_download"] = True
    elif state.get("awaiting_download"):
        archive_name = message.text.strip()
        files = drive_service.files().list(q=f"name='{archive_name}' and mimeType='application/zip'", fields="files(id, name)").execute().get("files", [])
        if not files:
            await message.answer("Архив не найден!")
        else:
            file_id = files[0]['id']
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmpfile:
                request = drive_service.files().get_media(fileId=file_id)
                downloader = MediaIoBaseDownload(tmpfile, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                tmpfile_path = tmpfile.name
            await message.answer_document(FSInputFile(tmpfile_path), caption=f"Архив: {archive_name}")
            os.remove(tmpfile_path)
        state["awaiting_download"] = False
    else:
        await message.answer("Выберите действие:\n/upload — выгрузить архив\n/get — получить архив")

@dp.message(lambda message: message.document is not None)
async def handle_upload(message: types.Message):
    user_id = message.from_user.id
    state = user_states.setdefault(user_id, {})
    if not state.get("authorized"):
        await message.answer("Сначала введите пароль!")
        return
    if not state.get("awaiting_files"):
        await message.answer("Чтобы загрузить файлы, сначала напишите /upload.")
        return
    # Сохраняем файл во временную папку
    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        await bot.download(message.document, destination=tmpfile.name)
        file_info = {"filename": message.document.file_name, "path": tmpfile.name}
        state.setdefault("files", []).append(file_info)
    await message.answer(f"Файл {message.document.file_name} загружен. Добавьте ещё или напишите /done.")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
