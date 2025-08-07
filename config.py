import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
PASSWORD = os.getenv("PASSWORD", "EKMOB")
