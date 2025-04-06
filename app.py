import os
import json
import subprocess
import requests
import re
import time
import uuid
import threading
import urllib.parse
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import datetime

from models import db, Scan, Subdomain, LiveHost, Port, HistoricalUrl

app = Flask(__name__)

# Configure SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reconaug.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database
db.init_app(app)

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
        'chaos_api': CHAOS_API_KEY != "",
        'sublist3r': False
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

    # Check Sublist3r
    try:
        # Check if Sublist3r directory exists
        if os.path.exists('/tools/Sublist3r/sublist3r.py'):
            tools['sublist3r'] = True
        else:
            # Try to run Sublist3r as a command
            subprocess.run(['sublist3r', '--help'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            tools['sublist3r'] = True
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return tools

def get_subdomains_sublist3r(domain):
    """Get subdomains using Sublist3r"""
    output_file = f"output/sublist3r_{domain}.txt"

    try:
        # Check if Sublist3r is available
        tools = check_tools()
        if not tools['sublist3r']:
            print("Sublist3r is not available. Skipping Sublist3r.")
            return []

        print(f"Running Sublist3r for {domain}...")

        # Check if Sublist3r is installed in /tools directory
        if os.path.exists('/tools/Sublist3r/sublist3r.py'):
            # Run Sublist3r from the installed directory
            subprocess.run(
                ['python3', '/tools/Sublist3r/sublist3r.py', '-d', domain, '-o', output_file, '-v'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False
            )
        else:
            # Run Sublist3r as a command
            subprocess.run(
                ['sublist3r', '-d', domain, '-o', output_file, '-v'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False
            )

        # Read the output file
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                subdomains = [line.strip() for line in f if line.strip()]
            print(f"Found {len(subdomains)} subdomains with Sublist3r")
            return subdomains
        return []
    except Exception as e:
        print(f"Error running Sublist3r: {e}")
        return []

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

@app.route('/history')
def scan_history_page():
    return render_template('history.html')

@app.route('/debug/database')
def debug_database():
    """Debug endpoint to check database contents"""
    try:
        # Get all scans
        scans = Scan.query.all()
        scan_data = []

        for scan in scans:
            scan_info = scan.to_dict()
            scan_info['subdomains_count_actual'] = Subdomain.query.filter_by(scan_id=scan.id).count()
            scan_info['live_hosts_count_actual'] = LiveHost.query.filter_by(scan_id=scan.id).count()
            scan_data.append(scan_info)

        # Get database stats
        stats = {
            'total_scans': Scan.query.count(),
            'total_subdomains': Subdomain.query.count(),
            'total_live_hosts': LiveHost.query.count(),
            'total_ports': Port.query.count(),
            'total_historical_urls': HistoricalUrl.query.count()
        }

        return jsonify({
            'stats': stats,
            'scans': scan_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/clear-database')
def clear_database():
    """Debug endpoint to clear the database"""
    try:
        # Delete all records from all tables
        HistoricalUrl.query.delete()
        Port.query.delete()
        LiveHost.query.delete()
        Subdomain.query.delete()
        Scan.query.delete()

        # Commit the changes
        db.session.commit()

        # Add a test scan
        add_test_scan()

        return jsonify({
            'message': 'Database cleared successfully',
            'status': 'success'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def run_scan_in_background(task_id, domain):
    """Run the scan in a background thread and update progress"""
    try:
        # Update task status
        task_manager.update_task(task_id, status='running', message='Starting subdomain discovery...')

        # Clean up any existing output files
        for file_pattern in [f"output/subfinder_{domain}.txt", f"output/crtsh_{domain}.txt",
                            f"output/domain_{domain}.txt", f"output/httpx_{domain}.txt",
                            f"output/gau_{domain}.txt", f"output/sublist3r_{domain}.txt"]:
            if os.path.exists(file_pattern):
                os.remove(file_pattern)

        # Run subdomain discovery tools in parallel
        task_manager.update_task(task_id, progress=10, message='Running subfinder and Sublist3r...')
        with ThreadPoolExecutor(max_workers=3) as executor:
            subfinder_future = executor.submit(get_subdomains_subfinder, domain)
            sublist3r_future = executor.submit(get_subdomains_sublist3r, domain)

            # Update progress while other tools are running
            task_manager.update_task(task_id, progress=15, message='Running crt.sh and other passive sources...')
            crtsh_future = executor.submit(get_subdomains_crtsh, domain)

            subfinder_results = subfinder_future.result()
            task_manager.update_task(task_id, progress=25, message=f'Found {len(subfinder_results)} subdomains with subfinder')

            sublist3r_results = sublist3r_future.result()
            task_manager.update_task(task_id, progress=30, message=f'Found {len(sublist3r_results)} subdomains with Sublist3r')

            crtsh_results = crtsh_future.result()
            task_manager.update_task(task_id, progress=40, message=f'Found {len(crtsh_results)} subdomains with passive sources')

        # Combine and deduplicate results
        all_domains = list(set(subfinder_results + sublist3r_results + crtsh_results))
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

        # Save results to database
        try:
            print(f"Saving scan results to database for domain: {domain}")
            print(f"Found {len(all_domains)} subdomains and {len(live_hosts)} live hosts")

            # Use application context for database operations
            with app.app_context():
                scan_id = save_scan_to_database(domain, all_domains, live_hosts)
                if scan_id:
                    print(f"Scan results saved successfully with ID: {scan_id}")
                    db_message = f'Scan complete. Results saved to database (ID: {scan_id}).'
                else:
                    print("Failed to save scan results to database")
                    db_message = 'Scan complete. Note: Failed to save results to database.'
        except Exception as db_error:
            print(f"Error saving to database: {db_error}")
            import traceback
            traceback.print_exc()
            db_message = 'Scan complete. Note: Failed to save results to database.'

        # Scan complete
        task_manager.update_task(
            task_id,
            status='complete',
            progress=100,
            message=f'Scan complete. Found {len(all_domains)} subdomains and {len(live_hosts)} live hosts. {db_message}',
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

    # Try to find the most recent scan for this domain to associate the URLs with
    try:
        # Use application context for database operations
        with app.app_context():
            scan = Scan.query.filter_by(domain=domain).order_by(Scan.timestamp.desc()).first()
            if scan:
                print(f"Found scan ID {scan.id} for domain {domain}")
                # Check if we already have historical URLs for this scan
                existing_urls = HistoricalUrl.query.filter_by(scan_id=scan.id).count()
                if existing_urls == 0:
                    print(f"No existing historical URLs for scan ID {scan.id}, saving {len(urls)} URLs")
                    # Save historical URLs to database
                    for url in urls:
                        db.session.add(HistoricalUrl(
                            scan_id=scan.id,
                            url=url
                        ))
                    db.session.commit()
                    print(f"Saved {len(urls)} historical URLs to database for scan ID {scan.id}")
                else:
                    print(f"Found {existing_urls} existing historical URLs for scan ID {scan.id}, skipping")
            else:
                print(f"No scan found for domain {domain}")
    except Exception as e:
        print(f"Error saving historical URLs to database: {e}")
        import traceback
        traceback.print_exc()

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

    # Save port scan results to database
    try:
        # Use application context for database operations
        with app.app_context():
            success = save_ports_to_database(host, ports)
            if success:
                print(f"Saved {len(ports)} ports to database for host {host}")
            else:
                print(f"Failed to save ports to database for host {host}")
    except Exception as e:
        print(f"Error saving ports to database: {e}")
        import traceback
        traceback.print_exc()

    return jsonify({
        'host': host,
        'count': len(ports),
        'ports': ports
    })

# Create a function to create database tables
def create_tables():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully")

# Helper function to save scan results to database
def save_scan_to_database(domain, subdomains, live_hosts, historical_urls=None):
    """Save scan results to the database"""
    try:
        print(f"Starting database save for domain: {domain}")

        # Create a new scan record
        scan = Scan(
            domain=domain,
            timestamp=datetime.utcnow(),
            status='complete',
            subdomains_count=len(subdomains),
            live_hosts_count=len(live_hosts)
        )
        db.session.add(scan)
        db.session.flush()  # Get the scan ID without committing
        print(f"Created scan record with ID: {scan.id}")

        # Add subdomains
        print(f"Adding {len(subdomains)} subdomains to database")
        for subdomain in subdomains:
            db.session.add(Subdomain(
                scan_id=scan.id,
                name=subdomain,
                source='combined'  # We don't track individual sources in this version
            ))

        # Add live hosts
        print(f"Adding {len(live_hosts)} live hosts to database")
        for host in live_hosts:
            try:
                live_host = LiveHost(
                    scan_id=scan.id,
                    url=host['url'],
                    status_code=host['status_code'],
                    technology=host['technology']
                )
                db.session.add(live_host)
                db.session.flush()  # Get the live host ID
            except KeyError as ke:
                print(f"KeyError in live host data: {ke}. Host data: {host}")
                # Continue with other hosts even if one fails
                continue

        # Add historical URLs if available
        if historical_urls:
            print(f"Adding {len(historical_urls)} historical URLs to database")
            for url in historical_urls:
                db.session.add(HistoricalUrl(
                    scan_id=scan.id,
                    url=url
                ))

        # Commit all changes
        db.session.commit()
        print(f"Scan results for {domain} saved to database successfully")
        return scan.id
    except Exception as e:
        db.session.rollback()
        print(f"Error saving scan results to database: {e}")
        import traceback
        traceback.print_exc()
        return None

# Helper function to save port scan results to database
def save_ports_to_database(host_url, ports):
    """Save port scan results to the database"""
    try:
        # Find the live host record
        host = LiveHost.query.filter_by(url=host_url).first()
        if not host:
            print(f"Live host {host_url} not found in database")
            return False

        # Add ports
        for port in ports:
            db.session.add(Port(
                host_id=host.id,
                port_number=port,
                service=get_common_service(port)
            ))

        # Commit changes
        db.session.commit()
        print(f"Port scan results for {host_url} saved to database")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error saving port scan results to database: {e}")
        return False

# Helper function to get common service name for a port
def get_common_service(port):
    """Return common service name for a port number"""
    common_ports = {
        21: 'FTP',
        22: 'SSH',
        23: 'Telnet',
        25: 'SMTP',
        53: 'DNS',
        80: 'HTTP',
        110: 'POP3',
        143: 'IMAP',
        443: 'HTTPS',
        445: 'SMB',
        3306: 'MySQL',
        3389: 'RDP',
        5432: 'PostgreSQL',
        8080: 'HTTP-Proxy',
        8443: 'HTTPS-Alt'
    }
    return common_ports.get(port, 'Unknown')

# Route to get scan history
@app.route('/scan-history')
def scan_history():
    """Get scan history"""
    try:
        print("Fetching scan history from database...")
        scans = Scan.query.order_by(Scan.timestamp.desc()).all()
        print(f"Found {len(scans)} scan records in database")

        # Convert to dict and log for debugging
        scan_dicts = [scan.to_dict() for scan in scans]
        print(f"Returning {len(scan_dicts)} scan records as JSON")

        return jsonify({
            'scans': scan_dicts
        })
    except Exception as e:
        print(f"Error fetching scan history: {e}")
        return jsonify({'error': str(e), 'message': 'Failed to fetch scan history'}), 500

# Route to get scan details
@app.route('/scan/<int:scan_id>')
def scan_details_api(scan_id):
    """API endpoint to get details of a specific scan"""
    try:
        scan = Scan.query.get_or_404(scan_id)
        subdomains = [s.name for s in scan.subdomains]
        live_hosts = [h.to_dict() for h in scan.live_hosts]

        return jsonify({
            'scan': scan.to_dict(),
            'subdomains': subdomains,
            'live_hosts': live_hosts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/scan-details/<int:scan_id>')
def scan_details_page(scan_id):
    """Page to display details of a specific scan"""
    try:
        scan = Scan.query.get_or_404(scan_id)
        subdomains = [s.name for s in scan.subdomains]
        live_hosts = [h.to_dict() for h in scan.live_hosts]

        # Get historical URLs
        historical_urls = [h.url for h in HistoricalUrl.query.filter_by(scan_id=scan_id).all()]

        return render_template(
            'scan_details.html',
            scan=scan,
            subdomains=subdomains,
            live_hosts=live_hosts,
            historical_urls=historical_urls
        )
    except Exception as e:
        print(f"Error rendering scan details page: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500

# Route to get historical URLs for a scan
@app.route('/scan/<int:scan_id>/historical-urls')
def scan_historical_urls(scan_id):
    """Get historical URLs for a specific scan"""
    try:
        urls = HistoricalUrl.query.filter_by(scan_id=scan_id).all()
        return jsonify({
            'urls': [url.url for url in urls]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Route to get ports for a live host
@app.route('/host/<int:host_id>/ports')
def host_ports(host_id):
    """Get ports for a specific live host"""
    try:
        host = LiveHost.query.get_or_404(host_id)
        ports = [{
            'port': p.port_number,
            'service': p.service
        } for p in host.ports]

        return jsonify({
            'host': host.to_dict(),
            'ports': ports
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Create tables when the app starts
create_tables()

# Initialize the database if needed
def initialize_database():
    with app.app_context():
        # Just make sure the tables exist
        print("Initializing database...")
        try:
            db.create_all()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Error initializing database: {e}")

# Initialize the database
initialize_database()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
