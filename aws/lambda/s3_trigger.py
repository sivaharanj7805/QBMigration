"""
Lambda function to trigger migration processing on S3 upload
Deploy this to AWS Lambda with S3 trigger on the migrations bucket
"""

import json
import logging
import re
import boto3
import os
import urllib.parse

logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# Validation pattern for session IDs (alphanumeric + hyphens only)
SESSION_ID_PATTERN = re.compile(r'^FB-[\w\-]{1,128}$')

# Maximum allowed S3 key length
MAX_KEY_LENGTH = 1024


def lambda_handler(event, context):
    """
    Handle S3 upload events and trigger migration processing

    Event structure:
    {
        "Records": [{
            "s3": {
                "bucket": {"name": "forensicbridge-migrations"},
                "object": {"key": "migrations/FB-123/data.enc"}
            }
        }]
    }
    """
    logger.info("Received S3 trigger event with %d records", len(event.get('Records', [])))

    expected_bucket = os.getenv('EXPECTED_BUCKET_NAME', '')
    processed = 0

    for record in event.get('Records', []):
        if record.get('eventName', '').startswith('ObjectCreated'):
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])

            # Input validation: verify bucket matches expected
            if expected_bucket and bucket != expected_bucket:
                logger.warning("Unexpected bucket %s, expected %s - skipping", bucket, expected_bucket)
                continue

            # Input validation: reject path traversal attempts
            if '..' in key or key.startswith('/'):
                logger.warning("Suspicious key with path traversal attempt: %s", key[:200])
                continue

            # Input validation: reject overly long keys
            if len(key) > MAX_KEY_LENGTH:
                logger.warning("S3 key exceeds maximum length: %d", len(key))
                continue

            logger.info("Processing upload: s3://%s/%s", bucket, key)

            # Extract session ID from key (format: migrations/{session_id}/...)
            parts = key.split('/')
            if len(parts) >= 2 and parts[0] == 'migrations':
                session_id = parts[1]

                # Validate session ID format
                if not SESSION_ID_PATTERN.match(session_id):
                    logger.warning("Invalid session ID format: %s", session_id[:64])
                    continue

                # Invoke migration processing
                trigger_migration_processing(session_id, bucket, key)
                processed += 1

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Processing triggered', 'processed': processed})
    }


def trigger_migration_processing(session_id: str, bucket: str, key: str):
    """
    Trigger migration processing via SNS or direct API call
    """
    # Option 1: Publish to SNS topic
    sns_topic = os.getenv('MIGRATION_SNS_TOPIC')
    if sns_topic:
        sns = boto3.client('sns')
        sns.publish(
            TopicArn=sns_topic,
            Message=json.dumps({
                'session_id': session_id,
                's3_bucket': bucket,
                's3_key': key,
                'action': 'process_migration'
            }),
            Subject='Migration Upload Complete'
        )
        logger.info("Published to SNS: %s for session %s", sns_topic, session_id)
        return
    
    # Option 2: Call Flask API directly
    # CRIT-09 FIX: Add API key authentication for internal endpoints
    api_url = os.getenv('API_BASE_URL')
    api_key = os.getenv('INTERNAL_API_KEY')  # Must be set in Lambda environment

    if api_url:
        import urllib.request

        if not api_key:
            raise ValueError("INTERNAL_API_KEY not configured - cannot call internal API securely")

        req_data = json.dumps({
            'session_id': session_id,
            's3_bucket': bucket,
            's3_key': key
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{api_url}/api/internal/trigger-processing",
            data=req_data,
            headers={
                'Content-Type': 'application/json',
                'X-Internal-API-Key': api_key,  # CRIT-09 FIX: Add authentication header
                'X-Lambda-Source': 'forensicbridge-s3-trigger'  # Identify the source
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                logger.info("API response status: %d", response.status)
        except Exception as e:
            logger.error("API call failed: %s", str(e), exc_info=True)
            raise
    
    # Option 3: Update DynamoDB/RDS directly
    # (Not recommended for Lambda - prefer async processing)
    
    logger.info("Migration triggered for session: %s", session_id)


# For local testing
if __name__ == "__main__":
    test_event = {
        "Records": [{
            "eventName": "ObjectCreated:Put",
            "s3": {
                "bucket": {"name": "forensicbridge-migrations"},
                "object": {"key": "migrations/FB-20260115-ABC123/data.ndjson.enc"}
            }
        }]
    }
    
    result = lambda_handler(test_event, None)
    print(result)
