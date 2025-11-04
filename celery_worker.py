# celery_worker.py
from celery import Celery, signals
from utils import main_generator_function
import os
from dotenv import load_dotenv
import redis

# Carga las variables de entorno del archivo .env
load_dotenv()

# Configura Celery para que se conecte a Redis.
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Inicializa la aplicación Celery
celery = Celery(
    'tasks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# --- LÓGICA CORREGIDA PARA GESTIONAR LA FILA DE TURNOS ---
# Nos conectamos a Redis directamente para manejar nuestra lista de turnos.
redis_client = redis.Redis.from_url(CELERY_BROKER_URL, decode_responses=True)
QUEUE_LIST_KEY = 'generation_queue_list' # El nombre de nuestra lista en Redis

# Esta es una "señal" de Celery. Se ejecuta automáticamente DESPUÉS de que una tarea termina.
# La firma se ha corregido para recibir los argumentos correctamente.
@signals.task_postrun.connect
def task_postrun_handler(task_id=None, **kwargs):
    """
    Cuando una tarea termina, la eliminamos de nuestra lista de turnos para que la fila avance.
    """
    try:
        # Intenta eliminar el task_id de la lista. El '1' significa que borre la primera ocurrencia.
        removed_count = redis_client.lrem(QUEUE_LIST_KEY, 1, task_id)
        if removed_count > 0:
            print(f"INFO: Task {task_id} removed from queue list.")
        else:
            print(f"WARN: Task {task_id} was not found in queue list to be removed.")
    except Exception as e:
        print(f"ERROR: Could not remove task {task_id} from queue list: {e}")

@celery.task
def generate_images_task(prompt_en, num_images, seed, selected_ratio, model_type, final_ref_images, save_images_flag):
    """
    Tarea asíncrona que envuelve la función de generación de imágenes.
    El worker de Celery ejecutará esta función en segundo plano.
    """
    result = main_generator_function(
        prompt=prompt_en,
        num_images=num_images,
        seed=seed,
        aspect_ratio_str=selected_ratio,
        model_type=model_type,
        ref_images=final_ref_images,
        save_images_flag=save_images_flag
    )
    return result