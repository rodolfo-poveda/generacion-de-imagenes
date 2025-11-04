#!/bin/sh

# Activa el entorno virtual que Nixpacks crea
. /opt/venv/bin/activate

# Inicia el servidor de Redis en segundo plano
redis-server --daemonize yes

# Inicia el worker de Celery en segundo plano
celery -A celery_worker.celery worker --loglevel=info &

# Inicia Gunicorn en primer plano (este es el proceso principal)
exec gunicorn --bind 0.0.0.0:5000 --workers 4 app:app