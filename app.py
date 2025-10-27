# app.py (solo cambio en update_session_settings; resto igual)
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session # <--- ¡Importante!
import os
import io
import random
from PIL import Image
import base64
import logging
import google.generativeai as genai
import time
# Importa estas variables de config.py
from config import MODEL_DISPLAY_NAMES, MODEL_NAMES_LIST, GOOGLE_SESSION_TOKEN, GEMINI_API_KEY
# Importa las funciones de utilidad de utils.py
from utils import main_generator_function, create_blank_image, improve_prompt_with_gemini, translate_to_english

app = Flask(__name__) # <--- ¡Esta es la instancia de la aplicación Flask!

# --- CAMBIO 1: CONFIGURACIÓN DE SESIÓN ROBUSTA PARA PRODUCCIÓN ---
# Elimina `app.secret_key` y lo centraliza en la configuración de la app,
# cargándolo desde una variable de entorno, que es la práctica correcta.
# Dokploy inyectará esta variable.
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'una-clave-secreta-solo-para-desarrollo-local')

# Configuración para usar el sistema de archivos como almacenamiento de sesión.
# Esto garantiza que todos los workers de Gunicorn compartan la misma sesión.
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False # Mantiene la sesión entre reinicios del navegador
app.config["SESSION_USE_SIGNER"] = True # Firma criptográficamente la cookie de sesión

# --- CAMBIO 2: RUTA DE SESIÓN ABSOLUTA PARA ENTORNOS DE CONTENEDOR ---
# Usar una ruta absoluta como '/tmp/' es más seguro y predecible dentro de un
# contenedor de Docker que una ruta relativa como './flask_session_data'.
app.config["SESSION_FILE_DIR"] = "/tmp/flask_session"

# --- CAMBIO 3: ELIMINAR CONFIGURACIONES INNECESARIAS O REDUNDANTES ---
# Se eliminan SESSION_FILE_THRESHOLD, SESSION_FILE_MODE
# ya que sus valores por defecto son adecuados y no es necesario especificarlos.

Session(app) # Inicializa Flask-Session con la configuración anterior

# Configuración del logging
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
        return jsonify({'status': 'error', 'message': '⚠️ Escribe un prompt para mejorar.'}), 400
    
    try:
        improved_prompt = improve_prompt_with_gemini(prompt)
        logging.info(f"Prompt mejorado para sesión {session.sid}: '{improved_prompt[:100]}...'")
        return jsonify({'status': 'success', 'improved_prompt': improved_prompt})
    except Exception as e:
        logging.error(f"Error en improve_prompt para sesión {session.sid}: {e}")
        return jsonify({'status': 'error', 'message': f'❌ Error al mejorar prompt: {str(e)}. Usando el original.'}), 500

@app.route('/generate_magic_prompt', methods=['POST'])
def generate_magic_prompt():
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content("Genera UN SOLO prompt corto (20-40 palabras) y aleatorio para generación de imágenes con IA. En español, estilo fotorealista/descriptivo con escenas vívidas similares a estos ejemplos: 'Foto de un gato flotando en el espacio con traje de astronauta, con la Tierra de fondo' o 'Retrato fotorrealista de una mujer con pendientes elaborados iluminada frontalmente, retrato de cuerpo completo, hiperrealista'. Incluye detalles sensoriales y narrativos, pero manténlo conciso. Responde SOLO con el prompt, sin explicaciones.")
        magic_prompt_es = response.text.strip()
        logging.info(f"Prompt mágico generado (ES) para sesión {session.sid}: '{magic_prompt_es[:100]}...'")
        if not magic_prompt_es:
            return jsonify({'status': 'error', 'message': '❌ Error al generar prompt. Inténtalo de nuevo.'}), 500
        return jsonify({'status': 'success', 'magic_prompt': magic_prompt_es})
    except Exception as e:
        logging.error(f"Error en generate_magic_prompt para sesión {session.sid}: {e}")
        return jsonify({'status': 'error', 'message': f'❌ Error al generar prompt mágico: {str(e)}.'}), 500    

@app.route('/generate', methods=['POST'])
def generate_images():
    data = request.json
    prompt = data.get('prompt', '')
    num_images = int(data.get('num_images', 4))
    seed = int(data.get('seed', -1))
    selected_ratio = data.get('aspect_ratio', '1:1')
    model_name_display = data.get('model_name_display')
    save_images_flag = data.get('save_images', False)
    ref_images_data_urls = data.get('reference_images', [])

    model_type = MODEL_DISPLAY_NAMES.get(model_name_display)

    if not prompt.strip():
        return jsonify({'status': 'error', 'message': '⚠️ Por favor, escribe una descripción.'}), 400

    # Log extra para debug de key
    gemini_key = os.getenv('GEMINI_API_KEY')
    if gemini_key:
        logging.info(f"GEMINI_API_KEY encontrada para traducción (primeros 10 chars: {gemini_key[:10]}...)")
    else:
        logging.warning("GEMINI_API_KEY NO encontrada - traducción fallará, usando prompt original.")

    # Traducir prompt a inglés para el modelo (mantener original en logs/español para frontend)
    prompt_english = translate_to_english(prompt)
    logging.info(f"Prompt original (ES): '{prompt[:100]}...' → Traducido (EN): '{prompt_english[:100]}...'")

    is_ref_model = model_type in ["R2I", "GEM_PIX"]
    refs_provided = bool(ref_images_data_urls)

    final_ref_images = ref_images_data_urls
    if is_ref_model and not refs_provided:
        if model_type == "R2I":
            return jsonify({'status': 'error', 'message': f"⚠️ El modelo '{model_name_display}' requiere una imagen de referencia."}), 400
        elif model_type == "GEM_PIX":
            logging.info("GEM_PIX selected without reference images. Creating blank image.")
            blank_img_pil = create_blank_image(selected_ratio)
            buffered = io.BytesIO()
            blank_img_pil.save(buffered, format="PNG") 
            blank_img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            final_ref_images = [f"data:image/png;base64,{blank_img_b64}"]
    
    if not GOOGLE_SESSION_TOKEN:
         return jsonify({'status': 'error', 'message': 'auth_error: GOOGLE_SESSION_TOKEN no configurado en el servidor.'}), 500

    result = main_generator_function(prompt_english, num_images, seed, selected_ratio, model_type, final_ref_images, save_images_flag)
    
    if result['status'] == 'success':
        converted_images = []
        for pil_img in result['images']:
            if isinstance(pil_img, Image.Image):
                buffered = io.BytesIO()
                pil_img.save(buffered, format="PNG")
                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                data_url = f"data:image/png;base64,{img_base64}"
                converted_images.append(data_url)
            else:
                converted_images.append(pil_img)
        result['images'] = converted_images
        
        session['results'] = result['images']
        session['save_images'] = save_images_flag 
        logging.info(f"Generated {len(result['images'])} images for session {session.sid}. Save images: {save_images_flag}")
        return jsonify({'status': 'success', 'images': result['images']})
    else:
        detailed_error_messages = {
            "minor_upload_error": "🚫 La imagen de referencia podría contener contenido inapropiado (ej. menores, contenido explícito). Por favor, usa otra imagen.",
            "prominent_people_error": "🚫 La imagen de referencia contiene personas prominentes o contenido sensible. Por favor, usa otra imagen.",
            "child_exploitation_error": "🚫 Contenido de explotación infantil detectado en la imagen de referencia. Esta acción está estrictamente prohibida.",
            "harmful_content_error": "🚫 La imagen de referencia contiene contenido dañino. Por favor, usa otra imagen.",
            "generic_upload_error": "❌ Error al procesar la imagen de referencia. Asegúrate de que sea una imagen válida y no esté dañada.",
            "image_too_large": "📦 La imagen de referencia es demasiado grande. El tamaño máximo permitido es 10MB.",
            "upload_failed: no_media_ids": "📤 Fallo interno: No se pudieron subir las imágenes de referencia. Intenta de nuevo.", 
            "unsafe_generation_error": "🎨 Tu descripción infringe las políticas de contenido seguro (ej. menores, contenido explícito, violento). Por favor, modifica tu prompt.",
            "minors_error": "🚫 Contenido relacionado con menores o de naturaleza sensible en la descripción. Por favor, ajusta tu prompt.",
            "sexual_error": "🚫 Contenido de naturaleza sexual en la descripción. Por favor, ajusta tu prompt.",
            "violence_error": "🚫 Contenido violento o gráfico en la descripción. Por favor, ajusta tu prompt.",
            "criminal_error": "🚫 Contenido relacionado con actividades criminales en la descripción. Por favor, ajusta tu prompt.",
            "no_images_returned": "🤔 La IA no pudo generar imágenes para tu descripción. Intenta con un prompt diferente.",
            "auth_error": f"🔑 Error de autenticación: Tu sesión ha caducado o es inválida. Vuelve a cargar la página e inténtalo de nuevo. Detalles: {result['message'].split(':', 1)[1].strip() if ':' in result['message'] else result['message']}",
            "connection_error: timeout": "🌐 La conexión con la IA se agotó (timeout). Revisa tu conexión a internet o intenta más tarde.",
            "connection_error": "🌐 Error de conexión con el servidor de IA. Revisa tu conexión a internet e inténtalo de nuevo.",
            "generic_api_error: invalid_json": "⚙️ La respuesta de la IA no es válida. Intenta de nuevo.",
            "generic_api_error: non_json_error_response": "⚙️ La IA devolvió un error inesperado en el formato. Intenta de nuevo.",
            "internal_config_error": "⚙️ Error de configuración interna de la aplicación. Por favor, contacta al soporte.", 
            "no_image_provided": "❌ No se proporcionó ninguna imagen para subir. Esto es un error interno.", 
            "generic_api_error": "⚙️ La IA devolvió un error interno. Intenta de nuevo o con un prompt/imagen diferente."
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
    data = request.json  # Datos del JS: {active_tab: "Nuevo Modelo"}
    
    if 'active_tab' in data:  # Si viene cambio de modelo
        new_tab = data['active_tab']  # Ej: "Imagen desde Referencia (V3.5)"
        session['active_tab'] = new_tab  # Actualiza en sesión (reload lo renderiza en header)
        
        session['results'] = []  # Limpia results viejos (nueva gen)
        session['save_images'] = False  # Resetea flag de save
        
        # CAMBIO CLAVE: Manejo inteligente de refs
        new_model_type = MODEL_DISPLAY_NAMES.get(new_tab, '')  # Obtiene tipo interno (ej: "R2I" para ref models)
        if new_model_type not in ["R2I", "GEM_PIX"]:  # Si nuevo modelo NO usa refs (ej: 3.1 o 3.5)
            session['reference_images_list'] = []  # Limpia refs (no sirven aquí)
            logging.info(f"Cleaned refs on switch to non-ref model: {new_tab}")  # Log para debug
        else:  # Si SÍ usa refs (R2I o GEM_PIX)
            # NO limpia: Preserva refs (ej: de "Usar en" desde 3.1)
            logging.info(f"Preserved refs on switch to ref model: {new_tab}")  # Log para debug
            
    if 'aspect_ratio_index' in data:  # Si viene cambio de ratio
        session['aspect_ratio_index'] = data['aspect_ratio_index']
    if 'save_images' in data:  # Si viene toggle de save
        session['save_images'] = data['save_images']
    
    logging.info(f"Session settings updated for SID {session.sid}: {data}")  # Log general
    return jsonify({'status': 'success'})  # OK al JS

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
        session.clear()  # Limpia toda la sesión para no guardar previas
        logging.info(f"Reset complete for session {session.sid}: cleared results, references, save_images, and aspect_ratio_index.")
    return jsonify({'status': 'success'})


if __name__ == '__main__':
    # No es necesario crear el directorio aquí, Flask-Session lo hará automáticamente
    app.run(debug=True)