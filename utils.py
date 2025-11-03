# utils.py
import base64
import io
import json
import os
import random
from datetime import datetime
from functools import lru_cache
from PIL import Image
import requests
import logging
from langdetect import detect, DetectorFactory

logging.getLogger("streamlit").setLevel(logging.ERROR)

from config import (
    GENERATE_URL_OBFUSCATED, UPLOAD_URL_OBFUSCATED, BASE_HEADERS,
    MODEL_DISPLAY_NAMES, GOOGLE_SESSION_TOKEN, GEMINI_API_KEY
)

import google.generativeai as genai

# --- DETECCIÓN DE IDIOMA CON langdetect ---
DetectorFactory.seed = 0

def is_english(prompt: str) -> bool:
    if not prompt or len(prompt.strip()) < 5:
        return False
    try:
        lang = detect(prompt.strip())
        return lang == 'en'
    except:
        logging.warning(f"Language detection failed for prompt: '{prompt[:50]}...'. Assuming non-English.")
        return False

# --- CACHE DE TRADUCCIONES ---
@lru_cache(maxsize=512)
def _gemini_translate(prompt: str) -> str:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            f"Translate this image generation prompt to English. Keep exact meaning, style, and details. Respond ONLY with the translation:\n\n{prompt}"
        )
        translated = response.text.strip()
        return translated if translated else prompt
    except Exception as e:
        logging.error(f"Gemini translation failed: {e}")
        return prompt

def translate_to_english(prompt: str) -> str:
    if is_english(prompt):
        logging.info(f"Prompt detected as English. Skipping translation.")
        return prompt.strip()
    return _gemini_translate(prompt.strip())

# --- MEJORA + TRADUCCIÓN EN UNA SOLA LLAMADA ---
def improve_and_translate_to_english(original_prompt: str) -> str:
    if not GEMINI_API_KEY:
        logging.warning("GEMINI_API_KEY not set. Using original prompt.")
        return original_prompt

    if is_english(original_prompt):
        improve_prompt = original_prompt
    else:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(
                f"Improve this image prompt: add vivid, subtle details, optimize for high-quality AI generation. "
                f"Keep original idea exactly. Then translate to English. "
                f"Respond ONLY with the final English prompt. NO explanations.\n\nPrompt: {original_prompt}"
            )
            improve_prompt = response.text.strip()
            logging.info(f"Improved & translated: '{original_prompt[:50]}...' → '{improve_prompt[:50]}...'")
            return improve_prompt if improve_prompt else original_prompt
        except Exception as e:
            logging.error(f"Gemini improve+translate failed: {e}")
            return original_prompt

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            f"Improve this English image prompt: add vivid, subtle details, optimize for high-quality AI generation. "
            f"Keep original idea exactly. Respond ONLY with the improved English prompt.\n\nPrompt: {improve_prompt}"
        )
        final = response.text.strip()
        return final if final else improve_prompt
    except Exception as e:
        logging.error(f"Gemini improve (EN) failed: {e}")
        return improve_prompt

# --- PROMPT MÁGICO EN INGLÉS DIRECTO ---
def generate_magic_prompt_in_english() -> str:
    if not GEMINI_API_KEY:
        logging.warning("GEMINI_API_KEY not set. Using fallback magic prompt.")
        return "A surreal floating island with glowing waterfalls, ancient ruins, and a golden sky at sunset, ultra-detailed, cinematic lighting"

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            "Generate ONE short (20-40 words) random image prompt in ENGLISH. Photorealistic or artistic style, vivid scenes. "
            "Examples: 'A cat floating in space wearing an astronaut suit, Earth in background' or "
            "'Hyperrealistic portrait of a woman with elaborate earrings, front lighting, full body'. "
            "Include sensory and narrative details. Respond ONLY with the prompt."
        )
        magic_en = response.text.strip()
        logging.info(f"Magic prompt generated (EN): '{magic_en[:100]}...'")
        return magic_en if magic_en else "A majestic dragon soaring over a crystal lake at dawn, mist rising, ultra-realistic"
    except Exception as e:
        logging.error(f"Gemini magic prompt failed: {e}")
        return "A cyberpunk city at night with neon lights reflecting on wet streets, flying cars, ultra-detailed"

# --- RESTO SIN CAMBIOS ---
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
        response.encoding = 'utf-8'
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

def main_generator_function(prompt, num_images, seed, aspect_ratio_str, model_type, ref_images, save_images_flag=False):
    import time
    logging.info(f"\n--- DEBUG: API Request ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
    logging.info(f"  Model Type (Internal): {model_type}")
    try:
        bearer_token, x_client_data = decode_token(GOOGLE_SESSION_TOKEN)
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
        logging.info(f"  DEBUG: Sending request to: {real_generate_url} with payload: {payload}")
        start_time = time.time()
        response = requests.post(real_generate_url, headers=headers, json=payload, timeout=90)
        end_time = time.time()
        response.encoding = 'utf-8'
        logging.info(f"  DEBUG: API request completed in {end_time - start_time:.2f} seconds, Status: {response.status_code}, Response (first 500 chars): {response.text[:500]}...")
        
        logging.info(f"--- DEBUG: API Response ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
        logging.info(f"  Status Code: {response.status_code}")

        if response.status_code == 200:
            try:
                response_json = response.json()
                generated_images_data = response_json.get("imagePanels", [{}])[0].get("generatedImages", [])
                
                if not generated_images_data:
                    logging.info(f"  DEBUG: API returned 200 OK, but no 'generatedImages' found in JSON response.")
                    return {'status': 'error', 'message': 'no_images_returned'}
                
                output_images_b64 = []

                for i, img_data in enumerate(generated_images_data):
                    if "encodedImage" in img_data:
                        try:
                            img_bytes = base64.b64decode(img_data["encodedImage"])
                            pil_image = Image.open(io.BytesIO(img_bytes))
                            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                            output_images_b64.append(f"data:image/png;base64,{img_b64}")
                        except Exception as e:
                            logging.error(f"  DEBUG: Error processing image {i}: {e}")
                            continue
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
        logging.error(f"Response status: {response.status_code if 'response' in locals() else 'No response'}, Response body: {response.text[:1000] if 'response' in locals() else 'No response'}")
        return {'status': 'error', 'message': f'connection_error: {str(e)}'}