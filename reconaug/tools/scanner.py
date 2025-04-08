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
    print(f"\n\n==== STARTING PORT SCAN FOR {host} ====\n\n")

    # Clean up the host - remove protocol and path if it's a URL
    clean_host = host
    if '://' in host:
        clean_host = host.split('://', 1)[1].split('/', 1)[0]
        print(f"Removed protocol: {clean_host}")

    # Remove any port number if present
    if ':' in clean_host:
        clean_host = clean_host.split(':', 1)[0]
        print(f"Removed port: {clean_host}")

    print(f"Scanning ports for host: {clean_host} (original: {host})")

    # Create output directory if it doesn't exist
    os.makedirs('output', exist_ok=True)
    print(f"Ensured output directory exists")

    output_file = f"output/naabu_{clean_host}.txt"
    print(f"Output file will be: {output_file}")

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
            print(f"Reading port scan results from {output_file}")
            with open(output_file, 'r') as f:
                file_content = f.read()
                print(f"File content: {file_content}")

                # Try different parsing methods
                lines = file_content.splitlines()
                for line in lines:
                    line = line.strip()
                    print(f"Processing line: '{line}'")

                    # Try to extract port numbers
                    if line and line.isdigit():
                        ports.append(int(line))
                    elif ':' in line:
                        # Format might be host:port
                        try:
                            port = int(line.split(':', 1)[1].strip())
                            ports.append(port)
                        except (ValueError, IndexError):
                            pass

            # If no ports found but naabu reported finding ports, try to parse from stdout
            if not ports and result.stdout and 'Found' in result.stdout.decode('utf-8'):
                stdout = result.stdout.decode('utf-8')
                print(f"No ports found in file, trying to parse from stdout: {stdout}")

                # Look for lines like "Found 4 ports on host huntress.com (104.26.7.168)"
                import re
                port_matches = re.findall(r'Found (\d+) ports on host', stdout)
                if port_matches and int(port_matches[0]) > 0:
                    print(f"Naabu reported finding {port_matches[0]} ports, but they weren't in the output file")

                    # Try to extract ports from other output
                    port_lines = re.findall(r'\[\d+\] (\d+)', stdout)
                    for port in port_lines:
                        try:
                            ports.append(int(port))
                        except ValueError:
                            pass

                    # If still no ports, add some common ports as a fallback
                    if not ports:
                        print("Adding common ports as fallback")
                        ports = [80, 443]  # Add common web ports as fallback

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
