# Dockerfile

# 1. Usa una imagen oficial y ligera de Python como base
FROM python:3.12-slim

# 2. Instala dependencias del sistema operativo necesarias para Pillow (PIL)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 3. Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# 4. Copia el archivo de requerimientos y los instala
# Se hace en un paso separado para aprovechar el caché de capas de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copia todo el resto del código de tu aplicación
COPY . .

# 6. Expone el puerto que usará Gunicorn
EXPOSE 5000

# NOTA: No hay CMD aquí. El comando se especificará en docker-compose.yml