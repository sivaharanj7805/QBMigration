import os
from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.insert(0, 'QBMigrationServer')

# Import Flask app FIRST
from app import create_app

# Create app with testing config
app = create_app('development')

# Now import AWS manager
from utils.aws_manager import AWSMigrationManager
from io import BytesIO
import uuid

print("=" * 60)
print("S3 UPLOAD TEST")
print("=" * 60)

# Run inside Flask app context
with app.app_context():
    region = os.getenv('AWS_REGION')
    bucket = os.getenv('AWS_S3_BUCKET')
    
    print(f"\nRegion: {region}")
    print(f"Bucket: {bucket}")
    
    aws = AWSMigrationManager(region=region)
    
    # Create test data
    test_data = b"TEST_ENCRYPTED_DATA_" + os.urandom(100)
    file_obj = BytesIO(test_data)
    migration_id = str(uuid.uuid4())
    
    print(f"\nUploading {len(test_data)} bytes...")
    
    result = aws.upload_to_s3(
        file_obj=file_obj,
        migration_id=migration_id
    )
    
    if result:
        print(f"\n✓ SUCCESS!")
        print(f"  URI: {result['uri']}")
        print(f"  Bucket: {result['bucket']}")
        print(f"  Key: {result['key']}")
        
        # Verify it exists
        print(f"\nVerifying upload...")
        try:
            response = aws.s3.head_object(
                Bucket=result['bucket'],
                Key=result['key']
            )
            print(f"✓ File verified!")
            print(f"  Size: {response['ContentLength']} bytes")
            print(f"  Encrypted: {response.get('ServerSideEncryption', 'No')}")
        except Exception as e:
            print(f"✗ Verification failed: {e}")
        
        # Cleanup
        print(f"\nCleaning up...")
        aws.delete_s3_file(migration_id)
        print("✓ Cleanup complete!")
        print("\n" + "=" * 60)
        print("TEST PASSED - S3 IS WORKING!")
        print("=" * 60)
    else:
        print("\n✗ UPLOAD FAILED!")
        print("Check the error above")