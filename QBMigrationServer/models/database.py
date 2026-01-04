from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

def init_db(app):
    """Initialize database"""
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
    
    return db