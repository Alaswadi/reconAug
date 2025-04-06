from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index_simple.html')

@main_bp.route('/history')
def scan_history_page():
    return render_template('history.html')
