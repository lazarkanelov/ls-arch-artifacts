import pytest
import boto3
import os
import json
from typing import Generator


@pytest.fixture(scope="session")
def aws_credentials():
    """Set up AWS credentials for LocalStack."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="session")
def localstack_endpoint() -> str:
    """Get LocalStack endpoint URL."""
    return os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def lambda_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create Lambda client for LocalStack."""
    client = boto3.client(
        "lambda",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client


@pytest.fixture(scope="session")
def events_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create EventBridge client for LocalStack."""
    client = boto3.client(
        "events",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client


@pytest.fixture(scope="session")
def iam_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create IAM client for LocalStack."""
    client = boto3.client(
        "iam",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client


@pytest.fixture(scope="session")
def cloudwatch_logs_client(aws_credentials, localstack_endpoint) -> Generator[boto3.client, None, None]:
    """Create CloudWatch Logs client for LocalStack."""
    client = boto3.client(
        "logs",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    yield client


@pytest.fixture(scope="function")
def sample_transaction_events():
    """Sample transaction events for testing."""
    return [
        {
            "version": "0",
            "id": "test-event-1",
            "detail-type": "transaction",
            "source": "custom.myApp",
            "account": "123456789012",
            "time": "2023-01-01T12:00:00Z",
            "region": "us-east-1",
            "detail": {
                "transactionId": "txn-001",
                "amount": 1500.00,
                "currency": "EUR",
                "location": "EUR-PARIS",
                "merchantId": "merchant-123",
                "timestamp": "2023-01-01T12:00:00Z"
            }
        },
        {
            "version": "0",
            "id": "test-event-2",
            "detail-type": "transaction",
            "source": "custom.myApp",
            "account": "123456789012",
            "time": "2023-01-01T12:05:00Z",
            "region": "us-east-1",
            "detail": {
                "transactionId": "txn-002",
                "amount": 250.75,
                "currency": "EUR",
                "location": "EUR-LONDON",
                "merchantId": "merchant-456",
                "timestamp": "2023-01-01T12:05:00Z"
            }
        },
        {
            "version": "0",
            "id": "test-event-3",
            "detail-type": "transaction",
            "source": "custom.myApp",
            "account": "123456789012",
            "time": "2023-01-01T12:10:00Z",
            "region": "us-east-1",
            "detail": {
                "transactionId": "txn-003",
                "amount": 5000.00,
                "currency": "USD",
                "location": "USD-NEWYORK",
                "merchantId": "merchant-789",
                "timestamp": "2023-01-01T12:10:00Z"
            }
        }
    ]