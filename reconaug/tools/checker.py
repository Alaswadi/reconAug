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
        print("Checking if httpx is available...")
        result = subprocess.run(['httpx', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        print(f"httpx check exit code: {result.returncode}")
        if result.stdout:
            print(f"httpx stdout: {result.stdout.decode('utf-8')}")
        if result.stderr:
            print(f"httpx stderr: {result.stderr.decode('utf-8')}")

        # Try to find httpx in PATH
        which_result = subprocess.run(['which', 'httpx'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if which_result.returncode == 0:
            print(f"httpx found at: {which_result.stdout.decode('utf-8').strip()}")
            tools['httpx'] = True
        else:
            print("httpx not found in PATH")
    except Exception as e:
        print(f"Error checking httpx: {e}")

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
