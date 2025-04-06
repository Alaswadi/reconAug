#!/usr/bin/env python3
import subprocess
import sys
import time

def test_gau(domain):
    print(f"Testing GAU on domain: {domain}")
    
    # Try running GAU directly
    try:
        print(f"Running: gau --threads 50 {domain}")
        start_time = time.time()
        process = subprocess.run(
            ['gau', '--threads', '50', domain],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120  # 2 minute timeout
        )
        end_time = time.time()
        
        # Check stderr for any errors
        if process.stderr:
            print(f"GAU stderr: {process.stderr}")
        
        # Parse the output
        urls = []
        if process.stdout:
            urls = [line.strip() for line in process.stdout.splitlines() if line.strip()]
        
        print(f"GAU found {len(urls)} URLs in {end_time - start_time:.2f} seconds")
        
        # Print the first 5 URLs if any
        if urls:
            print("First 5 URLs:")
            for url in urls[:5]:
                print(f"  - {url}")
        
        return urls
    except subprocess.TimeoutExpired:
        print(f"GAU timed out after 120 seconds")
        return []
    except Exception as e:
        print(f"Error running GAU: {e}")
        return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_gau.py <domain>")
        sys.exit(1)
    
    domain = sys.argv[1]
    test_gau(domain)
