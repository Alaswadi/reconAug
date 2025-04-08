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

        # Start the Celery task
        from reconaug.tasks import run_scan_task
        task = run_scan_task.delay(domain)
        print(f"Started Celery task with ID: {task.id}")

        # Redirect to the history page instead of the scan progress page
        return jsonify({
            'task_id': task.id,
            'domain': domain,
            'status': 'started',
            'redirect': '/history'
        })
    except Exception as e:
        print(f"Error in scan endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@scan_bp.route('/progress/<task_id>')
def scan_progress_page(task_id):
    """Page to display scan progress"""
    try:
        # Get the task from Celery
        from reconaug.tasks import celery
        task = celery.AsyncResult(task_id)

        # Get the domain from the task
        domain = ""
        if task.state == 'SUCCESS' and task.result:
            domain = task.result.get('domain', '')
        elif task.state == 'PENDING':
            print(f"Task {task_id} is pending")
        elif task.state == 'FAILURE':
            print(f"Task {task_id} failed: {task.info}")
        elif task.info:
            domain = task.info.get('domain', '')

        print(f"Rendering scan progress page for task {task_id}, domain: {domain}")
        return render_template('scan_progress_simple.html', task_id=task_id, domain=domain)
    except Exception as e:
        print(f"Error rendering scan progress page: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500

@scan_bp.route('/task-status/<task_id>')
def task_status(task_id):
    """Get task status from Celery"""
    try:
        from reconaug.tasks import celery
        task = celery.AsyncResult(task_id)

        if task.state == 'PENDING':
            response = {
                'status': 'pending',
                'progress': 0,
                'message': 'Task is pending...',
                'subdomains_count': 0,
                'live_hosts_count': 0
            }
        elif task.state == 'FAILURE':
            response = {
                'status': 'error',
                'progress': 100,
                'message': str(task.info),
                'complete': True
            }
        elif task.state == 'SUCCESS':
            response = task.result
        else:
            response = task.info or {
                'status': 'running',
                'progress': 0,
                'message': 'Task is running...',
                'subdomains_count': 0,
                'live_hosts_count': 0
            }

        return jsonify(response)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@scan_bp.route('/details/<int:scan_id>')
def details(scan_id):
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
        print(f"Starting background scan for domain: {domain}, task ID: {task_id}")
        # Create output directory if it doesn't exist
        os.makedirs('output', exist_ok=True)

        # Clean up any existing output files
        for file_pattern in [f"output/subfinder_{domain}.txt", f"output/crtsh_{domain}.txt",
                            f"output/domain_{domain}.txt", f"output/httpx_{domain}.txt",
                            f"output/gau_{domain}.txt", f"output/sublist3r_{domain}.txt"]:
            if os.path.exists(file_pattern):
                os.remove(file_pattern)

        # Run subdomain discovery tools in parallel
        print(f"Updating task {task_id} to 10% - Running subfinder and Sublist3r...")
        task_manager.update_task(task_id, progress=10, message='Running subfinder and Sublist3r...')
        with ThreadPoolExecutor(max_workers=3) as executor:
            subfinder_future = executor.submit(get_subdomains_subfinder, domain)
            sublist3r_future = executor.submit(get_subdomains_sublist3r, domain)

            # Update progress while other tools are running
            print(f"Updating task {task_id} to 15% - Running crt.sh and other passive sources...")
            task_manager.update_task(task_id, progress=15, message='Running crt.sh and other passive sources...')
            crtsh_future = executor.submit(get_subdomains_crtsh, domain)

            subfinder_results = subfinder_future.result()
            print(f"Updating task {task_id} to 25% - Found {len(subfinder_results)} subdomains with subfinder")
            task_manager.update_task(task_id, progress=25, message=f'Found {len(subfinder_results)} subdomains with subfinder')

            sublist3r_results = sublist3r_future.result()
            print(f"Updating task {task_id} to 30% - Found {len(sublist3r_results)} subdomains with Sublist3r")
            task_manager.update_task(task_id, progress=30, message=f'Found {len(sublist3r_results)} subdomains with Sublist3r')

            crtsh_results = crtsh_future.result()
            print(f"Updating task {task_id} to 40% - Found {len(crtsh_results)} subdomains with passive sources")
            task_manager.update_task(task_id, progress=40, message=f'Found {len(crtsh_results)} subdomains with passive sources')

        # Combine and deduplicate results
        all_domains = list(set(subfinder_results + sublist3r_results + crtsh_results))

        # Save all domains to a file
        output_file = f"output/domain_{domain}.txt"
        with open(output_file, 'w') as f:
            for d in all_domains:
                f.write(f"{d}\\n")

        print(f"Updating task {task_id} to 50% - Found {len(all_domains)} unique subdomains. Checking live hosts...")
        task_manager.update_task(
            task_id,
            progress=50,
            message=f'Found {len(all_domains)} unique subdomains. Checking live hosts...',
            subdomains_count=len(all_domains),
            live_hosts_count=0
        )

        # Check which domains are live
        live_hosts = check_live_hosts(all_domains)

        print(f"Updating task {task_id} to 80% - Found {len(live_hosts)} live hosts")
        task_manager.update_task(
            task_id,
            progress=80,
            message=f'Found {len(live_hosts)} live hosts',
            subdomains_count=len(all_domains),
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
        print(f"Updating task {task_id} to 100% - Scan complete")
        task_manager.update_task(
            task_id,
            status='complete',
            progress=100,
            message=f'Scan complete. Found {len(all_domains)} subdomains and {len(live_hosts)} live hosts. {db_message}',
            subdomains_count=len(all_domains),
            live_hosts_count=len(live_hosts),
            complete=True
        )
        print(f"Task {task_id} marked as complete")
    except Exception as e:
        print(f"Error in background scan: {e}")
        import traceback
        traceback.print_exc()

        print(f"Updating task {task_id} to error state")
        task_manager.update_task(
            task_id,
            status='error',
            progress=100,
            message=f'Error: {str(e)}',
            complete=True
        )
        print(f"Task {task_id} marked as error")
