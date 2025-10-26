# config.py
import os
from dotenv import load_dotenv

# --- CAMBIO CLAVE ---
# Modificamos la función load_dotenv() para que busque en la ruta del
# contenedor de producción. Si ese archivo no existe (como en tu entorno local),
# la función no hará nada y el script continuará.
# Luego, la segunda llamada a load_dotenv() sin argumentos buscará el
# archivo .env local, haciendo que el código funcione en ambos entornos.
load_dotenv(dotenv_path='/run/secrets/google_token.env')

# Esta segunda llamada asegura que en local se siga leyendo el .env
load_dotenv()


# --- EL RESTO DE TU CÓDIGO PERMANECE EXACTAMENTE IGUAL ---

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

# Esta línea no cambia. os.getenv() encontrará la variable que haya sido
# cargada por cualquiera de las dos llamadas a load_dotenv().
GOOGLE_SESSION_TOKEN = os.getenv("GOOGLE_SESSION_TOKEN")