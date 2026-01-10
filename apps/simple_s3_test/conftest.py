"""Pytest fixtures for S3 bucket testing."""
import os
import boto3
import pytest


@pytest.fixture(scope="session")
def localstack_endpoint():
    """Get LocalStack endpoint from environment."""
    return os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def s3_client(localstack_endpoint):
    """Create S3 client configured for LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
