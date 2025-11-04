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
import uuid
from threading import Thread

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- NUEVO SISTEMA DE TAREAS LIGERO (REEMPLAZA A REDIS/CELERY) ---
# Un diccionario en memoria para guardar el estado y resultado de las tareas.
# Esto es suficiente para este caso de uso y extremadamente ligero.
tasks = {}

def run_generation_in_background(task_id, prompt_en, num_images, seed, selected_ratio, model_type, final_ref_images, save_images_flag):
    """
    Esta función se ejecutará en un hilo separado (en segundo plano).
    Llama a la función de generación principal y guarda el resultado en el diccionario 'tasks'.
    """
    logging.info(f"Thread for task {task_id} started.")
    try:
        # Llamamos a la función que hace el trabajo pesado
        result = main_generator_function(
            prompt_en, num_images, seed, selected_ratio, model_type, final_ref_images, save_images_flag
        )
        # Guardamos el resultado junto con el estado de éxito
        tasks[task_id] = {'status': 'SUCCESS', 'result': result}
    except Exception as e:
        logging.error(f"Task {task_id} failed in background thread: {e}")
        # En caso de un error inesperado, lo guardamos para que el frontend lo sepa
        tasks[task_id] = {'status': 'FAILURE', 'result': {'status': 'error', 'message': 'La generación falló por un error inesperado.'}}
    logging.info(f"Thread for task {task_id} finished.")
# ----------------------------------------------------------------

@app.before_request
def initialize_session():
    if request.endpoint:
        logging.info(f"Session before request: {session.sid if session.sid else 'No SID'}, Keys: {list(session.keys())}")

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

        SESSION_TIMEOUT_MIN = 30
        if request.endpoint == 'index':
            now = time.time()
            last_activity = session.get('last_activity', 0)
            if now - last_activity > SESSION_TIMEOUT_MIN * 60 or 'last_activity' not in session:
                logging.info(f"New visit detected for SID {session.sid}: Cleaning old refs/results.")
                session['results'] = []
                session['reference_images_list'] = []
                session['save_images'] = False
                session['last_prompt'] = ''
                session['last_activity'] = now
            else:
                session['last_activity'] = now

@app.route('/')
def index():
    logging.info(f"Rendering index.html. Active tab: {session.get('active_tab')}, Results count: {len(session.get('results', []))}")
    return render_template('index.html',
                           model_names_list=MODEL_NAMES_LIST,
                           active_tab=session['active_tab'],
                           results=session['results'], 
                           reference_images_list=session['reference_images_list'],
                           aspect_ratio_index=session['aspect_ratio_index'],
                           save_images=session['save_images'],
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
        logging.info(f"Prompt improved & translated for session {session.sid}: '{improved_en[:100]}...'")
        return jsonify({'status': 'success', 'improved_prompt': improved_en})
    except Exception as e:
        logging.error(f"Error in improve_prompt for session {session.sid}: {e}")
        return jsonify({'status': 'error', 'message': f'Error al mejorar prompt: {str(e)}. Usando el original.'}), 500

@app.route('/generate_magic_prompt', methods=['POST'])
def generate_magic_prompt():
    try:
        magic_en = generate_magic_prompt_in_english()
        return jsonify({'status': 'success', 'magic_prompt': magic_en})
    except Exception as e:
        logging.error(f"Error in generate_magic_prompt for session {session.sid}: {e}")
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
         return jsonify({'status': 'error', 'message': 'auth_error: GOOGLE_SESSION_TOKEN no configurado en el servidor.'}), 500

    # --- LÓGICA DE HILOS ---
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'PENDING'}
    
    # Preparamos los argumentos para la función que se ejecutará en segundo plano
    thread_args = (task_id, prompt_en, num_images, seed, selected_ratio, model_type, final_ref_images, save_images_flag)
    # Creamos e iniciamos el hilo
    thread = Thread(target=run_generation_in_background, args=thread_args)
    thread.daemon = True # El hilo morirá si la aplicación principal muere
    thread.start()
    
    # Respondemos inmediatamente al frontend con el ID de la tarea
    return jsonify({'status': 'processing', 'task_id': task_id}), 202

@app.route('/check_task/<task_id>', methods=['GET'])
def check_task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Tarea no encontrada o expirada.'}), 404

    if task['status'] == 'PENDING':
        return jsonify({'status': 'processing'})
        
    elif task['status'] == 'SUCCESS':
        result = task['result']
        if result['status'] == 'success':
            session['results'] = result['images']
            session['save_images'] = result.get('save_images', False)
            tasks.pop(task_id, None) # Limpiar la tarea de la memoria una vez entregada
            return jsonify({'status': 'success', 'images': result['images']})
        else:
            # Reutilizamos tu diccionario de errores detallados original
            detailed_error_messages = {
                "minor_upload_error": "La imagen de referencia no pudo ser procesada. Podría infringir las políticas de contenido (menores, contenido explícito). Prueba con otra imagen.",
                "prominent_people_error": "La imagen de referencia parece contener personas famosas o contenido sensible. Por favor, intenta con una imagen diferente.",
                "child_exploitation_error": "Se ha detectado contenido inaceptable en la imagen. Esta acción está estrictamente prohibida y no será procesada.",
                "harmful_content_error": "La imagen de referencia parece contener elementos dañinos y no puede ser procesada. Por favor, usa otra.",
                "generic_upload_error": "Hubo un problema al subir tu imagen. Asegúrate de que es un archivo válido (JPG/PNG) y no está dañado.",
                "image_too_large": "¡La imagen es muy grande! Por favor, intenta con una imagen de menos de 10MB.",
                "upload_failed: no_media_ids": "Ocurrió un error al subir la imagen de referencia. Por favor, inténtalo de nuevo.",
                "unsafe_generation_error": "Tu descripción parece infringir las políticas de contenido seguro. Por favor, modifica el texto para continuar.",
                "no_images_returned": "La IA no pudo generar un resultado para tu descripción. ¡Intenta ser más específico o prueba con una idea diferente!",
                "auth_error": "Tu sesión parece haber caducado. Por favor, recarga la página para continuar.",
                "connection_error: timeout": "La solicitud tardó demasiado en responder. Esto puede pasar con imágenes muy pesadas o una conexión lenta. Inténtalo de nuevo.",
                "connection_error": "No se pudo conectar con el servidor de IA. Revisa tu conexión a internet y vuelve a intentarlo.",
                "generic_api_error": "Ocurrió un error inesperado con la IA. Si el problema persiste, prueba con una descripción o imagen diferente."
            }
            message_key = result.get('message', 'generic_api_error')
            final_user_message = detailed_error_messages.get(message_key, detailed_error_messages["generic_api_error"])
            tasks.pop(task_id, None)
            return jsonify({'status': 'error', 'message': final_user_message})
            
    elif task['status'] == 'FAILURE':
        result = task['result']
        tasks.pop(task_id, None)
        return jsonify({'status': 'error', 'message': result.get('message')})
    
    return jsonify({'status': 'processing'})

@app.route('/update_session_settings', methods=['POST'])
def update_session_settings():
    data = request.json  
    if 'active_tab' in data:  
        new_tab = data['active_tab']  
        session['active_tab'] = new_tab  
        session['results'] = []  
        session['save_images'] = False  
        new_model_type = MODEL_DISPLAY_NAMES.get(new_tab, '')  
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
    if image_data_url and len(session['reference_images_list']) < 3:
        if image_data_url not in session['reference_images_list']: 
            session['reference_images_list'].append(image_data_url)
    return jsonify({'status': 'success', 'reference_images': session['reference_images_list']})

@app.route('/remove_reference_image/<int:index>', methods=['POST'])
def remove_reference_image(index):
    if 0 <= index < len(session['reference_images_list']):
        session['reference_images_list'].pop(index)
    return jsonify({'status': 'success', 'reference_images': session['reference_images_list']})

@app.route('/clear_session_results', methods=['POST'])
def clear_session_results():
    session['results'] = []
    session['reference_images_list'] = []
    session['save_images'] = False
    session['aspect_ratio_index'] = 0
    session['last_prompt'] = ''
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)