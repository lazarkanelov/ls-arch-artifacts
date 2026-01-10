"""Simple S3 application code."""
import os
import boto3


def get_s3_client():
    """Get S3 client configured for LocalStack."""
    endpoint = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )


def list_buckets():
    """List all S3 buckets."""
    client = get_s3_client()
    response = client.list_buckets()
    return [b["Name"] for b in response.get("Buckets", [])]


def create_test_object(bucket_name, key, content):
    """Create a test object in a bucket."""
    client = get_s3_client()
    client.put_object(Bucket=bucket_name, Key=key, Body=content)


def get_test_object(bucket_name, key):
    """Get a test object from a bucket."""
    client = get_s3_client()
    response = client.get_object(Bucket=bucket_name, Key=key)
    return response["Body"].read().decode("utf-8")
