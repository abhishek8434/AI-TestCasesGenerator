// URL testing functionality
async function testUrl() {
    const urlInput = document.getElementById('siteUrl');
    const resultSpan = document.getElementById('urlTestResult');
    const url = urlInput.value.trim();

    // Clear previous result
    resultSpan.textContent = '';
    resultSpan.className = '';

    try {
        // Basic URL validation
        new URL(url);

        // Try to fetch the URL
        resultSpan.textContent = 'Testing URL...';
        const response = await fetch('/api/test-url', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url: url })
        });

        if (response.ok) {
            resultSpan.textContent = '✓ URL is accessible';
            resultSpan.className = 'text-success';
        } else {
            resultSpan.textContent = '✗ URL is not accessible';
            resultSpan.className = 'text-danger';
        }
    } catch (error) {
        resultSpan.textContent = '✗ Invalid URL format';
        resultSpan.className = 'text-danger';
    }
}

// Function to handle source type change
function handleSourceTypeChange() {
    console.log('=== handleSourceTypeChange called ===');
    const sourceType = document.getElementById('sourceType').value;
    console.log('Source type changed to:', sourceType);
    
    // Get all field containers
    const jiraFields = document.getElementById('jiraFields');
    const azureFields = document.getElementById('azureFields');
    const imageFields = document.getElementById('imageFields');
    const urlFields = document.getElementById('urlFields');
    const itemIdField = document.getElementById('itemIdField');
    // Get the test case types section by ID
    const testCaseTypesSection = document.getElementById('testCaseTypesSection');
    
    // Hide all fields first
    [jiraFields, azureFields, imageFields, urlFields, itemIdField, testCaseTypesSection].forEach(field => {
        if (field) {
            field.style.display = 'none';
            console.log('Hiding field:', field.id || field.className || 'testCaseTypesSection');
        }
    });
    
    console.log('Found elements:', {
        jiraFields: !!jiraFields,
        azureFields: !!azureFields,
        imageFields: !!imageFields,
        urlFields: !!urlFields,
        itemIdField: !!itemIdField,
        testCaseTypesSection: !!testCaseTypesSection
    });
    
    // Show relevant fields based on source type
    switch (sourceType) {
        case 'jira':
            jiraFields.style.display = 'block';
            itemIdField.style.display = 'block';
            testCaseTypesSection.style.display = 'block';
            break;
        case 'azure':
            azureFields.style.display = 'block';
            itemIdField.style.display = 'block';
            testCaseTypesSection.style.display = 'block';
            break;
        case 'image':
            imageFields.style.display = 'block';
            testCaseTypesSection.style.display = 'block';
            break;
        case 'url':
            console.log('URL case - showing urlFields, hiding itemIdField and testCaseTypesSection');
            urlFields.style.display = 'block';
            // Hide Item ID and Test Case Types for URL - they're not needed
            if (itemIdField) {
                itemIdField.style.display = 'none';
                itemIdField.style.visibility = 'hidden';
                itemIdField.style.opacity = '0';
                itemIdField.style.height = '0';
                itemIdField.style.overflow = 'hidden';
                console.log('Item ID field hidden with multiple methods');
            } else {
                console.error('Item ID field not found!');
            }
            if (testCaseTypesSection) {
                testCaseTypesSection.style.display = 'none';
                testCaseTypesSection.style.visibility = 'hidden';
                testCaseTypesSection.style.opacity = '0';
                testCaseTypesSection.style.height = '0';
                testCaseTypesSection.style.overflow = 'hidden';
                console.log('Test Case Types section hidden with multiple methods');
            } else {
                console.error('Test Case Types section not found!');
            }
            break;
    }
    
    console.log('Fields updated for source type:', sourceType);
}

// Function to handle URL form submission
async function handleUrlSubmission(e) {
    e.preventDefault();
    // Clear any stale key from previous generations
    window.generatedUrlKey = null;
    console.log('URL form submission triggered');
    
    const urlInput = document.getElementById('siteUrl');
    const url = urlInput.value.trim();
    const errorDiv = document.getElementById('siteUrl-error');
    
    // Clear previous error
    errorDiv.textContent = '';
    errorDiv.style.display = 'none';
    
    // Validate URL
    try {
        new URL(url);
    } catch (error) {
        errorDiv.textContent = 'Please enter a valid website URL (e.g., https://example.com)';
        errorDiv.style.display = 'block';
        return;
    }
    
    // Get selected test case types
    const selectedCheckboxes = document.querySelectorAll('input[name="testCaseTypes[]"]:checked');
    const selectedTypes = Array.from(selectedCheckboxes).map(cb => cb.value);
    
    if (selectedTypes.length === 0) {
        errorDiv.textContent = 'Please select at least one test case type';
        errorDiv.style.display = 'block';
        return;
    }
    
    // Show loader
    const loader = document.querySelector('.loader-container');
    if (loader) loader.style.display = 'flex';
    
    try {
        // Make API request
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                sourceType: 'url',
                url_config: { url },
                testCaseTypes: selectedTypes
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }

        // Store the URL key and start status checking instead of immediate redirect
        window.generatedUrlKey = result.url_key;
        console.log('Generation started, URL key:', window.generatedUrlKey);
        
        // Start checking generation status instead of immediate redirect
        checkGenerationStatus(null, result, null);
        
    } catch (error) {
        console.error('Error:', error);
        errorDiv.textContent = error.message;
        errorDiv.style.display = 'block';
        if (loader) loader.style.display = 'none';
    }
}

// Add event listeners when document is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('Document ready, setting up event listeners');
    
    // URL form submission will be handled by the main form submission
    // No separate button needed since we're using the main "Generate Tests with AI" button
    
    // Source type change listener
    const sourceTypeSelect = document.getElementById('sourceType');
    if (sourceTypeSelect) {
        sourceTypeSelect.addEventListener('change', handleSourceTypeChange);
        console.log('Source type change listener added');
        
        // Trigger initial state
        console.log('Triggering initial state');
        handleSourceTypeChange();
    } else {
        console.error('Source type select element not found!');
    }
});

// Form submission handler

async function submitFormManually() {
    console.log('Manual form submission triggered');
    // Clear any stale key from previous generations
    window.generatedUrlKey = null;
    console.log('=== FORM SUBMISSION DEBUG ===');
    alert('submitFormManually function called!'); // Test if function is called
    document.body.style.backgroundColor = '#eeffee'; // Visual feedback

    try {
        // Clear all previous errors first
        clearAllErrors();

        // Trim all input fields BEFORE collecting data
        await trimAllInputFields();

        // Get form data
        const form = document.getElementById('generatorForm');
        console.log('Form element:', form);
        const formData = new FormData(form);
        const sourceType = document.getElementById('sourceType').value;
        console.log('Source type:', sourceType);
        alert('Form data collected!'); // Test if we reach here
        let hasErrors = false;

        // Validate form data
        if (sourceType === 'jira') {
            // Validate Jira fields
            const jiraUrl = document.getElementById('jiraUrl').value.trim();
            const jiraUser = document.getElementById('jiraUser').value.trim();
            const jiraToken = document.getElementById('jiraToken').value.trim();

            if (!jiraUrl || !jiraUser || !jiraToken) {
                showSectionMessage('jiraFields', 'Please fill in all Jira fields', 'error');
                hasErrors = true;
            }

            // Validate Jira URL format
            if (jiraUrl && !jiraUrl.includes('.atlassian.net')) {
                showFieldError('jiraUrl', 'Please enter a valid Atlassian URL (e.g., https://your-domain.atlassian.net)');
                hasErrors = true;
            }
        } else if (sourceType === 'azure') {
            // Validate Azure fields
            const azureUrl = document.getElementById('azureUrl').value.trim();
            const azureOrg = document.getElementById('azureOrg').value.trim();
            const azureProject = document.getElementById('azureProject').value.trim();
            const azurePat = document.getElementById('azurePat').value.trim();

            if (!azureUrl || !azureOrg || !azureProject || !azurePat) {
                showSectionMessage('azureFields', 'Please fill in all Azure fields', 'error');
                hasErrors = true;
            }

            // Validate Azure URL format
            if (azureUrl && !azureUrl.includes('dev.azure.com')) {
                showFieldError('azureUrl', 'Please enter a valid Azure DevOps URL (e.g., https://dev.azure.com)');
                hasErrors = true;
            }
        } else if (sourceType === 'url') {
            console.log('Validating URL source type...');
            // Validate URL field
            const siteUrl = document.getElementById('siteUrl').value.trim();
            console.log('Site URL value:', siteUrl);

            if (!siteUrl) {
                console.log('No URL provided');
                showSectionMessage('urlFields', 'Please enter a website URL', 'error');
                hasErrors = true;
            }

            // Validate URL format
            try {
                new URL(siteUrl);
                console.log('URL format is valid');
            } catch (error) {
                console.log('Invalid URL format:', error);
                showFieldError('siteUrl', 'Please enter a valid website URL (e.g., https://example.com)');
                hasErrors = true;
            }
        }

        // Check if there are any validation errors
        console.log('Validation completed, hasErrors:', hasErrors);
        if (hasErrors) {
            console.log('Validation errors found, stopping submission');
            showGeneralMessage('Please fix the validation errors before submitting', 'error');
            return;
        }

        // Show initial progress
        updateLoader(0);
        console.log('Starting generation with initial progress 0%');

        // Track form submission with timing
        const submissionStartTime = Date.now();
        window.generationStartTime = submissionStartTime;

        // Prepare request data
        let requestData;
        if (sourceType === 'image') {
            requestData = formData;
        } else {
            // For Jira, Azure, and URL, convert FormData to JSON
            const jsonData = {};
            jsonData.sourceType = sourceType;
            jsonData.testCaseTypes = Array.from(formData.getAll('testCaseTypes[]'));
            console.log('Test case types from form:', jsonData.testCaseTypes);
            console.log('FormData entries:');
            for (let [key, value] of formData.entries()) {
                console.log(`${key}: ${value}`);
            }
            
            // Only add itemId for Jira and Azure (not for URL)
            if (sourceType === 'jira' || sourceType === 'azure') {
                jsonData.itemId = Array.from(formData.getAll('itemId[]'));
            }
            
            // Add source-specific config
            if (sourceType === 'jira') {
                jsonData.jira_config = {
                    url: document.getElementById('jiraUrl').value.trim(),
                    user: document.getElementById('jiraUser').value.trim(),
                    token: document.getElementById('jiraToken').value.trim()
                };
            } else if (sourceType === 'azure') {
                jsonData.azure_config = {
                    url: document.getElementById('azureUrl').value.trim(),
                    org: document.getElementById('azureOrg').value.trim(),
                    project: document.getElementById('azureProject').value.trim(),
                    pat: document.getElementById('azurePat').value.trim()
                };
            } else if (sourceType === 'url') {
                const siteUrl = document.getElementById('siteUrl').value.trim();
                console.log('Site URL element:', document.getElementById('siteUrl'));
                console.log('Site URL value:', siteUrl);
                jsonData.url_config = {
                    url: siteUrl
                };
            }
            requestData = jsonData;
            window.selectedItemsCount = sourceType === 'url' ? 0 : (jsonData.itemId ? jsonData.itemId.length : 0);
            
            console.log('Data prepared successfully');
            alert('Data prepared successfully!'); // Test if we reach here
            
            console.log('Final request data:', JSON.stringify(jsonData, null, 2));
            console.log('Request data type:', typeof requestData);
            console.log('Request data keys:', Object.keys(requestData));
        }

        // Make API request
        console.log('About to make API request to /api/generate');
        console.log('Request data:', JSON.stringify(requestData, null, 2));
        
        // Test if we can even reach this point
        console.log('=== ABOUT TO START FETCH ===');
        console.log('Request data type:', typeof requestData);
        console.log('Request data keys:', Object.keys(requestData));
        
        // Test if we can even reach this point
        console.log('Starting fetch request...');
        
        try {
            console.log('Starting fetch request...');
            console.log('Fetch URL: /api/generate');
            console.log('Fetch method: POST');
            console.log('Fetch headers:', sourceType === 'image' ? {} : {'Content-Type': 'application/json'});
            console.log('Fetch body type:', typeof (sourceType === 'image' ? requestData : JSON.stringify(requestData)));
            
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: sourceType === 'image' ? {} : {
                    'Content-Type': 'application/json'
                },
                body: sourceType === 'image' ? requestData : JSON.stringify(requestData)
            });
            console.log('Fetch request completed');

            console.log('Response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('Response received:', result);

            if (result.error) {
                showNotification('Error: ' + result.error, 'error');
                updateLoader(0);
                return;
            }

            // Store the URL key for use in redirection
            window.generatedUrlKey = result.url_key;
            console.log('Generation started, URL key:', window.generatedUrlKey);

            // Start checking generation status
            const itemIds = sourceType === 'image' ? null : (requestData.itemId || []);
            checkGenerationStatus(null, result, itemIds);

        } catch (error) {
            console.error('Error in fetch request:', error);
            console.error('Error details:', {
                message: error.message,
                stack: error.stack,
                type: error.constructor.name
            });
            showNotification('Error: ' + error.message, 'error');
            updateLoader(0);
        }

    } catch (error) {
        console.error('Error in manual form submission:', error);
        showNotification('Error: ' + error.message, 'error');
        updateLoader(0);
    }
}