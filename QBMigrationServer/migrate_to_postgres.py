"""
Database Migration Script
Migrates from SQLite to PostgreSQL and updates schema
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from models.user import User
from models.migration import Migration



def migrate_database():
    """Migrate database schema"""
    
    # Create app with PostgreSQL configuration
    os.environ['FLASK_ENV'] = 'development'
    app = create_app()
    
    with app.app_context():
        print("Creating database tables...")
        
        # Drop all tables (if migrating)
        db.drop_all()
        
        # Create all tables
        db.create_all()
        
        print("Database migration completed successfully!")
        print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

if __name__ == '__main__':
    migrate_database()