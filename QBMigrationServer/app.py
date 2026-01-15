import os
import logging
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request
from flask_login import LoginManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models.database import db, init_db
from models.user import User
from api.auth import auth_bp, limiter as auth_limiter
from api.upload import upload_bp, limiter as upload_limiter
from api.migrations import migrations_bp
from api.webhooks import webhooks_bp
from api.dashboard_api import dashboard_bp
from config import config
from utils.backup import init_backup_scheduler
from utils.cleanup_scheduler import init_cleanup_scheduler
from sqlalchemy import text
from logging.handlers import RotatingFileHandler
from datetime import datetime
from api.health import health_bp
import sys



def setup_logging(app):
    """Configure application logging with rotating file handler"""
    
    # Create logs directory
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # File handler (rotating - 10MB per file, keep 10 files)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=app.config.get('LOG_MAX_BYTES', 10 * 1024 * 1024),
        backupCount=app.config.get('LOG_BACKUP_COUNT', 10),
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Security log (separate file for security events)
    security_handler = RotatingFileHandler(
        os.path.join(log_dir, 'security.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding='utf-8'
    )
    security_handler.setLevel(logging.WARNING)
    
    # Format
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    security_handler.setFormatter(formatter)
    
    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(security_handler)
    
    app.logger.setLevel(logging.INFO)
    
    # Log startup
    app.logger.info('=' * 80)
    app.logger.info('QB MIGRATION SERVER STARTING')
    app.logger.info('=' * 80)
    app.logger.info(f'Environment: {os.getenv("FLASK_ENV", "development")}')
    app.logger.info(f'Debug Mode: {app.config.get("DEBUG", False)}')
    app.logger.info(f'Database: {app.config.get("SQLALCHEMY_DATABASE_URI", "unknown")}')
    app.logger.info(f'AWS S3 Bucket: {app.config.get("AWS_S3_BUCKET", "not configured")}')
    app.logger.info(f'AWS Region: {app.config.get("AWS_REGION", "not configured")}')
    app.logger.info(f'Rate Limiting: {app.config.get("RATELIMIT_ENABLED", False)}')
    app.logger.info(f'Auto Cleanup: {app.config.get("AUTO_CLEANUP_ENABLED", False)}')
    app.logger.info('=' * 80)


def setup_sentry(app):
    """Configure Sentry error tracking"""
    sentry_dsn = app.config.get('SENTRY_DSN')
    
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                environment=app.config.get('SENTRY_ENVIRONMENT', 'development'),
                traces_sample_rate=app.config.get('SENTRY_TRACES_SAMPLE_RATE', 0.1),
                send_default_pii=False
            )
            
            app.logger.info('Sentry error tracking initialized')
        except ImportError:
            app.logger.warning('Sentry SDK not installed, error tracking disabled')
        except Exception as e:
            app.logger.error(f'Failed to initialize Sentry: {str(e)}')
    else:
        app.logger.info('Sentry DSN not configured, error tracking disabled')


def verify_aws_configuration(app):
    """Verify AWS is properly configured"""
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_bucket = app.config.get('AWS_S3_BUCKET')
        aws_region = app.config.get('AWS_REGION')
        
        if not s3_bucket:
            app.logger.warning('AWS_S3_BUCKET not configured - AWS features disabled')
            return False
        
        # Test S3 access
        s3_client = boto3.client('s3', region_name=aws_region)
        
        try:
            s3_client.head_bucket(Bucket=s3_bucket)
            app.logger.info(f'AWS S3 bucket verified: {s3_bucket}')
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                app.logger.error(f'S3 bucket does not exist: {s3_bucket}')
            elif error_code == '403':
                app.logger.error(f'No permission to access S3 bucket: {s3_bucket}')
            else:
                app.logger.error(f'S3 bucket check failed: {str(e)}')
            return False
            
    except ImportError:
        app.logger.warning('boto3 not installed - AWS features disabled')
        return False
    except Exception as e:
        app.logger.error(f'AWS configuration check failed: {str(e)}')
        return False


def create_app(config_name='development'):
    """Application factory pattern - creates and configures Flask app"""
    
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])

    config_class = config[config_name]
    app.config.from_object(config_class)

    # Initialize config-specific setup
    if hasattr(config_class, 'init_app'):
        config_class.init_app(app)

    @app.before_request
    def check_content_length():
        """Reject requests that are too large"""
        max_size = app.config.get('MAX_CONTENT_LENGTH', 50 * 1024 * 1024)
        
        if request.content_length and request.content_length > max_size:
            # FIX: Use app.logger instead of logger
            app.logger.warning(f"Request too large ({request.content_length} bytes) from {request.remote_addr}")
            return jsonify({
                'success': False,
                'error': f'Request too large. Maximum size is {max_size // (1024 * 1024)}MB.'
            }), 413
    
    # Setup logging first
    setup_logging(app)
    
    # Setup error tracking
    setup_sentry(app)
    
    # Initialize database
    try:
        init_db(app)
        app.logger.info('Database initialized successfully')
    except Exception as e:
        app.logger.error(f'Failed to initialize database: {str(e)}')
        raise
    
    # Enable CORS
    CORS(app, 
         supports_credentials=True,
         origins=['http://localhost:3000', 'http://localhost:5000', 'https://yourdomain.com'],
         allow_headers=['Content-Type', 'Authorization', 'X-Migration-Id', 'X-Webhook-Signature'],
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
    app.logger.info('CORS enabled')
    
    # Setup rate limiting
    if app.config.get('RATELIMIT_ENABLED', True):
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://'),
            strategy=app.config.get('RATELIMIT_STRATEGY', 'fixed-window'),
            headers_enabled=app.config.get('RATELIMIT_HEADERS_ENABLED', True)
        )
        
        # Apply rate limiter to blueprints
        auth_limiter.init_app(app)
        upload_limiter.init_app(app)
        
        app.logger.info('Rate limiting enabled')
    else:
        app.logger.info('Rate limiting disabled')
    
    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        try:
            return User.query.get(int(user_id))
        except Exception as e:
            app.logger.error(f"Error loading user {user_id}: {str(e)}")
            return None
    
    @login_manager.unauthorized_handler
    def unauthorized():
        """Handle unauthorized access"""
        return jsonify({
            'success': False,
            'error': 'Authentication required'
        }), 401
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(migrations_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(dashboard_bp)
    app.logger.info('Blueprints registered: auth, upload, migrations, webhooks, dashboard')
    
    # Initialize backup scheduler
    if app.config.get('BACKUP_ENABLED', False):
        try:
            init_backup_scheduler(app)
            app.logger.info('Backup scheduler initialized')
        except Exception as e:
            app.logger.error(f'Failed to initialize backup scheduler: {str(e)}')
    
    # Initialize cleanup scheduler
    if app.config.get('AUTO_CLEANUP_ENABLED', True):
        try:
            init_cleanup_scheduler(app)
            app.logger.info('Cleanup scheduler initialized')
        except Exception as e:
            app.logger.error(f'Failed to initialize cleanup scheduler: {str(e)}')
    
    # Verify AWS configuration
    verify_aws_configuration(app)
    
    # Root endpoint
    @app.route('/')
    def index():
        """Root endpoint - basic server info"""
        return jsonify({
            'message': 'QB Migration Server',
            'status': 'running',
            'version': '2.0.0',
            'environment': os.getenv('FLASK_ENV', 'development'),
            'features': {
                'aws_enabled': bool(app.config.get('AWS_S3_BUCKET')),
                'rate_limiting': app.config.get('RATELIMIT_ENABLED', False),
                'auto_cleanup': app.config.get('AUTO_CLEANUP_ENABLED', False)
            },
            'endpoints': {
                'health': '/health',
                'auth': {
                    'register': '/api/auth/register',
                    'login': '/api/auth/login',
                    'logout': '/api/auth/logout',
                    'me': '/api/auth/me',
                    'verify': '/api/auth/verify/<token>'
                },
                'upload': '/api/upload',
                'migrations': {
                    'list': '/api/migrations',
                    'get': '/api/migrations/<id>',
                    'status': '/api/migrations/<id>/status',
                    'start': '/api/migrations/<id>/start',
                    'cancel': '/api/migrations/<id>/cancel',
                    'retry': '/api/migrations/<id>/retry'
                },
                'webhooks': {
                    'started': '/api/webhooks/migration-started',
                    'progress': '/api/webhooks/migration-progress',
                    'completed': '/api/webhooks/migration-completed',
                    'failed': '/api/webhooks/migration-failed'
                }
            }
        }), 200
    
    # Health check endpoint
    @app.route('/health')
    def health():
        """Health check endpoint for monitoring"""
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'checks': {}
        }
        
        # Check database connection
        try:
            db.session.execute(text('SELECT 1'))
            health_status['checks']['database'] = 'healthy'
        except Exception as e:
            app.logger.error(f"Database health check failed: {str(e)}")
            health_status['status'] = 'unhealthy'
            health_status['checks']['database'] = 'unhealthy'
            return jsonify(health_status), 503
        
        # Check AWS S3 access
        try:
            import boto3
            s3_bucket = app.config.get('AWS_S3_BUCKET')
            if s3_bucket:
                s3 = boto3.client('s3', region_name=app.config.get('AWS_REGION'))
                s3.head_bucket(Bucket=s3_bucket)
                health_status['checks']['aws_s3'] = 'healthy'
            else:
                health_status['checks']['aws_s3'] = 'not_configured'
        except Exception as e:
            app.logger.error(f"AWS S3 health check failed: {str(e)}")
            health_status['checks']['aws_s3'] = 'unhealthy'
        
        # Check disk space
        try:
            import shutil
            stat = shutil.disk_usage(os.path.dirname(__file__))
            free_gb = stat.free / (1024 ** 3)
            if free_gb < 1:
                health_status['checks']['disk_space'] = 'warning'
                app.logger.warning(f"Low disk space: {free_gb:.2f}GB free")
            else:
                health_status['checks']['disk_space'] = 'healthy'
        except Exception as e:
            app.logger.error(f"Disk space check failed: {str(e)}")
            health_status['checks']['disk_space'] = 'unknown'
        
        if health_status['status'] == 'unhealthy':
            return jsonify(health_status), 503
        
        return jsonify(health_status), 200
    
    # Security headers middleware
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        if not app.config.get('DEBUG'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            response.headers['Content-Security-Policy'] = "default-src 'self'"
        
        return response
    
    # Request logging middleware
    @app.before_request
    def log_request_info():
        """Log incoming requests"""
        if request.path not in ['/health', '/']:
            app.logger.info(f"{request.method} {request.path} from {request.remote_addr}")
    
    @app.after_request
    def log_response_info(response):
        """Log outgoing responses"""
        if request.path not in ['/health', '/']:
            app.logger.info(f"{request.method} {request.path} -> {response.status_code}")
        return response
    
    # Database session management
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Remove database sessions after each request"""
        try:
            if exception:
                app.logger.error(f"Exception during request: {str(exception)}")
                db.session.rollback()
            db.session.remove()
        except Exception as e:
            app.logger.error(f"Error during session teardown: {str(e)}")
    
    # Error handlers
    @app.errorhandler(400)
    def bad_request(error):
        """Handle 400 Bad Request errors"""
        app.logger.warning(f"Bad request: {str(error)}")
        return jsonify({
            'success': False,
            'error': 'Bad request',
            'message': str(error) if app.config.get('DEBUG') else 'Invalid request'
        }), 400
    
    @app.errorhandler(401)
    def unauthorized_error(error):
        """Handle 401 Unauthorized errors"""
        return jsonify({
            'success': False,
            'error': 'Unauthorized',
            'message': 'Authentication required'
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        """Handle 403 Forbidden errors"""
        return jsonify({
            'success': False,
            'error': 'Forbidden',
            'message': 'You do not have permission to access this resource'
        }), 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 Not Found errors"""
        return jsonify({
            'success': False,
            'error': 'Not found',
            'message': 'Endpoint not found'
        }), 404
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Handle 413 Payload Too Large errors"""
        app.logger.warning(f"Request too large from {request.remote_addr}")
        max_size = app.config.get('MAX_CONTENT_LENGTH', 0) / 1024 / 1024
        return jsonify({
            'success': False,
            'error': 'Payload too large',
            'message': f'Request body exceeds maximum allowed size ({max_size:.0f}MB)'
        }), 413
    
    @app.errorhandler(429)
    def too_many_requests(error):
        """Handle 429 Too Many Requests errors"""
        app.logger.warning(f"Rate limit exceeded from {request.remote_addr} on {request.path}")
        return jsonify({
            'success': False,
            'error': 'Too many requests',
            'message': 'Rate limit exceeded. Please try again later.'
        }), 429
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 Internal Server Error"""
        app.logger.error(f"Internal server error: {str(error)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred' if not app.config.get('DEBUG') else str(error)
        }), 500
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Catch-all handler for unexpected exceptions"""
        app.logger.exception(f"Unexpected error: {str(error)}")
        db.session.rollback()
        
        if app.config.get('DEBUG'):
            error_msg = str(error)
        else:
            error_msg = 'An unexpected error occurred. Our team has been notified.'
        
        return jsonify({
            'success': False,
            'error': 'Unexpected error',
            'message': error_msg
        }), 500
    
    app.logger.info('Flask app created successfully')
    return app


# Create the app instance
app = create_app(os.getenv('FLASK_ENV', 'development'))


if __name__ == '__main__':
    """Run the development server"""
    
    print("=" * 80)
    print("QB MIGRATION SERVER - AWS EPHEMERAL ARCHITECTURE")
    print("=" * 80)
    print("")
    print("Server: http://localhost:5000")
    print("")
    print("✓ Security Features:")
    print("  • Argon2id password hashing")
    print("  • Rate limiting (auth & uploads)")
    print("  • Account lockout (5 failed attempts)")
    print("  • File validation")
    print("  • Audit logging")
    print("")
    print("✓ AWS Features:")
    print("  • Upload to S3 (NOT local disk)")
    print("  • Ephemeral EC2 instances")
    print("  • Auto cleanup (15min intervals)")
    print("  • Zero data persistence")
    print("")
    print("Press CTRL+C to stop")
    print("=" * 80)
    print("")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
    except Exception as e:
        print(f"\n\nFailed to start server: {str(e)}")
        sys.exit(1)