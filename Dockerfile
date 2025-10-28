# Dockerfile
FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Establecer variables de entorno
ENV FLASK_APP=app.py

EXPOSE 5000

# MÁXIMO: 4 workers x 12 threads = ~48 slots paralelos (seguro para 1 core/4GB)
CMD ["gunicorn", "--workers", "4", "--threads", "12", "--worker-class", "gthread", "--bind", "0.0.0.0:5000", "--timeout", "180", "--max-requests", "1000", "app:app"]