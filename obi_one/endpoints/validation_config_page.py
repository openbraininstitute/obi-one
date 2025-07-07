# validation_config_page.py
from app.errors import ApiError, ApiErrorCode
# Import EntityType and ValidationQueue from the correct location
from obi_one.scientific.validations.validation_functions import EntityType, ValidationQueue


def get_validation_config_page_content() -> str:
    """
    Returns the HTML content for the validation configuration webpage.
    """
    # Escaping curly braces {{}} for f-string and updating JS logic for new endpoints
    return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Configure Validations</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }}
                .container {{ max-width: 900px; margin: 0 auto; background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                h1, h2 {{ color: #0056b3; }}
                select, input[type="text"], button {{ padding: 8px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #ddd; }}
                button {{ background-color: #007bff; color: white; cursor: pointer; border: none; }}
                button:hover {{ background-color: #0056b3; }}
                .add-button {{ background-color: #28a745; }}
                .delete-button {{ background-color: #dc3545; }}
                .list-item {{ display: flex; justify-content: space-between; align-items: center; background-color: #e9e9e9; padding: 8px; margin-bottom: 5px; border-radius: 4px; }}
                .message {{ padding: 10px; margin-bottom: 10px; border-radius: 4px; display: none; }}
                .message.success {{ background-color: #d4edda; color: #155724; border-color: #c3e6cb; }}
                .message.error {{ background-color: #f8d7da; color: #721c24; border-color: #f5c6cb; }}
                pre {{ background-color: #eee; padding: 10px; border-radius: 4px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Configure Entity Validations</h1>

                <div id="message" class="message"></div>

                <h2>Add New Validation Rule</h2>
                <div>
                    <label for="entityTypeSelect">Select Entity Type:</label>
                    <select id="entityTypeSelect">
                        <option value="">--Select Entity Type--</option>
                        {''.join(f'<option value="{entity_type.value}">{entity_type.value}</option>' for entity_type in EntityType)}
                    </select>
                </div>
                <div>
                    <label for="validationFunctionSelect">Select Validation Function:</label>
                    <select id="validationFunctionSelect" disabled>
                        <option value="">--Select Validation Function--</option>
                    </select>
                </div>
                <div>
                    <label for="validationStatus">Validation Status:</label>
                    <select id="validationStatus">
                        <option value="">--Select Status--</option>
                        <option value="{ValidationQueue.MUST_PASS_TO_UPLOAD}">Must Pass To Upload</option>
                        <option value="{ValidationQueue.MUST_RUN_UPON_UPLOAD}">Must Run Upon Upload</option>
                        <option value="{ValidationQueue.MUST_PASS_TO_SIMULATE}">Must Pass To Simulate</option>
                    </select>
                </div>
                <button class="add-button" onclick="addValidationRule()">Add Rule</button>

                <h2>Current Configuration</h2>
                <div id="config-list">
                    <p>Loading configuration...</p>
                </div>
                <pre id="json-raw-output" style="display:none;"></pre>
            </div>

            <script>
                const entityTypeSelect = document.getElementById('entityTypeSelect');
                const validationFunctionSelect = document.getElementById('validationFunctionSelect');
                const validationStatusSelect = document.getElementById('validationStatus');
                const configListDiv = document.getElementById('config-list');
                const jsonRawOutputPre = document.getElementById('json-raw-output');
                const BASE_URL = window.location.origin;
                const API_PREFIX = "/declared"; // Your API prefix

                entityTypeSelect.addEventListener('change', fetchValidationFunctions);

                async function fetchValidationFunctions() {{
                    const entityType = entityTypeSelect.value;
                    validationFunctionSelect.innerHTML = '<option value="">--Select Validation Function--</option>';
                    validationFunctionSelect.disabled = true;

                    if (!entityType) {{
                        return;
                    }}

                    try {{
                        const response = await fetch(`${{BASE_URL}}${{API_PREFIX}}/get-validation-functions/${{entityType}}`);
                        if (!response.ok) {{
                            const errorData = await response.json();
                            throw new Error('HTTP error! status: ' + response.status + ' - ' + (errorData.message || response.statusText));
                        }}
                        const functions = await response.json();
                        functions.forEach(funcName => {{
                            const option = document.createElement('option');
                            option.value = funcName;
                            option.textContent = funcName;
                            validationFunctionSelect.appendChild(option);
                        }});
                        validationFunctionSelect.disabled = false;
                    }} catch (error) {{
                        console.error('Error fetching validation functions:', error);
                        showMessage('Error fetching validation functions: ' + error.message, 'error');
                    }}
                }}

                async function addValidationRule() {{
                    const entityType = entityTypeSelect.value;
                    const validationFunction = validationFunctionSelect.value;
                    const status = validationStatusSelect.value;

                    if (!entityType || !validationFunction || !status) {{
                        showMessage('Please select an entity type, a validation function, and a status.', 'error');
                        return;
                    }}

                    const config = {{
                        entity_type: entityType,
                        validation_function: validationFunction,
                        status: status
                    }};

                    try {{
                        const response = await fetch(`${{BASE_URL}}${{API_PREFIX}}/save-validation-config`, {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json'
                            }},
                            body: JSON.stringify(config)
                        }});
                        if (!response.ok) {{
                            const errorData = await response.json();
                            throw new Error('HTTP error! status: ' + response.status + ' - ' + (errorData.message || response.statusText));
                        }}
                        const result = await response.json();
                        showMessage(result.message, 'success');
                        displayConfiguredRules(); // Refresh the displayed config
                    }} catch (error) {{
                        console.error('Error saving configuration:', error);
                        showMessage('Error saving configuration: ' + error.message + '. See console for details.', 'error');
                    }}
                }}

                async function deleteValidationRule(entityType, validationFunction, status) {{
                    if (!confirm(`Are you sure you want to delete the rule "${{validationFunction}}" for ${{entityType}} under ${{status}}?`)) {{
                        return;
                    }}

                    const ruleData = {{
                        entity_type: entityType,
                        validation_function: validationFunction,
                        status: status
                    }};
                    try {{
                        const response = await fetch(`${{BASE_URL}}${{API_PREFIX}}/delete-validation-rule`, {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json'
                            }},
                            body: JSON.stringify(ruleData)
                        }});
                        if (!response.ok) {{
                            const errorData = await response.json();
                            throw new Error('HTTP error! status: ' + response.status + ' - ' + (errorData.message || response.statusText));
                        }}
                        const result = await response.json();
                        showMessage(result.message, 'success');
                        displayConfiguredRules(); // Refresh the displayed config
                    }} catch (error) {{
                        console.error('Error deleting configuration:', error);
                        showMessage('Error deleting configuration: ' + error.message + '. See console for details.', 'error');
                    }}
                }}

                async function displayConfiguredRules() {{
                    configListDiv.innerHTML = '<p>Loading configuration...</p>';
                    jsonRawOutputPre.textContent = 'Loading...';

                    try {{
                        const response = await fetch(`${{BASE_URL}}${{API_PREFIX}}/get-all-entity-validation-configs`);
                        if (!response.ok) {{
                            const errorData = await response.json();
                            throw new Error('HTTP error! status: ' + response.status + ' - ' + (errorData.message || response.statusText));
                        }}
                        const allConfigs = await response.json();
                        jsonRawOutputPre.textContent = JSON.stringify(allConfigs, null, 2);

                        let html = '';
                        if (Object.keys(allConfigs).length === 0) {{
                            html = '<p>No validation rules configured yet.</p>';
                        }} else {{
                            for (const entityType in allConfigs) {{
                                html += `<h3>${{entityType}}</h3>`;
                                const entityConfig = allConfigs[entityType];
                                if (Object.keys(entityConfig).length === 0) {{
                                    html += '<p>No rules defined for this entity type.</p>';
                                }} else {{
                                    for (const status in entityConfig) {{
                                        html += `<h4>Status: ${{status}}</h4>`;
                                        if (entityConfig[status] && entityConfig[status].length > 0) {{
                                            html += '<ul>';
                                            entityConfig[status].forEach(funcName => {{
                                                html += `<li class="list-item"><span>${{funcName}}</span> <button class="delete-button" onclick="deleteValidationRule('${{entityType}}', '${{funcName}}', '${{status}}')">Delete</button></li>`;
                                            }});
                                            html += '</ul>';
                                        }} else {{
                                            html += '<p>No functions defined for this status.</p>';
                                        }}
                                    }}
                                }}
                            }}
                        }}
                        configListDiv.innerHTML = html;

                    }} catch (error) {{
                        console.error('Error displaying configuration:', error);
                        showMessage('Error displaying configuration: ' + error.message, 'error');
                        configListDiv.innerHTML = '<p>Error loading configuration.</p>';
                    }}
                }}

                let messageTimeout;
                function showMessage(msg, type) {{
                    const messageDiv = document.getElementById('message');
                    messageDiv.textContent = msg;
                    messageDiv.className = 'message ' + type;
                    messageDiv.style.display = 'block';
                    clearTimeout(messageTimeout);
                    messageTimeout = setTimeout(() => {{
                        messageDiv.style.display = 'none';
                    }}, 5000);
                }}

                // Initial display of configuration when the page loads
                document.addEventListener('DOMContentLoaded', () => {{
                    displayConfiguredRules();
                }});
            </script>
        </body>
        </html>
    """
