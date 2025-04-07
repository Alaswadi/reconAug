import os
import subprocess
import requests
import urllib3
from reconaug.tools.checker import check_tools

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_live_hosts(domains):
    """Check which domains are live using direct HTTP requests"""
    if not domains:
        print("No domains provided to check_live_hosts")
        return []

    print(f"Checking live hosts for {len(domains)} domains")

    # Use direct HTTP requests instead of httpx
    live_hosts = []
    for domain in domains:
        try:
            # Try HTTPS first
            url = f"https://{domain}"
            print(f"Checking {url}")
            response = requests.get(url, timeout=5, allow_redirects=True, verify=False)
            status_code = str(response.status_code)

            # Try to detect technology
            server = response.headers.get('Server', '')
            tech = server if server else 'Unknown'

            live_hosts.append({
                'url': url,
                'status_code': status_code,
                'technology': tech
            })
            print(f"Found live host: {url} (Status: {status_code}, Tech: {tech})")
        except requests.RequestException as e:
            try:
                # Try HTTP if HTTPS fails
                url = f"http://{domain}"
                print(f"HTTPS failed, trying {url}")
                response = requests.get(url, timeout=5, allow_redirects=True)
                status_code = str(response.status_code)

                # Try to detect technology
                server = response.headers.get('Server', '')
                tech = server if server else 'Unknown'

                live_hosts.append({
                    'url': url,
                    'status_code': status_code,
                    'technology': tech
                })
                print(f"Found live host: {url} (Status: {status_code}, Tech: {tech})")
            except requests.RequestException as e2:
                print(f"Host {domain} is not live: {e2}")

    print(f"Found {len(live_hosts)} live hosts out of {len(domains)} domains")
    return live_hosts

def get_historical_urls(domain):
    """Get historical URLs for a domain using gau"""
    output_file = f"output/gau_{domain}.txt"

    try:
        # Check if gau is available
        tools = check_tools()
        if not tools['gau']:
            return [], "gau tool not available"

        # Run gau
        subprocess.run(
            ['gau', domain, '--o', output_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        # Read the output file
        urls = []
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]

        return urls, None
    except subprocess.CalledProcessError as e:
        return [], f"Error running gau: {e}"
    except Exception as e:
        return [], f"Unexpected error: {e}"

def scan_ports(host):
    """Scan ports for a host using naabu"""
    # Clean up the host - remove protocol and path if it's a URL
    clean_host = host
    if '://' in host:
        clean_host = host.split('://', 1)[1].split('/', 1)[0]

    # Remove any port number if present
    if ':' in clean_host:
        clean_host = clean_host.split(':', 1)[0]

    print(f"Scanning ports for host: {clean_host} (original: {host})")
    output_file = f"output/naabu_{clean_host}.txt"

    try:
        # Check if naabu is available
        tools = check_tools()
        if not tools['naabu']:
            return [], "naabu tool not available"

        # Run naabu with verbose output
        print(f"Running naabu command: naabu -host {clean_host} -o {output_file}")
        result = subprocess.run(
            ['naabu', '-host', clean_host, '-o', output_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False  # Don't raise an exception on non-zero exit
        )

        # Print the output and error for debugging
        print(f"naabu exit code: {result.returncode}")
        if result.stdout:
            print(f"naabu stdout: {result.stdout.decode('utf-8')}")
        if result.stderr:
            print(f"naabu stderr: {result.stderr.decode('utf-8')}")

        # If the command failed, raise an exception
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, f"naabu -host {clean_host}", result.stdout, result.stderr)

        # Read the output file
        ports = []
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and line.isdigit():
                        ports.append(int(line))

        return ports, None
    except subprocess.CalledProcessError as e:
        return [], f"Error running naabu: {e}"
    except Exception as e:
        return [], f"Unexpected error: {e}"

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
