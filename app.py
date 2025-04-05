import os
import json
import subprocess
import requests
import re
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
    """Get subdomains using subfinder with multithreading"""
    output_file = f"output/subfinder_{domain}.txt"

    try:
        # Check if subfinder is available
        tools = check_tools()
        if not tools['subfinder']:
            return []

        # Run subfinder with increased threads (default is 10)
        subprocess.run(
            ['subfinder', '-d', domain, '-o', output_file, '-silent', '-t', '50'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return []
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"Error running subfinder: {e}")
        return []

def get_subdomains_crtsh(domain):
    """Get subdomains from crt.sh and other sources"""
    output_file = f"output/crtsh_{domain}.txt"
    subdomains = []

    try:
        # Get subdomains from crt.sh
        print(f"Fetching subdomains from crt.sh for {domain}...")
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
                    if d and '@' not in d and domain in d:
                        subdomains.append(d)

        # Get subdomains from Alienvault OTX
        print(f"Fetching subdomains from AlienVault OTX for {domain}...")
        try:
            otx_url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"
            otx_response = requests.get(otx_url, timeout=30)
            if otx_response.status_code == 200:
                otx_data = otx_response.json()
                if 'passive_dns' in otx_data:
                    for entry in otx_data['passive_dns']:
                        if 'hostname' in entry and domain in entry['hostname']:
                            subdomains.append(entry['hostname'])
        except Exception as e:
            print(f"Error fetching from AlienVault OTX: {e}")

        # Get subdomains from SecurityTrails (if API key is available)
        # Note: This requires an API key, so it's commented out by default
        # try:
        #     headers = {"APIKEY": "YOUR_API_KEY"}
        #     st_url = f"https://api.securitytrails.com/v1/domain/{domain}/subdomains"
        #     st_response = requests.get(st_url, headers=headers, timeout=30)
        #     if st_response.status_code == 200:
        #         st_data = st_response.json()
        #         if 'subdomains' in st_data:
        #             for subdomain in st_data['subdomains']:
        #                 subdomains.append(f"{subdomain}.{domain}")
        # except Exception as e:
        #     print(f"Error fetching from SecurityTrails: {e}")

        # Remove duplicates
        subdomains = list(set(subdomains))
        print(f"Found {len(subdomains)} subdomains from passive sources for {domain}")

        # Save to file
        with open(output_file, 'w') as f:
            for subdomain in subdomains:
                f.write(f"{subdomain}\n")

        return subdomains
    except Exception as e:
        print(f"Error in passive subdomain enumeration: {e}")
        return []

def check_live_hosts(domains, domain):
    """Check which domains are live using httpx with multithreading"""
    output_file = f"output/httpx_{domain}.txt"
    results = []

    if not domains:
        return results

    # Check if httpx is available
    tools = check_tools()
    if not tools['httpx']:
        return results

    # Save domains to a temporary file
    temp_file = f"output/domain_{domain}.txt"
    with open(temp_file, 'w') as f:
        for domain in domains:
            f.write(f"{domain}\n")

    try:
        # Run httpx with increased threads (default is 50) and no-color option
        process = subprocess.run(
            ['httpx', '-l', temp_file, '-silent', '-tech-detect', '-status-code', '-no-color',
             '-threads', '100', '-rate-limit', '150', '-o', output_file],
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
                            # Remove ANSI color codes from status code
                            status_code = parts[1].rstrip(']')
                            status_code = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', status_code)
                            status_code = re.sub(r'\[\d+m', '', status_code).strip()

                            # Try to convert to integer for proper comparison in frontend
                            try:
                                int(status_code)
                            except ValueError:
                                # If it's not a valid integer, extract digits
                                status_code = re.sub(r'\D', '', status_code) or '0'

                            # Remove ANSI color codes from technology
                            tech = parts[2].rstrip(']')
                            tech = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', tech)
                            tech = re.sub(r'\[\d+m', '', tech).strip()

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
        # Check if gau is available
        tools = check_tools()
        if not tools['gau']:
            return [], "GAU tool is not installed"

        # Run gau command with increased threads
        process = subprocess.run(
            ['gau', '--threads', '50', domain],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True
        )

        # Parse the output directly from stdout
        urls = []
        if process.stdout:
            urls = [line.strip() for line in process.stdout.splitlines() if line.strip()]

            # Save to file for reference
            with open(output_file, 'w') as f:
                for url in urls:
                    f.write(f"{url}\n")

        return urls, None
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        return [], str(e)

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

    # Run subdomain discovery tools in parallel
    print(f"Starting subdomain discovery for {domain}...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        subfinder_future = executor.submit(get_subdomains_subfinder, domain)
        crtsh_future = executor.submit(get_subdomains_crtsh, domain)

        subfinder_results = subfinder_future.result()
        crtsh_results = crtsh_future.result()

    # Combine and deduplicate results
    all_domains = list(set(subfinder_results + crtsh_results))
    print(f"Found {len(all_domains)} unique subdomains for {domain}")

    # Save combined domains
    with open(f"output/domain_{domain}.txt", 'w') as f:
        for d in all_domains:
            f.write(f"{d}\n")

    # Check live hosts in a separate thread
    print(f"Checking live hosts for {domain}...")
    with ThreadPoolExecutor(max_workers=1) as executor:
        live_hosts_future = executor.submit(check_live_hosts, all_domains, domain)
        live_hosts = live_hosts_future.result()

    print(f"Found {len(live_hosts)} live hosts for {domain}")

    return jsonify({
        'domain': domain,
        'subdomains_count': len(all_domains),
        'live_hosts_count': len(live_hosts),
        'subdomains': all_domains,
        'live_hosts': live_hosts
    })

@app.route('/run-gau', methods=['GET'])
def run_gau():
    domain = request.args.get('domain', '').strip()

    if not domain:
        return jsonify({'error': 'Domain is required'}), 400

    print(f"Running GAU for {domain}...")
    # Run GAU for the specific domain
    urls, error = get_historical_urls(domain)

    if error:
        print(f"Error running GAU for {domain}: {error}")
        return jsonify({
            'error': error,
            'urls': []
        }), 500

    print(f"Found {len(urls)} historical URLs for {domain}")
    return jsonify({
        'domain': domain,
        'count': len(urls),
        'urls': urls
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
