import os
from concurrent.futures import ThreadPoolExecutor
import json

from reconaug.celery_app import celery
from reconaug.tools.subdomain import get_subdomains_subfinder, get_subdomains_crtsh, get_subdomains_sublist3r
from reconaug.tools.scanner import check_live_hosts, get_historical_urls, scan_ports
from reconaug.utils.celery_db import save_scan_results, save_port_scan_results

@celery.task(bind=True)
def run_scan_task(self, domain):
    """Run a full scan as a Celery task"""
    try:
        # Create output directory if it doesn't exist
        os.makedirs('output', exist_ok=True)

        # Clean up any existing output files
        for file_pattern in [f"output/subfinder_{domain}.txt", f"output/crtsh_{domain}.txt",
                            f"output/domain_{domain}.txt", f"output/httpx_{domain}.txt",
                            f"output/gau_{domain}.txt", f"output/sublist3r_{domain}.txt"]:
            if os.path.exists(file_pattern):
                os.remove(file_pattern)

        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'running',
                'progress': 10,
                'message': 'Running subfinder and Sublist3r...',
                'subdomains_count': 0,
                'live_hosts_count': 0
            }
        )

        # Run subdomain discovery tools in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            subfinder_future = executor.submit(get_subdomains_subfinder, domain)
            sublist3r_future = executor.submit(get_subdomains_sublist3r, domain)

            # Update progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'running',
                    'progress': 15,
                    'message': 'Running crt.sh and other passive sources...',
                    'subdomains_count': 0,
                    'live_hosts_count': 0
                }
            )

            crtsh_future = executor.submit(get_subdomains_crtsh, domain)

            subfinder_results = subfinder_future.result()
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'running',
                    'progress': 25,
                    'message': f'Found {len(subfinder_results)} subdomains with subfinder',
                    'subdomains_count': len(subfinder_results),
                    'live_hosts_count': 0
                }
            )

            sublist3r_results = sublist3r_future.result()
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'running',
                    'progress': 30,
                    'message': f'Found {len(sublist3r_results)} subdomains with Sublist3r',
                    'subdomains_count': len(subfinder_results) + len(sublist3r_results),
                    'live_hosts_count': 0
                }
            )

            crtsh_results = crtsh_future.result()
            self.update_state(
                state='PROGRESS',
                meta={
                    'status': 'running',
                    'progress': 40,
                    'message': f'Found {len(crtsh_results)} subdomains with passive sources',
                    'subdomains_count': len(subfinder_results) + len(sublist3r_results) + len(crtsh_results),
                    'live_hosts_count': 0
                }
            )

        # Combine and deduplicate results
        all_domains = list(set(subfinder_results + sublist3r_results + crtsh_results))

        # Save all domains to a file
        output_file = f"output/domain_{domain}.txt"
        with open(output_file, 'w') as f:
            for d in all_domains:
                f.write(f"{d}\n")

        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'running',
                'progress': 50,
                'message': f'Found {len(all_domains)} unique subdomains. Checking live hosts...',
                'subdomains_count': len(all_domains),
                'live_hosts_count': 0
            }
        )

        # Check which domains are live
        live_hosts = check_live_hosts(all_domains)

        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'running',
                'progress': 80,
                'message': f'Found {len(live_hosts)} live hosts',
                'subdomains_count': len(all_domains),
                'live_hosts_count': len(live_hosts)
            }
        )

        # Save results to database
        scan_id = save_scan_results(domain, all_domains, live_hosts)
        if scan_id:
            db_message = f'Results saved to database (ID: {scan_id}).'
        else:
            db_message = 'Note: Failed to save results to database.'

        # Return the final result
        return {
            'status': 'complete',
            'progress': 100,
            'message': f'Scan complete. Found {len(all_domains)} subdomains and {len(live_hosts)} live hosts. {db_message}',
            'subdomains_count': len(all_domains),
            'live_hosts_count': len(live_hosts),
            'domain': domain,
            'scan_id': scan_id
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'progress': 100,
            'message': f'Error: {str(e)}',
            'error': str(e),
            'complete': True
        }

@celery.task(bind=True)
def run_gau_task(self, domain):
    """Run GAU as a Celery task"""
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'running',
                'progress': 10,
                'message': f'Running GAU for {domain}...'
            }
        )

        urls, error = get_historical_urls(domain)

        if error:
            return {
                'status': 'error',
                'message': f'Error running GAU: {error}',
                'urls': []
            }

        # Save URLs to the database
        try:
            from reconaug.utils.celery_db import save_historical_urls
            scan_id = save_historical_urls(domain, urls)
            if scan_id:
                print(f"Saved {len(urls)} historical URLs to database for scan ID: {scan_id}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error saving historical URLs to database: {e}")

        return {
            'status': 'complete',
            'progress': 100,
            'message': f'Found {len(urls)} historical URLs for {domain}',
            'domain': domain,
            'count': len(urls),
            'urls': urls[:1000] if len(urls) > 1000 else urls,
            'limited': len(urls) > 1000
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'progress': 100,
            'message': f'Error: {str(e)}',
            'error': str(e),
            'complete': True
        }

@celery.task(bind=True)
def run_port_scan_task(self, host):
    """Run port scan as a Celery task"""
    print(f"Starting port scan task for {host}")
    try:
        # Update task state to PROGRESS
        print(f"Updating task state to PROGRESS for {host}")
        self.update_state(
            state='PROGRESS',
            meta={
                'status': 'running',
                'progress': 10,
                'message': f'Scanning ports for {host}...'
            }
        )
        print(f"Task state updated for {host}")

        # Run the port scan
        print(f"Running port scan for {host}")
        ports, error = scan_ports(host)
        print(f"Port scan completed for {host}. Found {len(ports)} ports. Error: {error}")

        if error:
            print(f"Error scanning ports for {host}: {error}")
            return {
                'status': 'error',
                'message': f'Error scanning ports: {error}',
                'ports': []
            }

        # Save ports to database
        success = save_port_scan_results(host, ports)

        # Convert port numbers to port objects with service information
        port_objects = []
        for port in ports:
            service = 'Unknown'
            # Add common service names
            if port == 21:
                service = 'FTP'
            elif port == 22:
                service = 'SSH'
            elif port == 23:
                service = 'Telnet'
            elif port == 25:
                service = 'SMTP'
            elif port == 53:
                service = 'DNS'
            elif port == 80:
                service = 'HTTP'
            elif port == 110:
                service = 'POP3'
            elif port == 143:
                service = 'IMAP'
            elif port == 443:
                service = 'HTTPS'
            elif port == 445:
                service = 'SMB'
            elif port == 3306:
                service = 'MySQL'
            elif port == 3389:
                service = 'RDP'
            elif port == 5432:
                service = 'PostgreSQL'
            elif port == 8080:
                service = 'HTTP-Proxy'
            elif port == 8443:
                service = 'HTTPS-Alt'

            port_objects.append({
                'port_number': port,
                'service': service
            })

        return {
            'status': 'complete',
            'progress': 100,
            'message': f'Found {len(ports)} open ports for {host}',
            'host': host,
            'count': len(ports),
            'ports': port_objects
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'progress': 100,
            'message': f'Error: {str(e)}',
            'error': str(e),
            'complete': True
        }
