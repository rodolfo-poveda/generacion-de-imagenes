// static/js/app.js - VERSIÓN CON MODAL FUNCIONAL (EVENT LISTENERS PARA CLICK EN IMGS)

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

    // MODAL ELEMENTS
    const imageModal = document.getElementById('image-modal');
    const modalImage = document.getElementById('modal-image');

    if (!generateButton || !resultsContainer) {
        console.error("Error: Elemento(s) crítico(s) no encontrado(s) en el DOM. La aplicación no puede funcionar correctamente.");
        return;
    }

    let currentReferenceImages = window.initialSessionState.reference_images_list || [];
    let activeModelDisplayName = window.initialSessionState.active_tab;

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

    // Cerrar modal con tecla ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && imageModal && imageModal.style.display === 'block') {
            window.closeImageModal();
        }
    });

    function showMessage(element, message, type = 'error') {
        if (!element) return;
        element.textContent = message;
        element.style.display = 'block';
        element.className = `${type}-message`;
        clearTimeout(element.hideTimeout);
        element.hideTimeout = setTimeout(() => { element.style.display = 'none'; }, 8000);
    }

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
            console.log("DEBUG: Already on selected tab, no action needed.");
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
                showMessage(errorMessage, data.message);
            }
        } catch (error) {
            showMessage(errorMessage, 'Error al cambiar de modelo. Inténtalo de nuevo.');
            console.error('Fetch error on tab change:', error);
        } finally {
            if (loadingSpinner) loadingSpinner.style.display = 'none';
        }
    };

    window.toggleExpander = function(header) {
        header.classList.toggle('active');
        const content = header.nextElementSibling;
        if (content) {
            if (content.style.display === 'block') {
                content.style.display = 'none';
            } else {
                content.style.display = 'block';
            }
        }
    };

    generateButton.addEventListener('click', async function(event) {
        event.preventDefault();

        hideMessages();
        // Mostrar el spinner en el área principal
        if (loadingSpinner) loadingSpinner.style.display = 'block';
        resultsContainer.innerHTML = ''; // Limpiar el área de resultados
        if (mainResultsTitle) mainResultsTitle.textContent = '🎨 Tus Creaciones';
        if (clearResultsButton) clearResultsButton.style.display = 'none';

        // Scroll suave a resultados en móviles después de iniciar generación
        if (window.innerWidth < 768) {
            const resultsTitle = document.getElementById('main-results-title');
            if (resultsTitle) {
                resultsTitle.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }        

        const prompt = promptTextarea ? promptTextarea.value : '';
        const num_images = numImagesSlider ? numImagesSlider.value : 4; 
        const seed = seedInput ? seedInput.value : -1;
        const aspect_ratio = aspectRatioSelect ? aspectRatioSelect.value : '1:1';
        const selectedRadio = document.querySelector('input[name="model_name_display"]:checked');
        const model_name_display = selectedRadio ? selectedRadio.value : '';
        const save_images = saveImagesCheckbox ? saveImagesCheckbox.checked : false;

        if (!prompt.trim()) {
            showMessage(errorMessage, "⚠️ Por favor, escribe una descripción.");
            if (loadingSpinner) loadingSpinner.style.display = 'none';
            showInitialMessage();
            return;
        }

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: prompt,
                    num_images: num_images,
                    seed: seed,
                    aspect_ratio: aspect_ratio,
                    model_name_display: model_name_display,
                    save_images: save_images,
                    reference_images: currentReferenceImages
                }),
            });

            console.log("--- DEBUG (CLIENT): Raw response status and text from /generate endpoint ---");
            console.log("  HTTP Status Code:", response.status);
            const responseText = await response.text(); 
            console.log("  Raw Response Body (first 500 chars):", responseText.substring(0, 500) + "...");
            
            let result;
            try {
                result = JSON.parse(responseText); 
            } catch (jsonError) {
                console.error("--- DEBUG (CLIENT): JSON parsing error:", jsonError);
                console.error("--- DEBUG (CLIENT): Full raw response body:", responseText); 
                throw new Error("Failed to parse JSON response from server."); 
            }

            console.log("--- DEBUG (CLIENT): Parsed JSON result ---");
            console.log("  Status from Flask:", result.status);
            console.log("  Message from Flask:", result.message);
            if (result.images) {
                console.log("  Number of images received from Flask:", result.images.length);
                if (result.images.length > 0) {
                    console.log("  First image data (partial):", result.images[0].substring(0, 100) + "...");
                }
            }

            if (response.ok && result.status === 'success') {
                window.initialSessionState.results = result.images; 
                renderGeneratedImages(result.images); 
                showMessage(successMessage, `🎉 ¡${result.images.length} imagen(es) generada(s)!`, 'success');
                window.initialSessionState.save_images = save_images; 
                updateFooterSaveMessage(result.images.length > 0);
            } else {
                showMessage(errorMessage, result.message || 'Error desconocido al generar imágenes.');
                showInitialMessage();
                updateFooterSaveMessage(false);
            }
        } catch (error) {
            console.error("--- DEBUG (CLIENT): Fetch error on /generate:", error);
            showMessage(errorMessage, 'Error de conexión con el servidor. Inténtalo de nuevo.');
            showInitialMessage();
            updateFooterSaveMessage(false);
        } finally {
            // Ocultar el spinner al finalizar
            if (loadingSpinner) loadingSpinner.style.display = 'none';
        }
    });

    function renderGeneratedImages(images) {
        if (!resultsContainer) return;
        resultsContainer.innerHTML = '';
        if (mainResultsTitle) mainResultsTitle.textContent = '🎨 Tus Creaciones';

        if (images.length === 0) {
            console.warn("--- DEBUG (CLIENT): renderGeneratedImages: No images to render, showing initial message. ---");
            showInitialMessage();
            if (clearResultsButton) clearResultsButton.style.display = 'none';
            return;
        }
        console.log("--- DEBUG (CLIENT): renderGeneratedImages: Rendering", images.length, "images. ---");

        resultsContainer.classList.remove('cols-1', 'cols-2', 'cols-3', 'cols-4');
        if (images.length === 1) {
            resultsContainer.classList.add('cols-1');
        } else if (images.length === 2) {
            resultsContainer.classList.add('cols-2');
        } else if (images.length === 3) {
            resultsContainer.classList.add('cols-3');
        } else if (images.length === 4) {
            resultsContainer.classList.add('cols-4');
        } else {
            resultsContainer.classList.add('cols-4'); 
        }

        images.forEach((img_data_url, index) => {
            const card = document.createElement('div');
            card.className = 'result-card';

            const modelType = window.MODEL_DISPLAY_NAMES_JS[activeModelDisplayName];
            const isRefModel = ["R2I", "GEM_PIX"].includes(modelType);

            let actionButtonsHtml;
            if (isRefModel) {
                actionButtonsHtml = `
                    <button onclick="window.addReferenceImage('${img_data_url}', null, true)">➕ Añadir</button>
                `;
            } else {
                actionButtonsHtml = `
                    <div class="popover-container">
                        <button class="popover-button" onclick="window.togglePopover(this)">🎨 Usar en...</button>
                        <div class="popover-content">
                            <button onclick="window.addReferenceImage('${img_data_url}', '${window.MODEL_NAMES_LIST_JS[2]}')">${window.MODEL_NAMES_LIST_JS[2]}</button>
                            <button onclick="window.addReferenceImage('${img_data_url}', '${window.MODEL_NAMES_LIST_JS[3]}')">${window.MODEL_NAMES_LIST_JS[3]}</button>
                        </div>
                    </div>
                `;
            }

            if (!img_data_url || !img_data_url.startsWith('data:image/')) {
                console.error(`--- DEBUG (CLIENT): Image ${index} has invalid data URL:`, img_data_url ? img_data_url.substring(0, 100) + "..." : "empty/null");
                card.innerHTML = `<div style="color:red; text-align:center; padding:1rem;">Error: Imagen generada inválida o corrupta.</div>`;
            } else {
                 card.innerHTML = `
                    <img src="${img_data_url}" alt="Generated Image ${index + 1}" class="clickable-image">
                    <div class="action-row">
                        <div class="action-col">
                            ${actionButtonsHtml}
                        </div>
                        <div class="download-col">
                            <a href="${img_data_url}" download="generada_${index + 1}.png" class="download-button">📥</a>
                        </div>
                    </div>
                `;
                // AGREGAR EVENT LISTENER PARA MODAL (EVITA ESCAPING EN INNERHTML)
                const imgElement = card.querySelector('.clickable-image');
                if (imgElement) {
                    imgElement.addEventListener('click', () => window.openImageModal(img_data_url));
                    imgElement.style.cursor = 'pointer'; // Indicador visual
                }
            }
           
            resultsContainer.appendChild(card);
        });

        if (clearResultsButton) clearResultsButton.style.display = 'block';
    }

    if (clearResultsButton) {
        clearResultsButton.addEventListener('click', async function() {
            hideMessages();
            try {
                const response = await fetch('/clear_session_results', { method: 'POST' });
                const data = await response.json();
                if (data.status === 'success') {
                    window.initialSessionState.results = []; 
                    showInitialMessage();
                    updateFooterSaveMessage(false);
                    if (clearResultsButton) clearResultsButton.style.display = 'none';
                    showMessage(successMessage, "Resultados limpiados.", 'success');
                } else {
                    showMessage(errorMessage, data.message || "Error al limpiar resultados en el servidor.");
                }
            } catch (error) {
                console.error("Error calling /clear_session_results:", error);
                showMessage(errorMessage, "Error de conexión al limpiar resultados.");
            }
        });
    }

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
                    showMessage(errorMessage, `Archivo '${file.name}' no es una imagen.`);
                    continue;
                }
                if (file.size > 10 * 1024 * 1024) { 
                    showMessage(errorMessage, `Imagen '${file.name}' es demasiado grande. Máx 10MB.`);
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
            showMessage(errorMessage, `Límite de ${maxReferences} imágenes de referencia alcanzado.`);
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
                showMessage(errorMessage, data.message);
                return false;
            } else {
                currentReferenceImages = data.reference_images;
                return true;
            }
        } catch (error) {
            showMessage(errorMessage, `Error al actualizar referencias: ${error.message}`);
            console.error('Fetch error:', error);
            return false;
        }
    }

    window.addReferenceImage = async function(imageDataUrl, modelToActivate = null, fromAddButton = false) {
        hideMessages();
        const maxReferences = 3;

        if (currentReferenceImages.length >= maxReferences) {
            showMessage(errorMessage, `Límite de ${maxReferences} imágenes alcanzado.`);
            return;
        }
        
        const status = await updateSessionReferenceImages(imageDataUrl, 'add');
        if (status) { 
            if (modelToActivate && activeModelDisplayName !== modelToActivate) {
                const radioToActivate = document.querySelector(`input[name="model_name_display"][value="${modelToActivate}"]`);
                if (radioToActivate) {
                    radioToActivate.checked = true;
                    window.handleTabChange(modelToActivate);
                }
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
                <button onclick="window.removeReferenceImage(${index})">🗑️</button>
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
                showMessage(errorMessage, 'Error al actualizar configuración de guardado.');
                console.error('Fetch error:', error);
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
            infoMessageDiv.textContent = "💾 Las imágenes se han guardado en la carpeta `output/` del servidor.";
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
        } else {
            showInitialMessage();
        }
    }

    initializeUI();
});