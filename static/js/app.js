// static/js/app.js - VERSIÓN CORREGIDA PARA EXPANDER DE MODELOS (SIN RADIOS) CON MEJORAS EN ERRORES Y CÁMARA

document.addEventListener('DOMContentLoaded', function() {
    const body = document.body;

    window.initialSessionState = JSON.parse(body.getAttribute('data-initial-session-state'));
    window.MODEL_DISPLAY_NAMES_JS = JSON.parse(body.getAttribute('data-model-display-names'));
    window.MODEL_NAMES_LIST_JS = JSON.parse(body.getAttribute('data-model-names-list'));

    const promptTextarea = document.getElementById('prompt-textarea');
    const numImagesSlider = document.getElementById('num-images-slider');
    const numImagesValue = document.getElementById('num-images-value');
    const seedInput = document.getElementById('seed-input');
    const aspectRatioSelect = document.getElementById('aspect-ratio-select');
    const saveImagesCheckbox = document.getElementById('save_images_checkbox');
    const improvePromptButton = document.getElementById('improve-prompt-button');
    const magicPromptButton = document.getElementById('magic-prompt-button');
    const loadingSpinner = document.getElementById('loading-spinner');
    const errorMessage = document.getElementById('error-message');
    const successMessage = document.getElementById('success-message');
    const resultsContainer = document.getElementById('results-container');
    const mainResultsTitle = document.getElementById('main-results-title');
    const referenceImagesContainer = document.getElementById('reference-images-container');
    const fileUploader = document.getElementById('reference-file-uploader');
    const availableSlotsSpan = document.getElementById('available-slots');
    const referenceUploaderSection = document.getElementById('reference-uploader-section');
    const generateButton = document.getElementById('generate-button');
    const clearResultsButton = document.getElementById('clear-results-button');
    const cameraCaptureButton = document.getElementById('camera-capture-button');  // NUEVO: Para botón de cámara

    // NUEVO: Elementos de cámara
    const cameraModal = document.getElementById('camera-modal');
    const cameraVideo = document.getElementById('camera-video');
    const captureCanvas = document.getElementById('capture-canvas');
    const startCameraBtn = document.getElementById('start-camera-btn');
    const captureBtn = document.getElementById('capture-btn');
    const cancelCameraBtn = document.getElementById('cancel-camera-btn');

    // CAMBIO CLAVE: Detectar modelo activo desde expander header (no radios)
    function getActiveModelName() {
        const headerSpan = document.querySelector('.model-expander .expander-header span:first-child');
        return headerSpan ? headerSpan.textContent.trim() : window.initialSessionState.active_tab;
    }

    // Variables para bloquear botones durante procesos
    let isProcessing = false;  // Flag global para evitar múltiples clicks
    const interactiveButtons = [
        generateButton,
        improvePromptButton,
        magicPromptButton,
        clearResultsButton,
        cameraCaptureButton  // NUEVO: Incluye botón de cámara
    ].filter(btn => btn);  // Filtra solo los que existen (sin radios)

    // Función para bloquear todos los botones interactivos
    function disableAllButtons() {
        if (!isProcessing) {
            isProcessing = true;
            interactiveButtons.forEach(btn => {
                if (btn) {
                    btn.disabled = true;
                    btn.style.opacity = '0.6';  // Visual: oscurece para feedback
                    btn.style.cursor = 'not-allowed';
                }
            });
        }
    }

    // Función para reactivar todos los botones
    function enableAllButtons() {
        isProcessing = false;
        interactiveButtons.forEach(btn => {
            if (btn) {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
            }
        });
    }

    // MODAL ELEMENTS
    const imageModal = document.getElementById('image-modal');
    const modalImage = document.getElementById('modal-image');

    if (!generateButton || !resultsContainer) {
        console.error("Error: Elemento(s) crítico(s) no encontrado(s) en el DOM. La aplicación no puede funcionar correctamente.");
        return;
    }

    let currentReferenceImages = window.initialSessionState.reference_images_list || [];
    let activeModelDisplayName = getActiveModelName();  // Inicial desde DOM o session
    let mediaStream = null;  // NUEVO: Para trackear stream de cámara

    // FUNCIONES DEL MODAL PARA AMPLIAR IMÁGENES
    window.openImageModal = function(imageSrc) {
        if (imageModal && modalImage) {
            modalImage.src = imageSrc;
            // CAMBIO CLAVE: Usamos 'flex' para activar el centrado del CSS
            imageModal.style.display = 'flex'; 
            document.body.style.overflow = 'hidden'; // Prevenir scroll
        }
    };

    window.closeImageModal = function() {
        if (imageModal) {
            imageModal.style.display = 'none';
            document.body.style.overflow = 'auto'; // Restaurar scroll
        }
    };

    // NUEVO: FUNCIONES PARA CÁMARA
    window.openCameraModal = function() {
        if (cameraModal) {
            cameraModal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }
    };

    window.closeCameraModal = function() {
        if (cameraModal) {
            cameraModal.style.display = 'none';
            document.body.style.overflow = 'auto';
        }
        if (mediaStream) {
            mediaStream.getTracks().forEach(track => track.stop());
            mediaStream = null;
            cameraVideo.srcObject = null;
        }
        if (startCameraBtn) startCameraBtn.style.display = 'inline-block';
        if (captureBtn) captureBtn.style.display = 'none';
    };

    // Inicializar cámara
    if (startCameraBtn) {
        startCameraBtn.addEventListener('click', async () => {
            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'user' }  // Front-facing para mobile
                });
                cameraVideo.srcObject = mediaStream;
                startCameraBtn.style.display = 'none';
                captureBtn.style.display = 'inline-block';
            } catch (err) {
                showMessage(errorMessage, '😊 No pudimos acceder a la cámara. Verifica permisos o usa subida de archivo.', 'warning');
                console.error('Camera error:', err);
            }
        });
    }

    // Capturar foto
    if (captureBtn) {
        captureBtn.addEventListener('click', () => {
            const ctx = captureCanvas.getContext('2d');
            captureCanvas.width = cameraVideo.videoWidth;
            captureCanvas.height = cameraVideo.videoHeight;
            ctx.drawImage(cameraVideo, 0, 0);
            const imageDataUrl = captureCanvas.toDataURL('image/jpeg', 0.8);  // JPEG 80% para reducir tamaño
            window.addReferenceImage(imageDataUrl, null, true);
            window.closeCameraModal();
        });
    }

    // Event listener para botón de cámara
    if (cameraCaptureButton) {
        cameraCaptureButton.addEventListener('click', () => {
            if (currentReferenceImages.length >= 3) {
                showMessage(errorMessage, '😌 Límite de 3 referencias alcanzado. Elimina una primero.', 'warning');
                return;
            }
            window.openCameraModal();
        });
    }

    // Cerrar modal con tecla ESC (para ambos modales)
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (imageModal && imageModal.style.display === 'flex') {
                window.closeImageModal();
            }
            if (cameraModal && cameraModal.style.display === 'flex') {
                window.closeCameraModal();
            }
        }
    });

    // MEJORADO: showMessage con tipos suaves y botón reintentar para timeouts
    function showMessage(element, message, type = 'error') {
        if (!element) return;
        // Detectar si es timeout/conexión para agregar botón reintentar
        let retryBtn = '';
        if (type.includes('timeout') || type.includes('connection') || message.includes('timeout') || message.includes('conexión')) {
            retryBtn = '<br><button onclick="window.retryGeneration()" style="margin-top: 0.5rem; padding: 0.4rem 0.8rem; background: var(--primary-gradient); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 0.85rem;">🔄 Reintentar</button>';
        }
        element.innerHTML = `${message}${retryBtn}`;
        element.style.display = 'block';
        element.className = type === 'warning' ? 'warning-message' : `${type}-message`;  // Nueva clase warning para errores suaves
        clearTimeout(element.hideTimeout);
        element.hideTimeout = setTimeout(() => { element.style.display = 'none'; }, 10000);  // Aumentado a 10s para más tiempo de lectura
    }

    // NUEVO: Función para reintentar generación (llama al handler de generate)
    window.retryGeneration = function() {
        hideMessages();
        if (generateButton && !isProcessing) {
            generateButton.click();  // Simula click para reintentar
        }
    };

    function hideMessages() {
        if (errorMessage && errorMessage.hideTimeout) clearTimeout(errorMessage.hideTimeout);
        if (successMessage && successMessage.hideTimeout) clearTimeout(successMessage.hideTimeout);
        if (errorMessage) errorMessage.style.display = 'none';
        if (successMessage) successMessage.style.display = 'none';
    }

    if (numImagesSlider && numImagesValue) {
        numImagesSlider.addEventListener('input', () => {
            numImagesValue.textContent = numImagesSlider.value;
        });
        numImagesValue.textContent = numImagesSlider.value;
    }

    window.handleTabChange = async function(selectedModelDisplay) {
        if (activeModelDisplayName === selectedModelDisplay) {
            //console.log("DEBUG: Already on selected tab, no action needed.");
            return;
        }

        activeModelDisplayName = selectedModelDisplay;
        hideMessages();
        if (loadingSpinner) loadingSpinner.style.display = 'block';
        
        try {
            const response = await fetch('/update_session_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ active_tab: selectedModelDisplay })
            });
            const data = await response.json();
            if (data.status === 'success') {
                window.location.reload(); 
            } else {
                showMessage(errorMessage, data.message, 'warning');  // Usar warning para tabs suaves
            }
        } catch (error) {
            showMessage(errorMessage, '😊 Error al cambiar de modelo. Recarga la página si persiste.', 'warning');
            //console.error('Fetch error on tab change:', error);
        } finally {
            if (loadingSpinner) loadingSpinner.style.display = 'none';
        }
    };

    // CAMBIO CLAVE: toggleExpander usa classes para matching CSS
    window.toggleExpander = function(header) {
        header.classList.toggle('active');
        const content = header.nextElementSibling;
        if (content) {
            content.classList.toggle('active');
        }
        const arrow = header.querySelector('span:last-child');
        if (arrow) {
            arrow.textContent = header.classList.contains('active') ? '▲' : '▼';
        }
    };

    // Nuevo handler para el botón de mejorar prompt
    if (improvePromptButton) {
        improvePromptButton.addEventListener('click', async function(event) {
            event.preventDefault();
            const prompt = promptTextarea ? promptTextarea.value.trim() : '';
            if (!prompt) {
                showMessage(errorMessage, "⚠️ Escribe un prompt para mejorar.", 'warning');
                return;
            }
            hideMessages();
            disableAllButtons();
            improvePromptButton.textContent = '🧠 Mejorando...';
            try {
                const response = await fetch('/improve_prompt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: prompt })
                });
                const data = await response.json();
                if (data.status === 'success') {
                    promptTextarea.value = data.improved_prompt;
                    showMessage(successMessage, '🎉 Prompt mejorado y actualizado.', 'success');
                } else {
                    showMessage(errorMessage, data.message, 'warning');
                }
            } catch (error) {
                showMessage(errorMessage, '❌ Error de conexión al mejorar prompt. Inténtalo de nuevo.', 'warning');
                //console.error('Fetch error on improve_prompt:', error);
            } finally {
                improvePromptButton.disabled = false;
                improvePromptButton.textContent = '🧠 Mejorar Prompt con Gemini';
                enableAllButtons();
            }
        });
    }

    if (magicPromptButton) {
        magicPromptButton.addEventListener('click', async function(event) {
            event.preventDefault();
            hideMessages();
            disableAllButtons();
            magicPromptButton.textContent = '✨ Generando...';
            try {
                const response = await fetch('/generate_magic_prompt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await response.json();
                if (data.status === 'success') {
                    promptTextarea.value = data.magic_prompt;
                    showMessage(successMessage, '🎉 ¡Prompt mágico generado y listo para usar!', 'success');
                } else {
                    showMessage(errorMessage, data.message, 'warning');
                }
            } catch (error) {
                showMessage(errorMessage, '❌ Error de conexión al generar prompt mágico. Inténtalo de nuevo.', 'warning');
                //console.error('Fetch error on magic_prompt:', error);
            } finally {
                magicPromptButton.disabled = false;
                magicPromptButton.textContent = '✨ Prompt Mágico';
                enableAllButtons();
            }
        });
    }

    // Handler para clear results
    if (clearResultsButton) {
        clearResultsButton.addEventListener('click', async function(event) {
            event.preventDefault();
            hideMessages();
            disableAllButtons();
            try {
                const response = await fetch('/clear_session_results', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await response.json();
                if (data.status === 'success') {
                    window.location.reload();
                } else {
                    showMessage(errorMessage, 'No se pudo resetear. Recarga manualmente.', 'warning');
                }
            } catch (error) {
                showMessage(errorMessage, 'Error al resetear. Recarga la página.', 'warning');
                //console.error('Fetch error on clear:', error);
            } finally {
                enableAllButtons();
            }
        });
    }

    // Handler para generar imágenes (MEJORADO para timeouts y errores suaves)
    if (generateButton) {
        generateButton.addEventListener('click', async function(event) {
            event.preventDefault();
            const prompt = promptTextarea ? promptTextarea.value.trim() : '';
            if (!prompt) {
                showMessage(errorMessage, '😌 Escribe una descripción para empezar la magia.', 'warning');
                return;
            }
            hideMessages();
            disableAllButtons();
            generateButton.textContent = '🚀 Generando...';
            if (loadingSpinner) loadingSpinner.style.display = 'block';

            const formData = {
                prompt: prompt,
                num_images: numImagesSlider ? numImagesSlider.value : 4,
                seed: seedInput ? seedInput.value : -1,
                aspect_ratio: aspectRatioSelect ? aspectRatioSelect.value : '1:1',
                model_name_display: activeModelDisplayName,
                save_images: saveImagesCheckbox ? saveImagesCheckbox.checked : false,
                reference_images: currentReferenceImages
            };

            try {
                const response = await fetch('/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                const data = await response.json();
                if (data.status === 'success') {
                    renderGeneratedImages(data.images);
                    updateFooterSaveMessage(true);
                    if (data.images && data.images.length > 0 && saveImagesCheckbox && saveImagesCheckbox.checked) {
                        setTimeout(() => {
                            data.images.forEach((imgDataUrl, index) => {
                                downloadImage(imgDataUrl, index + 1);
                            });
                        }, 500);
                    }
                    showMessage(successMessage, `🎉 ¡${data.images.length} imágenes listas! Explora y crea más.`, 'success');
                    if (clearResultsButton) clearResultsButton.style.display = 'block';
                } else {
                    // Detectar timeouts/conexiones para tipo 'warning' y botón reintentar
                    let msgType = 'error';
                    if (data.message.includes('timeout') || data.message.includes('connection')) {
                        msgType = 'warning';
                    }
                    showMessage(errorMessage, data.message, msgType);
                }
            } catch (error) {
                showMessage(errorMessage, '🌐 Conexión pausada. Verifica internet y reintenta. 😊', 'warning');
                console.error('Fetch error on generate:', error);
            } finally {
                generateButton.textContent = '🚀 Generar Imágenes';
                if (loadingSpinner) loadingSpinner.style.display = 'none';
                enableAllButtons();
            }
        });
    }

    // Función para renderizar imágenes generadas
    function renderGeneratedImages(images) {
        if (!resultsContainer) return;
        resultsContainer.innerHTML = '';
        mainResultsTitle.textContent = `🎨 Tus Creaciones (${images.length} imágenes)`;
        images.forEach((imgDataUrl, index) => {
            const imgCard = document.createElement('div');
            imgCard.className = 'result-image-card';
            imgCard.innerHTML = `
                <img src="${imgDataUrl}" alt="Generated Image ${index + 1}" class="generated-image clickable-image">
                <div class="image-actions">
                    <button onclick="window.downloadImage('${imgDataUrl}', ${index + 1})" class="download-btn">💾 Descargar</button>
                </div>
            `;
            resultsContainer.appendChild(imgCard);

            // Event listener para modal
            const imgElement = imgCard.querySelector('.clickable-image');
            if (imgElement) {
                imgElement.addEventListener('click', () => window.openImageModal(imgDataUrl));
                imgElement.style.cursor = 'pointer';
            }
        });
    }

    // File uploader handler
    if (fileUploader) {
        fileUploader.addEventListener('change', async function(event) {
            const files = event.target.files;
            const maxReferences = 3;
            const availableSlots = maxReferences - currentReferenceImages.length;

            if (files.length === 0 || availableSlots <= 0) {
                fileUploader.value = '';
                return;
            }

            hideMessages();

            for (let i = 0; i < Math.min(files.length, availableSlots); i++) {
                const file = files[i];
                if (!file.type.startsWith('image/')) {
                    showMessage(errorMessage, `Archivo '${file.name}' no es una imagen.`, 'warning');
                    continue;
                }
                if (file.size > 10 * 1024 * 1024) { 
                    showMessage(errorMessage, `Imagen '${file.name}' es demasiado grande. Máx 10MB.`, 'warning');
                    continue;
                }

                const reader = new FileReader();
                reader.onload = async function(e) {
                    const imageDataUrl = e.target.result;
                    const status = await updateSessionReferenceImages(imageDataUrl, 'add');
                    if (status) {
                        renderReferenceImages();
                    }
                };
                reader.readAsDataURL(file);
            }
            fileUploader.value = '';
        });
    }

    async function updateSessionReferenceImages(imageDataUrl, action = 'add', index = -1) {
        const maxReferences = 3;
        if (action === 'add' && currentReferenceImages.length >= maxReferences) {
            showMessage(errorMessage, `Límite de ${maxReferences} imágenes de referencia alcanzado.`, 'warning');
            return false;
        }

        const url = action === 'add' ? '/add_reference_image' : `/remove_reference_image/${index}`;
        const method = 'POST';
        const body = action === 'add' ? JSON.stringify({ image: imageDataUrl }) : null;

        try {
            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: body
            });
            const data = await response.json();
            if (data.status !== 'success') {
                showMessage(errorMessage, data.message, 'warning');
                return false;
            } else {
                currentReferenceImages = data.reference_images;
                return true;
            }
        } catch (error) {
            showMessage(errorMessage, `Error al actualizar referencias: ${error.message}`, 'warning');
            //console.error('Fetch error:', error);
            return false;
        }
    }

    // CAMBIO CLAVE: addReferenceImage sin radios, directo a handleTabChange
    window.addReferenceImage = async function(imageDataUrl, modelToActivate = null, fromAddButton = false) {
        hideMessages();
        const maxReferences = 3;

        if (currentReferenceImages.length >= maxReferences) {
            showMessage(errorMessage, `Límite de ${maxReferences} imágenes alcanzado.`, 'warning');
            return;
        }
        
        const status = await updateSessionReferenceImages(imageDataUrl, 'add');
        if (status) { 
            if (modelToActivate && activeModelDisplayName !== modelToActivate) {
                window.handleTabChange(modelToActivate);
            } else {
                renderReferenceImages(); 
                if (fromAddButton) showMessage(successMessage, "Imagen añadida a referencias.", 'success');
            }
        }
    };

    window.removeReferenceImage = async function(index) {
        hideMessages();
        if (index >= 0 && index < currentReferenceImages.length) {
            const status = await updateSessionReferenceImages(null, 'remove', index);
            if (status) {
                renderReferenceImages();
                showMessage(successMessage, "Imagen de referencia eliminada.", 'success');
            }
        }
    };

    function renderReferenceImages() {
        if (!referenceImagesContainer) return;
        referenceImagesContainer.innerHTML = '';
        currentReferenceImages.forEach((img_data_url, index) => {
            const refCard = document.createElement('div');
            refCard.className = 'ref-image-card';
            refCard.innerHTML = `
                <img src="${img_data_url}" alt="Reference Image ${index + 1}" class="clickable-image">
                <button onclick="window.removeReferenceImage(${index})">✕</button>
            `;
            referenceImagesContainer.appendChild(refCard);

            // AGREGAR EVENT LISTENER PARA MODAL (EVITA ESCAPING EN INNERHTML)
            const imgElement = refCard.querySelector('.clickable-image');
            if (imgElement) {
                imgElement.addEventListener('click', () => window.openImageModal(img_data_url));
                imgElement.style.cursor = 'pointer'; // Indicador visual
            }
        });

        const maxReferences = 3;
        const availableSlots = maxReferences - currentReferenceImages.length;
        if (availableSlotsSpan) availableSlotsSpan.textContent = availableSlots;
        if (referenceUploaderSection) referenceUploaderSection.style.display = availableSlots > 0 ? 'block' : 'none';

        const modelType = window.MODEL_DISPLAY_NAMES_JS[activeModelDisplayName];
        const isRefModel = ["R2I", "GEM_PIX"].includes(modelType);
        const refSection = document.getElementById('reference-images-section');
        if (refSection) refSection.style.display = isRefModel ? 'block' : 'none';
    }

    window.togglePopover = function(button) {
        const popoverContent = button ? button.nextElementSibling : null;
        if (!popoverContent) return;

        document.querySelectorAll('.popover-content').forEach(content => {
            if (content !== popoverContent) {
                content.style.display = 'none';
            }
        });
        popoverContent.style.display = popoverContent.style.display === 'block' ? 'none' : 'block';
    };

    document.addEventListener('click', function(event) {
        document.querySelectorAll('.popover-container').forEach(container => {
            const button = container.querySelector('.popover-button');
            const content = container.querySelector('.popover-content');
            if (content && content.style.display === 'block' && !container.contains(event.target)) {
                content.style.display = 'none';
            }
        });
    });

    if (saveImagesCheckbox) {
        saveImagesCheckbox.addEventListener('change', async function() {
            hideMessages();
            try {
                await fetch('/update_session_settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ save_images: this.checked })
                });
                window.initialSessionState.save_images = this.checked;
                updateFooterSaveMessage(window.initialSessionState.results && window.initialSessionState.results.length > 0);
            } catch (error) {
                showMessage(errorMessage, 'Error al actualizar configuración de guardado.', 'warning');
                //console.error('Fetch error:', error);
            }
        });
    }

    function showInitialMessage() {
        if (resultsContainer) {
            resultsContainer.innerHTML = `
                <div class="text-center padding-4 opacity-60 initial-message">
                    <h3 class="font-light">👈 Empieza configurando tu idea en la barra lateral.</h3>
                </div>`;
        }
    }

    function updateFooterSaveMessage(hasCurrentResults = false) {
        const footer = document.querySelector('footer');
        if (!footer) return;
        let infoMessageDiv = footer.querySelector('.info-message');
        
        const currentSaveImages = window.initialSessionState.save_images;
        
        if (currentSaveImages && hasCurrentResults) {
            if (!infoMessageDiv) {
                infoMessageDiv = document.createElement('div');
                infoMessageDiv.className = 'info-message';
                const copyrightP = footer.querySelector('p');
                if (copyrightP) footer.insertBefore(infoMessageDiv, copyrightP);
                else footer.appendChild(infoMessageDiv);
            }
            infoMessageDiv.textContent = "💾 Las imágenes generadas se descargarán en tu dispositivo automáticamente.";
            infoMessageDiv.style.display = 'block';
        } else {
            if (infoMessageDiv) {
                infoMessageDiv.style.display = 'none';
            }
        }
    }

    function initializeUI() {
        renderReferenceImages();
        
        if (window.initialSessionState.results && window.initialSessionState.results.length > 0) {
            renderGeneratedImages(window.initialSessionState.results);
            updateFooterSaveMessage(true); 

            // Auto-descarga si save_images es true al inicializar
            if (window.initialSessionState.save_images) {
                setTimeout(() => {
                    window.initialSessionState.results.forEach((imgDataUrl, index) => {
                        downloadImage(imgDataUrl, index + 1);
                    });
                }, 500);
            }

            if (clearResultsButton) clearResultsButton.style.display = 'block';
        } else {
            showInitialMessage();  // Muestra mensaje por defecto sin generar nada
            if (clearResultsButton) clearResultsButton.style.display = 'none';
        }

        // Actualizar activeModelDisplayName desde DOM actual
        activeModelDisplayName = getActiveModelName();
    }

    // Función para descargar imagen (client-side)
    window.downloadImage = function(dataUrl, index) {
        const link = document.createElement('a');
        link.href = dataUrl;
        link.download = `imagen_generada_${index}_${new Date().getTime()}.png`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    initializeUI();
});