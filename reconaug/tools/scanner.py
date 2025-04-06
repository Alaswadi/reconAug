import os
import subprocess
import requests
from reconaug.tools.checker import check_tools

def check_live_hosts(domains):
    """Check which domains are live using httpx"""
    output_file = f"output/httpx_{domains[0].split('.')[0]}.txt"
    
    try:
        # Check if httpx is available
        tools = check_tools()
        if not tools['httpx']:
            return []
            
        # Create a temporary file with domains
        temp_file = f"output/temp_domains_{domains[0].split('.')[0]}.txt"
        with open(temp_file, 'w') as f:
            for domain in domains:
                f.write(f"{domain}\\n")
        
        # Run httpx with increased threads
        subprocess.run(
            [
                'httpx', '-l', temp_file, '-o', output_file, '-silent',
                '-threads', '50', '-status-code', '-tech-detect', '-follow-redirects'
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        
        # Parse the output file
        live_hosts = []
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split()
                    if len(parts) >= 2:
                        url = parts[0]
                        status_code = parts[1]
                        
                        # Extract technology if available
                        technology = ""
                        if len(parts) > 2:
                            technology = " ".join(parts[2:])
                        
                        live_hosts.append({
                            'url': url,
                            'status_code': status_code,
                            'technology': technology
                        })
        
        # Clean up temporary file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return live_hosts
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
        
        # Extract the base domain (remove www. if present)
        base_domain = domain
        if domain.startswith('www.'):
            base_domain = domain[4:]
        
        print(f"Running GAU for domain: {domain} (base domain: {base_domain})")
        
        # Create a temporary file to store the output
        temp_output_file = f"output/temp_gau_{domain}.txt"
        
        # Use a more reliable approach - write to file directly
        try:
            # First try with the exact domain
            print(f"Running GAU command: gau --threads 50 --o {temp_output_file} {domain}")
            process = subprocess.run(
                ['gau', '--threads', '50', '-o', temp_output_file, domain],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=180  # 3 minute timeout for the entire process
            )
            
            # Check if the output file exists and has content
            urls = []
            if os.path.exists(temp_output_file):
                with open(temp_output_file, 'r') as f:
                    urls = [line.strip() for line in f if line.strip()]
                
                # Move the temp file to the final output file
                os.rename(temp_output_file, output_file)
            else:
                print(f"GAU output file not found: {temp_output_file}")
                
                # Check stderr for errors
                if process.stderr:
                    print(f"GAU stderr: {process.stderr}")
            
            # If no results and domain starts with www, try without www
            if len(urls) == 0 and domain.startswith('www.'):
                print(f"No results found for {domain}, trying {base_domain}")
                
                # Try again with the base domain
                print(f"Running GAU command: gau --threads 50 --o {temp_output_file} {base_domain}")
                process = subprocess.run(
                    ['gau', '--threads', '50', '-o', temp_output_file, base_domain],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    text=True,
                    timeout=180  # 3 minute timeout for the entire process
                )
                
                # Check if the output file exists and has content
                if os.path.exists(temp_output_file):
                    with open(temp_output_file, 'r') as f:
                        urls = [line.strip() for line in f if line.strip()]
                    
                    # Move the temp file to the final output file
                    os.rename(temp_output_file, output_file)
                else:
                    print(f"GAU output file not found: {temp_output_file}")
                    
                    # Check stderr for errors
                    if process.stderr:
                        print(f"GAU stderr: {process.stderr}")
            
            # If still no results, try using the waybackurls tool as a fallback
            if len(urls) == 0:
                print(f"No results found with GAU, trying alternative method...")
                
                # Try using curl to fetch from the Wayback Machine API directly
                wayback_url = f"http://web.archive.org/cdx/search/cdx?url=*.{base_domain}/*&output=json&fl=original&collapse=urlkey"
                print(f"Fetching URLs from Wayback Machine API: {wayback_url}")
                
                try:
                    response = requests.get(wayback_url, timeout=60)
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            # Skip the header row
                            if len(data) > 1:
                                for row in data[1:]:
                                    if row and row[0]:
                                        urls.append(row[0])
                                
                                # Save to file
                                with open(output_file, 'w') as f:
                                    for url in urls:
                                        f.write(f"{url}\\n")
                        except Exception as e:
                            print(f"Error parsing Wayback Machine response: {e}")
                    else:
                        print(f"Wayback Machine API returned status code: {response.status_code}")
                except Exception as e:
                    print(f"Error fetching from Wayback Machine API: {e}")
            
            print(f"Found {len(urls)} URLs for {domain}")
            return urls, None
        except subprocess.TimeoutExpired:
            print(f"GAU timed out for {domain}")
            return [], "GAU process timed out"
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"Error running GAU: {e}")
        return [], str(e)

def scan_ports(host):
    """Scan ports using naabu"""
    output_file = f"output/naabu_{host}.txt"
    
    try:
        # Check if naabu is available
        tools = check_tools()
        if not tools['naabu']:
            return [], "Naabu tool is not installed"
            
        # Run naabu with increased threads
        subprocess.run(
            ['naabu', '-host', host, '-o', output_file, '-silent', '-c', '50'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )
        
        # Parse the output file
        ports = []
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and line.isdigit():
                        ports.append(int(line))
        
        return ports, None
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"Error running naabu: {e}")
        return [], str(e)
