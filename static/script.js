document.addEventListener('DOMContentLoaded', function() {
    // Form submission
    const scanForm = document.getElementById('scanForm');
    const scanButton = document.getElementById('scanButton');
    const loadingDiv = document.getElementById('loading');
    const resultsDiv = document.getElementById('results');

    // Results elements
    const resultDomain = document.getElementById('resultDomain');
    const subdomainsCount = document.getElementById('subdomainsCount');
    const liveHostsCount = document.getElementById('liveHostsCount');
    const historicalUrlsCount = document.getElementById('historicalUrlsCount');

    // Tables
    const liveHostsTable = document.getElementById('liveHostsTable');
    const subdomainsTable = document.getElementById('subdomainsTable');
    const historicalUrlsTable = document.getElementById('historicalUrlsTable');

    // Filters
    const liveHostsFilter = document.getElementById('liveHostsFilter');
    const subdomainsFilter = document.getElementById('subdomainsFilter');
    const historicalUrlsFilter = document.getElementById('historicalUrlsFilter');

    // Tab buttons
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabPanes = document.querySelectorAll('.tab-pane');

    // Store the full results for filtering
    let fullResults = {
        liveHosts: [],
        subdomains: [],
        historicalUrls: {}
    };

    // Track GAU loading status
    let gauLoading = {};

    // Progress bar elements
    const progressBar = document.getElementById('progressBar');
    const progressMessage = document.getElementById('progressMessage');
    const progressSubdomains = document.getElementById('progressSubdomains');
    const progressLiveHosts = document.getElementById('progressLiveHosts');

    // Current task ID
    let currentTaskId = null;
    let eventSource = null;

    // Function to update the progress UI
    function updateProgress(data) {
        progressBar.style.width = `${data.progress}%`;
        progressMessage.textContent = data.message;
        progressSubdomains.textContent = data.subdomains_count;
        progressLiveHosts.textContent = data.live_hosts_count;

        // If the task is complete, fetch the full results
        if (data.status === 'complete') {
            fetchTaskResults(currentTaskId);
        } else if (data.status === 'error') {
            alert(`Error: ${data.message}`);
            loadingDiv.classList.add('hidden');
            scanButton.disabled = false;
            scanButton.innerHTML = '<i class="fas fa-search"></i> Scan';
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        }
    }

    // Function to fetch the full task results
    function fetchTaskResults(taskId) {
        fetch(`/task/${taskId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                // Store the full results
                fullResults.liveHosts = data.live_hosts || [];
                fullResults.subdomains = data.subdomains || [];
                fullResults.historicalUrls = {}; // Reset historical URLs

                // Update the UI
                resultDomain.textContent = data.domain;
                subdomainsCount.textContent = data.subdomains_count;
                liveHostsCount.textContent = data.live_hosts_count;
                historicalUrlsCount.textContent = 0; // Reset to 0 since we're not running GAU automatically

                // Populate tables
                populateLiveHostsTable(fullResults.liveHosts);
                populateSubdomainsTable(fullResults.subdomains);
                populateHistoricalUrlsTable([]);

                // Hide loading, show results
                loadingDiv.classList.add('hidden');
                resultsDiv.classList.remove('hidden');
                scanButton.disabled = false;
                scanButton.innerHTML = '<i class="fas fa-search"></i> Scan';

                // Close the event source
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
            })
            .catch(error => {
                console.error('Error fetching results:', error);
                alert('An error occurred while fetching results. Please try again.');
                loadingDiv.classList.add('hidden');
                scanButton.disabled = false;
                scanButton.innerHTML = '<i class="fas fa-search"></i> Scan';
            });
    }

    // Function to start listening for task updates
    function listenForTaskUpdates(taskId) {
        // Close any existing event source
        if (eventSource) {
            eventSource.close();
        }

        // Create a new event source
        eventSource = new EventSource(`/task/${taskId}/events`);

        // Listen for messages
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateProgress(data);
        };

        // Handle errors
        eventSource.onerror = function() {
            console.error('EventSource failed');
            eventSource.close();
            eventSource = null;
        };
    }

    // Handle form submission
    scanForm.addEventListener('submit', function(e) {
        e.preventDefault();

        const domain = document.getElementById('domain').value.trim();

        if (!domain) {
            alert('Please enter a domain');
            return;
        }

        // Reset progress UI
        progressBar.style.width = '0%';
        progressMessage.textContent = 'Starting scan...';
        progressSubdomains.textContent = '0';
        progressLiveHosts.textContent = '0';

        // Show loading, hide results
        loadingDiv.classList.remove('hidden');
        resultsDiv.classList.add('hidden');
        scanButton.disabled = true;
        scanButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning...';

        // Send the request
        const formData = new FormData();
        formData.append('domain', domain);

        fetch('/scan', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Store the task ID
            currentTaskId = data.task_id;

            // Start listening for updates
            listenForTaskUpdates(currentTaskId);
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while starting the scan. Please try again.');
            loadingDiv.classList.add('hidden');
            scanButton.disabled = false;
            scanButton.innerHTML = '<i class="fas fa-search"></i> Scan';
        });
    });

    // Tab switching
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons and panes
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabPanes.forEach(pane => pane.classList.remove('active'));

            // Add active class to clicked button and corresponding pane
            this.classList.add('active');
            const tabId = this.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // Filter functionality
    liveHostsFilter.addEventListener('input', function() {
        const filterValue = this.value.toLowerCase();
        const filteredHosts = fullResults.liveHosts.filter(host =>
            host.url.toLowerCase().includes(filterValue) ||
            host.status_code.toLowerCase().includes(filterValue) ||
            host.technology.toLowerCase().includes(filterValue)
        );
        populateLiveHostsTable(filteredHosts);
    });

    subdomainsFilter.addEventListener('input', function() {
        const filterValue = this.value.toLowerCase();
        const filteredSubdomains = fullResults.subdomains.filter(subdomain =>
            subdomain.toLowerCase().includes(filterValue)
        );
        populateSubdomainsTable(filteredSubdomains);
    });

    historicalUrlsFilter.addEventListener('input', function() {
        const filterValue = this.value.toLowerCase();

        // Check if we're viewing a specific domain's historical URLs
        const domainHeader = document.querySelector('#historicalUrls .domain-header');
        if (domainHeader) {
            const domain = domainHeader.textContent.replace('Historical URLs for ', '');
            if (fullResults.historicalUrls[domain]) {
                const filteredUrls = fullResults.historicalUrls[domain].filter(url =>
                    url.toLowerCase().includes(filterValue)
                );
                populateHistoricalUrlsTable(filteredUrls, domain);
                return;
            }
        }

        // If not viewing a specific domain, show empty results
        populateHistoricalUrlsTable([]);
    });

    // Helper functions to populate tables
    function populateLiveHostsTable(hosts) {
        liveHostsTable.innerHTML = '';

        if (hosts.length === 0) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 4; // Updated to 4 columns
            cell.textContent = 'No live hosts found';
            cell.style.textAlign = 'center';
            row.appendChild(cell);
            liveHostsTable.appendChild(row);
            return;
        }

        hosts.forEach(host => {
            const row = document.createElement('tr');

            // Extract domain from URL
            let domain = new URL(host.url).hostname;

            // URL cell
            const urlCell = document.createElement('td');
            const urlLink = document.createElement('a');
            urlLink.href = host.url;
            urlLink.textContent = host.url;
            urlLink.target = '_blank';
            urlCell.appendChild(urlLink);

            // Status code cell with color coding
            const statusCell = document.createElement('td');
            statusCell.textContent = host.status_code;

            // Apply color based on status code
            let statusCode;
            try {
                statusCode = parseInt(host.status_code);
            } catch (e) {
                statusCode = 0;
            }

            if (statusCode >= 200 && statusCode < 300) {
                statusCell.classList.add('status-2xx'); // Green
            } else if (statusCode >= 300 && statusCode < 400) {
                statusCell.classList.add('status-3xx'); // Blue
            } else if (statusCode >= 400 && statusCode < 500) {
                statusCell.classList.add('status-4xx'); // Red
            } else if (statusCode >= 500) {
                statusCell.classList.add('status-5xx'); // Orange
            }

            // Technology cell
            const techCell = document.createElement('td');
            techCell.textContent = host.technology;

            // GAU button cell
            const gauCell = document.createElement('td');
            const gauButton = document.createElement('button');
            gauButton.textContent = 'Run GAU';
            gauButton.classList.add('gau-button');
            gauButton.dataset.domain = domain;

            // Check if GAU is already running or completed for this domain
            if (gauLoading[domain]) {
                gauButton.disabled = true;
                gauButton.textContent = 'Loading...';
            } else if (fullResults.historicalUrls[domain]) {
                gauButton.textContent = 'View URLs';
                gauButton.classList.add('view-button');
            }

            gauButton.addEventListener('click', function() {
                const domain = this.dataset.domain;

                if (fullResults.historicalUrls[domain]) {
                    // If we already have results, show them
                    showHistoricalUrls(domain);
                } else {
                    // Otherwise, run GAU
                    runGau(domain, this);
                }
            });

            gauCell.appendChild(gauButton);

            row.appendChild(urlCell);
            row.appendChild(statusCell);
            row.appendChild(techCell);
            row.appendChild(gauCell);

            liveHostsTable.appendChild(row);
        });
    }

    function populateSubdomainsTable(subdomains) {
        subdomainsTable.innerHTML = '';

        if (subdomains.length === 0) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.textContent = 'No subdomains found';
            cell.style.textAlign = 'center';
            row.appendChild(cell);
            subdomainsTable.appendChild(row);
            return;
        }

        subdomains.forEach(subdomain => {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.textContent = subdomain;
            row.appendChild(cell);
            subdomainsTable.appendChild(row);
        });
    }

    function populateHistoricalUrlsTable(urls, domain = null) {
        historicalUrlsTable.innerHTML = '';

        // Add domain header if provided
        if (domain) {
            const headerRow = document.createElement('tr');
            const headerCell = document.createElement('td');
            headerCell.colSpan = 2;
            headerCell.classList.add('domain-header');
            headerCell.textContent = `Historical URLs for ${domain}`;
            headerRow.appendChild(headerCell);
            historicalUrlsTable.appendChild(headerRow);
        }

        if (!urls || urls.length === 0) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 2;
            cell.textContent = 'No historical URLs found';
            cell.style.textAlign = 'center';
            row.appendChild(cell);
            historicalUrlsTable.appendChild(row);
            return;
        }

        urls.forEach(url => {
            const row = document.createElement('tr');

            // URL cell
            const urlCell = document.createElement('td');
            const link = document.createElement('a');
            link.href = url;
            link.textContent = url;
            link.target = '_blank';
            urlCell.appendChild(link);

            // Path cell - show the path part of the URL
            const pathCell = document.createElement('td');
            try {
                const urlObj = new URL(url);
                pathCell.textContent = urlObj.pathname + urlObj.search;
            } catch (e) {
                pathCell.textContent = 'Invalid URL';
            }

            row.appendChild(urlCell);
            row.appendChild(pathCell);
            historicalUrlsTable.appendChild(row);
        });
    }

    // Function to run GAU for a specific domain
    function runGau(domain, button) {
        // Update button state
        button.disabled = true;
        button.textContent = 'Loading...';
        gauLoading[domain] = true;

        // Create a progress indicator next to the button
        const parentCell = button.parentElement;
        const progressIndicator = document.createElement('div');
        progressIndicator.className = 'gau-progress';
        progressIndicator.innerHTML = '<span>0 URLs found</span>';
        parentCell.appendChild(progressIndicator);

        // Set up polling for progress updates
        let pollInterval = setInterval(() => {
            fetch(`/task/gau-${domain}`, {
                method: 'GET'
            })
            .then(response => response.json())
            .then(data => {
                if (data && data.urls_count !== undefined) {
                    progressIndicator.innerHTML = `<span>${data.urls_count} URLs found</span>`;
                }
            })
            .catch(error => console.error('Error polling GAU progress:', error));
        }, 1000);

        // Make AJAX request to run GAU
        fetch(`/run-gau?domain=${encodeURIComponent(domain)}`, {
            method: 'GET'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Clear polling interval
            clearInterval(pollInterval);

            // Store the results
            fullResults.historicalUrls[domain] = data.urls || [];

            // Update button
            button.disabled = false;
            button.textContent = 'View URLs';
            button.classList.add('view-button');
            gauLoading[domain] = false;

            // Update progress indicator
            progressIndicator.innerHTML = `<span>${data.urls.length} URLs found</span>`;
            progressIndicator.classList.add('gau-complete');

            // Remove progress indicator after a delay
            setTimeout(() => {
                progressIndicator.remove();
            }, 3000);
        })
        .catch(error => {
            // Clear polling interval
            clearInterval(pollInterval);

            console.error('Error:', error);
            button.disabled = false;
            button.textContent = 'Run GAU (Failed)';
            gauLoading[domain] = false;

            // Update progress indicator
            progressIndicator.innerHTML = '<span class="error">Failed</span>';
            progressIndicator.classList.add('gau-error');

            // Remove progress indicator after a delay
            setTimeout(() => {
                progressIndicator.remove();
            }, 3000);
        });
    }

    // Function to show historical URLs for a specific domain
    function showHistoricalUrls(domain) {
        // Switch to historical URLs tab
        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));

        document.querySelector('[data-tab="historicalUrls"]').classList.add('active');
        document.getElementById('historicalUrls').classList.add('active');

        // Populate the table with domain-specific results
        populateHistoricalUrlsTable(fullResults.historicalUrls[domain], domain);
    }
});
