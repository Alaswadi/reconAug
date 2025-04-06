// Scan History functionality
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const scanHistoryTable = document.getElementById('scanHistoryTable');
    const scanHistoryFilter = document.getElementById('scanHistoryFilter');

    // Store the full scan history
    let scanHistory = [];

    // Load scan history when the page loads
    loadScanHistory();

    // Refresh scan history every 30 seconds
    setInterval(loadScanHistory, 30000);

    // Add refresh button functionality
    const refreshButton = document.getElementById('refreshButton');
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            console.log('Manual refresh triggered');
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
            this.disabled = true;

            loadScanHistory();

            // Re-enable button after 2 seconds
            setTimeout(() => {
                this.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
                this.disabled = false;
            }, 2000);
        });
    }

    // Add clear database button functionality
    const clearDatabaseButton = document.getElementById('clearDatabaseButton');
    if (clearDatabaseButton) {
        clearDatabaseButton.addEventListener('click', function() {
            if (confirm('Are you sure you want to clear the database? This will delete all scan history.')) {
                console.log('Clearing database...');
                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Clearing...';
                this.disabled = true;

                fetch('/api/debug/clear-database')
                    .then(response => response.json())
                    .then(data => {
                        console.log('Database cleared:', data);
                        if (data.status === 'success') {
                            alert('Database cleared successfully');
                        } else {
                            alert(`Error clearing database: ${data.error}`);
                        }

                        // Reload scan history
                        loadScanHistory();

                        // Re-enable button
                        this.innerHTML = '<i class="fas fa-trash-alt"></i> Clear Database';
                        this.disabled = false;
                    })
                    .catch(error => {
                        console.error('Error clearing database:', error);
                        alert(`Error clearing database: ${error.message}`);

                        // Re-enable button
                        this.innerHTML = '<i class="fas fa-trash-alt"></i> Clear Database';
                        this.disabled = false;
                    });
            }
        });
    }

    // Filter scan history
    scanHistoryFilter.addEventListener('input', function() {
        const filterValue = this.value.toLowerCase();
        const filteredScans = scanHistory.filter(scan =>
            scan.domain.toLowerCase().includes(filterValue)
        );
        populateScanHistoryTable(filteredScans);
    });

    // Function to load scan history
    function loadScanHistory() {
        console.log('Loading scan history...');
        scanHistoryTable.innerHTML = '<tr><td colspan="5">Loading scan history...</td></tr>';

        fetch('/api/scan-history')
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

        if (!scans || scans.length === 0) {
            scanHistoryTable.innerHTML = '<tr><td colspan="5" class="no-data">No scan history found. Try scanning a domain from the home page.</td></tr>';
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
                // Navigate to the scan details page
                window.location.href = `/scan/scan-details/${scan.id}`;
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
