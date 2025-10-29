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

        SESSION_TIMEOUT_MIN = 30
        if request.endpoint == 'index':
            now = time.time()
            last_activity = session.get('last_activity', 0)
            if now - last_activity > SESSION_TIMEOUT_MIN * 60 or 'last_activity' not in session:
                logging.info(f"New visit detected for SID {session.sid}: Cleaning old refs/results.")
                session['results'] = []
                session['reference_images_list'] = []
                session['save_images'] = False
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
                           MODEL_NAMES_LIST=MODEL_NAMES_LIST)

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

    # Traducción optimizada
    prompt_en = translate_to_english(prompt_es)
    logging.info(f"Prompt original (ES): '{prompt_es[:100]}...' → Final (EN): '{prompt_en[:100]}...'")

    is_ref_model = model_type in ["R2I", "GEM_PIX"]
    refs_provided = bool(ref_images_data_urls)

    final_ref_images = ref_images_data_urls
    if is_ref_model and not refs_provided:
        if model_type == "R2I":
            return jsonify({'status': 'error', 'message': f"El modelo '{model_name_display}' requiere una imagen de referencia."}), 400
        elif model_type == "GEM_PIX":
            logging.info("GEM_PIX selected without reference images. Creating blank image.")
            blank_img_pil = create_blank_image(selected_ratio)
            buffered = io.BytesIO()
            blank_img_pil.save(buffered, format="PNG") 
            blank_img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            final_ref_images = [f"data:image/png;base64,{blank_img_b64}"]
    
    if not GOOGLE_SESSION_TOKEN:
         return jsonify({'status': 'error', 'message': 'auth_error: GOOGLE_SESSION_TOKEN no configurado en el servidor.'}), 500

    result = main_generator_function(prompt_en, num_images, seed, selected_ratio, model_type, final_ref_images, save_images_flag)
    
    if result['status'] == 'success':
        session['results'] = result['images']
        session['save_images'] = save_images_flag 
        logging.info(f"Generated {len(result['images'])} images for session {session.sid}. Save images: {save_images_flag}")
        return jsonify({'status': 'success', 'images': result['images']})
    else:
        detailed_error_messages = {
            "minor_upload_error": "La imagen de referencia podría contener contenido inapropiado (ej. menores, contenido explícito). Por favor, usa otra imagen.",
            "prominent_people_error": "La imagen de referencia contiene personas prominentes o contenido sensible. Por favor, usa otra imagen.",
            "child_exploitation_error": "Contenido de explotación infantil detectado en la imagen de referencia. Esta acción está estrictamente prohibida.",
            "harmful_content_error": "La imagen de referencia contiene contenido dañino. Por favor, usa otra imagen.",
            "generic_upload_error": "Error al procesar la imagen de referencia. Asegúrate de que sea una imagen válida y no esté dañada.",
            "image_too_large": "La imagen de referencia es demasiado grande. El tamaño máximo permitido es 10MB.",
            "upload_failed: no_media_ids": "Fallo interno: No se pudieron subir las imágenes de referencia. Intenta de nuevo.", 
            "unsafe_generation_error": "Tu descripción infringe las políticas de contenido seguro (ej. menores, contenido explícito, violento). Por favor, modifica tu prompt.",
            "minors_error": "Contenido relacionado con menores o de naturaleza sensible en la descripción. Por favor, ajusta tu prompt.",
            "sexual_error": "Contenido de naturaleza sexual en la descripción. Por favor, ajusta tu prompt.",
            "violence_error": "Contenido violento o gráfico en la descripción. Por favor, ajusta tu prompt.",
            "criminal_error": "Contenido relacionado con actividades criminales en la descripción. Por favor, ajusta tu prompt.",
            "no_images_returned": "La IA no pudo generar imágenes para tu descripción. Intenta con un prompt diferente.",
            "auth_error": f"Error de autenticación: Tu sesión ha caducado o es inválida. Vuelve a cargar la página e inténtalo de nuevo. Detalles: {result['message'].split(':', 1)[1].strip() if ':' in result['message'] else result['message']}",
            "connection_error: timeout": "La conexión con la IA se agotó (timeout). Revisa tu conexión a internet o intenta más tarde.",
            "connection_error": "Error de conexión con el servidor de IA. Revisa tu conexión a internet e inténtalo de nuevo.",
            "generic_api_error: invalid_json": "La respuesta de la IA no es válida. Intenta de nuevo.",
            "generic_api_error: non_json_error_response": "La IA devolvió un error inesperado en el formato. Intenta de nuevo.",
            "internal_config_error": "Error de configuración interna de la aplicación. Por favor, contacta al soporte.", 
            "no_image_provided": "No se proporcionó ninguna imagen para subir. Esto es un error interno.", 
            "generic_api_error": "La IA devolvió un error interno. Intenta de nuevo o con un prompt/imagen diferente."
        }
        
        message_key = result['message']
        if ":" in message_key:
            message_key_parts = message_key.split(':', 1)
            if message_key_parts[0] in detailed_error_messages:
                message_key = message_key_parts[0]
        
        final_user_message = detailed_error_messages.get(message_key, detailed_error_messages["generic_api_error"])
        
        logging.error(f"Error generating images for session {session.sid}: {result['message']} -> User message: {final_user_message}")
        return jsonify({'status': 'error', 'message': final_user_message}), 500

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
            logging.info(f"Cleaned refs on switch to non-ref model: {new_tab}")  
        else:  
            logging.info(f"Preserved refs on switch to ref model: {new_tab}")  
            
    if 'aspect_ratio_index' in data:  
        session['aspect_ratio_index'] = data['aspect_ratio_index']
    if 'save_images' in data:  
        session['save_images'] = data['save_images']
    
    logging.info(f"Session settings updated for SID {session.sid}: {data}")  
    return jsonify({'status': 'success'})  

@app.route('/add_reference_image', methods=['POST'])
def add_reference_image():
    data = request.json
    image_data_url = data.get('image') 
    if image_data_url and len(session['reference_images_list']) < 3:
        if image_data_url not in session['reference_images_list']: 
            session['reference_images_list'].append(image_data_url)
            logging.info(f"Added reference image for session {session.sid}. Current count: {len(session['reference_images_list'])}")
        else:
            logging.warning(f"Reference image already exists in session for SID {session.sid}.")
            
        return jsonify({'status': 'success', 'reference_images': session['reference_images_list']})
    logging.warning(f"Failed to add reference image for session {session.sid}. Limit reached or invalid image.")
    return jsonify({'status': 'error', 'message': 'Límite de 3 imágenes de referencia alcanzado o imagen inválida.'}), 400

@app.route('/remove_reference_image/<int:index>', methods=['POST'])
def remove_reference_image(index):
    if 0 <= index < len(session['reference_images_list']):
        removed_image = session['reference_images_list'].pop(index)
        logging.info(f"Removed reference image {index} for session {session.sid}. Current count: {len(session['reference_images_list'])}")
        return jsonify({'status': 'success', 'reference_images': session['reference_images_list']})
    logging.warning(f"Failed to remove reference image {index} for session {session.sid}. Invalid index.")
    return jsonify({'status': 'error', 'message': 'Índice de imagen de referencia inválido.'}), 400

@app.route('/clear_session_results', methods=['POST'])
def clear_session_results():
    if 'results' in session:
        session['results'] = []
        session['reference_images_list'] = []
        session['save_images'] = False
        session['aspect_ratio_index'] = 0
        session.clear()  
        logging.info(f"Reset complete for session {session.sid}: cleared results, references, save_images, and aspect_ratio_index.")
    return jsonify({'status': 'success'})


if __name__ == '__main__':
    app.run(debug=True)