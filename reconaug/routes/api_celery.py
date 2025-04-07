from flask import Blueprint, request, jsonify, Response, stream_with_context
import time
import json

api_celery_bp = Blueprint('api_celery', __name__)

@api_celery_bp.route('/debug/task/<task_id>')
def debug_task(task_id):
    """Debug endpoint to check task status"""
    try:
        from reconaug.tasks import celery
        task = celery.AsyncResult(task_id)

        result = {
            'task_id': task_id,
            'state': task.state,
            'info': str(task.info),
            'result': str(task.result) if task.state == 'SUCCESS' else None
        }

        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_celery_bp.route('/task/<task_id>/events')
def task_events(task_id):
    """Server-sent events endpoint for real-time updates using Celery"""
    print(f"SSE connection established for task: {task_id}")

    def generate():
        from reconaug.tasks import celery

        last_state = None
        counter = 0

        while True:
            counter += 1
            task = celery.AsyncResult(task_id)

            if counter % 10 == 0:  # Log every 10 seconds
                print(f"SSE heartbeat for task {task_id}, counter: {counter}")
                print(f"Task state: {task.state}")

            if task.state == 'PENDING':
                current_state = 'pending-0-Task is pending...'
                data = {
                    'status': 'pending',
                    'progress': 0,
                    'message': 'Task is pending...',
                    'subdomains_count': 0,
                    'live_hosts_count': 0
                }
            elif task.state == 'FAILURE':
                current_state = 'error-100-Task failed'
                data = {
                    'status': 'error',
                    'progress': 100,
                    'message': str(task.info),
                    'complete': True
                }
                # Task failed, send update and stop
                yield f"data: {json.dumps(data)}\n\n"
                break
            elif task.state == 'SUCCESS':
                current_state = 'complete-100-Task completed'
                data = task.result
                # Task completed, send update and stop
                yield f"data: {json.dumps(data)}\n\n"
                break
            else:
                # Task is in progress
                info = task.info or {}
                current_state = f"{info.get('status', 'running')}-{info.get('progress', 0)}-{info.get('message', 'Task is running...')}"
                data = {
                    'status': info.get('status', 'running'),
                    'progress': info.get('progress', 0),
                    'message': info.get('message', 'Task is running...'),
                    'subdomains_count': info.get('subdomains_count', 0),
                    'live_hosts_count': info.get('live_hosts_count', 0)
                }

            # Only send updates if the state has changed or every 5 seconds
            if current_state != last_state or counter % 5 == 0:
                print(f"Sending SSE update for task {task_id}: {current_state}")
                yield f"data: {json.dumps(data)}\n\n"
                last_state = current_state
                print(f"SSE update sent for task {task_id}")

            time.sleep(1)

    return Response(stream_with_context(generate()), content_type='text/event-stream')

@api_celery_bp.route('/celery/run-gau', methods=['GET'])
def celery_run_gau():
    domain = request.args.get('domain', '').strip()

    if not domain:
        return jsonify({'error': 'Domain is required'}), 400

    print(f"Running GAU for {domain}...")

    # Start the Celery task
    from reconaug.tasks import run_gau_task
    task = run_gau_task.delay(domain)

    # Return the task ID
    return jsonify({
        'task_id': task.id,
        'domain': domain,
        'status': 'started'
    })

@api_celery_bp.route('/celery/scan-ports', methods=['GET'])
def celery_scan_ports():
    host = request.args.get('host', '').strip()

    if not host:
        return jsonify({'error': 'Host is required'}), 400

    print(f"Scanning ports for {host}...")

    # Start the Celery task
    from reconaug.tasks import run_port_scan_task
    task = run_port_scan_task.delay(host)

    # Return the task ID
    return jsonify({
        'task_id': task.id,
        'host': host,
        'status': 'started'
    })
