import os
import threading
import re
from flask import Blueprint, request, jsonify, render_template, current_app
from concurrent.futures import ThreadPoolExecutor

from reconaug import db
from reconaug.models import Scan, Subdomain, LiveHost, Port, HistoricalUrl
from reconaug.tools.subdomain import (
    get_subdomains_subfinder, get_subdomains_crtsh,
    get_subdomains_sublist3r
)
from reconaug.tools.scanner import check_live_hosts, scan_ports, get_historical_urls
from reconaug.utils.task_manager import task_manager
from reconaug.utils.database import save_scan_to_database, save_ports_to_database

scan_bp = Blueprint('scan', __name__)

@scan_bp.route('/scan', methods=['POST'])
def scan():
    """Start a new scan"""
    try:
        print("Scan endpoint called")
        print(f"Request form: {request.form}")
        domain = request.form.get('domain', '').strip()
        print(f"Domain: {domain}")

        if not domain:
            print("Error: Domain is required")
            return jsonify({'error': 'Domain is required'}), 400

        # Validate domain format
        if not re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,}$', domain):
            print(f"Error: Invalid domain format: {domain}")
            return jsonify({'error': 'Invalid domain format'}), 400

        # Create a task for this scan
        task_id = task_manager.create_task(domain)
        print(f"Created task with ID: {task_id}")

        # Get the current application object
        app = current_app._get_current_object()

        # Start the scan in a background thread
        scan_thread = threading.Thread(
            target=run_scan_in_background,
            args=(domain, task_id, app)
        )
        scan_thread.daemon = True
        scan_thread.start()
        print(f"Started background scan thread for domain: {domain}, task ID: {task_id}")

        return jsonify({
            'task_id': task_id,
            'domain': domain,
            'status': 'started'
        })
    except Exception as e:
        print(f"Error in scan endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@scan_bp.route('/scan-status/<task_id>')
def scan_status(task_id):
    """Get scan status"""
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify(task)

@scan_bp.route('/scan-details/<int:scan_id>')
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

def run_scan_in_background(domain, task_id, app):
    """Run the scan in a background thread"""
    try:
        # Create output directory if it doesn't exist
        os.makedirs('output', exist_ok=True)

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

        # Save all domains to a file
        output_file = f"output/domain_{domain}.txt"
        with open(output_file, 'w') as f:
            for d in all_domains:
                f.write(f"{d}\\n")

        task_manager.update_task(
            task_id,
            progress=50,
            message=f'Found {len(all_domains)} unique subdomains. Checking live hosts...'
        )

        # Check which domains are live
        live_hosts = check_live_hosts(all_domains)

        task_manager.update_task(
            task_id,
            progress=80,
            message=f'Found {len(live_hosts)} live hosts'
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
        print(f"Error in background scan: {e}")
        import traceback
        traceback.print_exc()

        task_manager.update_task(
            task_id,
            status='error',
            progress=100,
            message=f'Error: {str(e)}',
            complete=True
        )
