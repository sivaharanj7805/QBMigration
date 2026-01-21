"""
Database initialization script for ForensicBridge
Run this script to create/update all database tables including user accounts.

Usage:
    python init_database.py
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def init_database():
    """Initialize database with all tables"""
    print("=" * 60)
    print("ForensicBridge Database Initialization")
    print("=" * 60)
    
    # Import Flask app and database
    from app import create_app
    from models.database import db
    
    app = create_app()
    
    with app.app_context():
        # Import all models so SQLAlchemy knows about them
        from models.user import User
        from models.migration import Migration
        from models.license import License
        
        print("\n1. Creating all database tables...")
        db.create_all()
        print("   [OK] Tables created successfully")
        
        # Add any missing columns
        print("\n2. Checking for missing columns...")
        from sqlalchemy import text, inspect
        
        inspector = inspect(db.engine)
        existing_columns = [col['name'] for col in inspector.get_columns('users')]
        
        # Columns we need for tier system
        tier_columns = {
            'subscription_tier': 'VARCHAR(50) DEFAULT NULL',
            'migrations_purchased': 'INTEGER DEFAULT 0',
            'migrations_used': 'INTEGER DEFAULT 0',
            'stripe_customer_id': 'VARCHAR(255) DEFAULT NULL',
            'stripe_payment_intent': 'VARCHAR(255) DEFAULT NULL',
            'tier_purchased_at': 'TIMESTAMP DEFAULT NULL'
        }
        
        with db.engine.connect() as conn:
            for col_name, col_type in tier_columns.items():
                if col_name not in existing_columns:
                    try:
                        conn.execute(text(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}'))
                        conn.commit()
                        print(f"   [OK] Added column: {col_name}")
                    except Exception as e:
                        if 'already exists' in str(e):
                            print(f"   [--] Column exists: {col_name}")
                        else:
                            print(f"   [ERR] Error adding {col_name}: {e}")
                else:
                    print(f"   [--] Column exists: {col_name}")
        
        # Verify tables exist
        print("\n3. Verifying tables...")
        tables = inspector.get_table_names()
        required_tables = ['users', 'migrations', 'licenses']
        for table in required_tables:
            if table in tables:
                print(f"   [OK] Table exists: {table}")
            else:
                print(f"   [ERR] Missing table: {table}")
        
        # Show user count
        print("\n4. Current database stats:")
        try:
            user_count = User.query.count()
            migration_count = Migration.query.count()
            print(f"   - Users: {user_count}")
            print(f"   - Migrations: {migration_count}")
        except Exception as e:
            print(f"   - Error getting stats: {e}")
        
        print("\n" + "=" * 60)
        print("Database initialization complete!")
        print("=" * 60)
        print("\nYou can now:")
        print("  1. Start the Flask server: python run.py")
        print("  2. Register a new account at http://localhost:3000/register")
        print("  3. Login at http://localhost:3000/login")

if __name__ == '__main__':
    init_database()
