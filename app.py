import os
import json
import subprocess
import requests
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# Create output directory if it doesn't exist
os.makedirs('output', exist_ok=True)

def check_tools():
    """Check if required tools are installed"""
    tools = {
        'subfinder': False,
        'httpx': False,
        'gau': False
    }

    try:
        # Check subfinder
        subprocess.run(['subfinder', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        tools['subfinder'] = True
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    try:
        # Check httpx
        subprocess.run(['httpx', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        tools['httpx'] = True
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    try:
        # Check gau
        subprocess.run(['gau', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        tools['gau'] = True
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return tools

def get_subdomains_subfinder(domain):
    """Get subdomains using subfinder"""
    output_file = f"output/subfinder_{domain}.txt"

    try:
        subprocess.run(
            ['subfinder', '-d', domain, '-o', output_file, '-silent'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return []
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

def get_subdomains_crtsh(domain):
    """Get subdomains from crt.sh"""
    output_file = f"output/crtsh_{domain}.txt"
    subdomains = []

    try:
        response = requests.get(f"https://crt.sh/?q=%.{domain}&output=json", timeout=30)
        if response.status_code == 200:
            data = response.json()

            # Extract domains from the JSON response
            for entry in data:
                domains = []
                if 'common_name' in entry and entry['common_name']:
                    domains.append(entry['common_name'])
                if 'name_value' in entry and entry['name_value']:
                    domains.extend(entry['name_value'].split('\\n'))

                for d in domains:
                    # Clean up the domain
                    d = d.strip()
                    if d.startswith('*.'):
                        d = d[2:]
                    if d and '@' not in d:
                        subdomains.append(d)

            # Remove duplicates
            subdomains = list(set(subdomains))

            # Save to file
            with open(output_file, 'w') as f:
                for subdomain in subdomains:
                    f.write(f"{subdomain}\n")

        return subdomains
    except Exception as e:
        print(f"Error fetching from crt.sh: {e}")
        return []

def check_live_hosts(domains, domain):
    """Check which domains are live using httpx"""
    output_file = f"output/httpx_{domain}.txt"
    results = []

    if not domains:
        return results

    # Save domains to a temporary file
    temp_file = f"output/domain_{domain}.txt"
    with open(temp_file, 'w') as f:
        for domain in domains:
            f.write(f"{domain}\n")

    try:
        # Run httpx
        process = subprocess.run(
            ['httpx', '-l', temp_file, '-silent', '-tech-detect', '-status-code', '-o', output_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )

        # Parse the results
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parts = line.split(' [')
                        if len(parts) >= 3:
                            url = parts[0]
                            status_code = parts[1].rstrip(']')
                            tech = parts[2].rstrip(']')
                            results.append({
                                'url': url,
                                'status_code': status_code,
                                'technology': tech
                            })
        return results
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"Error running httpx: {e}")
        return []

def get_historical_urls(domain):
    """Get historical URLs using gau"""
    output_file = f"output/gau_{domain}.txt"

    try:
        subprocess.run(
            ['gau', '--threads', '5', domain, '--o', output_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )

        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return []
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

@app.route('/')
def index():
    tools = check_tools()
    return render_template('index.html', tools=tools)

@app.route('/scan', methods=['POST'])
def scan():
    domain = request.form.get('domain', '').strip()

    if not domain:
        return jsonify({'error': 'Domain is required'}), 400

    # Clean up any existing output files
    for file_pattern in [f"output/subfinder_{domain}.txt", f"output/crtsh_{domain}.txt",
                         f"output/domain_{domain}.txt", f"output/httpx_{domain}.txt",
                         f"output/gau_{domain}.txt"]:
        if os.path.exists(file_pattern):
            os.remove(file_pattern)

    # Run tools in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        subfinder_future = executor.submit(get_subdomains_subfinder, domain)
        crtsh_future = executor.submit(get_subdomains_crtsh, domain)

        subfinder_results = subfinder_future.result()
        crtsh_results = crtsh_future.result()

    # Combine and deduplicate results
    all_domains = list(set(subfinder_results + crtsh_results))

    # Save combined domains
    with open(f"output/domain_{domain}.txt", 'w') as f:
        for d in all_domains:
            f.write(f"{d}\n")

    # Check live hosts
    live_hosts = check_live_hosts(all_domains, domain)

    # Get historical URLs (if gau is available)
    tools = check_tools()
    historical_urls = []
    if tools['gau']:
        historical_urls = get_historical_urls(domain)

    return jsonify({
        'domain': domain,
        'subdomains_count': len(all_domains),
        'live_hosts_count': len(live_hosts),
        'historical_urls_count': len(historical_urls),
        'subdomains': all_domains,
        'live_hosts': live_hosts,
        'historical_urls': historical_urls[:100]  # Limit to 100 for performance
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
