# utils.py
import base64
import io
import json
import os
import random
from datetime import datetime
from PIL import Image
import requests
import logging

logging.getLogger("streamlit").setLevel(logging.ERROR)

from config import (
    GENERATE_URL_OBFUSCATED, UPLOAD_URL_OBFUSCATED, BASE_HEADERS,
    MODEL_DISPLAY_NAMES, GOOGLE_SESSION_TOKEN, GEMINI_API_KEY
)

# Nueva importación para Gemini
import google.generativeai as genai

def decode_token(token_b64):
    if not token_b64 or not token_b64.strip(): raise ValueError("El token está vacío.")
    decoded_str = base64.b64decode(token_b64.strip()).decode('utf-8')
    parts = decoded_str.split(":", 1)
    if len(parts) != 2: raise ValueError("Formato de token inválido.")
    return parts[0].strip(), parts[1].strip()

def upload_image(bearer_token, x_client_data, pil_image, mime_type=None):
    if pil_image is None: return ('error', 'no_image_provided')
    try: real_upload_url = base64.b64decode(UPLOAD_URL_OBFUSCATED).decode('utf-8')
    except: return ('error', 'internal_config_error')
    
    if pil_image.mode != 'RGB': pil_image = pil_image.convert('RGB')
    
    pil_image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    buffered = io.BytesIO()
    pil_image.save(buffered, format="JPEG", quality=85, optimize=True)
    if len(buffered.getvalue()) > 10 * 1024 * 1024: return ('error', 'image_too_large')
    image_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {bearer_token}", "X-Client-Data": x_client_data, "X-Browser-Year": "2025"}
    payload = {"imageInput": {"rawImageBytes": image_b64, "mimeType": "image/jpeg", "isUserUploaded": True}, "clientContext": {"tool": "ASSET_MANAGER"}}
    
    try:
        response = requests.post(real_upload_url, headers=headers, json=payload, timeout=30)
        response.encoding = 'utf-8'  # Ensure encoding to avoid bytes in json()
        if response.status_code == 200: 
            return ('success', response.json()["mediaGenerationId"]["mediaGenerationId"])
        else:
            try:
                resp_json = response.json()
            except json.JSONDecodeError:
                logging.error(f"Upload response not JSON: {response.text[:200]}")
                return ('error', 'generic_upload_error')
            reason = resp_json.get("error", {}).get("details", [{}])[0].get("reason", "UNKNOWN_ERROR")
            error_map = {
                "PUBLIC_ERROR_MINOR_UPLOAD": "minor_upload_error",
                "PUBLIC_ERROR_PROMINENT_PEOPLE_UPLOAD": "prominent_people_error",
                "PUBLIC_ERROR_CHILD_EXPLOITATION_UPLOAD": "child_exploitation_error",
                "PUBLIC_ERROR_HARMFUL_CONTENT_UPLOAD": "harmful_content_error",
            }
            return ('error', error_map.get(reason, 'generic_upload_error'))
    except requests.exceptions.Timeout:
        return ('error', 'connection_error: upload_timeout')
    except Exception as e:
        logging.error(f"Upload exception: {e}")
        return ('error', f'connection_error: {str(e)}')

def create_blank_image(aspect_ratio_str):
    sizes = {"16:9": (1024, 576), "9:16": (576, 1024), "1:1": (512, 512), "4:3": (768, 576), "3:4": (576, 768)}
    return Image.new('RGB', sizes.get(aspect_ratio_str, (512, 512)), color='white')

# Nueva función para mejorar el prompt con Gemini
def improve_prompt_with_gemini(original_prompt):
    if not GEMINI_API_KEY:
        logging.warning("GEMINI_API_KEY no configurada para mejora de prompt - usando original.")
        return original_prompt
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Responde SOLO con el prompt mejorado para generación de imágenes con IA de alta calidad. Mantén completamente la idea original sin agregar elementos nuevos o exagerados, solo refina con detalles sutiles, vívidos y optimizaciones mínimas para mejor resultado. NO agregues explicaciones, opciones ni texto adicional. Solo el prompt: {original_prompt}")
        improved_prompt = response.text.strip()
        logging.info(f"Mejora de prompt exitosa: '{original_prompt[:50]}...' → '{improved_prompt[:50]}...'")
        if not improved_prompt:
            return original_prompt  # Fallback si no hay respuesta
        return improved_prompt
    except Exception as e:
        logging.error(f"Error al mejorar prompt con Gemini: {e}")
        return original_prompt  # Fallback al original en caso de error

# Nueva función para traducir prompt a inglés
def translate_to_english(prompt):
    key = GEMINI_API_KEY  # Usa la variable de config
    if not key:
        logging.warning("GEMINI_API_KEY no encontrada - usando prompt original para traducción.")
        return prompt
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Traduce este prompt al inglés manteniendo el significado exacto y el estilo. Responde SOLO con la traducción: {prompt}")
        translated = response.text.strip()
        logging.info(f"Traducción exitosa: '{prompt[:50]}...' → '{translated[:50]}...'")
        if not translated:
            return prompt  # Fallback si no hay respuesta
        return translated
    except Exception as e:
        logging.error(f"Error al traducir prompt a inglés: {e}")
        return prompt  # Fallback al original en caso de error

def main_generator_function(prompt, num_images, seed, aspect_ratio_str, model_type, ref_images, save_images_flag=False):
    logging.info(f"\n--- DEBUG: API Request ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
    logging.info(f"  Model Type (Internal): {model_type}")
    try: bearer_token, x_client_data = decode_token(GOOGLE_SESSION_TOKEN)
    except ValueError as e: 
        logging.error(f"Token decode error: {e}")
        return {'status': 'error', 'message': f'auth_error: {str(e)}'}
    
    aspect_map = {"16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE", "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT", "1:1": "IMAGE_ASPECT_RATIO_SQUARE", "4:3": "IMAGE_ASPECT_RATIO_LANDSCAPE_FOUR_THREE", "3:4": "IMAGE_ASPECT_RATIO_PORTRAIT_THREE_FOUR"}
    api_aspect_ratio = aspect_map.get(aspect_ratio_str, "IMAGE_ASPECT_RATIO_SQUARE")
    
    tool, project_id = ("VIDEO_FX", "3bbf5eba-be3f-4022-b9a0-158b93131757") \
                       if model_type in ["IMAGEN_3_1", "IMAGEN_3_5"] and not ref_images \
                       else ("PINHOLE", "cc8e7fa2-9e2b-4742-ad19-41d3732460db")
    
    logging.info(f"  Tool: {tool}, Project ID: {project_id}")
    logging.info(f"  Aspect Ratio: {api_aspect_ratio}")
    logging.info(f"  Prompt: '{prompt.strip()}'")
    logging.info(f"  Num Images: {num_images}, Seed: {seed}")
    logging.info(f"  Reference Images provided (count in data URLs): {len(ref_images)}")
    
    # Create blank if no refs for ref models
    if model_type in ["R2I", "GEM_PIX"] and not ref_images:
        logging.info(f"{model_type} selected without reference images. Creating blank image.")
        blank_pil = create_blank_image(aspect_ratio_str)
        buffered = io.BytesIO()
        blank_pil.save(buffered, format="PNG")
        blank_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        ref_images = [f"data:image/png;base64,{blank_b64}"]
    
    headers = {**BASE_HEADERS, "Authorization": f"Bearer {bearer_token}", "X-Client-Data": x_client_data, "X-Browser-Year": "2025"}
    
    payload = {"clientContext": {"tool": tool, "projectId": project_id}, "userInput": {"candidatesCount": int(num_images), "prompts": [prompt.strip()]}, "aspectRatio": api_aspect_ratio, "modelInput": {"modelNameType": model_type}}
    payload["userInput"]["seed"] = random.randint(0, 99999) if int(seed) == -1 else int(seed)

    if ref_images:
        media_ids = []
        for i, pil_img_data_url in enumerate(ref_images):
            try:
                header, encoded = pil_img_data_url.split(",", 1)
                data = base64.b64decode(encoded)
                pil_img = Image.open(io.BytesIO(data))
            except Exception as e:
                logging.error(f"Error decoding ref image {i}: {e}")
                return {'status': 'error', 'message': 'generic_upload_error'}
            
            status, msg = upload_image(bearer_token, x_client_data, pil_img)
            if status == 'error': 
                logging.info(f"  DEBUG: Upload image {i} error: {msg}")
                return {'status': 'error', 'message': msg} 
            media_ids.append(msg)
        if not media_ids: 
            logging.info("  DEBUG: No media IDs after upload process for reference images.")
            return {'status': 'error', 'message': 'upload_failed: no_media_ids'} 
        payload["userInput"]["referenceImageInput"] = {"referenceImages": [{"mediaId": mid, "imageType": "REFERENCE_IMAGE_TYPE_CONTEXT"} for mid in media_ids]}
        logging.info(f"  DEBUG: Payload includes {len(media_ids)} reference image(s).")

    try:
        real_generate_url = base64.b64decode(GENERATE_URL_OBFUSCATED).decode('utf-8')
        logging.info(f"  DEBUG: Sending request to: {real_generate_url}")

        response = requests.post(real_generate_url, headers=headers, json=payload, timeout=90)
        response.encoding = 'utf-8'  # Ensure no bytes in text/json
        
        logging.info(f"--- DEBUG: API Response ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
        logging.info(f"  Status Code: {response.status_code}")
        logging.info(f"  Response Body (first 500 chars): {response.text[:500]}...")

        if response.status_code == 200:
            try:
                response_json = response.json()
                generated_images_data = response_json.get("imagePanels", [{}])[0].get("generatedImages", [])
                
                if not generated_images_data:
                    logging.info(f"  DEBUG: API returned 200 OK, but no 'generatedImages' found in JSON response.")
                    return {'status': 'error', 'message': 'no_images_returned'}
                
                output_images_b64 = []
                # ELIMINADO: No guardar en servidor. Removido el bloque if save_images_flag para os.makedirs y pil_image.save

                for i, img_data in enumerate(generated_images_data):
                    if "encodedImage" in img_data:
                        try:
                            img_bytes = base64.b64decode(img_data["encodedImage"])
                            pil_image = Image.open(io.BytesIO(img_bytes))
                            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                            output_images_b64.append(f"data:image/png;base64,{img_b64}")
                            
                            # ELIMINADO: No guardar en servidor. Removidas las líneas de save_images_flag aquí
                            
                        except Exception as e:
                            logging.error(f"  DEBUG: Error processing image {i}: {e}")
                            continue  # Skip bad image
                    else:
                        logging.info(f"  DEBUG: Image {i} in response did not contain 'encodedImage'.")

                if not output_images_b64:
                    return {'status': 'error', 'message': 'no_images_returned'}

                logging.info(f"  DEBUG: Successfully processed {len(output_images_b64)} images.")
                return {'status': 'success', 'images': output_images_b64}

            except json.JSONDecodeError as e:
                logging.error(f"  DEBUG: API returned 200 OK, but response body is not valid JSON. Raw text: {response.text[:500]}")
                return {'status': 'error', 'message': 'generic_api_error: invalid_json'}
            except Exception as e:
                logging.error(f"  DEBUG: Error processing 200 OK API response: {e}")
                return {'status': 'error', 'message': f'generic_api_error: {str(e)}'}

        else:
            logging.info(f"  DEBUG: API returned non-200 status. Trying to extract error details...")
            try:
                resp_json = response.json()
                reason = resp_json.get("error", {}).get("details", [{}])[0].get("reason", "UNKNOWN_ERROR")
                error_map_generation = {
                    "PUBLIC_ERROR_UNSAFE_GENERATION": "unsafe_generation_error",
                    "PUBLIC_ERROR_MINORS": "minors_error",
                    "PUBLIC_ERROR_SEXUAL": "sexual_error",
                    "PUBLIC_ERROR_VIOLENCE": "violence_error",
                    "PUBLIC_ERROR_CRIMINAL": "criminal_error",
                }
                final_error_message = error_map_generation.get(reason, 'generic_api_error')
                logging.info(f"  DEBUG: API Error Reason: {reason}, Mapped: {final_error_message}")
                return {'status': 'error', 'message': final_error_message}
            except json.JSONDecodeError:
                logging.error(f"  DEBUG: Could not decode API error response as JSON. Raw text: {response.text[:500]}")
                return {'status': 'error', 'message': 'generic_api_error: non_json_error_response'}
            except Exception as e:
                logging.error(f"  DEBUG: Error processing non-200 API response: {e}")
                return {'status': 'error', 'message': f'generic_api_error: {str(e)}'}

    except requests.exceptions.Timeout:
        logging.error(f"--- DEBUG: API Request timed out after 90 seconds. ---")
        return {'status': 'error', 'message': 'connection_error: timeout'}
    except requests.exceptions.ConnectionError as e:
        logging.error(f"--- DEBUG: API Connection Error: {e} ---")
        return {'status': 'error', 'message': f'connection_error: {str(e)}'}
    except Exception as e:
        logging.error(f"Unhandled exception in main_generator_function: {e}")
        logging.error(f"Response status: {response.status_code}, Response body: {response.text[:1000]}")
        return {'status': 'error', 'message': f'connection_error: {str(e)}'}