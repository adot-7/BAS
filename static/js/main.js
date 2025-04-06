document.addEventListener('DOMContentLoaded', () => {
    // --- Helper Functions ---
    const messageArea = document.getElementById('messageArea');

    function showMessage(text, type = 'info') {
        messageArea.textContent = text;
        messageArea.className = type; // 'success', 'error', 'info'
        messageArea.classList.remove('hidden');
        // Clear message after 5 seconds
        setTimeout(() => {
            messageArea.classList.add('hidden');
            messageArea.className = 'hidden';
        }, 5000);
    }

    function displayResult(elementId, data) {
        const element = document.getElementById(elementId);
        element.textContent = JSON.stringify(data, null, 2);
        element.classList.remove('hidden');
    }

    function clearResult(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = ''; // Clear the content
            element.classList.add('hidden'); // Hide the element
            element.classList.remove('error'); // Remove error styling if present
        }
    }

    async function handleFormSubmit(event, resultElementId) {
        event.preventDefault();
        clearResult(resultElementId); // Clear the result before making the request
        const form = event.target;
        const formData = new FormData(form);
        const url = form.getAttribute('data-action') || form.action || window.location.pathname; // Default to current path if action not set
        const method = form.getAttribute('method') || 'post';

        // Adjust options for file uploads vs JSON/GET
        let options = { method: method.toUpperCase() };
        if (form.enctype === 'multipart/form-data') {
            options.body = formData;
        } else if (method.toLowerCase() === 'post' && !(formData instanceof URLSearchParams)) {
            options.body = JSON.stringify(Object.fromEntries(formData));
            options.headers = { 'Content-Type': 'application/json' };
        } else { // Assumes GET or form encoded POST
            if (method.toLowerCase() === 'get') {
                const params = new URLSearchParams(formData).toString();
                form.action = `${url}?${params}`; // Modify action for GET
            } else {
                options.body = new URLSearchParams(formData); // Form encoded POST
                options.headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
            }

        }

        try {
            let fetchUrl = options.method === 'GET' ? form.action : url; // Use modified URL for GET
            const response = await fetch(fetchUrl, options);
            const resultData = await response.json();

            if (!response.ok || !resultData.success) {
                throw new Error(resultData.message || resultData.detail || `HTTP error! status: ${response.status}`);
            }

            showMessage(`${form.id || 'Action'} successful!`, 'success');
            displayResult(resultElementId, resultData);

        } catch (error) {
            console.error('Error:', error);
            showMessage(`Error: ${error.message}`, 'error');
            const element = document.getElementById(resultElementId);
            element.textContent = `Error: ${error.message}`;
            element.classList.remove('hidden');
            element.classList.add('error'); // Style as error
        } finally {
            // Maybe reset form or spinner logic here
        }
    }

    async function handleButtonClick(url, method, resultElementId, body = null) {
        clearResult(resultElementId); // Clear the result before making the request
        try {
            const options = { method: method.toUpperCase() };
            if (body) {
                options.body = JSON.stringify(body);
                options.headers = { 'Content-Type': 'application/json' };
            }
            const response = await fetch(url, options);
            const resultData = await response.json();

            if (!response.ok || !resultData.success) {
                throw new Error(resultData.message || resultData.detail || `HTTP error! status: ${response.status}`);
            }
            showMessage('Action successful!', 'success');
            displayResult(resultElementId, resultData);
        } catch (error) {
            console.error('Error:', error);
            showMessage(`Error: ${error.message}`, 'error');
            const element = document.getElementById(resultElementId);
            element.textContent = `Error: ${error.message}`;
            element.classList.remove('hidden');
            element.classList.add('error');
        }
    }


    // --- Event Listeners ---

    // Import Containers
    const importContainersForm = document.getElementById('importContainersForm');
    if (importContainersForm) {
        importContainersForm.addEventListener('submit', async (e) => {
            e.preventDefault(); // Prevent default form submission
            const formData = new FormData(importContainersForm);
            const resultElementId = 'containersResult';
            const url = '/api/import/containers';

            try {
                const response = await fetch(url, { method: 'POST', body: formData });
                const resultData = await response.json();
                if (!response.ok || !resultData.success) {
                    throw new Error(resultData.message || `Import failed (Status: ${response.status})`);
                }
                showMessage(`Successfully imported ${resultData.containersImported} containers.`, 'success');
                displayResult(resultElementId, resultData);
            } catch (error) {
                console.error('Error:', error);
                showMessage(`Error: ${error.message}`, 'error');
                const element = document.getElementById(resultElementId);
                element.textContent = `Error: ${error.message}`;
                element.classList.remove('hidden');
                element.classList.add('error');
            }
        });
    }

    // Import Items
    const importItemsForm = document.getElementById('importItemsForm');
    if (importItemsForm) {
        importItemsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(importItemsForm);
            const resultElementId = 'itemsResult';
            const url = '/api/import/items';
            try {
                const response = await fetch(url, { method: 'POST', body: formData });
                const resultData = await response.json();
                if (!response.ok || !resultData.success) throw new Error(resultData.message || `Import failed (Status: ${response.status})`);
                showMessage(`Successfully imported ${resultData.itemsImported} items.`, 'success');
                displayResult(resultElementId, resultData);
            } catch (error) {
                console.error('Error:', error); showMessage(`Error: ${error.message}`, 'error');
                const element = document.getElementById(resultElementId); element.textContent = `Error: ${error.message}`;
                element.classList.remove('hidden'); element.classList.add('error');
            }
        });
    }

    // Trigger Placement
    const triggerPlacementButton = document.getElementById('triggerPlacementButton');
    if (triggerPlacementButton) {
        triggerPlacementButton.addEventListener('click', async () => {
            const placementResultElement = document.getElementById('placementResult');

            // Toggle visibility if result is already displayed
            if (!placementResultElement.classList.contains('hidden')) {
                placementResultElement.classList.add('hidden');
                return;
            }

            // Show loading message
            placementResultElement.textContent = 'Processing... Please wait.';
            placementResultElement.classList.remove('hidden');
            placementResultElement.classList.remove('error');

            try {
                const response = await fetch('/api/placement', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const resultData = await response.json();

                if (!response.ok || !resultData.success) {
                    throw new Error(resultData.message || `Placement failed (Status: ${response.status})`);
                }

                // Display the placements in a readable JSON format
                placementResultElement.textContent = JSON.stringify(resultData, null, 2);
                showMessage('Placement successful!', 'success');
            } catch (error) {
                console.error('Error:', error);
                showMessage(`Error: ${error.message}`, 'error');
                placementResultElement.textContent = `Error: ${error.message}`;
                placementResultElement.classList.add('error');
            }
        });
    }

    // Search Form
    const searchForm = document.getElementById('searchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(searchForm);
            const query = formData.get('searchQuery');
            const type = formData.get('searchType');
            const params = new URLSearchParams({ [type]: query }).toString();
            const url = `/api/search?${params}`;
            handleButtonClick(url, 'GET', 'searchResult');
        });
    }

    // Identify Waste Button
    const identifyWasteButton = document.getElementById('identifyWasteButton');
    if (identifyWasteButton) {
        identifyWasteButton.addEventListener('click', () => handleButtonClick('/api/waste/identify', 'GET', 'wasteIdentifyResult'));
    }

    // Simulate Form
    const simulateForm = document.getElementById('simulateForm');
    if (simulateForm) {
        simulateForm.action = '/api/simulate/day';
        simulateForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            const formData = new FormData(form);

            // Parse fields
            const numOfDays = parseInt(formData.get('numOfDays'), 10);
            const itemsToBeUsedPerDayInput = formData.get('itemsToBeUsedPerDay');
            const itemsToBeUsedPerDay = itemsToBeUsedPerDayInput
                ? itemsToBeUsedPerDayInput.split(',').map(itemId => ({ itemId: itemId.trim() }))
                : [];

            // Prepare request body
            const body = {
                numOfDays: numOfDays,
                itemsToBeUsedPerDay: itemsToBeUsedPerDay
            };

            // Send API request
            handleButtonClick('/api/simulate/day', 'POST', 'simulateResult', body);
        });
    }

    // Logs Form
    const logsForm = document.getElementById('logsForm');
    if (logsForm) {
        logsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(logsForm);
            const params = new URLSearchParams();
            // Append parameters only if they have values
            ['startDate', 'endDate', 'itemId', 'userId', 'actionType'].forEach(key => {
                const value = formData.get(key);
                if (value) {
                    params.append(key, value);
                }
            });

            const url = `/api/logs?${params.toString()}`;
            handleButtonClick(url, 'GET', 'logsResult');
        });
    }

    // Remove Waste Return Plan Form logic
    const wasteReturnPlanForm = document.getElementById('wasteReturnPlanForm');
    if (wasteReturnPlanForm) {
        wasteReturnPlanForm.remove(); // Remove the form element if it exists
    }

    // Remove Complete Undocking Form logic
    const completeUndockingForm = document.getElementById('completeUndockingForm');
    if (completeUndockingForm) {
        completeUndockingForm.remove(); // Remove the form element if it exists
    }

});