from flask import Flask, render_template, jsonify
from flask_login import LoginManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models.database import db, init_db
from models.user import User
from api.upload import upload_bp
from api.migrations import migrations_bp
from api.auth import auth_bp
from workers.migration_worker import init_celery
from config import config
import os
import logging
from logging.handlers import RotatingFileHandler

def create_app(config_name='development'):
    """Application factory"""
    
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    init_db(app)
    
    # CORS
    CORS(app, supports_credentials=True)
    
    # Rate limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri=app.config.get('RATELIMIT_STORAGE_URL')
    )
    
    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Celery
    init_celery(app)
    
    # Register blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(migrations_bp)
    app.register_blueprint(auth_bp)
    
    # Routes
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/upload')
    def upload_page():
        return render_template('upload.html')
    
    @app.route('/status/<migration_id>')
    def status_page(migration_id):
        return render_template('status.html', migration_id=migration_id)
    
    # Health check
    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy'}), 200
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
    
    # Logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler(
            'logs/qbmigration.log',
            maxBytes=10240000,
            backupCount=10
        )
        
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('QB Migration startup')
    
    return app


# Create app instance
app = create_app(os.getenv('FLASK_ENV', 'development'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)