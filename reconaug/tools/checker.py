import os
import subprocess

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
        subprocess.run(['gau', '-h'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
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
