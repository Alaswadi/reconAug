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

@api_celery_bp.route('/task/<task_id>')
def get_task(task_id):
    """Get task details from Celery"""
    try:
        from reconaug.tasks import celery
        task = celery.AsyncResult(task_id)

        print(f"Task {task_id} state: {task.state}, info: {task.info}, result: {task.result}")

        # Start with a basic response structure
        response = {
            'task_id': task_id,
            'state': task.state
        }

        if task.state == 'PENDING':
            response.update({
                'status': 'pending',
                'progress': 0,
                'message': 'Task is pending...'
            })
        elif task.state == 'FAILURE':
            response.update({
                'status': 'error',
                'progress': 100,
                'message': str(task.info),
                'complete': True
            })
        elif task.state == 'SUCCESS':
            # For successful tasks, return the actual result
            if isinstance(task.result, dict):
                response.update(task.result)

                # Make sure we have a status field
                if 'status' not in response:
                    response['status'] = 'complete'

                # Special handling for GAU results
                if 'urls' in response and isinstance(response['urls'], list):
                    # Make sure we're not returning too much data
                    if len(response['urls']) > 1000:
                        response['urls'] = response['urls'][:1000]
                        response['limited'] = True
            else:
                # If result is not a dict, create a basic response
                response.update({
                    'status': 'complete',
                    'progress': 100,
                    'message': 'Task completed',
                    'result': str(task.result)
                })
        else:
            # For tasks in progress
            if task.info and isinstance(task.info, dict):
                response.update(task.info)
            else:
                response.update({
                    'status': 'running',
                    'progress': 0,
                    'message': 'Task is running...'
                })

        return jsonify(response)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

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

    print(f"\n\n==== API ENDPOINT: SCANNING PORTS FOR {host} ====\n\n")

    try:
        # Start the Celery task
        from reconaug.tasks import run_port_scan_task
        print(f"Importing run_port_scan_task successful")

        # Check if Celery is connected
        from reconaug.celery_app import celery
        print(f"Celery ping: {celery.control.ping()}")

        # Start the task
        print(f"Starting Celery task for {host}...")
        task = run_port_scan_task.delay(host)
        print(f"Celery task started with ID: {task.id}")

        # Return the task ID
        return jsonify({
            'task_id': task.id,
            'host': host,
            'status': 'started'
        })
    except Exception as e:
        import traceback
        print(f"Error starting port scan task: {e}")
        traceback.print_exc()
        return jsonify({
            'error': f"Error starting port scan task: {str(e)}",
            'host': host,
            'status': 'error'
        }), 500
