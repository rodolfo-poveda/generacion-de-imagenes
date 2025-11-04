# Dockerfile

FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema para Pillow
RUN apt-get update && apt-get install -y libjpeg-dev zlib1g-dev --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Comando de Gunicorn optimizado para tu servidor de 1 CPU
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "app:app"]