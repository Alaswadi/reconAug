// Scan History functionality
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const scanHistoryTable = document.getElementById('scanHistoryTable');
    const scanHistoryFilter = document.getElementById('scanHistoryFilter');
    const scanDetailsModal = document.getElementById('scanDetailsModal');
    const scanDetailsTitle = document.getElementById('scanDetailsTitle');
    const scanSubdomainsTable = document.getElementById('scanSubdomainsTable');
    const scanLiveHostsTable = document.getElementById('scanLiveHostsTable');
    const scanHistoricalUrlsTable = document.getElementById('scanHistoricalUrlsTable');

    // Tab elements
    const scanTabButtons = document.querySelectorAll('.scan-tab-button');
    const scanTabPanes = document.querySelectorAll('.scan-tab-pane');

    // Filter elements
    const scanSubdomainsFilter = document.getElementById('scanSubdomainsFilter');
    const scanLiveHostsFilter = document.getElementById('scanLiveHostsFilter');
    const scanHistoricalUrlsFilter = document.getElementById('scanHistoricalUrlsFilter');

    // Store the full scan history
    let scanHistory = [];
    let currentScanDetails = null;

    // Load scan history when the page loads
    loadScanHistory();

    // Close modal when clicking the close button
    document.querySelector('#scanDetailsModal .close-button').addEventListener('click', function() {
        scanDetailsModal.classList.add('hidden');
    });

    // Close modal when clicking outside the modal content
    scanDetailsModal.addEventListener('click', function(event) {
        if (event.target === scanDetailsModal) {
            scanDetailsModal.classList.add('hidden');
        }
    });

    // Handle scan tab switching
    scanTabButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons and panes
            scanTabButtons.forEach(btn => btn.classList.remove('active'));
            scanTabPanes.forEach(pane => pane.classList.remove('active'));

            // Add active class to clicked button and corresponding pane
            this.classList.add('active');
            const tabId = this.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // Filter scan history
    scanHistoryFilter.addEventListener('input', function() {
        const filterValue = this.value.toLowerCase();
        const filteredScans = scanHistory.filter(scan =>
            scan.domain.toLowerCase().includes(filterValue)
        );
        populateScanHistoryTable(filteredScans);
    });

    // Filter scan subdomains
    scanSubdomainsFilter.addEventListener('input', function() {
        if (!currentScanDetails) return;

        const filterValue = this.value.toLowerCase();
        const filteredSubdomains = currentScanDetails.subdomains.filter(subdomain =>
            subdomain.toLowerCase().includes(filterValue)
        );
        populateScanSubdomainsTable(filteredSubdomains);
    });

    // Filter scan live hosts
    scanLiveHostsFilter.addEventListener('input', function() {
        if (!currentScanDetails) return;

        const filterValue = this.value.toLowerCase();
        const filteredHosts = currentScanDetails.live_hosts.filter(host =>
            host.url.toLowerCase().includes(filterValue) ||
            host.status_code.toLowerCase().includes(filterValue) ||
            host.technology.toLowerCase().includes(filterValue)
        );
        populateScanLiveHostsTable(filteredHosts);
    });

    // Filter scan historical URLs
    scanHistoricalUrlsFilter.addEventListener('input', function() {
        if (!currentScanDetails || !currentScanDetails.historical_urls) return;

        const filterValue = this.value.toLowerCase();
        const filteredUrls = currentScanDetails.historical_urls.filter(url =>
            url.toLowerCase().includes(filterValue)
        );
        populateScanHistoricalUrlsTable(filteredUrls);
    });

    // Function to load scan history
    function loadScanHistory() {
        console.log('Loading scan history...');
        scanHistoryTable.innerHTML = '<tr><td colspan="5">Loading scan history...</td></tr>';

        fetch('/scan-history')
            .then(response => {
                console.log('Scan history response status:', response.status);
                if (!response.ok) {
                    throw new Error(`Network response was not ok: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Scan history data received:', data);
                scanHistory = data.scans || [];
                console.log(`Found ${scanHistory.length} scan records`);
                populateScanHistoryTable(scanHistory);
            })
            .catch(error => {
                console.error('Error loading scan history:', error);
                scanHistoryTable.innerHTML = `<tr><td colspan="5">Error loading scan history: ${error.message}</td></tr>`;
            });
    }

    // Function to populate scan history table
    function populateScanHistoryTable(scans) {
        scanHistoryTable.innerHTML = '';

        if (scans.length === 0) {
            scanHistoryTable.innerHTML = '<tr><td colspan="5">No scan history found</td></tr>';
            return;
        }

        scans.forEach(scan => {
            const row = document.createElement('tr');

            // Domain cell
            const domainCell = document.createElement('td');
            domainCell.textContent = scan.domain;

            // Date cell
            const dateCell = document.createElement('td');
            dateCell.classList.add('scan-date');
            const scanDate = new Date(scan.timestamp);
            dateCell.textContent = scanDate.toLocaleString();

            // Subdomains count cell
            const subdomainsCell = document.createElement('td');
            subdomainsCell.textContent = scan.subdomains_count;

            // Live hosts count cell
            const liveHostsCell = document.createElement('td');
            liveHostsCell.textContent = scan.live_hosts_count;

            // Actions cell
            const actionsCell = document.createElement('td');
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'action-buttons';

            // View details button
            const viewButton = document.createElement('button');
            viewButton.textContent = 'View Details';
            viewButton.className = 'view-button-sm';
            viewButton.addEventListener('click', function() {
                viewScanDetails(scan.id);
            });

            // Rescan button
            const rescanButton = document.createElement('button');
            rescanButton.textContent = 'Rescan';
            rescanButton.className = 'scan-history-button';
            rescanButton.addEventListener('click', function() {
                rescanDomain(scan.domain);
            });

            actionsDiv.appendChild(viewButton);
            actionsDiv.appendChild(rescanButton);
            actionsCell.appendChild(actionsDiv);

            // Add cells to row
            row.appendChild(domainCell);
            row.appendChild(dateCell);
            row.appendChild(subdomainsCell);
            row.appendChild(liveHostsCell);
            row.appendChild(actionsCell);

            scanHistoryTable.appendChild(row);
        });
    }

    // Function to view scan details
    function viewScanDetails(scanId) {
        fetch(`/scan/${scanId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                currentScanDetails = data;

                // Set modal title
                scanDetailsTitle.textContent = `Scan Details: ${data.scan.domain}`;

                // Populate subdomain table
                populateScanSubdomainsTable(data.subdomains);

                // Populate live hosts table
                populateScanLiveHostsTable(data.live_hosts);

                // Load historical URLs
                loadHistoricalUrls(scanId);

                // Reset to first tab
                scanTabButtons[0].click();

                // Show modal
                scanDetailsModal.classList.remove('hidden');
            })
            .catch(error => {
                console.error('Error loading scan details:', error);
                alert('Error loading scan details');
            });
    }

    // Function to load historical URLs for a scan
    function loadHistoricalUrls(scanId) {
        fetch(`/scan/${scanId}/historical-urls`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (currentScanDetails) {
                    currentScanDetails.historical_urls = data.urls || [];
                    populateScanHistoricalUrlsTable(currentScanDetails.historical_urls);
                }
            })
            .catch(error => {
                console.error('Error loading historical URLs:', error);
                scanHistoricalUrlsTable.innerHTML = '<tr><td>Error loading historical URLs</td></tr>';
            });
    }

    // Function to populate scan subdomains table
    function populateScanSubdomainsTable(subdomains) {
        scanSubdomainsTable.innerHTML = '';

        if (!subdomains || subdomains.length === 0) {
            scanSubdomainsTable.innerHTML = '<tr><td>No subdomains found</td></tr>';
            return;
        }

        subdomains.forEach(subdomain => {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.textContent = subdomain;
            row.appendChild(cell);
            scanSubdomainsTable.appendChild(row);
        });
    }

    // Function to populate scan live hosts table
    function populateScanLiveHostsTable(hosts) {
        scanLiveHostsTable.innerHTML = '';

        if (!hosts || hosts.length === 0) {
            scanLiveHostsTable.innerHTML = '<tr><td colspan="4">No live hosts found</td></tr>';
            return;
        }

        hosts.forEach(host => {
            const row = document.createElement('tr');

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
            techCell.textContent = host.technology || 'Unknown';

            // View ports button cell
            const portsCell = document.createElement('td');
            const viewPortsButton = document.createElement('button');
            viewPortsButton.textContent = 'View Ports';
            viewPortsButton.className = 'view-button-sm';
            viewPortsButton.dataset.hostId = host.id;
            viewPortsButton.addEventListener('click', function() {
                viewHostPorts(host.id, host.url);
            });
            portsCell.appendChild(viewPortsButton);

            row.appendChild(urlCell);
            row.appendChild(statusCell);
            row.appendChild(techCell);
            row.appendChild(portsCell);

            scanLiveHostsTable.appendChild(row);
        });
    }

    // Function to populate scan historical URLs table
    function populateScanHistoricalUrlsTable(urls) {
        scanHistoricalUrlsTable.innerHTML = '';

        if (!urls || urls.length === 0) {
            scanHistoricalUrlsTable.innerHTML = '<tr><td>No historical URLs found</td></tr>';
            return;
        }

        urls.forEach(url => {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            const link = document.createElement('a');
            link.href = url;
            link.textContent = url;
            link.target = '_blank';
            cell.appendChild(link);
            row.appendChild(cell);
            scanHistoricalUrlsTable.appendChild(row);
        });
    }

    // Function to view host ports
    function viewHostPorts(hostId, hostUrl) {
        fetch(`/host/${hostId}/ports`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.ports && data.ports.length > 0) {
                    showPortsModal(hostUrl, data.ports);
                } else {
                    alert(`No ports found for ${hostUrl}`);
                }
            })
            .catch(error => {
                console.error('Error loading ports:', error);
                alert('Error loading ports');
            });
    }

    // Function to show ports modal
    function showPortsModal(host, ports) {
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

        // Create a table for the ports
        const table = document.createElement('table');
        table.className = 'port-table';

        // Create table header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const portHeader = document.createElement('th');
        portHeader.textContent = 'Port';
        const serviceHeader = document.createElement('th');
        serviceHeader.textContent = 'Service';

        headerRow.appendChild(portHeader);
        headerRow.appendChild(serviceHeader);
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create table body
        const tbody = document.createElement('tbody');

        ports.forEach(port => {
            const row = document.createElement('tr');

            const portCell = document.createElement('td');
            portCell.textContent = port.port;

            const serviceCell = document.createElement('td');
            serviceCell.textContent = port.service || 'Unknown';

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

    // Function to rescan a domain
    function rescanDomain(domain) {
        // Create a form to submit the domain
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/scan';

        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'domain';
        input.value = domain;

        form.appendChild(input);
        document.body.appendChild(form);

        form.submit();
        document.body.removeChild(form);
    }
});
