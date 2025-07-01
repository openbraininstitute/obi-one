from app.errors import ApiError, ApiErrorCode

def get_validation_config_page_content() -> str:
    """
    Returns the HTML content for the validation configuration webpage.
    """
    return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Configure Validations</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
                .container { max-width: 900px; margin: 0 auto; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                h1, h2 { color: #0056b3; }
                select, input[type="text"], button { padding: 8px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ddd; }
                button { background-color: #007bff; color: white; cursor: pointer; border: none; }
                button:hover { background-color: #0056b3; }
                .add-button { background-color: #28a745; }
                .delete-button { background-color: #dc3545; }
                .list-item { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px dashed #eee; }
                .list-item:last-child { border-bottom: none; }
                .validation-category { border: 1px solid #eee; padding: 10px; margin-bottom: 15px; border-radius: 5px; background-color: #fafafa; }
                .section { margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
                #json-output { white-space: pre-wrap; background-color: #e9e9e9; padding: 15px; border-radius: 5px; overflow-x: auto; max-height: 400px; }
                .message { padding: 10px; margin-top: 15px; border-radius: 5px; }
                .message.success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
                .message.error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Validation Configuration Editor</h1>
                <div class="section">
                    <h2>Select Entity Type</h2>
                    <select id="entity-type-select"></select>
                    <button id="add-new-entity-type" class="add-button">Add New Entity Type</button>
                </div>
                <div id="entity-details" class="section" style="display: none;">
                    <h2>Current Entity: <span id="current-entity-name"></span></h2>
                    <div class="validation-category">
                        <h3>Must Pass To Upload</h3>
                        <div id="must-pass-to-upload-list"></div>
                        <select id="add-select-must-pass-to-upload"></select>
                        <button class="add-button" onclick="addValidation('must_pass_to_upload')">Add Selected</button>
                        <select id="delete-select-must-pass-to-upload"></select>
                        <button class="delete-button" onclick="deleteValidation('must_pass_to_upload')">Delete Selected</button>
                    </div>
                    <div class="validation-category">
                        <h3>Must Run Upon Upload</h3>
                        <div id="must-run-upon-upload-list"></div>
                        <select id="add-select-must-run-upon-upload"></select>
                        <button class="add-button" onclick="addValidation('must_run_upon_upload')">Add Selected</button>
                        <select id="delete-select-must-run-upon-upload"></select>
                        <button class="delete-button" onclick="deleteValidation('must_run_upon_upload')">Delete Selected</button>
                    </div>
                    <div class="validation-category">
                        <h3>Must Pass To Simulate</h3>
                        <div id="must-pass-to-simulate-list"></div>
                        <select id="add-select-must-pass-to-simulate"></select>
                        <button class="add-button" onclick="addValidation('must_pass_to_simulate')">Add Selected</button>
                        <select id="delete-select-must-pass-to-simulate"></select>
                        <button class="delete-button" onclick="deleteValidation('must_pass_to_simulate')">Delete Selected</button>
                    </div>
                    <button class="delete-button" onclick="deleteEntity()">Delete Current Entity Type</button>
                    <button onclick="saveConfig()">Save Changes</button>
                    <div id="message" class="message" style="display: none;"></div>
                </div>
                <div class="section">
                    <h2>Raw JSON Configuration</h2>
                    <pre id="json-output"></pre>
                </div>
            </div>
            <script>
                let config = {"entity_types": {}}; // In-memory representation of the config
                let currentEntityType = null;
                let availableEntityTypes = [];
                let availableValidationFunctions = [];
                const BASE_URL = window.location.origin;
                const API_PREFIX = "/declared";
                document.addEventListener('DOMContentLoaded', init);
                async function init() {
                    await fetchAvailableTypesAndFunctions();
                    await fetchConfig();
                    renderEntityTypeSelect();
                }
                async function fetchAvailableTypesAndFunctions() {
                    try {
                        const typesResponse = await fetch(BASE_URL + API_PREFIX + '/available_entity_types');
                        const typesData = await typesResponse.json();
                        availableEntityTypes = typesData.entity_types;
                        const functionsResponse = await fetch(BASE_URL + API_PREFIX + '/available_validation_functions');
                        const functionsData = await functionsResponse.json();
                        availableValidationFunctions = functionsData.validation_functions;
                    } catch (error) {
                        console.error('Error fetching available types or functions:', error);
                        showMessage('Error fetching available types or functions. See console for details.', 'error');
                    }
                }
                async function fetchConfig() {
                    try {
                        const response = await fetch(BASE_URL + API_PREFIX + '/validation_config');
                        if (!response.ok) {
                            throw new Error('HTTP error! status: ' + response.status);
                        }
                        config = await response.json();
                        displayJsonOutput();
                    } catch (error) {
                        console.error('Error fetching configuration:', error);
                        showMessage('Error fetching configuration. See console for details.', 'error');
                        config = {"entity_types": {}};
                    }
                }
                function renderEntityTypeSelect() {
                    const select = document.getElementById('entity-type-select');
                    select.innerHTML = '';
                    const currentEntities = Object.keys(config.entity_types);
                    currentEntities.forEach(type => {
                        const option = document.createElement('option');
                        option.value = type;
                        option.textContent = type;
                        select.appendChild(option);
                    });
                    if (currentEntities.length > 0) {
                        const separator = document.createElement('option');
                        separator.textContent = '--- New Types ---';
                        separator.disabled = true;
                        select.appendChild(separator);
                    }
                    availableEntityTypes.forEach(type => {
                        if (!currentEntities.includes(type)) {
                            const option = document.createElement('option');
                            option.value = type;
                            option.textContent = type;
                            select.appendChild(option);
                        }
                    });
                    select.onchange = (event) => selectEntityType(event.target.value);
                    if (currentEntities.length > 0) {
                        selectEntityType(currentEntities[0]);
                    } else if (availableEntityTypes.length > 0) {
                        selectEntityType(availableEntityTypes[0]);
                    } else {
                        document.getElementById('entity-details').style.display = 'none';
                    }
                }
                function selectEntityType(type) {
                    currentEntityType = type;
                    document.getElementById('current-entity-name').textContent = type;
                    document.getElementById('entity-details').style.display = 'block';
                    if (!config.entity_types[type]) {
                        config.entity_types[type] = {
                            "must_pass_to_upload": [],
                            "must_run_upon_upload": [],
                            "must_pass_to_simulate": []
                        };
                    }
                    renderValidationLists();
                }
                document.getElementById('add-new-entity-type').onclick = () => {
                    const newEntityType = document.getElementById('entity-type-select').value;
                    if (newEntityType && !Object.keys(config.entity_types).includes(newEntityType)) {
                        selectEntityType(newEntityType);
                        renderEntityTypeSelect();
                        showMessage('Added new entity type: ' + newEntityType, 'success');
                    } else if (Object.keys(config.entity_types).includes(newEntityType)) {
                        showMessage('Entity type "' + newEntityType + '" already exists.', 'error');
                        selectEntityType(newEntityType);
                    } else {
                        showMessage('Please select an entity type to add.', 'error');
                    }
                };
                function renderValidationLists() {
                    if (!currentEntityType || !config.entity_types[currentEntityType]) return;
                    const lists = {
                        'must_pass_to_upload': document.getElementById('must-pass-to-upload-list'),
                        'must_run_upon_upload': document.getElementById('must-run-upon-upload-list'),
                        'must_pass_to_simulate': document.getElementById('must-pass-to-simulate-list')
                    };
                    const addSelects = {
                        'must_pass_to_upload': document.getElementById('add-select-must-pass-to-upload'),
                        'must_run_upon_upload': document.getElementById('add-select-must-run-upon-upload'),
                        'must_pass_to_simulate': document.getElementById('add-select-must-pass-to-simulate')
                    };
                    const deleteSelects = {
                        'must_pass_to_upload': document.getElementById('delete-select-must-pass-to-upload'),
                        'must_run_upon_upload': document.getElementById('delete-select-must-run-upon-upload'),
                        'must_pass_to_simulate': document.getElementById('delete-select-must-pass-to-simulate')
                    };
                    Object.keys(lists).forEach(category => {
                        lists[category].innerHTML = '';
                        addSelects[category].innerHTML = '';
                        deleteSelects[category].innerHTML = '';
                        availableValidationFunctions.forEach(func => {
                            if (func.entity === currentEntityType && !config.entity_types[currentEntityType][category].includes(func.name)) {
                                const option = document.createElement('option');
                                option.value = func.name;
                                option.textContent = func.name;
                                addSelects[category].appendChild(option);
                            }
                        });
                        if (addSelects[category].options.length === 0) {
                            const option = document.createElement('option');
                            option.value = "";
                            option.textContent = "No functions to add";
                            option.disabled = true;
                            option.selected = true;
                            addSelects[category].appendChild(option);
                        }
                        config.entity_types[currentEntityType][category].forEach(func => {
                            const listItem = document.createElement('div');
                            listItem.className = 'list-item';
                            listItem.textContent = func;
                            lists[category].appendChild(listItem);
                            const option = document.createElement('option');
                            option.value = func;
                            option.textContent = func;
                            deleteSelects[category].appendChild(option);
                        });
                        if (deleteSelects[category].options.length === 0) {
                            const option = document.createElement('option');
                            option.value = "";
                            option.textContent = "No functions to delete";
                            option.disabled = true;
                            option.selected = true;
                            deleteSelects[category].appendChild(option);
                        }
                    });
                    displayJsonOutput();
                }
                function addValidation(category) {
                    const selectId = 'add-select-' + category.replace(/_/g, '-');
                    const funcName = document.getElementById(selectId).value;
                    if (funcName && currentEntityType) {
                        if (!config.entity_types[currentEntityType][category].includes(funcName)) {
                            config.entity_types[currentEntityType][category].push(funcName);
                            renderValidationLists();
                            showMessage('Added "' + funcName + '" to ' + category + ' for ' + currentEntityType, 'success');
                        } else {
                            showMessage('"' + funcName + '" already exists in ' + category + ' for ' + currentEntityType, 'error');
                        }
                    } else {
                        showMessage('Please select a function to add.', 'error');
                    }
                }
                function deleteValidation(category) {
                    const selectId = 'delete-select-' + category.replace(/_/g, '-');
                    const selectElement = document.getElementById(selectId);
                    const funcName = selectElement.value;
                    if (funcName && currentEntityType) {
                        config.entity_types[currentEntityType][category] = config.entity_types[currentEntityType][category].filter(f => f !== funcName);
                        renderValidationLists();
                        showMessage('Deleted "' + funcName + '" from ' + category + ' for ' + currentEntityType, 'success');
                    } else {
                        showMessage('Please select a function to delete.', 'error');
                    }
                }
                function deleteEntity() {
                    if (currentEntityType && confirm('Are you sure you want to delete the configuration for ' + currentEntityType + '?')) {
                        delete config.entity_types[currentEntityType];
                        currentEntityType = null;
                        renderEntityTypeSelect();
                        document.getElementById('entity-details').style.display = 'none';
                        showMessage('Deleted entity type: ' + currentEntityType, 'success');
                        saveConfig();
                    }
                }
                async function saveConfig() {
                    try {
                        const response = await fetch(BASE_URL + API_PREFIX + '/validation_config', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(config)
                        });
                        if (!response.ok) {
                            const errorData = await response.json();
                            throw new Error('HTTP error! status: ' + response.status + ' - ' + (errorData.message || response.statusText));
                        }
                        const result = await response.json();
                        showMessage(result.message, 'success');
                        displayJsonOutput();
                    } catch (error) {
                        console.error('Error saving configuration:', error);
                        showMessage('Error saving configuration: ' + error.message + '. See console for details.', 'error');
                    }
                }
                function displayJsonOutput() {
                    document.getElementById('json-output').textContent = JSON.stringify(config, null, 2);
                }
                let messageTimeout;
                function showMessage(msg, type) {
                    const messageDiv = document.getElementById('message');
                    messageDiv.textContent = msg;
                    messageDiv.className = 'message ' + type;
                    messageDiv.style.display = 'block';
                    clearTimeout(messageTimeout);
                    messageTimeout = setTimeout(() => {
                        messageDiv.style.display = 'none';
                    }, 5000);
                }
            </script>
        </body>
        </html>
    """
