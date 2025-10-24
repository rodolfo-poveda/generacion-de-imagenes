# config.py
import os
from dotenv import load_dotenv

load_dotenv()

GENERATE_URL_OBFUSCATED = "aHR0cHM6Ly9haXNhbmRib3gtcGEuZ29vZ2xlYXBpcy5jb20vdjE6cnVuSW1hZ2VGeA=="
UPLOAD_URL_OBFUSCATED = "aHR0cHM6Ly9haXNhbmRib3gtcGEuZ29vZ2xlYXBpcy5jb20vdjE6dXBsb2FkVXNlckltYWdl"
BASE_HEADERS = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

MODEL_DISPLAY_NAMES = {
    "Texto a Imagen (v3.1)": "IMAGEN_3_1",
    "Texto a Imagen Ultra (v3.5)": "IMAGEN_3_5",
    "Imagen desde Referencia (V3.5)": "R2I",
    "Edición Mágica (Nano)": "GEM_PIX"
}
MODEL_NAMES_LIST = list(MODEL_DISPLAY_NAMES.keys())

GOOGLE_SESSION_TOKEN = os.getenv("GOOGLE_SESSION_TOKEN")