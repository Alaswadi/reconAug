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

def run_gau_in_background(task_id, domain):
    """Run GAU in a background thread and update progress"""
    try:
        # Initialize task
        task_manager.update_task(task_id, status='running', message=f'Running GAU for {domain}...', urls_count=0)

        # Run GAU for the specific domain
        urls, error = get_historical_urls(domain)

        if error:
            print(f"Error running GAU for {domain}: {error}")
            task_manager.update_task(
                task_id,
                status='error',
                message=f'Error running GAU: {error}',
                complete=True
            )
            return

        # Update task with results
        print(f"Found {len(urls)} historical URLs for {domain}")
        task_manager.update_task(
            task_id,
            status='complete',
            message=f'Found {len(urls)} historical URLs',
            urls=urls,
            urls_count=len(urls),
            complete=True
        )
    except Exception as e:
        print(f"Error in background GAU: {e}")
        task_manager.update_task(
            task_id,
            status='error',
            message=f'Error: {str(e)}',
            complete=True
        )

@app.route('/run-gau', methods=['GET'])
def run_gau():
    domain = request.args.get('domain', '').strip()

    if not domain:
        return jsonify({'error': 'Domain is required'}), 400

    # Create a task ID for this GAU run
    task_id = f"gau-{domain}"

    # Check if there's already a completed task for this domain
    existing_task = task_manager.get_task(task_id)
    if existing_task and existing_task['complete'] and existing_task['status'] == 'complete':
        # Return cached results
        return jsonify({
            'domain': domain,
            'count': existing_task['urls_count'],
            'urls': existing_task['urls']
        })

    # Create a new task with the custom task_id
    with task_manager.lock:
        task_manager.tasks[task_id] = {
            'domain': domain,
            'status': 'starting',
            'progress': 0,
            'message': 'Initializing GAU scan...',
            'urls': [],
            'urls_count': 0,
            'start_time': time.time(),
            'last_update': time.time(),
            'complete': False
        }

    # Start GAU in a background thread
    threading.Thread(target=run_gau_in_background, args=(task_id, domain)).start()

    # Return immediately with a task ID
    return jsonify({
        'task_id': task_id,
        'domain': domain,
        'status': 'started'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
