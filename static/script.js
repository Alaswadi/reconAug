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
        historicalUrls: []
    };
    
    // Handle form submission
    scanForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const domain = document.getElementById('domain').value.trim();
        
        if (!domain) {
            alert('Please enter a domain');
            return;
        }
        
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
            // Store the full results
            fullResults.liveHosts = data.live_hosts || [];
            fullResults.subdomains = data.subdomains || [];
            fullResults.historicalUrls = data.historical_urls || [];
            
            // Update the UI
            resultDomain.textContent = data.domain;
            subdomainsCount.textContent = data.subdomains_count;
            liveHostsCount.textContent = data.live_hosts_count;
            historicalUrlsCount.textContent = data.historical_urls_count;
            
            // Populate tables
            populateLiveHostsTable(fullResults.liveHosts);
            populateSubdomainsTable(fullResults.subdomains);
            populateHistoricalUrlsTable(fullResults.historicalUrls);
            
            // Hide loading, show results
            loadingDiv.classList.add('hidden');
            resultsDiv.classList.remove('hidden');
            scanButton.disabled = false;
            scanButton.innerHTML = '<i class="fas fa-search"></i> Scan';
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while scanning. Please try again.');
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
        const filteredUrls = fullResults.historicalUrls.filter(url => 
            url.toLowerCase().includes(filterValue)
        );
        populateHistoricalUrlsTable(filteredUrls);
    });
    
    // Helper functions to populate tables
    function populateLiveHostsTable(hosts) {
        liveHostsTable.innerHTML = '';
        
        if (hosts.length === 0) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 3;
            cell.textContent = 'No live hosts found';
            cell.style.textAlign = 'center';
            row.appendChild(cell);
            liveHostsTable.appendChild(row);
            return;
        }
        
        hosts.forEach(host => {
            const row = document.createElement('tr');
            
            const urlCell = document.createElement('td');
            const urlLink = document.createElement('a');
            urlLink.href = host.url;
            urlLink.textContent = host.url;
            urlLink.target = '_blank';
            urlCell.appendChild(urlLink);
            
            const statusCell = document.createElement('td');
            statusCell.textContent = host.status_code;
            
            const techCell = document.createElement('td');
            techCell.textContent = host.technology;
            
            row.appendChild(urlCell);
            row.appendChild(statusCell);
            row.appendChild(techCell);
            
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
    
    function populateHistoricalUrlsTable(urls) {
        historicalUrlsTable.innerHTML = '';
        
        if (urls.length === 0) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.textContent = 'No historical URLs found';
            cell.style.textAlign = 'center';
            row.appendChild(cell);
            historicalUrlsTable.appendChild(row);
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
            historicalUrlsTable.appendChild(row);
        });
    }
});
