from flask import Blueprint, render_template

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index_base.html')

@main_bp.route('/history')
def history():
    return render_template('history.html')
