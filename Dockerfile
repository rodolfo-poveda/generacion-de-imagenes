# Dockerfile final y optimizado (versión single-worker para fix rápido)
FROM python:3.12-slim

# Establece el directorio de trabajo
WORKDIR /app

# Instala las dependencias del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

# Copia e instala las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación
COPY . .

# Expone el puerto
EXPOSE 5000

# CMD single-worker: Evita issues de sharing entre procesos. Escalable después con Redis.
# Timeout alto para generaciones lentas. Max-requests para evitar leaks.
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:5000", "--timeout", "300", "--max-requests", "1000", "app:app"]