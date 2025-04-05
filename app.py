import os
import json
import subprocess
import requests
import re
import time
import uuid
import threading
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict

app = Flask(__name__)

# Create output directory if it doesn't exist
os.makedirs('output', exist_ok=True)

# Task manager for background tasks
class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.lock = threading.Lock()

    def create_task(self, domain):
        task_id = str(uuid.uuid4())
        with self.lock:
            self.tasks[task_id] = {
                'domain': domain,
                'status': 'starting',
                'progress': 0,
                'message': 'Initializing scan...',
                'subdomains': [],
                'subdomains_count': 0,
                'live_hosts': [],
                'live_hosts_count': 0,
                'start_time': time.time(),
                'last_update': time.time(),
                'complete': False
            }
        return task_id

    def update_task(self, task_id, **kwargs):
        with self.lock:
            if task_id in self.tasks:
                for key, value in kwargs.items():
                    self.tasks[task_id][key] = value
                self.tasks[task_id]['last_update'] = time.time()

    def get_task(self, task_id):
        with self.lock:
            return self.tasks.get(task_id, None)

    def clean_old_tasks(self, max_age=3600):  # Clean tasks older than 1 hour
        current_time = time.time()
        with self.lock:
            for task_id in list(self.tasks.keys()):
                if current_time - self.tasks[task_id]['last_update'] > max_age:
                    del self.tasks[task_id]

# Initialize task manager
task_manager = TaskManager()

# Chaos API key for ProjectDiscovery
CHAOS_API_KEY = "47a628d5-3721-4ae6-8369-a1111e509cfb"

def check_tools():
    """Check if required tools are installed"""
    tools = {
        'subfinder': False,
        'httpx': False,
        'gau': False,
        'naabu': False,
        'chaos_api': CHAOS_API_KEY != ""
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

    try:
        # Check naabu
        subprocess.run(['naabu', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        tools['naabu'] = True
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

def get_subdomains_from_chaos(domain):
    """Get subdomains from ProjectDiscovery's Chaos API"""
    subdomains = []

    if not CHAOS_API_KEY:
        print("Chaos API key not available. Skipping Chaos API.")
        return subdomains

    try:
        print(f"Fetching subdomains from Chaos API for {domain}...")
        headers = {"Authorization": CHAOS_API_KEY}
        chaos_url = f"https://dns.projectdiscovery.io/dns/{domain}/subdomains"

        response = requests.get(chaos_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if 'subdomains' in data:
                for subdomain in data['subdomains']:
                    full_domain = f"{subdomain}.{domain}"
                    subdomains.append(full_domain)
                print(f"Found {len(subdomains)} subdomains from Chaos API")
            else:
                print("No subdomains found in Chaos API response")
        else:
            print(f"Error fetching from Chaos API: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error fetching from Chaos API: {e}")

    return subdomains

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

        # Get subdomains from Chaos API
        chaos_subdomains = get_subdomains_from_chaos(domain)
        subdomains.extend(chaos_subdomains)

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

def check_ports(host):
    """Check for open ports using naabu"""
    output_file = f"output/naabu_{host}.txt"

    try:
        # Check if naabu is available
        try:
            subprocess.run(['naabu', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        except (FileNotFoundError, subprocess.SubprocessError):
            return [], "Naabu tool is not installed"

        # Run naabu command with common ports
        print(f"Running port scan on {host}...")
        process = subprocess.run(
            ['naabu', '-host', host, '-top-ports', '100', '-silent'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True
        )

        # Parse the output directly from stdout
        ports = []
        if process.stdout:
            for line in process.stdout.splitlines():
                line = line.strip()
                if line and ':' in line:
                    # Format is typically host:port
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[1].isdigit():
                        port = int(parts[1])
                        ports.append(port)

            # Save to file for reference
            with open(output_file, 'w') as f:
                for port in sorted(ports):
                    f.write(f"{port}\n")

        # If no ports found in stdout, try to read from the output file
        if not ports and os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and line.isdigit():
                        ports.append(int(line))

        return sorted(ports), None
    except Exception as e:
        print(f"Error running naabu: {e}")
        return [], str(e)

@app.route('/')
def index():
    return render_template('index.html')

def run_scan_in_background(task_id, domain):
    """Run the scan in a background thread and update progress"""
    try:
        # Update task status
        task_manager.update_task(task_id, status='running', message='Starting subdomain discovery...')

        # Clean up any existing output files
        for file_pattern in [f"output/subfinder_{domain}.txt", f"output/crtsh_{domain}.txt",
                            f"output/domain_{domain}.txt", f"output/httpx_{domain}.txt",
                            f"output/gau_{domain}.txt"]:
            if os.path.exists(file_pattern):
                os.remove(file_pattern)

        # Run subdomain discovery tools in parallel
        task_manager.update_task(task_id, progress=10, message='Running subfinder...')
        with ThreadPoolExecutor(max_workers=2) as executor:
            subfinder_future = executor.submit(get_subdomains_subfinder, domain)

            # Update progress while subfinder is running
            task_manager.update_task(task_id, progress=15, message='Running crt.sh and other passive sources...')
            crtsh_future = executor.submit(get_subdomains_crtsh, domain)

            subfinder_results = subfinder_future.result()
            task_manager.update_task(task_id, progress=30, message=f'Found {len(subfinder_results)} subdomains with subfinder')

            crtsh_results = crtsh_future.result()
            task_manager.update_task(task_id, progress=40, message=f'Found {len(crtsh_results)} subdomains with passive sources')

        # Combine and deduplicate results
        all_domains = list(set(subfinder_results + crtsh_results))
        task_manager.update_task(
            task_id,
            progress=50,
            message=f'Found {len(all_domains)} unique subdomains',
            subdomains=all_domains,
            subdomains_count=len(all_domains)
        )

        # Save combined domains
        with open(f"output/domain_{domain}.txt", 'w') as f:
            for d in all_domains:
                f.write(f"{d}\n")

        # Start checking live hosts
        task_manager.update_task(task_id, progress=60, message='Starting live host discovery with httpx...')

        # Process live hosts in batches to provide updates
        batch_size = max(10, len(all_domains) // 10)  # Process in 10 batches or batches of 10, whichever is larger
        live_hosts = []

        for i in range(0, len(all_domains), batch_size):
            batch = all_domains[i:i+batch_size]
            progress = 60 + int((i / len(all_domains)) * 35)  # Progress from 60% to 95%
            task_manager.update_task(
                task_id,
                progress=progress,
                message=f'Checking live hosts ({i}/{len(all_domains)})...'
            )

            batch_results = check_live_hosts(batch, domain)
            live_hosts.extend(batch_results)

            # Update live hosts as they come in
            task_manager.update_task(
                task_id,
                live_hosts=live_hosts,
                live_hosts_count=len(live_hosts)
            )

        # Scan complete
        task_manager.update_task(
            task_id,
            status='complete',
            progress=100,
            message=f'Scan complete. Found {len(all_domains)} subdomains and {len(live_hosts)} live hosts.',
            complete=True
        )

    except Exception as e:
        # Update task with error
        task_manager.update_task(
            task_id,
            status='error',
            message=f'Error during scan: {str(e)}',
            complete=True
        )
        print(f"Error in background scan: {e}")

@app.route('/scan', methods=['POST'])
def scan():
    domain = request.form.get('domain', '').strip()

    if not domain:
        return jsonify({'error': 'Domain is required'}), 400

    # Create a new task
    task_id = task_manager.create_task(domain)

    # Start the scan in a background thread
    threading.Thread(target=run_scan_in_background, args=(task_id, domain)).start()

    # Return the task ID immediately
    return jsonify({
        'task_id': task_id,
        'domain': domain,
        'status': 'started'
    })

@app.route('/task/<task_id>', methods=['GET'])
def get_task(task_id):
    """Get the current status of a task"""
    task = task_manager.get_task(task_id)

    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify(task)

@app.route('/task/<task_id>/events')
def task_events(task_id):
    """Server-Sent Events endpoint for real-time task updates"""
    def generate():
        last_progress = -1
        last_status = None
        last_message = None
        last_subdomains_count = 0
        last_live_hosts_count = 0

        # Initial delay to allow the task to start
        time.sleep(0.5)

        while True:
            task = task_manager.get_task(task_id)

            if not task:
                # Task not found, send error and end stream
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                break

            # Check if there are updates to send
            if (task['progress'] != last_progress or
                task['status'] != last_status or
                task['message'] != last_message or
                task['subdomains_count'] != last_subdomains_count or
                task['live_hosts_count'] != last_live_hosts_count):

                # Send the update
                yield f"data: {json.dumps({k: v for k, v in task.items() if k not in ['subdomains', 'live_hosts']})}\n\n"

                # Update last values
                last_progress = task['progress']
                last_status = task['status']
                last_message = task['message']
                last_subdomains_count = task['subdomains_count']
                last_live_hosts_count = task['live_hosts_count']

            # If task is complete, end the stream
            if task['complete']:
                break

            # Wait before checking again
            time.sleep(1)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

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

@app.route('/scan-ports', methods=['GET'])
def scan_ports():
    host = request.args.get('host', '').strip()

    if not host:
        return jsonify({'error': 'Host is required'}), 400

    print(f"Running port scan for {host}...")
    # Run port scan for the specific host
    ports, error = check_ports(host)

    if error:
        print(f"Error running port scan for {host}: {error}")
        return jsonify({
            'error': error,
            'ports': []
        }), 500

    print(f"Found {len(ports)} open ports for {host}")
    return jsonify({
        'host': host,
        'count': len(ports),
        'ports': ports
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
