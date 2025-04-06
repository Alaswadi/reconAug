from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy
db = SQLAlchemy()

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    # Configure SQLite database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reconaug.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)

    # Import and register blueprints
    from reconaug.routes.main import main_bp
    from reconaug.routes.scan import scan_bp
    from reconaug.routes.api import api_bp
    from reconaug.routes.api_celery import api_celery_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(scan_bp, url_prefix='/scan')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(api_celery_bp, url_prefix='/api')

    # Create database tables
    with app.app_context():
        db.create_all()

        # Initialize Celery
        from reconaug.celery_app import create_celery_app
        app.celery = create_celery_app(app)

    return app
