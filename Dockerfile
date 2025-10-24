# Dockerfile
FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Establecer variables de entorno
ENV FLASK_APP=app.py
# Considera usar un .env para el token localmente, y para Dockploy inyectarlo como secreto o variable de entorno

EXPOSE 5000

# Comando para ejecutar la aplicación con Gunicorn (más robusto que flask run)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]