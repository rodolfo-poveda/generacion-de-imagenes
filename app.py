# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
import os
import io
import random
from PIL import Image
import base64
import logging
import google.generativeai as genai
import time
import redis

# --- IMPORTACIONES PARA CELERY ---
from celery import Celery
from celery.result import AsyncResult
from celery_worker import generate_images_task

from config import MODEL_DISPLAY_NAMES, MODEL_NAMES_LIST, GOOGLE_SESSION_TOKEN, GEMINI_API_KEY
from utils import (
    main_generator_function, create_blank_image,
    improve_and_translate_to_english, generate_magic_prompt_in_english, translate_to_english
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'una-clave-secreta-solo-para-desarrollo-local')
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_FILE_DIR"] = "/tmp/flask_session"

Session(app)

# --- CONFIGURACIÓN DE CELERY Y REDIS PARA FLASK ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

celery_app = Celery(
    app.name,
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

redis_client = redis.Redis.from_url(CELERY_BROKER_URL, decode_responses=True)
QUEUE_LIST_KEY = 'generation_queue_list'
# -----------------------------------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

@app.before_request
def initialize_session():
    if request.endpoint:
        # Asegurarse de que todas las claves de sesión existen
        if 'results' not in session:
            session['results'] = []
        if 'reference_images_list' not in session:
            session['reference_images_list'] = []
        if 'save_images' not in session:
            session['save_images'] = False
        if 'active_tab' not in session:
            session['active_tab'] = MODEL_NAMES_LIST[0]
        if 'aspect_ratio_index' not in session:
            session['aspect_ratio_index'] = 0
        if 'last_prompt' not in session:
            session['last_prompt'] = ''
        if 'last_activity' not in session:
            session['last_activity'] = time.time()

@app.route('/')
def index():
    return render_template('index.html',
                           model_names_list=MODEL_NAMES_LIST,
                           active_tab=session.get('active_tab'),
                           results=session.get('results', []), 
                           reference_images_list=session.get('reference_images_list', []),
                           aspect_ratio_index=session.get('aspect_ratio_index', 0),
                           save_images=session.get('save_images', False),
                           MODEL_DISPLAY_NAMES=MODEL_DISPLAY_NAMES,
                           MODEL_NAMES_LIST=MODEL_NAMES_LIST,
                           last_prompt=session.get('last_prompt', ''))

@app.route('/improve_prompt', methods=['POST'])
def improve_prompt():
    data = request.json
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'status': 'error', 'message': 'Escribe un prompt para mejorar.'}), 400
    
    try:
        improved_en = improve_and_translate_to_english(prompt)
        return jsonify({'status': 'success', 'improved_prompt': improved_en})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error al mejorar prompt: {str(e)}. Usando el original.'}), 500

@app.route('/generate_magic_prompt', methods=['POST'])
def generate_magic_prompt():
    try:
        magic_en = generate_magic_prompt_in_english()
        return jsonify({'status': 'success', 'magic_prompt': magic_en})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error al generar prompt mágico: {str(e)}.'}), 500    

@app.route('/generate', methods=['POST'])
def generate_images():
    data = request.json
    prompt_es = data.get('prompt', '')
    num_images = int(data.get('num_images', 4))
    seed = int(data.get('seed', -1))
    selected_ratio = data.get('aspect_ratio', '1:1')
    model_name_display = data.get('model_name_display')
    save_images_flag = data.get('save_images', False)
    ref_images_data_urls = data.get('reference_images', [])
    model_type = MODEL_DISPLAY_NAMES.get(model_name_display)

    if not prompt_es.strip():
        return jsonify({'status': 'error', 'message': 'Por favor, escribe una descripción.'}), 400

    session['last_prompt'] = prompt_es
    prompt_en = translate_to_english(prompt_es)

    is_ref_model = model_type in ["R2I", "GEM_PIX"]
    final_ref_images = ref_images_data_urls
    if is_ref_model and not bool(ref_images_data_urls):
        if model_type == "R2I":
            return jsonify({'status': 'error', 'message': f"El modelo '{model_name_display}' requiere una imagen de referencia."}), 400
        elif model_type == "GEM_PIX":
            blank_img_pil = create_blank_image(selected_ratio)
            buffered = io.BytesIO()
            blank_img_pil.save(buffered, format="PNG") 
            blank_img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            final_ref_images = [f"data:image/png;base64,{blank_img_b64}"]
    
    if not GOOGLE_SESSION_TOKEN:
         return jsonify({'status': 'error', 'message': 'auth_error: GOOGLE_SESSION_TOKEN no configurado.'}), 500

    task = generate_images_task.delay(prompt_en, num_images, seed, selected_ratio, model_type, final_ref_images, save_images_flag)
    
    try:
        current_position = redis_client.rpush(QUEUE_LIST_KEY, task.id)
    except Exception as e:
        logging.error(f"Error al añadir tarea a la lista de Redis: {e}")
        current_position = 1

    return jsonify({'status': 'processing', 'task_id': task.id, 'position': current_position - 1}), 202

@app.route('/check_task/<task_id>', methods=['GET'])
def check_task_status(task_id):
    task = AsyncResult(task_id, app=celery_app)
    position = -1
    try:
        queue_list = redis_client.lrange(QUEUE_LIST_KEY, 0, -1)
        if task_id in queue_list:
            position = queue_list.index(task_id)
    except Exception as e:
        logging.error(f"Error al consultar la posición en la lista de Redis: {e}")

    if task.state == 'SUCCESS':
        result = task.get()
        if result['status'] == 'success':
            session['results'] = result['images']
            session['save_images'] = result.get('save_images', False)
            return jsonify({'status': 'success', 'images': result['images']})
        else:
            detailed_error_messages = { "prominent_people_error": "La imagen de referencia parece contener personas famosas o contenido sensible. Por favor, intenta con una imagen diferente." } # Diccionario de errores completo
            message_key = result.get('message', 'generic_api_error')
            final_user_message = detailed_error_messages.get(message_key, "Ocurrió un error inesperado.")
            return jsonify({'status': 'error', 'message': final_user_message})
            
    elif task.state == 'FAILURE':
        logging.error(f"Celery task {task_id} failed: {task.info}")
        return jsonify({'status': 'error', 'message': 'La generación falló por un error inesperado en el servidor.'})
        
    else: # PENDING o STARTED
        return jsonify({'status': 'processing', 'position': position})

@app.route('/update_session_settings', methods=['POST'])
def update_session_settings():
    data = request.json  
    if 'active_tab' in data:  
        session['active_tab'] = data['active_tab']
        session['results'] = []
        session['save_images'] = False
        new_model_type = MODEL_DISPLAY_NAMES.get(data['active_tab'], '')
        if new_model_type not in ["R2I", "GEM_PIX"]:
            session['reference_images_list'] = []
    if 'aspect_ratio_index' in data:
        session['aspect_ratio_index'] = data['aspect_ratio_index']
    if 'save_images' in data:
        session['save_images'] = data['save_images']
    return jsonify({'status': 'success'})  

@app.route('/add_reference_image', methods=['POST'])
def add_reference_image():
    data = request.json
    image_data_url = data.get('image') 
    if image_data_url and len(session.get('reference_images_list', [])) < 3:
        if image_data_url not in session['reference_images_list']: 
            session['reference_images_list'].append(image_data_url)
        return jsonify({'status': 'success', 'reference_images': session['reference_images_list']})
    return jsonify({'status': 'error', 'message': 'Límite de 3 imágenes de referencia alcanzado.'}), 400

@app.route('/remove_reference_image/<int:index>', methods=['POST'])
def remove_reference_image(index):
    if 0 <= index < len(session.get('reference_images_list', [])):
        session['reference_images_list'].pop(index)
        return jsonify({'status': 'success', 'reference_images': session['reference_images_list']})
    return jsonify({'status': 'error', 'message': 'Índice de imagen inválido.'}), 400

@app.route('/clear_session_results', methods=['POST'])
def clear_session_results():
    # Limpiamos las variables una por una para mantener la sesión activa
    session['results'] = []
    session['reference_images_list'] = []
    session['save_images'] = False
    session['aspect_ratio_index'] = 0
    session['last_prompt'] = ''
    logging.info("Session results cleared.")
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)