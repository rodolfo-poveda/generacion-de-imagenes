# Dockerfile

# 1. Usar una imagen base de Python ligera y oficial.
FROM python:3.12-slim

# 2. Instalar dependencias del sistema operativo que Pillow (PIL) necesita.
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 3. Establecer el directorio de trabajo dentro del contenedor.
WORKDIR /app

# 4. Copiar e instalar las dependencias de Python.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar el resto del código de la aplicación.
COPY . .

# 6. Exponer el puerto que Gunicorn usará.
EXPOSE 5000