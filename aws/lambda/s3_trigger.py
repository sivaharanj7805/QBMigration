"""
Lambda function to trigger migration processing on S3 upload
Deploy this to AWS Lambda with S3 trigger on the migrations bucket
"""

import json
import boto3
import os
import urllib.parse


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
    print(f"Received event: {json.dumps(event)}")
    
    for record in event.get('Records', []):
        if record.get('eventName', '').startswith('ObjectCreated'):
            bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'])
            
            print(f"Processing upload: s3://{bucket}/{key}")
            
            # Extract session ID from key (format: migrations/{session_id}/...)
            parts = key.split('/')
            if len(parts) >= 2 and parts[0] == 'migrations':
                session_id = parts[1]
                
                # Invoke migration processing
                trigger_migration_processing(session_id, bucket, key)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Processing triggered')
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
        print(f"Published to SNS: {sns_topic}")
        return
    
    # Option 2: Call Flask API directly
    api_url = os.getenv('API_BASE_URL')
    if api_url:
        import urllib.request
        
        req_data = json.dumps({
            'session_id': session_id,
            's3_bucket': bucket,
            's3_key': key
        }).encode('utf-8')
        
        req = urllib.request.Request(
            f"{api_url}/api/internal/trigger-processing",
            data=req_data,
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                print(f"API response: {response.read().decode()}")
        except Exception as e:
            print(f"API call failed: {str(e)}")
    
    # Option 3: Update DynamoDB/RDS directly
    # (Not recommended for Lambda - prefer async processing)
    
    print(f"Migration triggered for session: {session_id}")


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
