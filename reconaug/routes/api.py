from flask import Blueprint, request, jsonify, Response, stream_with_context, current_app
import time
from reconaug import db
from reconaug.models import Scan, Subdomain, LiveHost, Port, HistoricalUrl
from reconaug.tools.checker import check_tools
from reconaug.tools.scanner import get_historical_urls, scan_ports
from reconaug.utils.database import save_ports_to_database
from reconaug.utils.task_manager import task_manager

api_bp = Blueprint('api', __name__)

@api_bp.route('/tools')
def tools():
    """Get available tools"""
    return jsonify(check_tools())

@api_bp.route('/scan/<int:scan_id>')
def scan_details_api(scan_id):
    """API endpoint to get details of a specific scan"""
    try:
        scan = Scan.query.get_or_404(scan_id)
        subdomains = [s.name for s in scan.subdomains]
        live_hosts = [h.to_dict() for h in scan.live_hosts]

        return jsonify({
            'scan': scan.to_dict(),
            'subdomains': subdomains,
            'live_hosts': live_hosts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/scan-history')
def scan_history():
    """Get scan history"""
    try:
        print("Fetching scan history from database...")
        scans = Scan.query.order_by(Scan.timestamp.desc()).all()
        print(f"Found {len(scans)} scan records in database")

        # Convert to dict and log for debugging
        scan_dicts = [scan.to_dict() for scan in scans]
        print(f"Returning {len(scan_dicts)} scan records as JSON")

        return jsonify({
            'scans': scan_dicts
        })
    except Exception as e:
        print(f"Error fetching scan history: {e}")
        return jsonify({'error': str(e), 'message': 'Failed to fetch scan history'}), 500

@api_bp.route('/scan/<int:scan_id>/historical-urls')
def scan_historical_urls(scan_id):
    """Get historical URLs for a specific scan"""
    try:
        urls = HistoricalUrl.query.filter_by(scan_id=scan_id).all()
        return jsonify({
            'urls': [url.url for url in urls]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/host/<int:host_id>/ports')
def host_ports(host_id):
    """Get ports for a specific live host"""
    try:
        host = LiveHost.query.get_or_404(host_id)
        ports = [{
            'port': p.port_number,
            'service': p.service
        } for p in host.ports]

        return jsonify({
            'host': host.to_dict(),
            'ports': ports,
            'has_ports': len(ports) > 0
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/host/check-ports')
def check_host_ports():
    """Check if a host has ports scanned"""
    try:
        host_url = request.args.get('url')
        if not host_url:
            return jsonify({'error': 'URL parameter is required'}), 400

        # Find the host in the database
        host = LiveHost.query.filter_by(url=host_url).first()

        if not host:
            return jsonify({
                'url': host_url,
                'has_ports': False,
                'message': 'Host not found in database'
            })

        # Check if the host has ports
        ports_count = Port.query.filter_by(host_id=host.id).count()

        return jsonify({
            'url': host_url,
            'host_id': host.id,
            'has_ports': ports_count > 0,
            'ports_count': ports_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/run-gau', methods=['GET'])
def run_gau():
    domain = request.args.get('domain', '').strip()

    if not domain:
        return jsonify({'error': 'Domain is required'}), 400

    print(f"Running GAU for {domain}...")
    # Run GAU for the specific domain
    urls, error = get_historical_urls(domain)

    if error:
        print(f"Error running GAU for {domain}: {error}")
        return jsonify({
            'error': error,
            'urls': []
        }), 500

    print(f"Found {len(urls)} historical URLs for {domain}")

    # Try to find the most recent scan for this domain to associate the URLs with
    if len(urls) > 0:
        try:
            # Use application context for database operations
            with current_app.app_context():
                # Try exact domain match first
                scan = Scan.query.filter_by(domain=domain).order_by(Scan.timestamp.desc()).first()

                # If no scan found and domain starts with www, try without www
                if not scan and domain.startswith('www.'):
                    base_domain = domain[4:]
                    scan = Scan.query.filter_by(domain=base_domain).order_by(Scan.timestamp.desc()).first()

                # If no scan found and domain doesn't start with www, try with www
                if not scan and not domain.startswith('www.'):
                    www_domain = f"www.{domain}"
                    scan = Scan.query.filter_by(domain=www_domain).order_by(Scan.timestamp.desc()).first()

                if scan:
                    print(f"Found scan ID {scan.id} for domain {scan.domain}")
                    # Check if we already have historical URLs for this scan
                    existing_urls = HistoricalUrl.query.filter_by(scan_id=scan.id).count()
                    if existing_urls == 0:
                        print(f"No existing historical URLs for scan ID {scan.id}, saving {len(urls)} URLs")
                        # Save historical URLs to database
                        for url in urls:
                            db.session.add(HistoricalUrl(
                                scan_id=scan.id,
                                url=url
                            ))
                        db.session.commit()
                        print(f"Saved {len(urls)} historical URLs to database for scan ID {scan.id}")
                    else:
                        print(f"Found {existing_urls} existing historical URLs for scan ID {scan.id}, skipping")
                else:
                    print(f"No scan found for domain {domain} or its variations")
        except Exception as e:
            print(f"Error saving historical URLs to database: {e}")
            import traceback
            traceback.print_exc()

    # Limit the number of URLs returned to the frontend to avoid overwhelming the browser
    max_urls_to_return = 1000
    urls_to_return = urls[:max_urls_to_return] if len(urls) > max_urls_to_return else urls

    if len(urls) > max_urls_to_return:
        print(f"Limiting returned URLs from {len(urls)} to {max_urls_to_return}")

    return jsonify({
        'domain': domain,
        'count': len(urls),
        'urls': urls_to_return,
        'limited': len(urls) > max_urls_to_return
    })

@api_bp.route('/scan-ports', methods=['GET'])
def scan_ports_api():
    host = request.args.get('host', '').strip()

    if not host:
        return jsonify({'error': 'Host is required'}), 400

    print(f"Scanning ports for {host}...")
    # Run port scan for the specific host
    ports, error = scan_ports(host)

    if error:
        print(f"Error scanning ports for {host}: {error}")
        return jsonify({
            'error': error,
            'ports': []
        }), 500

    print(f"Found {len(ports)} open ports for {host}")

    # Save port scan results to database
    try:
        # Use application context for database operations
        with current_app.app_context():
            success = save_ports_to_database(host, ports)
            if success:
                print(f"Saved {len(ports)} ports to database for host {host}")
            else:
                print(f"Failed to save ports to database for host {host}")
    except Exception as e:
        print(f"Error saving ports to database: {e}")
        import traceback
        traceback.print_exc()

    return jsonify({
        'host': host,
        'count': len(ports),
        'ports': ports
    })

@api_bp.route('/task/<task_id>')
def get_task(task_id):
    """Get task details from Celery"""
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

            # If the task is complete, include the full results
            if response.get('status') == 'complete' and response.get('scan_id'):
                try:
                    # Get the scan from the database
                    scan_id = response.get('scan_id')
                    scan = Scan.query.get(scan_id)
                    if scan:
                        # Get subdomains and live hosts
                        subdomains = [s.name for s in scan.subdomains]
                        live_hosts = [h.to_dict() for h in scan.live_hosts]

                        # Add to the response
                        response['subdomains'] = subdomains
                        response['live_hosts'] = live_hosts
                except Exception as e:
                    print(f"Error getting scan details: {e}")
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

@api_bp.route('/task/<task_id>/events')
def task_events(task_id):
    """Server-sent events endpoint for real-time updates"""
    print(f"SSE connection established for task: {task_id}")

    def generate():
        last_status = None
        counter = 0
        while True:
            counter += 1
            task = task_manager.get_task(task_id)

            if counter % 10 == 0:  # Log every 10 seconds
                print(f"SSE heartbeat for task {task_id}, counter: {counter}")
                if task:
                    print(f"Task status: {task['status']}, progress: {task['progress']}, complete: {task['complete']}")
                else:
                    print(f"Task not found: {task_id}")

            if not task:
                print(f"Task not found in SSE: {task_id}")
                yield f"data: {{'error': 'Task not found'}}\\n\\n"
                break

            # Always send updates to ensure client gets the latest data
            current_status = f"{task['status']}-{task['progress']}-{task['message']}"
            if current_status != last_status or counter % 5 == 0:  # Send update if status changed or every 5 seconds
                print(f"Sending SSE update for task {task_id}: {current_status}")

                # Include subdomains_count and live_hosts_count if available
                subdomains_count = task.get('subdomains_count', 0)
                live_hosts_count = task.get('live_hosts_count', 0)

                data_json = f"data: {{'status': '{task['status']}', 'progress': {task['progress']}, 'message': '{task['message']}', 'complete': {str(task['complete']).lower()}, 'subdomains_count': {subdomains_count}, 'live_hosts_count': {live_hosts_count}}}\\n\\n"
                yield data_json
                last_status = current_status
                print(f"SSE update sent for task {task_id} with subdomains: {subdomains_count}, live hosts: {live_hosts_count}")

            # If the task is complete, stop sending updates
            if task['complete']:
                print(f"Task {task_id} is complete, closing SSE connection")
                break

            time.sleep(1)

    return Response(stream_with_context(generate()), content_type='text/event-stream')

@api_bp.route('/debug/database')
def debug_database():
    """Debug endpoint to check database contents"""
    try:
        # Get all scans
        scans = Scan.query.all()
        scan_data = []

        for scan in scans:
            scan_info = scan.to_dict()
            scan_info['subdomains_count_actual'] = Subdomain.query.filter_by(scan_id=scan.id).count()
            scan_info['live_hosts_count_actual'] = LiveHost.query.filter_by(scan_id=scan.id).count()
            scan_data.append(scan_info)

        # Get database stats
        stats = {
            'total_scans': Scan.query.count(),
            'total_subdomains': Subdomain.query.count(),
            'total_live_hosts': LiveHost.query.count(),
            'total_ports': Port.query.count(),
            'total_historical_urls': HistoricalUrl.query.count()
        }

        return jsonify({
            'stats': stats,
            'scans': scan_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/debug/clear-database')
def clear_database():
    """Debug endpoint to clear the database"""
    try:
        # Delete all records from all tables
        HistoricalUrl.query.delete()
        Port.query.delete()
        LiveHost.query.delete()
        Subdomain.query.delete()
        Scan.query.delete()

        # Commit the changes
        db.session.commit()

        return jsonify({
            'message': 'Database cleared successfully',
            'status': 'success'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@api_bp.route('/debug/task/<task_id>')
def debug_task(task_id):
    """Debug endpoint to check task status"""
    try:
        # Get the task
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({
                'error': f'Task {task_id} not found',
                'status': 'error',
                'all_tasks': list(task_manager.tasks.keys())
            }), 404

        # Return the task details
        return jsonify({
            'task': task,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@api_bp.route('/debug/tasks')
def debug_all_tasks():
    """Debug endpoint to list all tasks"""
    try:
        # Get all tasks
        with task_manager.task_lock:
            tasks = {task_id: task.copy() for task_id, task in task_manager.tasks.items()}

        # Return the tasks
        return jsonify({
            'tasks': tasks,
            'count': len(tasks),
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500
