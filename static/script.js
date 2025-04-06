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
        historicalUrls: {},
        historicalUrlsCount: {},
        historicalUrlsLimited: {}
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
        console.log('Updating progress UI with data:', data);

        // Update progress bar
        if (data.progress !== undefined) {
            progressBar.style.width = `${data.progress}%`;
        }

        // Update message
        if (data.message !== undefined) {
            progressMessage.textContent = data.message;
        }

        // Update subdomains count if available
        if (data.subdomains_count !== undefined) {
            progressSubdomains.textContent = data.subdomains_count;
        }

        // Update live hosts count if available
        if (data.live_hosts_count !== undefined) {
            progressLiveHosts.textContent = data.live_hosts_count;
        }

        // If the task is complete, fetch the full results
        if (data.status === 'complete') {
            console.log('Task complete, fetching full results');
            fetchTaskResults(currentTaskId);
        } else if (data.status === 'error') {
            console.error('Task error:', data.message);
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
        fetch(`/api/task/${taskId}`)
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
                fullResults.historicalUrlsCount = {}; // Reset counts
                fullResults.historicalUrlsLimited = {}; // Reset limited flags

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
        eventSource = new EventSource(`/api/task/${taskId}/events`);

        // Listen for messages
        eventSource.onmessage = function(event) {
            console.log('SSE message received:', event.data);
            try {
                const data = JSON.parse(event.data);
                console.log('Parsed SSE data:', data);
                updateProgress(data);
            } catch (error) {
                console.error('Error parsing SSE data:', error);
                console.error('Raw event data:', event.data);
            }
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

        fetch('/scan/scan', {
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

            // Port scan button cell
            const portCell = document.createElement('td');
            const portButton = document.createElement('button');
            portButton.textContent = 'Scan Ports';
            portButton.classList.add('port-button');
            portButton.dataset.host = domain;

            // Check if port scan is already running or completed for this host
            if (portScanLoading[domain]) {
                portButton.disabled = true;
                portButton.textContent = 'Scanning...';
            } else if (portScanResults[domain]) {
                portButton.textContent = 'View Ports';
                portButton.classList.add('view-button');
            }

            portButton.addEventListener('click', function() {
                const host = this.dataset.host;

                if (portScanResults[host]) {
                    // If we already have results, show them
                    showPortScanResults(host);
                } else {
                    // Otherwise, run port scan
                    scanPorts(host, this);
                }
            });

            portCell.appendChild(portButton);

            row.appendChild(urlCell);
            row.appendChild(statusCell);
            row.appendChild(techCell);
            row.appendChild(gauCell);
            row.appendChild(portCell);

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

            // Add note if results are limited
            if (fullResults.historicalUrlsLimited && fullResults.historicalUrlsLimited[domain]) {
                const limitRow = document.createElement('tr');
                const limitCell = document.createElement('td');
                limitCell.colSpan = 2;
                limitCell.classList.add('limit-note');
                limitCell.innerHTML = `<strong>Note:</strong> Showing ${urls.length} of ${fullResults.historicalUrlsCount[domain]} total URLs. The complete list is saved in the database.`;
                limitRow.appendChild(limitCell);
                historicalUrlsTable.appendChild(limitRow);
            }
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

    // Store port scan results
    let portScanResults = {};
    let portScanLoading = {};

    // Function to run GAU for a specific domain
    function runGau(domain, button) {
        // Update button state
        button.disabled = true;
        button.textContent = 'Loading...';
        gauLoading[domain] = true;

        // Make AJAX request to run GAU
        fetch(`/api/run-gau?domain=${encodeURIComponent(domain)}`, {
            method: 'GET'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Store the results
            fullResults.historicalUrls[domain] = data.urls || [];
            fullResults.historicalUrlsCount = fullResults.historicalUrlsCount || {};
            fullResults.historicalUrlsCount[domain] = data.count || 0;
            fullResults.historicalUrlsLimited = fullResults.historicalUrlsLimited || {};
            fullResults.historicalUrlsLimited[domain] = data.limited || false;

            // Update button
            button.disabled = false;
            button.textContent = 'View URLs';
            button.classList.add('view-button');
            gauLoading[domain] = false;

            // Show a notification
            let message = `Found ${data.count} historical URLs for ${domain}`;
            if (data.limited) {
                message += ` (showing ${data.urls.length} in the UI)`;
            }
            alert(message);
        })
        .catch(error => {
            console.error('Error:', error);
            button.disabled = false;
            button.textContent = 'Run GAU (Failed)';
            gauLoading[domain] = false;
        });
    }

    // Function to scan ports for a specific host
    function scanPorts(host, button) {
        // Update button state
        button.disabled = true;
        button.textContent = 'Scanning...';
        portScanLoading[host] = true;

        // Make AJAX request to scan ports
        fetch(`/api/scan-ports?host=${encodeURIComponent(host)}`, {
            method: 'GET'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Store the results
            portScanResults[host] = data.ports || [];

            // Update button
            button.disabled = false;
            button.textContent = 'View Ports';
            button.classList.add('view-button');
            portScanLoading[host] = false;

            // Show a notification
            alert(`Found ${data.ports.length} open ports on ${host}`);
        })
        .catch(error => {
            console.error('Error:', error);
            button.disabled = false;
            button.textContent = 'Scan Ports (Failed)';
            portScanLoading[host] = false;
        });
    }

    // Function to show port scan results
    function showPortScanResults(host) {
        const ports = portScanResults[host] || [];

        if (ports.length === 0) {
            alert(`No open ports found on ${host}`);
            return;
        }

        // Create a modal to display the results
        const modal = document.createElement('div');
        modal.className = 'modal';

        // Create modal content
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';

        // Create close button
        const closeButton = document.createElement('span');
        closeButton.className = 'close-button';
        closeButton.innerHTML = '&times;';
        closeButton.onclick = function() {
            document.body.removeChild(modal);
        };

        // Create header
        const header = document.createElement('h2');
        header.textContent = `Open Ports on ${host}`;

        // Create port list
        const portList = document.createElement('div');
        portList.className = 'port-list';

        // Group ports by common services
        const commonPorts = {
            '21': 'FTP',
            '22': 'SSH',
            '23': 'Telnet',
            '25': 'SMTP',
            '53': 'DNS',
            '80': 'HTTP',
            '110': 'POP3',
            '143': 'IMAP',
            '443': 'HTTPS',
            '445': 'SMB',
            '3306': 'MySQL',
            '3389': 'RDP',
            '5432': 'PostgreSQL',
            '8080': 'HTTP-Proxy',
            '8443': 'HTTPS-Alt'
        };

        // Create a table for the ports
        const table = document.createElement('table');
        table.className = 'port-table';

        // Create table header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const portHeader = document.createElement('th');
        portHeader.textContent = 'Port';
        const serviceHeader = document.createElement('th');
        serviceHeader.textContent = 'Possible Service';

        headerRow.appendChild(portHeader);
        headerRow.appendChild(serviceHeader);
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create table body
        const tbody = document.createElement('tbody');

        ports.forEach(port => {
            const row = document.createElement('tr');

            const portCell = document.createElement('td');
            portCell.textContent = port;

            const serviceCell = document.createElement('td');
            serviceCell.textContent = commonPorts[port] || 'Unknown';

            row.appendChild(portCell);
            row.appendChild(serviceCell);
            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        portList.appendChild(table);

        // Assemble modal
        modalContent.appendChild(closeButton);
        modalContent.appendChild(header);
        modalContent.appendChild(portList);
        modal.appendChild(modalContent);

        // Add modal to body
        document.body.appendChild(modal);
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
