# Dockerfile actualizado
FROM python:3.12-slim 

# Instala dependencias del sistema para PIL y otras libs (solo lo esencial para slim)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e instala dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código
COPY . .

# Variables de entorno (tu Flask app)
ENV FLASK_APP=app.py

EXPOSE 5000

# Tu CMD de Gunicorn: Perfecto para prod (ajusta workers si tu VPS tiene más cores)
CMD ["gunicorn", "--workers", "4", "--threads", "12", "--worker-class", "gthread", "--bind", "0.0.0.0:5000", "--timeout", "180", "--max-requests", "1000", "app:app"]