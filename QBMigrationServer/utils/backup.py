import os
import shutil
from datetime import datetime, timedelta
import logging
from pathlib import Path
from cryptography.fernet import Fernet
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class BackupManager:
    """Manage encrypted database backups with S3 storage"""
    
    def __init__(self, app):
        self.app = app
        self.backup_dir = app.config.get('BACKUP_DIR', 'backups')
        self.retention_days = app.config.get('BACKUP_RETENTION_DAYS', 7)
        self.enabled = app.config.get('BACKUP_ENABLED', True)
        self.backup_to_s3 = app.config.get('BACKUP_TO_S3', True)
        self.encryption_key = app.config.get('BACKUP_ENCRYPTION_KEY')
        
        # Initialize S3 if enabled
        if self.backup_to_s3:
            try:
                self.s3 = boto3.client('s3', region_name=app.config.get('AWS_REGION'))
                self.s3_bucket = app.config.get('AWS_S3_BUCKET')
            except Exception as e:
                logger.error(f"Failed to initialize S3 for backups: {str(e)}")
                self.backup_to_s3 = False
        
        # Create backup directory
        if self.enabled:
            os.makedirs(self.backup_dir, exist_ok=True)
            logger.info(f"Backup manager initialized. Directory: {self.backup_dir}")
    
    def create_backup(self):
        """
        Create encrypted database backup
        
        Returns:
            str: Path to backup file or None if failed
        """
        if not self.enabled:
            logger.info("Backups disabled, skipping")
            return None
        
        try:
            # Get database path
            db_uri = self.app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            # Support both SQLite and PostgreSQL
            if db_uri.startswith('sqlite:///'):
                return self._backup_sqlite(db_uri)
            elif db_uri.startswith('postgresql://'):
                return self._backup_postgresql(db_uri)
            else:
                logger.warning(f"Unsupported database type: {db_uri}")
                return None
                
        except Exception as e:
            logger.exception(f"Backup failed: {str(e)}")
            return None
    
    def _backup_sqlite(self, db_uri):
        """Backup SQLite database"""
        try:
            db_path = db_uri.replace('sqlite:///', '')
            
            if not os.path.exists(db_path):
                logger.error(f"Database file not found: {db_path}")
                return None
            
            # Create backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"qb_migrations_backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Copy database file
            shutil.copy2(db_path, backup_path)
            
            # Verify backup
            if not os.path.exists(backup_path):
                logger.error(f"Backup verification failed: {backup_path}")
                return None
            
            backup_size = os.path.getsize(backup_path)
            logger.info(f"SQLite backup created: {backup_path} ({backup_size} bytes)")
            
            # Encrypt backup
            encrypted_path = self._encrypt_backup(backup_path)
            if encrypted_path:
                # Delete unencrypted backup
                os.remove(backup_path)
                backup_path = encrypted_path
            
            # Upload to S3
            if self.backup_to_s3:
                self._upload_to_s3(backup_path, backup_filename)
            
            # Verify backup integrity
            if self._verify_backup(backup_path):
                logger.info(f"Backup verified successfully: {backup_path}")
            else:
                logger.error(f"Backup verification failed: {backup_path}")
                return None
            
            # Clean up old backups
            self.cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            logger.exception(f"SQLite backup failed: {str(e)}")
            return None
    
    def _backup_postgresql(self, db_uri):
        """Backup PostgreSQL database using pg_dump"""
        try:
            import subprocess
            from urllib.parse import urlparse
            
            # Parse database URI
            parsed = urlparse(db_uri)
            
            # Create backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"qb_migrations_backup_{timestamp}.sql"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Set environment variables for pg_dump
            env = os.environ.copy()
            if parsed.password:
                env['PGPASSWORD'] = parsed.password
            
            # Run pg_dump
            cmd = [
                'pg_dump',
                '-h', parsed.hostname or 'localhost',
                '-p', str(parsed.port or 5432),
                '-U', parsed.username or 'postgres',
                '-d', parsed.path.lstrip('/'),
                '-F', 'c',  # Custom format (compressed)
                '-f', backup_path
            ]
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"pg_dump failed: {result.stderr}")
                return None
            
            # Verify backup
            if not os.path.exists(backup_path):
                logger.error(f"Backup file not created: {backup_path}")
                return None
            
            backup_size = os.path.getsize(backup_path)
            logger.info(f"PostgreSQL backup created: {backup_path} ({backup_size} bytes)")
            
            # Encrypt backup
            encrypted_path = self._encrypt_backup(backup_path)
            if encrypted_path:
                os.remove(backup_path)
                backup_path = encrypted_path
            
            # Upload to S3
            if self.backup_to_s3:
                self._upload_to_s3(backup_path, backup_filename)
            
            # Clean up old backups
            self.cleanup_old_backups()
            
            return backup_path
            
        except subprocess.TimeoutExpired:
            logger.error("pg_dump timed out after 5 minutes")
            return None
        except Exception as e:
            logger.exception(f"PostgreSQL backup failed: {str(e)}")
            return None
    
    def _encrypt_backup(self, backup_path):
        """
        Encrypt backup file
        
        Args:
            backup_path: Path to unencrypted backup
            
        Returns:
            str: Path to encrypted backup or None
        """
        if not self.encryption_key:
            logger.warning("Backup encryption key not configured, storing unencrypted")
            return None
        
        try:
            # Initialize Fernet
            key = self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key
            f = Fernet(key)
            
            # Read backup file
            with open(backup_path, 'rb') as file:
                backup_data = file.read()
            
            # Encrypt
            encrypted_data = f.encrypt(backup_data)
            
            # Write encrypted file
            encrypted_path = f"{backup_path}.encrypted"
            with open(encrypted_path, 'wb') as file:
                file.write(encrypted_data)
            
            logger.info(f"Backup encrypted: {encrypted_path}")
            
            return encrypted_path
            
        except Exception as e:
            logger.exception(f"Backup encryption failed: {str(e)}")
            return None
    
    def _decrypt_backup(self, encrypted_path, output_path):
        """
        Decrypt backup file
        
        Args:
            encrypted_path: Path to encrypted backup
            output_path: Path to write decrypted backup
            
        Returns:
            bool: True if successful
        """
        if not self.encryption_key:
            logger.error("Encryption key not configured")
            return False
        
        try:
            # Initialize Fernet
            key = self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key
            f = Fernet(key)
            
            # Read encrypted file
            with open(encrypted_path, 'rb') as file:
                encrypted_data = file.read()
            
            # Decrypt
            decrypted_data = f.decrypt(encrypted_data)
            
            # Write decrypted file
            with open(output_path, 'wb') as file:
                file.write(decrypted_data)
            
            logger.info(f"Backup decrypted: {output_path}")
            
            return True
            
        except Exception as e:
            logger.exception(f"Backup decryption failed: {str(e)}")
            return False
    
    def _verify_backup(self, backup_path):
        """
        Verify backup integrity
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            bool: True if valid
        """
        try:
            # Check file exists and has content
            if not os.path.exists(backup_path):
                return False
            
            if os.path.getsize(backup_path) == 0:
                logger.error("Backup file is empty")
                return False
            
            # If encrypted, try to decrypt a small portion
            if backup_path.endswith('.encrypted'):
                if not self.encryption_key:
                    logger.warning("Cannot verify encrypted backup without key")
                    return True  # Assume valid
                
                try:
                    key = self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key
                    f = Fernet(key)
                    
                    with open(backup_path, 'rb') as file:
                        sample = file.read(1024)  # Read first 1KB
                    
                    f.decrypt(sample)  # Will raise exception if invalid
                    return True
                except Exception as e:
                    logger.error(f"Backup verification failed: {str(e)}")
                    return False
            
            # For unencrypted SQLite, try to open
            if backup_path.endswith('.db'):
                import sqlite3
                try:
                    conn = sqlite3.connect(backup_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM sqlite_master")
                    cursor.fetchone()
                    conn.close()
                    return True
                except Exception as e:
                    logger.error(f"SQLite backup verification failed: {str(e)}")
                    return False
            
            return True
            
        except Exception as e:
            logger.exception(f"Backup verification failed: {str(e)}")
            return False
    
    def _upload_to_s3(self, backup_path, backup_filename):
        """Upload backup to S3"""
        try:
            if not self.s3_bucket:
                logger.warning("S3 bucket not configured")
                return False
            
            s3_key = f"backups/{backup_filename}"
            
            # Upload with encryption
            self.s3.upload_file(
                backup_path,
                self.s3_bucket,
                s3_key,
                ExtraArgs={
                    'ServerSideEncryption': 'AES256',
                    'StorageClass': 'STANDARD_IA',
                    'Metadata': {
                        'created-at': datetime.utcnow().isoformat(),
                        'type': 'database-backup'
                    }
                }
            )
            
            logger.info(f"Backup uploaded to S3: s3://{self.s3_bucket}/{s3_key}")
            
            return True
            
        except Exception as e:
            logger.exception(f"S3 upload failed: {str(e)}")
            return False
    
    def cleanup_old_backups(self):
        """Delete backups older than retention period"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            # Clean up local backups
            for filename in os.listdir(self.backup_dir):
                if not filename.startswith('qb_migrations_backup_'):
                    continue
                
                filepath = os.path.join(self.backup_dir, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_time < cutoff_date:
                    os.remove(filepath)
                    logger.info(f"Deleted old backup: {filename}")
            
            # Clean up S3 backups
            if self.backup_to_s3 and self.s3_bucket:
                try:
                    response = self.s3.list_objects_v2(
                        Bucket=self.s3_bucket,
                        Prefix='backups/'
                    )
                    
                    if 'Contents' in response:
                        for obj in response['Contents']:
                            last_modified = obj['LastModified'].replace(tzinfo=None)
                            
                            if last_modified < cutoff_date:
                                self.s3.delete_object(
                                    Bucket=self.s3_bucket,
                                    Key=obj['Key']
                                )
                                logger.info(f"Deleted old S3 backup: {obj['Key']}")
                except Exception as e:
                    logger.error(f"S3 cleanup failed: {str(e)}")
                    
        except Exception as e:
            logger.exception(f"Backup cleanup failed: {str(e)}")
    
    def list_backups(self):
        """List all available backups"""
        backups = []
        
        try:
            # List local backups
            for filename in os.listdir(self.backup_dir):
                if not filename.startswith('qb_migrations_backup_'):
                    continue
                
                filepath = os.path.join(self.backup_dir, filename)
                
                backups.append({
                    'filename': filename,
                    'path': filepath,
                    'size': os.path.getsize(filepath),
                    'created': datetime.fromtimestamp(os.path.getmtime(filepath)),
                    'location': 'local',
                    'encrypted': filename.endswith('.encrypted')
                })
            
            # List S3 backups
            if self.backup_to_s3 and self.s3_bucket:
                try:
                    response = self.s3.list_objects_v2(
                        Bucket=self.s3_bucket,
                        Prefix='backups/'
                    )
                    
                    if 'Contents' in response:
                        for obj in response['Contents']:
                            backups.append({
                                'filename': obj['Key'].split('/')[-1],
                                'path': f"s3://{self.s3_bucket}/{obj['Key']}",
                                'size': obj['Size'],
                                'created': obj['LastModified'].replace(tzinfo=None),
                                'location': 's3',
                                'encrypted': True  # S3 server-side encryption
                            })
                except Exception as e:
                    logger.error(f"Failed to list S3 backups: {str(e)}")
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x['created'], reverse=True)
            
        except Exception as e:
            logger.exception(f"Failed to list backups: {str(e)}")
        
        return backups
    
    def restore_backup(self, backup_path):
        """
        Restore database from backup
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            bool: True if successful
        """
        try:
            if not os.path.exists(backup_path) and not backup_path.startswith('s3://'):
                logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Download from S3 if needed
            if backup_path.startswith('s3://'):
                s3_path = backup_path.replace('s3://', '').split('/', 1)
                bucket = s3_path[0]
                key = s3_path[1]
                
                local_path = os.path.join(self.backup_dir, 'restore_temp.db')
                self.s3.download_file(bucket, key, local_path)
                backup_path = local_path
            
            # Decrypt if encrypted
            if backup_path.endswith('.encrypted'):
                decrypted_path = backup_path.replace('.encrypted', '')
                if not self._decrypt_backup(backup_path, decrypted_path):
                    return False
                backup_path = decrypted_path
            
            # Get database path
            db_uri = self.app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            if db_uri.startswith('sqlite:///'):
                db_path = db_uri.replace('sqlite:///', '')
                
                # Create backup of current database
                current_backup = f"{db_path}.before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(db_path, current_backup)
                logger.info(f"Current database backed up to: {current_backup}")
                
                # Restore from backup
                shutil.copy2(backup_path, db_path)
                
                logger.info(f"Database restored from: {backup_path}")
                return True
                
            elif db_uri.startswith('postgresql://'):
                logger.error("PostgreSQL restore not yet implemented")
                return False
            else:
                logger.error(f"Unsupported database type: {db_uri}")
                return False
            
        except Exception as e:
            logger.exception(f"Restore failed: {str(e)}")
            return False


def init_backup_scheduler(app):
    """Initialize backup scheduler"""
    if not app.config.get('BACKUP_ENABLED', True):
        logger.info("Backups disabled by configuration")
        return None
    
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        
        backup_manager = BackupManager(app)
        
        scheduler = BackgroundScheduler()
        
        interval_hours = app.config.get('BACKUP_INTERVAL_HOURS', 6)
        scheduler.add_job(
            func=backup_manager.create_backup,
            trigger=IntervalTrigger(hours=interval_hours),
            id='database_backup',
            name='Database backup job',
            replace_existing=True
        )
        
        scheduler.start()
        
        logger.info(f"Backup scheduler started (interval: {interval_hours} hours)")
        
        # Create initial backup
        backup_manager.create_backup()
        
        return scheduler
        
    except ImportError:
        logger.warning("APScheduler not installed, backups disabled")
        return None
    except Exception as e:
        logger.exception(f"Failed to initialize backup scheduler: {str(e)}")
        return None