import os
import subprocess
import requests
from reconaug.tools.checker import check_tools, CHAOS_API_KEY

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
        
        return subdomains
    except Exception as e:
        print(f"Error in get_subdomains_crtsh: {e}")
        return []

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
