# Dockerfile final y optimizado
FROM python:3.12-slim

# Establece el directorio de trabajo
WORKDIR /app

# Instala las dependencias del sistema corrigiendo el nombre del paquete
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

# Expone el puerto que Gunicorn usará
EXPOSE 5000

# Comando de Gunicorn optimizado para producción con un timeout largo
CMD ["gunicorn", "--workers", "4", "--threads", "12", "--worker-class", "gthread", "--bind", "0.0.0.0:5000", "--timeout", "180", "--max-requests", "1000", "app:app"]